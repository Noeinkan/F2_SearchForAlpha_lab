"""Disk cache and refresh policy for the fundamentals page's remote inputs.

ROADMAP 7.9. Before this, every visit to ``/fundamentals/<ticker>`` -- a route
change, a return from the chart, the Refresh button -- downloaded the whole SEC
company-facts file (3.8 MB for Apple) and called Yahoo up to seven times.
Filings change a few times a quarter, so the page now reuses what it fetched
recently and goes back to the network only when an entry has outlived its tier.

One tier per kind of input:

    tier      inputs                                        fresh for  override
    filings   SEC company facts, Yahoo statements,          24 h       SFA_FUNDAMENTALS_FILINGS_TTL_HOURS
              period-end price history
    quote     Yahoo quote and analyst estimates (``info``)  15 min     SFA_FUNDAMENTALS_QUOTE_TTL_MINUTES
    symbols   SEC ticker -> CIK map                         7 days     --

Three rules hold for every tier:

- ``force=True`` (the page's Refresh button) skips the freshness check and goes
  to the network.
- A failed or empty refetch never replaces a good entry. The old entry is served
  instead, however old, and the read says ``stale`` so the page can tell the
  reader.
- Empty results are not written, so a ticker with no data asks again next time
  instead of staying empty for a day. An override of ``0`` means "always
  refetch" and keeps the stale fallback.

Entries are JSON under ``state/fundamentals/<kind>/<ident>.json``.
"""

from __future__ import annotations

import json
import logging
import os
import time
import uuid
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Generic, Literal, TypeVar
from urllib.parse import quote

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[1]
# Module attribute, not baked into paths at import: tests point it elsewhere.
CACHE_DIR = REPO_ROOT / "state" / "fundamentals"

T = TypeVar("T")

ReadState = Literal["network", "cache", "stale", "miss"]


@dataclass(frozen=True)
class Tier:
    name: str
    default_seconds: float
    env: str | None = None
    env_unit_seconds: float = 1.0

    @property
    def ttl_seconds(self) -> float:
        raw = os.environ.get(self.env, "").strip() if self.env else ""
        if raw:
            try:
                return max(0.0, float(raw)) * self.env_unit_seconds
            except ValueError:
                logger.warning("Ignoring %s=%r: not a number", self.env, raw)
        return float(self.default_seconds)


FILINGS = Tier("filings", 24 * 3600, "SFA_FUNDAMENTALS_FILINGS_TTL_HOURS", 3600)
QUOTE = Tier("quote", 15 * 60, "SFA_FUNDAMENTALS_QUOTE_TTL_MINUTES", 60)
SYMBOLS = Tier("symbols", 7 * 24 * 3600)


@dataclass(frozen=True)
class CacheRead(Generic[T]):
    """One input, and where it came from.

    ``state`` is ``network`` (fetched now), ``cache`` (a fresh entry),
    ``stale`` (the refetch failed, so an expired entry was served) or ``miss``
    (the source had nothing and no entry existed). ``fetched_at`` is when the
    value left the network, in epoch seconds; ``None`` on a miss.
    """

    value: T
    state: ReadState
    fetched_at: float | None
    tier: Tier


def has_data(value: Any) -> bool:
    """False for ``None`` and for empty frames, series, dicts, lists and tuples of those."""
    if value is None:
        return False
    if isinstance(value, (pd.DataFrame, pd.Series)):
        return not value.empty
    if isinstance(value, tuple):
        return any(has_data(item) for item in value)
    if isinstance(value, (dict, list)):
        return len(value) > 0
    return True


def entry_path(kind: str, ident: str) -> Path:
    # Percent-encoding keeps ^GSPC or BRK-B reversible and path-safe.
    return CACHE_DIR / kind / f"{quote(str(ident), safe='')}.json"


def read_through(
    kind: str,
    ident: str,
    tier: Tier,
    loader: Callable[[], T],
    *,
    force: bool = False,
    enabled: bool = True,
    encode: Callable[[T], Any] = lambda value: value,
    decode: Callable[[Any], T | None] = lambda raw: raw,
    usable: Callable[[T], bool] = has_data,
    now: float | None = None,
) -> CacheRead[T]:
    """Return a fresh entry, else call ``loader``, else fall back to the old entry.

    ``decode`` may return ``None`` to reject an entry written in an older shape;
    it then counts as missing.
    """
    clock = time.time() if now is None else now
    if not enabled:
        value = loader()
        ok = usable(value)
        return CacheRead(value, "network" if ok else "miss", clock if ok else None, tier)

    path = entry_path(kind, ident)
    entry = _load_entry(path, decode)
    if entry is not None and not force and clock - entry[1] < tier.ttl_seconds:
        return CacheRead(entry[0], "cache", entry[1], tier)

    try:
        value = loader()
    except Exception as exc:
        if entry is None:
            raise
        logger.warning("%s refetch for %s failed, serving cached copy: %s", kind, ident, exc)
        return CacheRead(entry[0], "stale", entry[1], tier)

    if usable(value):
        _write_entry(path, encode(value), clock)
        return CacheRead(value, "network", clock, tier)
    if entry is not None:
        logger.info("%s refetch for %s came back empty, serving cached copy", kind, ident)
        return CacheRead(entry[0], "stale", entry[1], tier)
    return CacheRead(value, "miss", None, tier)


