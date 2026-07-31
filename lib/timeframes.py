"""Bar-interval helpers for OHLCV fetch and metrics annualization.

Supported intervals: ``1d``, ``1h``, ``4h``.

``periods_per_year`` approximates US equity regular-session bars:
252 trading days × 6.5 hours. Hourly → 252 × 6.5 = 1638; 4h → 252 × 6.5 / 4 ≈ 410.

Yahoo Finance caps intraday (1h) history at roughly 730 calendar days; 4h is
built by resampling 1h bars so it inherits the same lookback limit.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

SUPPORTED_INTERVALS = ("1d", "1h", "4h")

# Canonical id → yfinance interval (4h fetches 1h then resamples).
YF_INTERVAL = {"1d": "1d", "1h": "1h", "4h": "1h"}

PERIODS_PER_YEAR = {"1d": 252, "1h": 1638, "4h": 410}

# Yahoo intraday lookback cap (calendar days). None = no clamp.
MAX_LOOKBACK_DAYS: dict[str, Optional[int]] = {"1d": None, "1h": 730, "4h": 730}

_ALIASES = {
    "d": "1d",
    "day": "1d",
    "daily": "1d",
    "1d": "1d",
    "h": "1h",
    "1h": "1h",
    "60m": "1h",
    "60min": "1h",
    "4h": "4h",
    "240m": "4h",
}


class IntervalError(ValueError):
    """Raised when an interval string is not supported."""


def normalize_interval(raw: str | None) -> str:
    """Return canonical interval id (``1d`` / ``1h`` / ``4h``)."""
    if raw is None or str(raw).strip() == "":
        return "1d"
    key = str(raw).strip().lower()
    if key in _ALIASES:
        return _ALIASES[key]
    raise IntervalError(
        f"Unsupported interval {raw!r}; expected one of {SUPPORTED_INTERVALS}"
    )


def periods_per_year(interval: str | None) -> int:
    """Annualization factor for Sharpe / Sortino / Calmar."""
    return PERIODS_PER_YEAR[normalize_interval(interval)]


def yf_interval(interval: str | None) -> str:
    """yfinance ``interval`` argument for a canonical bar size."""
    return YF_INTERVAL[normalize_interval(interval)]


def _parse_date(value: str | datetime | pd.Timestamp) -> datetime:
    if isinstance(value, datetime):
        return value.replace(tzinfo=None) if value.tzinfo else value
    if isinstance(value, pd.Timestamp):
        return value.to_pydatetime().replace(tzinfo=None)
    return datetime.strptime(str(value)[:10], "%Y-%m-%d")


def _fmt_date(value: datetime) -> str:
    return value.strftime("%Y-%m-%d")


def clamp_window(
    start: str,
    end: str,
    interval: str | None,
    *,
    as_of: datetime | None = None,
    relocate: bool = False,
) -> tuple[str, str]:
    """Clamp the window into Yahoo's rolling lookback for ``interval``.

    Yahoo measures the intraday cap (~730 days) from *now*, not from
    ``end``. Daily bars are not clamped.

    Returns ``(start, end)`` as ``YYYY-MM-DD`` strings.

    When the entire window is older than Yahoo's lookback:
    - ``relocate=False`` (CLI default): raise ``IntervalError``
    - ``relocate=True`` (Dash UI): shift the window into the available
      range, preserving duration when possible, ending at ``as_of``/today.

    ``as_of`` is for tests; production uses ``datetime.now()``.
    """
    canon = normalize_interval(interval)
    max_days = MAX_LOOKBACK_DAYS[canon]
    start_dt = _parse_date(start)
    end_dt = _parse_date(end)
    if end_dt < start_dt:
        start_dt, end_dt = end_dt, start_dt

    if max_days is None:
        return _fmt_date(start_dt), _fmt_date(end_dt)

    now = as_of or datetime.now()
    if isinstance(now, pd.Timestamp):
        now = now.to_pydatetime()
    now = now.replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)
    earliest = now - timedelta(days=max_days)
    latest = now

    orig_start, orig_end = start_dt, end_dt

    if end_dt > latest:
        logger.warning(
            "Interval %s end %s is in the future / beyond Yahoo now; clamping → %s",
            canon,
            _fmt_date(end_dt),
            _fmt_date(latest),
        )
        end_dt = latest

    if end_dt < earliest:
        if not relocate:
            raise IntervalError(
                f"Yahoo {canon} history only covers the last {max_days} days "
                f"(from {_fmt_date(earliest)}). Requested window "
                f"{_fmt_date(orig_start)} → {_fmt_date(orig_end)} is outside that range. "
                f"Use a more recent --to date (e.g. within the last {max_days} days)."
            )
        duration = orig_end - orig_start
        end_dt = latest
        start_dt = end_dt - duration
        if start_dt < earliest:
            start_dt = earliest
        logger.warning(
            "Interval %s window %s→%s outside Yahoo lookback; relocated → %s→%s",
            canon,
            _fmt_date(orig_start),
            _fmt_date(orig_end),
            _fmt_date(start_dt),
            _fmt_date(end_dt),
        )
        return _fmt_date(start_dt), _fmt_date(end_dt)

    if start_dt < earliest:
        logger.warning(
            "Interval %s lookback capped at %s days from now; clamping start %s → %s",
            canon,
            max_days,
            _fmt_date(start_dt),
            _fmt_date(earliest),
        )
        start_dt = earliest

    if start_dt >= end_dt:
        raise IntervalError(
            f"After applying Yahoo's {max_days}-day {canon} lookback "
            f"(from {_fmt_date(earliest)}), the window is empty. "
            f"Widen --to or use interval=1d for older history."
        )

    return _fmt_date(start_dt), _fmt_date(end_dt)


_OHLCV_AGG = {
    "Open": "first",
    "High": "max",
    "Low": "min",
    "Close": "last",
    "Volume": "sum",
}


def resample_ohlcv(
    df: pd.DataFrame,
    rule: str = "4h",
    *,
    min_bars: int | None = None,
) -> pd.DataFrame:
    """Resample OHLCV to ``rule``; drop empty / incomplete buckets.

    ``min_bars`` is the minimum number of source rows required to keep a
    bucket. When omitted, ``4h`` defaults to 2 (half of a full 1h→4h set);
    other rules default to 1.
    """
    if df.empty:
        return df.copy()

    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index)

    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)

    cols = [c for c in _OHLCV_AGG if c in out.columns]
    if not cols:
        raise ValueError("DataFrame has no OHLCV columns to resample")

    agg = {c: _OHLCV_AGG[c] for c in cols}
    extras = [c for c in out.columns if c not in agg]
    for c in extras:
        agg[c] = "last"

    grouped = out.resample(rule, label="left", closed="left")
    counts = grouped.size()
    resampled = grouped.agg(agg)

    if min_bars is None:
        if isinstance(rule, str) and rule.endswith("h") and rule[:-1].isdigit():
            hours = int(rule[:-1])
            min_bars = max(1, hours // 2)
        else:
            min_bars = 1

    resampled = resampled.loc[counts >= min_bars]
    if "Open" in resampled.columns and "Close" in resampled.columns:
        resampled = resampled.dropna(subset=["Open", "Close"])
    else:
        resampled = resampled.dropna(how="all")
    return resampled
