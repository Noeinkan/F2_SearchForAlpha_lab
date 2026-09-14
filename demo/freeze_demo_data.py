"""Capture the frozen dataset the public demo runs on.

This is the only part of the demo that touches the network. It calls the same
seams the live dashboard calls -- ``lib.data_processing._yahoo_history`` for
bars and ``lib.fundamentals.fetch_fundamentals`` for the fundamentals payload --
and writes what they return to ``demo/fixtures/``. The demo then reads those
files back through ``demo.snapshot`` and never calls a vendor.

    python -m demo.freeze_demo_data --snapshot 2026-09-11

``--snapshot`` is the last *completed* trading session to keep. Bars after it
are dropped, and the fundamentals payload is taken "as of" that session's
close: its quote fields are rewritten from the frozen daily bars, so the price
on the fundamentals page matches the price on the chart instead of whatever
pre-market print Yahoo was showing at capture time.

Refresh: run this, check the numbers on screen, commit ``demo/fixtures/``,
update ``demo/demo.json``, redeploy.
"""

from __future__ import annotations

import argparse
import gzip
import json
import logging
import math
import shutil
import sys
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Any

import pandas as pd

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from demo import snapshot as snap  # noqa: E402

logger = logging.getLogger("freeze_demo_data")

# Large, liquid, long-listed names plus the two index ETFs. TSLA first: it is
# the dashboard's DEFAULT_TICKER and the landing card's captures.
DEFAULT_TICKERS = [
    "TSLA", "AAPL", "MSFT", "NVDA", "AMZN", "GOOGL",
    "META", "JPM", "KO", "XOM", "SPY", "QQQ",
]
# ETFs file no 10-K, so there is no Big Five table to show for them.
NO_FUNDAMENTALS = {
    "SPY": "an ETF files no 10-K, so there are no statements to analyse",
    "QQQ": "an ETF files no 10-K, so there are no statements to analyse",
}

# Twenty years of daily bars. Older history adds CPU to every backtest a
# visitor runs without adding anything a demo needs to show.
DAILY_FROM = "2006-01-01"
# Yahoo measures its intraday cap from the real today, 730 days back. 727
# leaves a margin; lib.timeframes uses 728 for the same reason.
INTRADAY_DAYS = 727


def _write_bars(frame: pd.DataFrame, path: Path) -> int:
    frame = frame.copy()
    frame.index = pd.to_datetime(frame.index)
    if getattr(frame.index, "tz", None) is not None:
        # Same conversion fetch_data applies: keep the exchange wall clock.
        frame.index = frame.index.tz_localize(None)
    keep = [c for c in ("Open", "High", "Low", "Close", "Volume") if c in frame.columns]
    frame = frame[keep]
    frame = frame[frame["Close"].notna()]
    frame.index.name = "Date"
    path.parent.mkdir(parents=True, exist_ok=True)
    # mtime=0 keeps the gzip header stable, so a re-run with identical bars
    # produces a byte-identical file and no git churn.
    with open(path, "wb") as raw, gzip.GzipFile(fileobj=raw, mode="wb", mtime=0) as handle:
        handle.write(frame.to_csv(float_format="%.6f").encode("utf-8"))
    return len(frame)


def freeze_bars(symbols: list[str], snapshot_day: date, out_dir: Path) -> dict[str, dict[str, Any]]:
    from lib.data_processing import _yahoo_history

    end_exclusive = (snapshot_day + timedelta(days=1)).isoformat()
    intraday_from = (date.today() - timedelta(days=INTRADAY_DAYS)).isoformat()
    counts: dict[str, dict[str, Any]] = {}
    for symbol in symbols:
        daily = _yahoo_history(symbol, DAILY_FROM, end_exclusive, "1d")
        hourly = _yahoo_history(symbol, intraday_from, end_exclusive, "1h")
        if daily.empty:
            raise SystemExit(f"No daily bars for {symbol}; refusing to write a partial fixture")
        n_daily = _write_bars(daily, out_dir / "ohlcv" / f"{symbol}_1d.csv.gz")
        n_hourly = _write_bars(hourly, out_dir / "ohlcv" / f"{symbol}_1h.csv.gz") if not hourly.empty else 0
        first = pd.to_datetime(daily.index.min()).date().isoformat()
        last = pd.to_datetime(daily.index.max()).date().isoformat()
        counts[symbol] = {"daily": n_daily, "hourly": n_hourly, "from": first, "to": last}
        logger.info("%s: %d daily (%s..%s), %d hourly", symbol, n_daily, first, last, n_hourly)
    return counts


class _FrozenDatetime(datetime):
    """``datetime`` whose ``now()`` is the snapshot session's close."""

    frozen: datetime = datetime(2000, 1, 1)

    @classmethod
    def now(cls, tz=None):  # noqa: D401 - matches datetime.now
        value = cls.frozen
        return value if tz is None else value.replace(tzinfo=tz)


