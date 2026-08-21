"""Fetch error types and retry policy shared by every market-data source.

This module deliberately has no vendor imports, so a second market-data
source can depend on it without a circular import back through
``lib.data_processing``.

``DataFetchError`` is re-exported from ``lib.data_processing`` for backwards
compatibility -- it lived there historically and several modules still import
it from that path.
"""

from __future__ import annotations

import logging
import time
from typing import Callable, TypeVar

logger = logging.getLogger(__name__)

T = TypeVar("T")

# HTTP statuses worth retrying: rate limiting and transient upstream faults.
RETRYABLE_STATUSES = frozenset({429, 500, 502, 503, 504})

# Substrings that identify a retryable failure when no status code is exposed.
# yfinance's transport varies between ``requests`` and ``curl_cffi``, and the
# latter frequently surfaces errors as plain strings with no ``response``.
_RETRYABLE_MARKERS = (
    "429",
    "too many requests",
    "rate limit",
    "rate-limit",
    "timed out",
    "timeout",
    "connection reset",
    "connection aborted",
    "temporarily unavailable",
    "service unavailable",
    "bad gateway",
    "gateway timeout",
)

MAX_RETRIES = 2
BACKOFF_FACTOR = 1.0
# Never sleep longer than this, whatever ``Retry-After`` claims -- this runs
# inside a Dash callback and must not hang the UI.
MAX_BACKOFF_SECONDS = 8.0


class DataFetchError(Exception):
    """Raised when market data cannot be fetched or fails validation."""

    pass


class TransientFetchError(DataFetchError):
    """A fetch failure that is worth retrying: rate limit, timeout, 5xx.

    Subclasses ``DataFetchError`` so existing ``except DataFetchError`` blocks
    keep catching it. Callers that can react to a retryable failure -- the
    dashboard status bar, any future fallback vendor -- test for this type
    explicitly rather than string-matching the message.
    """

    def __init__(
        self,
        message: str,
        *,
        status_code: int | None = None,
        retry_after: float | None = None,
    ) -> None:
        super().__init__(message)
        self.status_code = status_code
        self.retry_after = retry_after


def _status_of(exc: BaseException) -> int | None:
    """Best-effort HTTP status extraction across transport libraries."""
    response = getattr(exc, "response", None)
    for holder in (response, exc):
        if holder is None:
            continue
        for attr in ("status_code", "status", "code"):
            value = getattr(holder, attr, None)
            if isinstance(value, int) and 100 <= value <= 599:
                return value
    return None


def _retry_after_of(exc: BaseException) -> float | None:
    """Parse a ``Retry-After`` header if the exception carries one."""
    response = getattr(exc, "response", None)
    headers = getattr(response, "headers", None)
    if not headers:
        return None
    try:
        raw = headers.get("Retry-After")
    except Exception:
        return None
    if raw is None:
        return None
    try:
        # Only the delta-seconds form is handled; the HTTP-date form is rare
        # and falls through to plain exponential backoff.
        return max(0.0, float(str(raw).strip()))
    except (TypeError, ValueError):
        return None


def classify_fetch_error(exc: BaseException, message: str) -> DataFetchError:
    """Wrap ``exc`` as a transient or permanent fetch error.

    Returns ``TransientFetchError`` when the failure looks retryable (429, 5xx,
    timeout, dropped connection) and a plain ``DataFetchError`` otherwise -- an
    unknown ticker must not be retried.
    """
    status = _status_of(exc)
    if status is not None:
        if status in RETRYABLE_STATUSES:
            return TransientFetchError(
                message,
                status_code=status,
                retry_after=_retry_after_of(exc),
            )
        # An explicit non-retryable status (404, 403, ...) settles it.
        return DataFetchError(message)

    if isinstance(exc, (TimeoutError, ConnectionError)):
        return TransientFetchError(message)

    text = f"{type(exc).__name__}: {exc}".lower()
    if any(marker in text for marker in _RETRYABLE_MARKERS):
        return TransientFetchError(message)

    return DataFetchError(message)


def retry_with_backoff(
    operation: Callable[[], T],
    *,
    describe: str,
    max_retries: int = MAX_RETRIES,
    backoff_factor: float = BACKOFF_FACTOR,
    sleep: Callable[[float], None] = time.sleep,
) -> T:
    """Run ``operation``, retrying only failures classified as transient.

    ``operation`` is expected to raise ``DataFetchError`` (typically built via
    :func:`classify_fetch_error`). Permanent errors propagate on the first
    attempt; transient ones are retried up to ``max_retries`` extra times with
    exponential backoff, honouring ``Retry-After`` when the server sent one.
    """
    attempts = max_retries + 1
    for attempt in range(attempts):
        try:
            return operation()
        except TransientFetchError as exc:
            if attempt >= attempts - 1:
                logger.warning("%s failed after %d attempts: %s", describe, attempts, exc)
                raise
            wait = backoff_factor * (2**attempt)
            if exc.retry_after is not None:
                wait = max(wait, exc.retry_after)
            wait = min(wait, MAX_BACKOFF_SECONDS)
            logger.warning(
                "%s hit a transient error (%s); retrying in %.1fs",
                describe,
                exc,
                wait,
            )
            sleep(wait)

    # Unreachable: the loop either returns or raises.
    raise DataFetchError(f"{describe} exhausted its retries")
