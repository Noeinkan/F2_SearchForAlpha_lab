"""One dashboard state per visitor.

The dashboard was written as a single-user desktop tool: ``lib.dash.state``
holds one process-wide ``dashboard_state`` with the loaded frame, the ticker
and the optimiser's progress. Served to the public as-is, two visitors would
share it -- one loads AAPL and the other's backtest silently runs on AAPL.

This module replaces that singleton with a proxy that forwards every
attribute to the state belonging to the visitor behind the current request.
Visitors are told apart by a random session cookie (or, if cookies are
blocked, by a hash of IP and User-Agent). Nothing is written to disk and
nothing survives the process: an idle state is dropped after
``session_idle_minutes``, and the oldest one goes when ``max_sessions`` is
reached.

Work that leaves the request thread (the optimiser's thread pool, the grid and
Bayesian worker threads) carries the session with it through ``contextvars``;
``demo.patches`` installs the context-copying executor and thread.
"""

from __future__ import annotations

import contextvars
import hashlib
import logging
import re
import secrets
import threading
import time
from collections import OrderedDict
from contextlib import contextmanager
from typing import Any, Iterator

from lib.dash.state import DashboardState

logger = logging.getLogger(__name__)

COOKIE_NAME = "sfa_demo_session"
_SID_RE = re.compile(r"^[A-Za-z0-9_-]{20,64}$")

# The session id of the request being served (or of the job it started).
current_sid: contextvars.ContextVar[str | None] = contextvars.ContextVar("sfa_demo_sid", default=None)
# Explicit state override: used while the app bootstraps its template session.
_pinned_state: contextvars.ContextVar[DashboardState | None] = contextvars.ContextVar("sfa_demo_state", default=None)


def new_session_id() -> str:
    return secrets.token_urlsafe(24)


def valid_session_id(value: str | None) -> bool:
    return bool(value) and bool(_SID_RE.match(value or ""))


def fallback_session_id(ip: str, user_agent: str) -> str:
    """Stable id for a client that sends no cookie back."""
    digest = hashlib.sha256(f"{ip}|{user_agent}".encode("utf-8")).hexdigest()
    return f"anon-{digest[:32]}"


class SessionStore:
    """Holds each visitor's ``DashboardState``, created lazily from a template."""

    def __init__(self, *, max_sessions: int, idle_seconds: float, clock=time.monotonic) -> None:
        self.template = DashboardState()
        self._max = max(1, int(max_sessions))
        self._idle = float(idle_seconds)
        self._clock = clock
        self._lock = threading.Lock()
        self._states: OrderedDict[str, tuple[DashboardState, float]] = OrderedDict()

    def _clone_template(self) -> DashboardState:
        state = DashboardState()
        t = self.template
        # The frame is shared, not copied: nothing in lib/dash mutates the
        # loaded frame in place (enrichment and backtests work on copies), and
        # sharing the object lets every fresh visitor hit the same enriched
        # cache entry instead of recomputing indicators for the default ticker.
        state.df = t.df
        state.interval = t.interval
        state.ticker = t.ticker
        state.all_tickers_df = t.all_tickers_df
        state.ticker_dropdown_options = t.ticker_dropdown_options
        state.set_theme(t.theme_name)
        return state

    def get(self, sid: str) -> DashboardState:
        now = self._clock()
        with self._lock:
            self._purge_locked(now)
            entry = self._states.get(sid)
            if entry is not None:
                state = entry[0]
                self._states[sid] = (state, now)
                self._states.move_to_end(sid)
                return state
            while len(self._states) >= self._max:
                evicted, _ = self._states.popitem(last=False)
                logger.info("demo session evicted (cap %d): %s…", self._max, evicted[:6])
            state = self._clone_template()
            self._states[sid] = (state, now)
            return state

    def peek(self, sid: str) -> DashboardState | None:
        """The state for ``sid`` if it exists, without refreshing or creating it."""
        with self._lock:
            entry = self._states.get(sid)
            return entry[0] if entry else None

    def _purge_locked(self, now: float) -> None:
        stale = [sid for sid, (_, seen) in self._states.items() if now - seen > self._idle]
        for sid in stale:
            del self._states[sid]

    def purge(self) -> int:
        with self._lock:
            before = len(self._states)
            self._purge_locked(self._clock())
            return before - len(self._states)

    def __len__(self) -> int:
        with self._lock:
            return len(self._states)

    @contextmanager
    def pinned(self, state: DashboardState) -> Iterator[DashboardState]:
        token = _pinned_state.set(state)
        try:
            yield state
        finally:
            _pinned_state.reset(token)


class SessionScopedState:
    """Stands in for ``lib.dash.state.dashboard_state``.

    Attribute reads and writes go to the current visitor's ``DashboardState``,
    so property setters (``df``, ``ticker``…) and methods keep working.
    """

    def __init__(self, store: SessionStore) -> None:
        object.__setattr__(self, "_store", store)
        object.__setattr__(self, "_warned", False)

    def _resolve(self) -> DashboardState:
        pinned = _pinned_state.get()
        if pinned is not None:
            return pinned
        sid = current_sid.get()
        if sid:
            return self._store.get(sid)
        # No request and no carried session: a thread nobody told us about.
        # Hand it a throwaway state rather than anyone's real one.
        if not object.__getattribute__(self, "_warned"):
            logger.warning("dashboard_state read outside any demo session; using a throwaway state")
            object.__setattr__(self, "_warned", True)
        return DashboardState()

    def __getattr__(self, name: str) -> Any:
        return getattr(self._resolve(), name)

    def __setattr__(self, name: str, value: Any) -> None:
        setattr(self._resolve(), name, value)

    def __repr__(self) -> str:  # pragma: no cover - debugging aid
        return f"<SessionScopedState sid={current_sid.get()!r}>"
