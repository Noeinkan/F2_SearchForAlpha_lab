"""Persistent parquet cache for dashboard OHLCV fetches.

Survives process restarts so bootstrap / Load Data can skip Yahoo on a warm
day. In-memory LRU in ``dashboard_state`` still sits in front of this layer.
"""

from __future__ import annotations

import logging
import os
import re
import time
from datetime import datetime
from pathlib import Path
from typing import Optional

import pandas as pd

logger = logging.getLogger(__name__)

# Override in tests via env or monkeypatch of ``cache_dir``.
_ENV_CACHE_DIR = "SFA_OHLCV_CACHE_DIR"
_DEFAULT_RELATIVE = Path("state") / "ohlcv_cache"

# Intraday bars change within the session; daily keys are stable for a trading day.
_INTRADAY_TTL_SECONDS = 3600
_SAFE_KEY = re.compile(r"[^A-Za-z0-9._-]+")


def cache_dir() -> Path:
    """Root directory for parquet files (created lazily on write)."""
    override = os.environ.get(_ENV_CACHE_DIR, "").strip()
    if override:
        return Path(override)
    return _DEFAULT_RELATIVE


def cache_path(ticker: str, interval: str, start_date: str, end_date: str) -> Path:
    """Filesystem path for one fetch window."""
    safe = _SAFE_KEY.sub("_", f"{ticker}_{interval}_{start_date}_{end_date}")
    return cache_dir() / f"{safe}.parquet"


def _is_fresh(path: Path, interval: str, *, now: Optional[float] = None) -> bool:
    """Return True when ``path`` is still within the TTL for ``interval``."""
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return False
    clock = time.time() if now is None else now
    if interval == "1d":
        mtime_day = datetime.fromtimestamp(mtime).date()
        today = datetime.fromtimestamp(clock).date()
        return mtime_day == today
    return (clock - mtime) <= _INTRADAY_TTL_SECONDS


def read_cached(
    ticker: str,
    interval: str,
    start_date: str,
    end_date: str,
    *,
    now: Optional[float] = None,
) -> Optional[pd.DataFrame]:
    """Load a fresh parquet frame, or None on miss / stale / corrupt."""
    path = cache_path(ticker, interval, start_date, end_date)
    if not path.is_file():
        return None
    if not _is_fresh(path, interval, now=now):
        logger.debug("Disk cache stale for %s", path.name)
        return None
    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        logger.warning("Disk cache read failed for %s: %s", path.name, exc)
        return None
    if df.empty:
        return None
    if not isinstance(df.index, pd.DatetimeIndex):
        try:
            df.index = pd.to_datetime(df.index)
        except Exception:
            logger.warning("Disk cache index restore failed for %s", path.name)
            return None
    if getattr(df.index, "tz", None) is not None:
        df.index = df.index.tz_localize(None)
    logger.debug("Disk cache hit for %s (%s rows)", path.name, len(df))
    return df


def write_cached(
    ticker: str,
    interval: str,
    start_date: str,
    end_date: str,
    df: pd.DataFrame,
) -> None:
    """Persist ``df``; failures are logged and ignored (Yahoo already succeeded)."""
    if df is None or df.empty:
        return
    path = cache_path(ticker, interval, start_date, end_date)
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        df.to_parquet(path)
        logger.debug("Disk cache wrote %s (%s rows)", path.name, len(df))
    except Exception as exc:
        logger.warning("Disk cache write failed for %s: %s", path.name, exc)


__all__ = [
    "cache_dir",
    "cache_path",
    "read_cached",
    "write_cached",
]
