"""Scheduled Flow Scanner refresh, run inside the dashboard process (ROADMAP 6.8).

``run_dashboard`` starts a daemon thread that wakes once a minute and rescans
every ticker whose stored report has gone stale:

* **Which tickers** -- the flow scanner's ``watchlist.txt`` plus every ticker
  that already has a stored report (anything someone has scanned from the
  page), capped at ``FLOW_REFRESH_MAX_TICKERS``, watchlist first.
* **When** -- a report is due once it is ``FLOW_REFRESH_MINUTES`` old while the
  US market is open, or once it predates the latest close. So chains refresh
  through the session, take one last snapshot after the bell, and then sit
  still overnight and at weekends.

Market hours are the 9:30-16:00 ET weekday window with no holiday calendar: on
a holiday the refresh re-reads an unchanged chain each interval, which spends
requests but shows nothing wrong.

A throttled scan ends the round, and every attempt -- failed or not -- counts
as "seen" for the interval, so a rate limit is not hammered once a minute.
The public demo builds its app with ``create_app`` and never reaches
``start_flow_refresh``.
"""

from __future__ import annotations

import logging
import threading
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from pathlib import Path
from typing import Callable

from lib.dash import flow_store
from lib.dash.dash_config import FLOW_REFRESH_MAX_TICKERS, FLOW_REFRESH_MINUTES
from scripts.flow_scanner import ET, is_market_hours, load_watchlist

logger = logging.getLogger(__name__)

WATCHLIST_PATH = flow_store.REPO_ROOT / "watchlist.txt"
POLL_SECONDS = 60.0

# Ticker -> when the refresh last tried it, successful or not.
_last_attempt: dict[str, datetime] = {}
_started: threading.Event | None = None
_start_guard = threading.Lock()


def latest_close(now: datetime) -> datetime:
    """The most recent weekday 16:00 ET at or before ``now``."""
    now_et = now.astimezone(ET)
    close = now_et.replace(hour=16, minute=0, second=0, microsecond=0)
    if close > now_et:
        close -= timedelta(days=1)
    while close.weekday() >= 5:
        close -= timedelta(days=1)
    return close


def is_due(last_seen: datetime | None, now: datetime, interval: timedelta) -> bool:
    """Whether a report last refreshed (or attempted) at ``last_seen`` needs a rescan."""
    if last_seen is None:
        return True
    if last_seen < latest_close(now):
        return True
    return is_market_hours(now.astimezone(ET)) and now - last_seen >= interval


def refresh_tickers(watchlist_path: Path | None = None, limit: int = FLOW_REFRESH_MAX_TICKERS) -> list[str]:
    """Watchlist tickers first, then stored ones oldest-first, deduplicated and capped."""
    path = watchlist_path or WATCHLIST_PATH
    watchlist: list[str] = []
    if path.is_file():
        try:
            watchlist = load_watchlist(str(path))
        except OSError as exc:
            logger.warning("Flow refresh could not read %s: %s", path, exc)
    ordered = dict.fromkeys(flow_store.normalize_ticker(t) for t in [*watchlist, *flow_store.stored_tickers()])
    return [t for t in ordered if t][: max(0, limit)]


def _last_seen(ticker: str) -> datetime | None:
    stamps = [s for s in (flow_store.stored_at(ticker), _last_attempt.get(ticker)) if s is not None]
    return max(stamps) if stamps else None


@dataclass
class RefreshRound:
    refreshed: list[str] = field(default_factory=list)
    kept_previous: list[str] = field(default_factory=list)
    busy: list[str] = field(default_factory=list)
    stopped_on_rate_limit: bool = False


def refresh_once(
    now: datetime | None = None,
    *,
    interval_minutes: int = FLOW_REFRESH_MINUTES,
    tickers: list[str] | None = None,
    scan: Callable[..., flow_store.ScanOutcome | None] | None = None,
    stop: threading.Event | None = None,
) -> RefreshRound:
    """Rescan every due ticker once. Safe to call from a test with a fake ``scan``."""
    now = now or datetime.now(ET)
    interval = timedelta(minutes=max(1, interval_minutes))
    scan = scan or flow_store.scan_into_store
    result = RefreshRound()

    for ticker in tickers if tickers is not None else refresh_tickers():
        if stop is not None and stop.is_set():
            break
        if not is_due(_last_seen(ticker), now, interval):
            continue
        _last_attempt[ticker] = now
        outcome = scan(ticker, blocking=False)
        if outcome is None:
            result.busy.append(ticker)
            continue
        if outcome.promoted:
            result.refreshed.append(ticker)
        else:
            result.kept_previous.append(ticker)
        if outcome.error_kind == "rate_limited":
            result.stopped_on_rate_limit = True
            break
    return result


def _run(stop: threading.Event, interval_minutes: int) -> None:
    logger.info("Flow refresh started: every %d min in market hours", interval_minutes)
    while not stop.is_set():
        try:
            round_ = refresh_once(interval_minutes=interval_minutes, stop=stop)
            if round_.refreshed or round_.kept_previous:
                logger.info(
                    "Flow refresh: refreshed %s, kept previous %s%s",
                    round_.refreshed or "-",
                    round_.kept_previous or "-",
                    " (stopped: rate limited)" if round_.stopped_on_rate_limit else "",
                )
        except Exception:
            # A bad round must not kill the thread for the rest of the process.
            logger.exception("Flow refresh round failed")
        stop.wait(POLL_SECONDS)


def start_flow_refresh(interval_minutes: int = FLOW_REFRESH_MINUTES) -> threading.Event | None:
    """Start the refresh thread once per process. Returns its stop event, or ``None`` when off."""
    global _started
    if interval_minutes <= 0:
        logger.info("Flow refresh disabled (SFA_FLOW_REFRESH_MINUTES=0)")
        return None
    with _start_guard:
        if _started is not None:
            return _started
        _started = threading.Event()
        threading.Thread(
            target=_run,
            args=(_started, interval_minutes),
            name="flow-refresh",
            daemon=True,
        ).start()
        return _started
