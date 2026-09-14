"""Rate limits and the optimiser-run gate.

Two mechanisms, both in memory (the demo keeps no state worth surviving a
restart, and a restart also clears whatever a limit was protecting):

``SlidingWindowLimiter`` counts events per key (the client IP) over a window
and says how long until the next one is allowed.

``JobGate`` tracks optimiser runs in flight across every visitor. A run is a
``Ticket`` with a probe that says whether it is still running and a cancel
that stops it; the gate refuses a new run while ``max_concurrent`` are going,
and ``sweep()`` stops any run older than the timeout.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque
from dataclasses import dataclass, field
from typing import Callable

logger = logging.getLogger(__name__)


class SlidingWindowLimiter:
    def __init__(self, limit: int, window_seconds: float, clock: Callable[[], float] = time.monotonic) -> None:
        self.limit = max(1, int(limit))
        self.window = float(window_seconds)
        self._clock = clock
        self._events: dict[str, deque[float]] = {}
        self._lock = threading.Lock()

    def hit(self, key: str) -> float:
        """Record one event. Returns 0 if allowed, else seconds until it would be."""
        now = self._clock()
        with self._lock:
            events = self._events.setdefault(key, deque())
            while events and now - events[0] >= self.window:
                events.popleft()
            if len(events) >= self.limit:
                return max(0.0, self.window - (now - events[0]))
            events.append(now)
            if len(self._events) > 10_000:  # a crawler with rotating IPs: drop the idle keys
                for idle in [k for k, v in self._events.items() if not v]:
                    del self._events[idle]
            return 0.0


@dataclass
class Ticket:
    kind: str
    owner: str
    started: float
    probe: Callable[[], bool]
    cancel: Callable[[str], None]  # receives "timeout" or "abandoned"
    last_seen: float = field(default=0.0)


class JobGate:
    def __init__(
        self,
        max_concurrent: int,
        timeout_seconds: float,
        *,
        stale_seconds: float = 30.0,
        clock: Callable[[], float] = time.monotonic,
    ) -> None:
        self.max_concurrent = max(1, int(max_concurrent))
        self.timeout = float(timeout_seconds)
        self.stale = float(stale_seconds)
        self._clock = clock
        self._tickets: dict[tuple[str, str], Ticket] = {}
        self._lock = threading.Lock()

    def sweep(self) -> list[Ticket]:
        """Drop finished runs, stop runs past the timeout. Returns those stopped."""
        now = self._clock()
        stopped: list[Ticket] = []
        with self._lock:
            for key, ticket in list(self._tickets.items()):
                try:
                    running = bool(ticket.probe())
                except Exception:  # noqa: BLE001 - a broken probe must not wedge the gate
                    running = False
                if not running:
                    del self._tickets[key]
                    continue
                too_old = now - ticket.started > self.timeout
                # A run driven by browser polling stops advancing when its tab
                # closes; after `stale` seconds without a poll it is abandoned.
                abandoned = bool(ticket.last_seen) and now - ticket.last_seen > self.stale
                if too_old or abandoned:
                    del self._tickets[key]
                    stopped.append((ticket, "timeout" if too_old else "abandoned"))
        for ticket, reason in stopped:
            logger.info("demo job stopped (%s, %s): %s…", ticket.kind, reason, ticket.owner[:6])
            try:
                ticket.cancel(reason)
            except Exception:  # noqa: BLE001
                logger.exception("cancelling demo job failed")
        return [ticket for ticket, _ in stopped]

    def running(self) -> int:
        self.sweep()
        with self._lock:
            return len(self._tickets)

    def owner_of(self, kind: str) -> str | None:
        """For one-at-a-time jobs (grid, Bayesian, walk-forward): who runs it."""
        with self._lock:
            for (k, _), ticket in self._tickets.items():
                if k == kind:
                    return ticket.owner
        return None

    def has(self, kind: str, owner: str) -> bool:
        with self._lock:
            return (kind, owner) in self._tickets

    def admit(self, kind: str, owner: str) -> bool:
        """True if a new run may start now (checks capacity, does not register)."""
        self.sweep()
        with self._lock:
            if (kind, owner) in self._tickets:
                return True
            return len(self._tickets) < self.max_concurrent

    def register(self, kind: str, owner: str, probe: Callable[[], bool], cancel: Callable[[str], None], *, polled: bool = False) -> None:
        now = self._clock()
        with self._lock:
            self._tickets[(kind, owner)] = Ticket(kind, owner, now, probe, cancel, last_seen=now if polled else 0.0)

    def touch(self, kind: str, owner: str) -> None:
        with self._lock:
            ticket = self._tickets.get((kind, owner))
            if ticket is not None and ticket.last_seen:
                ticket.last_seen = self._clock()

    def release(self, kind: str, owner: str) -> None:
        with self._lock:
            self._tickets.pop((kind, owner), None)
