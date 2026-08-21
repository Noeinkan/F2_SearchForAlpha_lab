"""Persistent parquet cache for dashboard OHLCV fetches.

Symbol+interval keys survive process restarts. Soft TTL serves immediately;
stale entries trigger a background incremental Yahoo refresh (SWR). Hard TTL
forces a blocking incremental (or full) fetch. In-memory LRU in
``dashboard_state`` still sits in front of this layer.
"""

from __future__ import annotations

import logging
import os
import re
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable, Literal, Optional

import pandas as pd

from lib.data_processing import ACTION_COLUMNS

logger = logging.getLogger(__name__)

_ENV_CACHE_DIR = "SFA_OHLCV_CACHE_DIR"
_DEFAULT_RELATIVE = Path("state") / "ohlcv_cache"

# Soft = serve without network; hard = beyond this must block (or miss).
_SOFT_INTRADAY_SECONDS = 3600
_HARD_INTRADAY_SECONDS = 6 * 3600
_HARD_DAILY_SECONDS = 7 * 24 * 3600

_SAFE_KEY = re.compile(r"[^A-Za-z0-9._-]+")

Freshness = Literal["fresh", "stale", "expired", "missing"]

# Single-flight locks for background revalidation.
_revalidate_locks: dict[str, threading.Lock] = {}
_revalidate_locks_guard = threading.Lock()

# Tests can replace this to run revalidate synchronously.
_revalidate_executor: Optional[Callable[[Callable[[], None]], None]] = None


def cache_dir() -> Path:
    """Root directory for parquet files (created lazily on write)."""
    override = os.environ.get(_ENV_CACHE_DIR, "").strip()
    if override:
        return Path(override)
    return _DEFAULT_RELATIVE


def cache_path(ticker: str, interval: str) -> Path:
    """Filesystem path for one symbol+interval series."""
    safe = _SAFE_KEY.sub("_", f"{ticker}_{interval}")
    return cache_dir() / f"{safe}.parquet"


def _lock_key(ticker: str, interval: str) -> str:
    return f"{ticker}|{interval}"


def _get_revalidate_lock(ticker: str, interval: str) -> threading.Lock:
    key = _lock_key(ticker, interval)
    with _revalidate_locks_guard:
        lock = _revalidate_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _revalidate_locks[key] = lock
        return lock


def classify_freshness(
    path: Path,
    interval: str,
    *,
    now: Optional[float] = None,
) -> Freshness:
    """Classify cache file age for SWR decisions."""
    if not path.is_file():
        return "missing"
    try:
        mtime = path.stat().st_mtime
    except OSError:
        return "missing"
    clock = time.time() if now is None else now
    age = clock - mtime
    if interval == "1d":
        mtime_day = datetime.fromtimestamp(mtime).date()
        today = datetime.fromtimestamp(clock).date()
        if mtime_day == today:
            return "fresh"
        if age <= _HARD_DAILY_SECONDS:
            return "stale"
        return "expired"
    if age <= _SOFT_INTRADAY_SECONDS:
        return "fresh"
    if age <= _HARD_INTRADAY_SECONDS:
        return "stale"
    return "expired"


def _normalize_frame(df: pd.DataFrame) -> Optional[pd.DataFrame]:
    if df is None or df.empty:
        return None
    out = df.copy()
    if isinstance(out.columns, pd.MultiIndex):
        out.columns = out.columns.get_level_values(0)
    if not isinstance(out.index, pd.DatetimeIndex):
        try:
            out.index = pd.to_datetime(out.index)
        except Exception:
            return None
    if getattr(out.index, "tz", None) is not None:
        out.index = out.index.tz_localize(None)
    # Parquet files written before fetch_data set actions=False still carry
    # corporate-action columns. Drop them on read so old caches self-heal
    # instead of feeding the columns back into the indicator pipeline.
    stale_action_cols = [c for c in ACTION_COLUMNS if c in out.columns]
    if stale_action_cols:
        out = out.drop(columns=stale_action_cols)
    return out