def _json_safe(value: Any) -> Any:
    if isinstance(value, float) and (math.isnan(value) or math.isinf(value)):
        return None
    if isinstance(value, dict):
        return {k: _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    return value


def freeze_fundamentals(symbols: list[str], snapshot_day: date, out_dir: Path) -> dict[str, str]:
    """Run the real fundamentals fetch with *now* pinned to the snapshot close."""
    import lib.fundamentals as fundamentals

    _FrozenDatetime.frozen = datetime.combine(snapshot_day, datetime.min.time()).replace(hour=16)
    original_datetime = fundamentals.datetime
    original_info = fundamentals._safe_info
    original_history = fundamentals._safe_history
    current: dict[str, str] = {}

    def pinned_info(ticker_obj: Any) -> dict[str, Any]:
        info = original_info(ticker_obj)
        closes = snap.last_closes(current["symbol"])
        if closes:
            last, prev = closes
            info.update(
                currentPrice=last,
                regularMarketPrice=last,
                previousClose=prev,
                regularMarketPreviousClose=prev,
                regularMarketChange=last - prev,
                marketState="CLOSED",
            )
            # Yahoo's percent field describes its own live quote. Dropped, so
            # _live_price_snapshot derives it from the two pinned closes.
            info.pop("regularMarketChangePercent", None)
        for key in ("preMarketPrice", "preMarketChange", "postMarketPrice", "postMarketChange"):
            info.pop(key, None)
        return info

    def pinned_history(ticker_obj: Any, first_year: int | None) -> pd.DataFrame:
        history = original_history(ticker_obj, first_year)
        if history is None or history.empty:
            return history
        index = pd.to_datetime(history.index)
        naive = index.tz_localize(None) if getattr(index, "tz", None) is not None else index
        return history.loc[naive.normalize() <= pd.Timestamp(snapshot_day)]

    fundamentals.datetime = _FrozenDatetime
    fundamentals._safe_info = pinned_info
    fundamentals._safe_history = pinned_history
    unavailable: dict[str, str] = {}
    try:
        for symbol in symbols:
            if symbol in NO_FUNDAMENTALS:
                unavailable[symbol] = NO_FUNDAMENTALS[symbol]
                continue
            current["symbol"] = symbol
            try:
                payload = fundamentals.fetch_fundamentals(symbol)
            except Exception as exc:  # noqa: BLE001 - recorded, not hidden
                unavailable[symbol] = str(exc)
                logger.warning("%s: fundamentals unavailable: %s", symbol, exc)
                continue
            path = out_dir / "fundamentals" / f"{symbol}.json"
            path.parent.mkdir(parents=True, exist_ok=True)
            with open(path, "w", encoding="utf-8") as handle:
                # No sort_keys: statement rows mix int year keys with str
                # labels. json turns the ints into strings, which is also what
                # the payload becomes on its way through the fundamentals-store.
                json.dump(_json_safe(payload), handle, separators=(",", ":"))
                handle.write("\n")
            logger.info("%s: fundamentals %s, %d fiscal years", symbol, payload.get("as_of"), len(payload.get("years") or []))
    finally:
        fundamentals.datetime = original_datetime
        fundamentals._safe_info = original_info
        fundamentals._safe_history = original_history
    return unavailable


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--snapshot", required=True, help="last completed session to keep, YYYY-MM-DD")
    parser.add_argument("--tickers", nargs="*", default=DEFAULT_TICKERS)
    args = parser.parse_args(argv)
    logging.basicConfig(level=logging.INFO, format="%(message)s")

    snapshot_day = datetime.strptime(args.snapshot, "%Y-%m-%d").date()
    if snapshot_day >= date.today():
        raise SystemExit("--snapshot must be a completed session, i.e. before today")
    symbols = [s.strip().upper() for s in args.tickers if s.strip()]

    staging = snap.FIXTURE_DIR.with_name("fixtures.staging")
    shutil.rmtree(staging, ignore_errors=True)
    staging.mkdir(parents=True)

    counts = freeze_bars(symbols, snapshot_day, staging)
    last_days = {c["to"] for c in counts.values()}
    if last_days != {snapshot_day.isoformat()}:
        raise SystemExit(f"Last bar differs from --snapshot across tickers: {sorted(last_days)}")

    manifest = {
        "snapshot": snapshot_day.isoformat(),
        "capturedAt": date.today().isoformat(),
        "tickers": symbols,
        "dailyFrom": DAILY_FROM,
        "intradayDays": INTRADAY_DAYS,
        "bars": counts,
        "fundamentalsUnavailable": {},
        "sources": {
            "bars": "Yahoo Finance via yfinance, split- and dividend-adjusted (auto_adjust=True)",
            "fundamentals": "SEC EDGAR XBRL company facts, with yfinance for analyst estimates and period-end prices",
        },
    }
    # The fundamentals pin reads closes through demo.snapshot, which reads the
    # manifest -- so the staging manifest has to exist before that step runs.
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    original_dir = snap.FIXTURE_DIR
    saved_paths = (snap.FIXTURE_DIR, snap.OHLCV_DIR, snap.FUNDAMENTALS_DIR, snap.MANIFEST_PATH)
    snap.FIXTURE_DIR, snap.OHLCV_DIR = staging, staging / "ohlcv"
    snap.FUNDAMENTALS_DIR, snap.MANIFEST_PATH = staging / "fundamentals", staging / "manifest.json"
    snap.manifest.cache_clear()
    snap._read_bars.cache_clear()
    try:
        manifest["fundamentalsUnavailable"] = freeze_fundamentals(symbols, snapshot_day, staging)
    finally:
        snap.FIXTURE_DIR, snap.OHLCV_DIR, snap.FUNDAMENTALS_DIR, snap.MANIFEST_PATH = saved_paths
        snap.manifest.cache_clear()
        snap._read_bars.cache_clear()
    (staging / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")

    shutil.rmtree(original_dir, ignore_errors=True)
    staging.rename(original_dir)
    size_kb = sum(p.stat().st_size for p in original_dir.rglob("*") if p.is_file()) / 1024
    logger.info("Wrote %s (%.0f KB)", original_dir, size_kb)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
