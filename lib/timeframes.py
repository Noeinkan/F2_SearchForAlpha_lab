"""Bar-interval helpers for OHLCV fetch and metrics annualization.

Supported intervals: ``1d``, ``1h``, ``4h``.

``periods_per_year`` is 252 sessions times :data:`BARS_PER_SESSION`, and
``BARS_PER_SESSION`` is the count the tape actually emits, not a duration
divided by a bar size. A US regular session is 6.5 hours long but Yahoo returns
**seven** 1h bars for it — 09:30 through 15:30, the last one a 30-minute stub —
so hourly annualises at 252 × 7 = 1764, not the 252 × 6.5 = 1638 this module
used to assume. 4h is built by :func:`resample_ohlcv`, which buckets from the
session open, so those seven bars become two (four bars then three) and 4h
annualises at 252 × 2 = 504. ``lib/tests/test_timeframes.py`` checks the map
against a synthetic tape rather than trusting the arithmetic.

Yahoo Finance caps intraday (1h) history at 730 calendar days, and rejects a
request spanning exactly 730 days with an empty response — so the clamp asks
for 728 to stay strictly inside the cap with a day of slack for the local-vs-
exchange timezone offset. 4h is built by resampling 1h bars so it inherits the
same lookback limit.
"""

from __future__ import annotations

import logging
from datetime import datetime, timedelta
from typing import Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

SUPPORTED_INTERVALS = ("1d", "1h", "4h")

# Canonical id → yfinance interval (4h fetches 1h then resamples).
YF_INTERVAL = {"1d": "1d", "1h": "1h", "4h": "1h"}

# Sessions per year, and the bars each interval emits per session. Keep the two
# factored apart: the session count is a market fact, the bar count is a
# property of the tape and is what `bars_per_session` measures on real data.
SESSIONS_PER_YEAR = 252
BARS_PER_SESSION = {"1d": 1, "1h": 7, "4h": 2}

PERIODS_PER_YEAR = {
    interval: SESSIONS_PER_YEAR * bars for interval, bars in BARS_PER_SESSION.items()
}

# Yahoo intraday lookback cap (calendar days). None = no clamp.
# 728, not 730: a request spanning the full 730 days comes back empty.
MAX_LOOKBACK_DAYS: dict[str, Optional[int]] = {"1d": None, "1h": 728, "4h": 728}

# Floor for "give me everything" daily requests. Predates every listed equity,
# so yfinance simply returns from the listing date.
EARLIEST_HISTORY = "1900-01-01"

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

    Yahoo measures the intraday cap from *now*, not from ``end``. Daily bars
    are not clamped.

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


def full_history_window(
    interval: str | None,
    *,
    as_of: datetime | None = None,
) -> tuple[str, str]:
    """Widest window Yahoo will serve for ``interval``, as ``(start, end)``.

    The dashboard no longer asks the user how much history to fetch — it always
    takes the maximum, and narrowing happens downstream on the already-loaded
    frame. Daily has no cap, so it reaches back to ``EARLIEST_HISTORY`` and
    yfinance returns from the listing date. Intraday reuses ``MAX_LOOKBACK_DAYS``
    so this and ``clamp_window`` can never disagree about where the cap is.

    ``as_of`` is for tests; production uses ``datetime.now()``.
    """
    canon = normalize_interval(interval)
    now = as_of or datetime.now()
    if isinstance(now, pd.Timestamp):
        now = now.to_pydatetime()
    now = now.replace(tzinfo=None, hour=0, minute=0, second=0, microsecond=0)

    max_days = MAX_LOOKBACK_DAYS[canon]
    start = EARLIEST_HISTORY if max_days is None else _fmt_date(now - timedelta(days=max_days))
    return start, _fmt_date(now)


_OHLCV_AGG = {
    "Open": "first",
    "High": "max",
    "Low": "min",
    "Close": "last",
    "Volume": "sum",
    # Corporate actions are per-bar events, so they must be summed across a
    # bucket. Aggregating them with "last" -- the default for unknown columns
    # below -- silently drops a dividend that landed on any bar but the last.
    # fetch_data excludes these columns, but resample_ohlcv is public and is
    # called with vendor frames that may still carry them.
    "Dividends": "sum",
    "Stock Splits": "sum",
    "Capital Gains": "sum",
}


