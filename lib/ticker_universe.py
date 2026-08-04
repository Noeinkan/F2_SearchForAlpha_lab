"""Symbol universe for the dashboard's search.

Reads the committed ``config/tickers_universe.csv`` produced by
``scripts/build_universe.py``. That file carries sector/industry metadata and
non-equity asset classes (ETF / Index / FX / Future), which is what makes
category search and the asset-class tabs possible.

The app never fetches the universe over the network. If the CSV is missing or
unreadable we fall back to :func:`lib.data_processing.get_all_tickers` and widen
its four-column result into this module's schema, so a fresh checkout without a
built universe still works — just without sector data.
"""

from __future__ import annotations

import logging
import threading
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Column contract shared with scripts/build_universe.py. The first four names
# match the legacy schema so `get_all_tickers()` output slots straight in.
UNIVERSE_COLUMNS = [
    "Symbol",
    "Security",
    "AssetClass",
    "Exchange",
    "Sector",
    "Industry",
    "Index",
    "Country",
    "MarketCap",
]

# Tab order in the symbol-search modal. Anything not listed sorts last.
ASSET_CLASS_ORDER = ["Stock", "ETF", "Index", "FX", "Future"]

UNIVERSE_PATH = Path(__file__).resolve().parent.parent / "config" / "tickers_universe.csv"

_CACHE: Optional[pd.DataFrame] = None
_CACHE_LOCK = threading.Lock()


def _normalise(frame: pd.DataFrame) -> pd.DataFrame:
    """Coerce any source frame into the universe schema."""
    out = frame.reindex(columns=UNIVERSE_COLUMNS).copy()
    for column in UNIVERSE_COLUMNS:
        out[column] = out[column].fillna("").astype(str).str.strip()

    out["Symbol"] = out["Symbol"].str.upper()
    out = out[out["Symbol"] != ""]
    out.loc[out["AssetClass"] == "", "AssetClass"] = "Stock"
    return out.drop_duplicates(subset="Symbol", keep="first").reset_index(drop=True)


def _load_from_disk() -> Optional[pd.DataFrame]:
    if not UNIVERSE_PATH.exists():
        logger.warning("Universe CSV not found at %s", UNIVERSE_PATH)
        return None
    try:
        raw = pd.read_csv(UNIVERSE_PATH, dtype=str)
    except Exception as exc:
        logger.error("Failed to read universe CSV %s: %s", UNIVERSE_PATH, exc)
        return None
    if "Symbol" not in raw.columns:
        logger.error("Universe CSV %s has no Symbol column", UNIVERSE_PATH)
        return None
    return _normalise(raw)


def _load_fallback() -> pd.DataFrame:
    """Widen the legacy four-column ticker list into the universe schema."""
    try:
        from lib.data_processing import get_all_tickers

        legacy = get_all_tickers()
    except Exception as exc:
        logger.error("Fallback ticker fetch failed: %s", exc)
        legacy = pd.DataFrame(
            [{"Symbol": "SPY", "Security": "SPDR S&P 500 ETF", "Index": "Index ETF", "Exchange": "NYSE ARCA"}]
        )

    widened = _normalise(legacy)
    logger.info("Universe loaded from network fallback (%s symbols, no sectors)", len(widened))
    return widened


def load_universe(*, refresh: bool = False) -> pd.DataFrame:
    """Return the full symbol universe, cached for the process lifetime."""
    global _CACHE
    if _CACHE is not None and not refresh:
        return _CACHE

    with _CACHE_LOCK:
        if _CACHE is not None and not refresh:
            return _CACHE
        frame = _load_from_disk()
        if frame is None or frame.empty:
            frame = _load_fallback()
        else:
            logger.info("Universe loaded from %s (%s symbols)", UNIVERSE_PATH, len(frame))
        _CACHE = frame
        return _CACHE


def clear_cache() -> None:
    """Drop the cached universe. Used by tests."""
    global _CACHE
    with _CACHE_LOCK:
        _CACHE = None


def asset_classes() -> list[str]:
    """Distinct asset classes present, in tab order."""
    present = set(load_universe()["AssetClass"].unique())
    ordered = [name for name in ASSET_CLASS_ORDER if name in present]
    ordered.extend(sorted(present - set(ordered)))
    return ordered


def sectors(asset_class: str | None = None) -> list[str]:
    """Distinct non-empty sector values, optionally scoped to one asset class."""
    frame = load_universe()
    if asset_class:
        frame = frame[frame["AssetClass"] == asset_class]
    values = {value for value in frame["Sector"].tolist() if value}
    return sorted(values)


def lookup(symbol: str) -> Optional[dict]:
    """Return the universe row for ``symbol``, or None when unlisted."""
    key = str(symbol or "").strip().upper()
    if not key:
        return None
    frame = load_universe()
    match = frame[frame["Symbol"] == key]
    if match.empty:
        return None
    return match.iloc[0].to_dict()


def describe(symbol: str) -> str:
    """Human-readable company/instrument name, falling back to the symbol."""
    row = lookup(symbol)
    if not row:
        return str(symbol or "").strip().upper()
    return row.get("Security") or str(symbol).strip().upper()