def _load_entry(path: Path, decode: Callable[[Any], Any]) -> tuple[Any, float] | None:
    try:
        with open(path, encoding="utf-8") as handle:
            payload = json.load(handle)
        fetched_at = float(payload["fetched_at"])
        value = decode(payload["value"])
    except FileNotFoundError:
        return None
    except (OSError, ValueError, KeyError, TypeError) as exc:
        logger.warning("Ignoring unreadable fundamentals cache entry %s: %s", path, exc)
        return None
    if value is None:
        return None
    return value, fetched_at


def _write_entry(path: Path, raw: Any, fetched_at: float) -> None:
    tmp = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        with open(tmp, "w", encoding="utf-8") as handle:
            json.dump({"fetched_at": fetched_at, "value": raw}, handle, separators=(",", ":"), allow_nan=False)
        # Atomic on the same volume, so a reader never sees half a file.
        os.replace(tmp, path)
    except (OSError, TypeError, ValueError) as exc:
        logger.warning("Could not write fundamentals cache entry %s: %s", path, exc)
        tmp.unlink(missing_ok=True)


# ---------------------------------------------------------------------------
# DataFrame codec
# ---------------------------------------------------------------------------
# Hand-rolled rather than DataFrame.to_json: read_json guesses dtypes and
# date-like labels, and a cached frame must come back exactly as fetched --
# timestamps with their zone, integer labels as integers.

def encode_frame(frame: pd.DataFrame) -> dict[str, Any]:
    return {
        "index": _encode_axis(frame.index),
        "columns": _encode_axis(frame.columns),
        "values": [[_encode_number(cell) for cell in row] for row in frame.itertuples(index=False, name=None)],
    }


def decode_frame(raw: dict[str, Any]) -> pd.DataFrame:
    index = _decode_axis(raw["index"])
    columns = _decode_axis(raw["columns"])
    values = [[np.nan if cell is None else cell for cell in row] for row in raw["values"]]
    return pd.DataFrame(values, index=index, columns=columns, dtype="float64")


def _encode_axis(axis: pd.Index) -> dict[str, Any]:
    if isinstance(axis, pd.DatetimeIndex) or (
        len(axis) and all(isinstance(label, (pd.Timestamp, datetime)) for label in axis)
    ):
        stamps = pd.DatetimeIndex(axis)
        tz = str(stamps.tz) if stamps.tz is not None else None
        if tz is not None:
            stamps = stamps.tz_convert("UTC").tz_localize(None)
        return {"kind": "datetime", "tz": tz, "values": [stamp.isoformat() for stamp in stamps]}
    return {
        "kind": "labels",
        "values": [int(label) if isinstance(label, (int, np.integer)) else str(label) for label in axis],
    }


def _decode_axis(raw: dict[str, Any]) -> pd.Index:
    if raw["kind"] == "datetime":
        stamps = pd.DatetimeIndex(pd.to_datetime(raw["values"]))
        if raw.get("tz"):
            stamps = stamps.tz_localize("UTC").tz_convert(raw["tz"])
        return stamps
    return pd.Index(raw["values"])


def _encode_number(cell: Any) -> float | None:
    try:
        number = float(cell)
    except (TypeError, ValueError):
        return None
    return number if np.isfinite(number) else None


# ---------------------------------------------------------------------------
# Reporting
# ---------------------------------------------------------------------------

def format_age(seconds: float) -> str:
    seconds = max(0.0, seconds)
    if seconds < 60:
        return "<1m"
    if seconds < 3600:
        return f"{int(seconds // 60)}m"
    if seconds < 48 * 3600:
        return f"{int(seconds // 3600)}h"
    return f"{int(seconds // 86400)}d"


def describe_reads(reads: dict[str, CacheRead[Any]], *, now: float | None = None) -> dict[str, Any]:
    """JSON-safe summary of where each input came from, for the payload and the status line."""
    clock = time.time() if now is None else now
    sources = []
    for label, read in reads.items():
        if read.state == "miss" or read.fetched_at is None:
            continue
        sources.append({
            "source": label,
            "state": read.state,
            "tier": read.tier.name,
            "fetched_at": datetime.fromtimestamp(read.fetched_at).strftime("%Y-%m-%d %H:%M"),
            "age": format_age(clock - read.fetched_at),
            "fresh_for": format_age(read.tier.ttl_seconds),
        })
    return {
        "sources": sources,
        "stale": [item["source"] for item in sources if item["state"] == "stale"],
        "cached": [item["source"] for item in sources if item["state"] == "cache"],
    }
