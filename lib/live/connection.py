"""
Reconnect policy for the paper trading runner.

IB Gateway restarts itself once a day, and a runner that took every dropped
connection as fatal would stop every night. Two pieces decide what a drop means:

    ReconnectPolicy : how long to wait between reconnect attempts, doubling from
                      ``initial_delay_seconds`` up to ``max_delay_seconds``. It
                      never gives up on its own; the broker_disconnected guard is
                      what ends a runner that cannot get back.
    RestartWindow   : the minutes after the Gateway's scheduled restart during
                      which a drop is expected, so the broker_disconnected guard
                      stays quiet. Outside it the guard's usual limit applies, so
                      a Gateway that never comes back (the weekly re-login) still
                      stops the runner, and alerts, once the window closes.

Both read ``config/agent.yaml`` under ``ib:``.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time, timedelta, tzinfo
from typing import Any
from zoneinfo import ZoneInfo


@dataclass(frozen=True)
class ReconnectPolicy:
    initial_delay_seconds: float = 2.0
    max_delay_seconds: float = 30.0

    def delay(self, attempt: int) -> float:
        """Seconds to wait after the ``attempt``-th failed try (0-based)."""
        return min(self.max_delay_seconds, self.initial_delay_seconds * (2 ** max(0, attempt)))

    @classmethod
    def from_config(cls, cfg: dict[str, Any] | None) -> ReconnectPolicy:
        cfg = cfg or {}
        return cls(
            initial_delay_seconds=float(cfg.get("initial_delay_seconds", cls.initial_delay_seconds)),
            max_delay_seconds=float(cfg.get("max_delay_seconds", cls.max_delay_seconds)),
        )


@dataclass(frozen=True)
class RestartWindow:
    """A daily window, ``minutes`` long from ``start``, in ``tz``.

    ``tz=None`` means this computer's local time zone, resolved at each check so
    a runner left up across a daylight-saving change keeps the right hour.
    """

    start: time
    minutes: int
    tz: tzinfo | None = None

    def contains(self, moment: datetime) -> bool:
        local = moment.astimezone(self.tz)
        # A window that starts before midnight can still be open just after it,
        # so yesterday's start is checked as well as today's.
        for day_offset in (0, -1):
            day = local.date() + timedelta(days=day_offset)
            opens = _localise(datetime.combine(day, self.start), self.tz)
            if opens <= local < opens + timedelta(minutes=self.minutes):
                return True
        return False

    @classmethod
    def from_config(cls, cfg: dict[str, Any] | None) -> RestartWindow | None:
        """Build from ``ib.daily_restart``; ``None`` when the section is absent."""
        if not cfg or not cfg.get("time"):
            return None
        hours, minutes = (int(part) for part in str(cfg["time"]).split(":", 1))
        tz_name = cfg.get("timezone")
        return cls(
            start=time(hours, minutes),
            minutes=int(cfg.get("window_minutes", 15)),
            tz=ZoneInfo(str(tz_name)) if tz_name else None,
        )


def _localise(naive: datetime, tz: tzinfo | None) -> datetime:
    return naive.replace(tzinfo=tz) if tz is not None else naive.astimezone()