def _session_buckets(index: pd.DatetimeIndex, rule: str) -> np.ndarray:
    """Group codes that restart at every session open.

    Within a session, bars are chunked by elapsed time since that session's
    first bar; a new session always starts a new chunk. That is the whole point
    of anchoring — a bucket can never hold bars from two sessions, so no 4h bar
    straddles the overnight boundary.

    Codes are assigned in order of first appearance, which for a sorted index
    is chronological order.
    """
    from lib.sessions import session_ids

    width = pd.Timedelta(rule).value
    if width <= 0:
        raise ValueError(f"Resample rule {rule!r} has no positive duration")

    stamps = pd.DatetimeIndex(index).as_unit("ns").asi8
    ids = session_ids(index)
    # Broadcast each bar's session-open timestamp back over its session.
    opens = stamps[np.flatnonzero(np.concatenate(([True], np.diff(ids) > 0)))]
    elapsed = stamps - opens[ids]
    codes, _ = pd.factorize(pd.MultiIndex.from_arrays([ids, elapsed // width]))
    return codes


def resample_ohlcv(
    df: pd.DataFrame,
    rule: str = "4h",
    *,
    min_bars: int | None = None,
    session_anchored: bool = True,
) -> pd.DataFrame:
    """Resample OHLCV to ``rule``; drop empty / incomplete buckets.

    ``session_anchored`` (the default) buckets from each session's own open
    rather than from the wall clock, so a bucket never spans an overnight gap
    and every label is a real bar timestamp. A US 1h tape (09:30 … 15:30)
    becomes 09:30 and 13:30, instead of the wall-clock 08:00 and 12:00 — the
    old labels named a time the exchange was shut. Pass
    ``session_anchored=False`` for the pre-3.9 wall-clock behaviour.

    ``min_bars`` is the minimum number of source rows required to keep a
    bucket. When omitted, ``4h`` defaults to 2 (half of a full 1h→4h set);
    other rules default to 1. A session whose trailing bucket holds fewer than
    that loses the tail — unchanged from the wall-clock version, and it does
    not arise on a US 1h tape, whose two buckets hold four bars and three.
    """
    if df.empty:
        return df.copy()

    out = df.copy()
    if not isinstance(out.index, pd.DatetimeIndex):
        out.index = pd.to_datetime(out.index)

    if out.index.tz is not None:
        out.index = out.index.tz_localize(None)

    cols = [c for c in _OHLCV_AGG if c in out.columns]
    # Guard on price/volume specifically: _OHLCV_AGG also names corporate-action
    # columns, and a frame carrying only those is not resamplable.
    if not any(c in out.columns for c in ("Open", "High", "Low", "Close", "Volume")):
        raise ValueError("DataFrame has no OHLCV columns to resample")

    agg = {c: _OHLCV_AGG[c] for c in cols}
    extras = [c for c in out.columns if c not in agg]
    for c in extras:
        agg[c] = "last"

    if min_bars is None:
        if isinstance(rule, str) and rule.endswith("h") and rule[:-1].isdigit():
            hours = int(rule[:-1])
            min_bars = max(1, hours // 2)
        else:
            min_bars = 1

    if session_anchored:
        codes = _session_buckets(out.index, rule)
        grouped = out.groupby(codes, sort=True)
        resampled = grouped.agg(agg)
        counts = grouped.size().to_numpy()
        # Label each bucket with its own first bar, not a synthetic boundary.
        _, first_pos = np.unique(codes, return_index=True)
        resampled.index = out.index[first_pos]
        keep = counts >= min_bars
    else:
        grouped = out.resample(rule, label="left", closed="left")
        counts = grouped.size()
        resampled = grouped.agg(agg)
        keep = (counts >= min_bars).to_numpy()

    resampled = resampled.loc[keep]
    if "Open" in resampled.columns and "Close" in resampled.columns:
        resampled = resampled.dropna(subset=["Open", "Close"])
    else:
        resampled = resampled.dropna(how="all")
    return resampled
