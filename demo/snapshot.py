"""Read-only access to the frozen demo fixture.

The fixture is written by ``demo/freeze_demo_data.py`` and committed:

    demo/fixtures/manifest.json              snapshot date, tickers, row counts
    demo/fixtures/ohlcv/<SYMBOL>_1d.csv.gz   daily bars, split/dividend adjusted
    demo/fixtures/ohlcv/<SYMBOL>_1h.csv.gz   hourly bars (the 4h view resamples these)
    demo/fixtures/fundamentals/<SYMBOL>.json the payload ``lib.fundamentals.fetch_fundamentals`` returned

Bars are stored exactly as ``lib.data_processing._yahoo_history`` returned them,
minus the timezone, so everything downstream of that seam runs unchanged on
them. Nothing here touches the network.
"""

from __future__ import annotations

import json
import threading
from datetime import datetime, timedelta
from functools import lru_cache
from pathlib import Path
from typing import Any

import pandas as pd

from lib.fetch_errors import DataFetchError

FIXTURE_DIR = Path(__file__).resolve().parent / "fixtures"
OHLCV_DIR = FIXTURE_DIR / "ohlcv"
FUNDAMENTALS_DIR = FIXTURE_DIR / "fundamentals"
MANIFEST_PATH = FIXTURE_DIR / "manifest.json"

# yfinance interval -> fixture file suffix. 4h is fetched as 1h and resampled
# by lib.data_processing.fetch_data, exactly as it is live.
_FILE_INTERVAL = {"1d": "1d", "1h": "1h"}

_LOCK = threading.Lock()


class NotInSnapshot(DataFetchError):
    """The symbol (or interval) is not part of the frozen demo snapshot."""


@lru_cache(maxsize=1)
def manifest() -> dict[str, Any]:
    with open(MANIFEST_PATH, encoding="utf-8") as handle:
        return json.load(handle)


def snapshot_date() -> str:
    """Last trading day in the fixture, ``YYYY-MM-DD``."""
    return str(manifest()["snapshot"])


def snapshot_label() -> str:
    """``11 Sep 2026`` — the form the banner and header badge print."""
    day = datetime.strptime(snapshot_date(), "%Y-%m-%d")
    return f"{day.day} {day.strftime('%b %Y')}"


def snapshot_now() -> datetime:
    """The demo's notion of *now*: midnight after the last snapshot session.

    ``lib.timeframes`` derives every fetch window from ``datetime.now()``.
    Anchoring it here keeps the intraday lookback lined up with the fixture
    instead of drifting a day further past it every day the demo stays up.
    """
    day = datetime.strptime(snapshot_date(), "%Y-%m-%d")
    return day + timedelta(days=1)


def tickers() -> list[str]:
    return [str(t).upper() for t in manifest()["tickers"]]


def has_ticker(symbol: str | None) -> bool:
    return str(symbol or "").strip().upper() in set(tickers())


def _unavailable_message(symbol: str) -> str:
    # Kept under 40 characters: the terminal header prints str(exc)[:40].
    return f"{symbol} not in demo snapshot"


@lru_cache(maxsize=64)
def _read_bars(symbol: str, file_interval: str) -> pd.DataFrame:
    path = OHLCV_DIR / f"{symbol}_{file_interval}.csv.gz"
    if not path.is_file():
        raise NotInSnapshot(_unavailable_message(symbol))
    frame = pd.read_csv(path, index_col=0, parse_dates=True)
    frame.index = pd.DatetimeIndex(frame.index)
    frame.index.name = None
    return frame


def load_bars(symbol: str, start_date: str, end_date: str, yf_int: str) -> pd.DataFrame:
    """Drop-in for ``lib.data_processing._yahoo_history`` over the fixture.

    Honours yfinance's window semantics: ``start`` inclusive, ``end`` exclusive.
    Returns a fresh copy so callers may mutate it.
    """
    key = str(symbol or "").strip().upper()
    file_interval = _FILE_INTERVAL.get(yf_int)
    if not key or not has_ticker(key) or file_interval is None:
        raise NotInSnapshot(_unavailable_message(key or "?"))
    with _LOCK:
        frame = _read_bars(key, file_interval)
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date)
    window = frame.loc[(frame.index >= start) & (frame.index < end)]
    return window.copy()


def load_fundamentals(symbol: str) -> dict[str, Any]:
    """Drop-in for ``lib.fundamentals.fetch_fundamentals`` over the fixture."""
    key = str(symbol or "").strip().upper()
    if not key:
        raise ValueError("Ticker is required")
    unavailable = manifest().get("fundamentalsUnavailable", {})
    if key in unavailable:
        raise ValueError(f"No fundamentals for {key} in this demo: {unavailable[key]}")
    path = FUNDAMENTALS_DIR / f"{key}.json"
    if not path.is_file():
        raise ValueError(
            f"{key} is not in this demo's frozen snapshot. "
            f"Try one of: {', '.join(tickers())}."
        )
    with open(path, encoding="utf-8") as handle:
        return json.load(handle)


def last_closes(symbol: str) -> tuple[float, float] | None:
    """(last close, previous close) from the daily fixture, or None."""
    key = str(symbol or "").strip().upper()
    if not has_ticker(key):
        return None
    with _LOCK:
        frame = _read_bars(key, "1d")
    closes = frame["Close"].dropna()
    if len(closes) < 2:
        return None
    return float(closes.iloc[-1]), float(closes.iloc[-2])
