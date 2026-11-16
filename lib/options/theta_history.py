"""End-of-day option and stock history from ThetaData, through a local Theta Terminal.

ThetaData serves its data only through the Theta Terminal, a Java program the
user runs next to the dashboard (``java -jar ThetaTerminalv3.jar``). It listens
on ``http://127.0.0.1:25503/v3`` and answers plain HTTP. The free plan covers
one year of end-of-day (EOD) option and stock history, one request at a time,
with a one-day delay; quote, open-interest and contract-list endpoints need a
paid plan, so everything here is built from the EOD endpoints alone:

* ``/option/history/eod`` with ``expiration=*`` and one date lists every
  contract quoted that day, including ones that have since expired.
* the same endpoint with one contract and a date range gives its daily bid/ask.
* ``/stock/history/eod`` gives the unadjusted underlying close and, with it, the
  trading calendar used to spot days a contract had no quote.

The EOD quote is the last national best bid/offer at ThetaData's 17:15 ET
report, so every observation here is stamped with that report time.
"""

from __future__ import annotations

import csv
import io
import logging
import math
import os
import threading
import time as clock
from datetime import date, datetime, time, timedelta, timezone
from typing import Any, Callable
from zoneinfo import ZoneInfo

import requests

from lib.fetch_errors import DataFetchError, TransientFetchError, retry_with_backoff

logger = logging.getLogger(__name__)

BASE_URL = os.environ.get("SFA_THETA_URL", "http://127.0.0.1:25503/v3").rstrip("/")
# Free plan: one year of EOD history. A paid plan reaches further back.
HISTORY_DAYS = int(os.environ.get("SFA_THETA_HISTORY_DAYS", "365") or 365)
TIMEOUT_SECONDS = 120
SOURCE_LABEL = "ThetaData EOD"
MARKET_TZ = ZoneInfo("America/New_York")
EOD_REPORT_TIME = time(17, 15)
STANDARD_MULTIPLIER = 100

# The free plan allows one request in flight per account and 20 requests a
# minute; queueing them here, spaced by MIN_INTERVAL_SECONDS, keeps a bulk
# download and a dashboard click from being refused by the terminal.
MIN_INTERVAL_SECONDS = float(os.environ.get("SFA_THETA_MIN_INTERVAL", "3.0") or 3.0)
_request_lock = threading.Lock()
_last_request_at = 0.0


class ThetaUnavailable(DataFetchError):
    """The Theta Terminal is not running or not reachable."""


class ThetaTooLarge(DataFetchError):
    """HTTP 570: the date range holds too much data; ask for a shorter one."""


def history_window(today: date | None = None) -> tuple[date, date]:
    """First and last date the configured plan can return (last = yesterday)."""
    today = today or date.today()
    return today - timedelta(days=HISTORY_DAYS), today - timedelta(days=1)


def _ymd(value: date | str) -> str:
    return (value if isinstance(value, date) else date.fromisoformat(str(value)[:10])).strftime("%Y%m%d")


def _get(path: str, params: dict[str, Any], *, session_get: Callable[..., Any] | None = None) -> list[dict]:
    url = f"{BASE_URL}/{path.lstrip('/')}"
    getter = session_get or requests.get

    def operation() -> list[dict]:
        try:
            response = getter(url, params={**params, "format": "csv"}, timeout=TIMEOUT_SECONDS)
        except requests.ConnectionError as exc:
            raise ThetaUnavailable(
                f"Theta Terminal is not running at {BASE_URL}. Start it with "
                "`java -jar ThetaTerminalv3.jar` and try again."
            ) from exc
        except requests.Timeout as exc:
            raise TransientFetchError(f"ThetaData timed out on {path}") from exc
        status = response.status_code
        if status == 570:
            raise ThetaTooLarge(f"ThetaData says the request for {path} asks for too much data")
        if status == 429 or status >= 500:
            raise TransientFetchError(f"ThetaData returned HTTP {status} on {path}", status_code=status)
        body = response.text or ""
        # v3 answers "no data" with a 4xx and a short message; an empty table is not an error.
        if status in (404, 472) or (200 <= status < 300 and not body.strip()):
            return []
        if not 200 <= status < 300:
            detail = " ".join(body.split())[:200]
            raise DataFetchError(f"ThetaData refused {path} (HTTP {status}): {detail or 'no detail'}")
        return [{str(k).strip().lower(): v for k, v in row.items() if k is not None}
                for row in csv.DictReader(io.StringIO(body))]

    def spaced() -> list[dict]:
        global _last_request_at
        wait = _last_request_at + MIN_INTERVAL_SECONDS - clock.monotonic()
        if wait > 0 and session_get is None:
            clock.sleep(wait)
        try:
            return operation()
        finally:
            _last_request_at = clock.monotonic()

    with _request_lock:
        return retry_with_backoff(spaced, describe=f"ThetaData {path}")


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def _positive(value: Any) -> float | None:
    number = _number(value)
    return number if number is not None and number > 0 else None


