"""
Alerts for the paper trading runner.

When something the operator has to act on happens — a guard trips, the broker
refuses an order, the runner dies on an exception — the runner writes a log line
and a state row, which nobody sees unless they go looking. This module also
pushes it to the webhook named by ``SFA_ALERT_WEBHOOK``. Unset means log only.

One POST per event, never retried and never raised: an unreachable webhook must
not stop the runner from cancelling its orders and shutting down.

Payload formats (``SFA_ALERT_FORMAT`` overrides the automatic choice):

    json  ``{"text", "content", "event", "strategy", "ticker", ...}``. ``text``
          is what a Slack incoming webhook displays and ``content`` what Discord
          displays; the other fields are for anything that parses JSON.
    text  the message as a plain body with ``Title`` / ``Priority`` / ``Tags``
          headers, which ntfy turns into a phone push notification. Picked
          automatically for URLs on ntfy.sh.
"""

from __future__ import annotations

import asyncio
import os
from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from urllib.parse import urlparse

import structlog

logger = structlog.get_logger(__name__)

ALERT_WEBHOOK_ENV = "SFA_ALERT_WEBHOOK"
ALERT_FORMAT_ENV = "SFA_ALERT_FORMAT"
TIMEOUT_SECONDS = 5.0

GUARD_TRIGGERED = "guard_triggered"
ORDER_FAILED = "order_failed"
RUNNER_CRASHED = "runner_crashed"


@dataclass(frozen=True)
class Alert:
    event: str
    strategy: str
    ticker: str
    summary: str
    details: dict[str, Any] = field(default_factory=dict)
    timestamp: datetime = field(default_factory=lambda: datetime.now(UTC))

    @property
    def title(self) -> str:
        return f"sfa {self.strategy} ({self.ticker}): {self.event.replace('_', ' ')}"

    @property
    def message(self) -> str:
        return f"{self.title} - {self.summary}"

    def as_payload(self) -> dict[str, Any]:
        return {
            "text": self.message,
            "content": self.message,
            "event": self.event,
            "strategy": self.strategy,
            "ticker": self.ticker,
            "summary": self.summary,
            "details": self.details,
            "timestamp": self.timestamp.isoformat(),
        }


AlertSink = Callable[[Alert], Awaitable[bool]]


def resolve_format(url: str, override: str | None = None) -> str:
    choice = (override or "").strip().lower()
    if choice in {"json", "text"}:
        return choice
    host = (urlparse(url).hostname or "").lower()
    return "text" if host == "ntfy.sh" or host.endswith(".ntfy.sh") else "json"


def build_request(alert: Alert, fmt: str) -> dict[str, Any]:
    """Keyword arguments for ``requests.post``, minus the URL."""
    if fmt == "text":
        return {
            "data": alert.message.encode("utf-8"),
            # HTTP headers must be latin-1; a non-ASCII strategy name must not
            # turn into a failed delivery.
            "headers": {
                "Title": alert.title.encode("ascii", "replace").decode("ascii"),
                "Priority": "high",
                "Tags": "warning",
            },
        }
    return {"json": alert.as_payload()}


def send_alert(
    alert: Alert,
    *,
    url: str | None = None,
    fmt: str | None = None,
    post: Callable[..., Any] | None = None,
) -> bool:
    """Log the alert and POST it to the webhook. True only when delivered."""
    logger.warning(
        "alert",
        alert_event=alert.event,
        strategy=alert.strategy,
        ticker=alert.ticker,
        summary=alert.summary,
    )
    url = url if url is not None else os.environ.get(ALERT_WEBHOOK_ENV, "").strip()
    if not url:
        return False
    fmt = resolve_format(url, fmt if fmt is not None else os.environ.get(ALERT_FORMAT_ENV))
    if post is None:
        import requests

        post = requests.post
    try:
        response = post(url, timeout=TIMEOUT_SECONDS, **build_request(alert, fmt))
        status = int(getattr(response, "status_code", 200))
        if status >= 400:
            logger.warning("alert.delivery_failed", alert_event=alert.event, status=status)
            return False
        return True
    except Exception as exc:  # never let an alert take the runner down
        logger.warning("alert.delivery_failed", alert_event=alert.event, error=str(exc))
        return False


async def notify(alert: Alert) -> bool:
    """Async wrapper: the POST runs in a worker thread so the bar loop keeps going."""
    return await asyncio.to_thread(send_alert, alert)