def load_frame(ticker: str, interval: str) -> Optional[pd.DataFrame]:
    """Load parquet ignoring TTL; None on miss / corrupt / empty."""
    path = cache_path(ticker, interval)
    if not path.is_file():
        return None
    try:
        df = pd.read_parquet(path)
    except Exception as exc:
        logger.warning("Disk cache read failed for %s: %s", path.name, exc)
        return None
    normalized = _normalize_frame(df)
    if normalized is None:
        logger.warning("Disk cache empty or bad index for %s", path.name)
        return None
    logger.debug("Disk cache loaded %s (%s rows)", path.name, len(normalized))
    return normalized


def write_frame(ticker: str, interval: str, df: pd.DataFrame) -> None:
    """Atomically persist ``df``; failures are logged and ignored."""
    normalized = _normalize_frame(df)
    if normalized is None:
        return
    path = cache_path(ticker, interval)
    tmp = path.with_suffix(path.suffix + ".tmp")
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        normalized.to_parquet(tmp)
        os.replace(tmp, path)
        logger.debug("Disk cache wrote %s (%s rows)", path.name, len(normalized))
    except Exception as exc:
        logger.warning("Disk cache write failed for %s: %s", path.name, exc)
        try:
            if tmp.is_file():
                tmp.unlink()
        except OSError:
            pass


def merge_ohlcv(existing: pd.DataFrame, new: pd.DataFrame) -> pd.DataFrame:
    """Concat, sort, keep last row per timestamp."""
    left = _normalize_frame(existing)
    right = _normalize_frame(new)
    if left is None and right is None:
        return pd.DataFrame()
    if left is None:
        return right  # type: ignore[return-value]
    if right is None:
        return left
    merged = pd.concat([left, right])
    merged = merged[~merged.index.duplicated(keep="last")]
    return merged.sort_index()


def incremental_start(existing: pd.DataFrame) -> str:
    """Fetch start date with one calendar day of overlap."""
    last = existing.index.max()
    if isinstance(last, pd.Timestamp):
        last_dt = last.to_pydatetime()
    else:
        last_dt = pd.Timestamp(last).to_pydatetime()
    start = last_dt - timedelta(days=1)
    return start.strftime("%Y-%m-%d")


def slice_window(
    df: pd.DataFrame,
    start_date: str,
    end_date: str,
) -> pd.DataFrame:
    """Restrict frame to [start_date, end_date] inclusive when bounds apply."""
    if df is None or df.empty:
        return df
    start = pd.Timestamp(start_date)
    end = pd.Timestamp(end_date) + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
    return df.loc[(df.index >= start) & (df.index <= end)]


def schedule_revalidate(
    ticker: str,
    interval: str,
    end_date: str,
    fetch_fn: Callable[[str, str], pd.DataFrame],
) -> bool:
    """Start a single-flight background incremental refresh.

    ``fetch_fn(start, end)`` should call Yahoo for the given window.
    Returns True if a job was scheduled (or run via test executor).
    """
    lock = _get_revalidate_lock(ticker, interval)
    if not lock.acquire(blocking=False):
        logger.debug("Revalidate already in flight for %s %s", ticker, interval)
        return False

    def _job() -> None:
        try:
            existing = load_frame(ticker, interval)
            if existing is None or existing.empty:
                start = "1900-01-01"
                new = fetch_fn(start, end_date)
                if new is not None and not new.empty:
                    write_frame(ticker, interval, new)
                return
            start = incremental_start(existing)
            new = fetch_fn(start, end_date)
            if new is None or new.empty:
                # Touch mtime so soft TTL resets even if no new bars.
                path = cache_path(ticker, interval)
                if path.is_file():
                    path.touch()
                return
            merged = merge_ohlcv(existing, new)
            write_frame(ticker, interval, merged)
        except Exception as exc:
            logger.warning(
                "Background OHLCV revalidate failed for %s %s: %s",
                ticker,
                interval,
                exc,
            )
        finally:
            lock.release()

    if _revalidate_executor is not None:
        _revalidate_executor(_job)
    else:
        threading.Thread(
            target=_job,
            name=f"ohlcv-revalidate-{ticker}-{interval}",
            daemon=True,
        ).start()
    return True


__all__ = [
    "cache_dir",
    "cache_path",
    "classify_freshness",
    "load_frame",
    "write_frame",
    "merge_ohlcv",
    "incremental_start",
    "slice_window",
    "schedule_revalidate",
]