def _right(value: Any) -> str | None:
    text = str(value or "").strip().upper()
    return text[0] if text[:1] in ("C", "P") else None


def _expiry(value: Any) -> str | None:
    text = str(value or "").strip()
    try:
        if len(text) == 8 and text.isdigit():
            return datetime.strptime(text, "%Y%m%d").date().isoformat()
        return date.fromisoformat(text[:10]).isoformat()
    except ValueError:
        return None


def observation_stamp(created: Any, trade_date: date | str | None = None) -> tuple[str, str]:
    """``(trade date, UTC ISO timestamp)`` of one EOD row.

    ``created`` is ThetaData's report time in New York time. When it is missing
    the documented 17:15 ET report time on ``trade_date`` stands in.
    """
    stamp = None
    text = str(created or "").strip()
    if text:
        try:
            stamp = datetime.fromisoformat(text.replace("Z", "+00:00"))
        except ValueError:
            stamp = None
    if stamp is None:
        if trade_date is None:
            raise ValueError("An EOD row needs a report time or a trade date")
        day = trade_date if isinstance(trade_date, date) else date.fromisoformat(str(trade_date)[:10])
        stamp = datetime.combine(day, EOD_REPORT_TIME)
    if stamp.tzinfo is None:
        stamp = stamp.replace(tzinfo=MARKET_TZ)
    local = stamp.astimezone(MARKET_TZ)
    return local.date().isoformat(), stamp.astimezone(timezone.utc).isoformat(timespec="seconds")


def parse_option_row(row: dict, *, trade_date: date | str | None = None) -> dict | None:
    """One EOD row as a quote dict, or None when it does not name a contract."""
    expiry = _expiry(row.get("expiration"))
    cp = _right(row.get("right"))
    strike = _positive(row.get("strike"))
    if not expiry or not cp or strike is None:
        return None
    day, observed = observation_stamp(row.get("created"), trade_date)
    volume = _number(row.get("volume"))
    return {
        "date": day, "observed_at": observed,
        "expiry": expiry, "cp": cp, "strike": strike,
        "bid": _positive(row.get("bid")), "ask": _positive(row.get("ask")),
        "close": _positive(row.get("close")),
        "volume": volume if volume is not None and volume >= 0 else None,
        "multiplier": STANDARD_MULTIPLIER,
    }


def option_eod(symbol: str, start: date | str, end: date | str, *, expiration: date | str = "*",
               strike: float | None = None, right: str = "both",
               session_get: Callable[..., Any] | None = None) -> list[dict]:
    """Daily EOD quotes; ``expiration='*'`` returns every contract quoted in the range."""
    params: dict[str, Any] = {
        "symbol": symbol.upper(),
        "expiration": expiration if expiration == "*" else _ymd(expiration),
        "start_date": _ymd(start), "end_date": _ymd(end),
        "right": {"C": "call", "P": "put"}.get(str(right).upper()[:1], "both"),
    }
    if strike is not None:
        params["strike"] = f"{float(strike):.3f}"
    single_day = _ymd(start) == _ymd(end)
    rows = _get("option/history/eod", params, session_get=session_get)
    quotes = [parse_option_row(row, trade_date=start if single_day else None) for row in rows]
    return [q for q in quotes if q is not None]


def stock_eod(symbol: str, start: date | str, end: date | str, *,
              session_get: Callable[..., Any] | None = None) -> dict[str, float]:
    """``{trade date: unadjusted close}``; option strikes are never split-adjusted, so neither is this."""
    rows = _get("stock/history/eod", {"symbol": symbol.upper(), "start_date": _ymd(start),
                                       "end_date": _ymd(end)}, session_get=session_get)
    closes: dict[str, float] = {}
    for row in rows:
        close = _positive(row.get("close"))
        if close is None:
            continue
        stamp = row.get("created") or row.get("last_trade") or row.get("date")
        try:
            day, _ = observation_stamp(stamp, None)
        except ValueError:
            day = _expiry(stamp) or ""
        if day:
            closes[day] = close
    return closes
