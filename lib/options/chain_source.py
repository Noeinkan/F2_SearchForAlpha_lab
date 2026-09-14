"""Option-chain source for the Flow Scanner: the one place it reaches Yahoo.

Yahoo is the only chain source wired today -- every alternative with a real
chain needs an account (ROADMAP 6.7). What this module adds is resilience on
that one source:

* every Yahoo call runs through ``retry_with_backoff``, so a 429 or 5xx is
  retried and, if it persists, raised as ``TransientFetchError`` -- the type
  the dashboard already renders as RATE LIMITED rather than as a bad ticker;
* one expiry that fails no longer loses the whole ticker. It is recorded in
  ``ChainSnapshot.failed_expiries`` and the other expiries are kept; only when
  every expiry fails does the fetch raise.

Nothing here imports ``scripts/``: the scanner turns the raw frames into its
own ``Contract`` rows, so a second chain source only has to return a
``ChainSnapshot``.
"""

from __future__ import annotations

import logging
import math
import time
from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any, Callable

import pandas as pd
import yfinance as yf

from lib.fetch_errors import (
    DataFetchError,
    TransientFetchError,
    classify_fetch_error,
    retry_with_backoff,
)

logger = logging.getLogger(__name__)

# Used by ``--scan`` when Yahoo's most-actives screener cannot be reached.
FALLBACK_SYMBOLS = [
    "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
    "AMD", "AVGO", "JPM", "BAC", "XOM", "COIN", "PLTR", "SMCI", "ARM", "SNOW",
    "MARA", "RIOT", "NFLX", "CRM", "ORCL", "DIS", "BA", "KO", "PEP", "F",
]

Sleep = Callable[[float], None]


@dataclass(frozen=True)
class Quote:
    """Underlying price context. Zeros mean Yahoo did not say, not a price of 0."""

    spot: float = 0.0
    prev_close: float = 0.0
    day_low: float = 0.0
    day_high: float = 0.0
    wk52_low: float = 0.0
    wk52_high: float = 0.0


@dataclass(frozen=True)
class ExpiryChain:
    expiry: date
    calls: pd.DataFrame
    puts: pd.DataFrame


@dataclass
class ChainSnapshot:
    ticker: str
    quote: Quote
    chains: list[ExpiryChain] = field(default_factory=list)
    # Expiry ("YYYY-MM-DD") -> why it is missing from ``chains``.
    failed_expiries: dict[str, str] = field(default_factory=dict)


def _num(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        out = float(value)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if math.isnan(out) else out


def fetch_quote(tk: Any) -> Quote:
    """Best-effort price context; never raises.

    ``Ticker.info`` is the richest source and also the flakiest, so
    ``fast_info`` fills in when it comes back without a price. A quote that
    stays empty does not fail the ticker: the chain is still worth showing.
    """
    try:
        info = tk.info or {}
    except Exception:
        info = {}

    spot = _num(info.get("currentPrice") or info.get("regularMarketPrice"))
    prev = _num(info.get("previousClose"))
    day_low = _num(info.get("dayLow"))
    day_high = _num(info.get("dayHigh"))
    wk52_low = _num(info.get("fiftyTwoWeekLow"))
    wk52_high = _num(info.get("fiftyTwoWeekHigh"))

    if spot <= 0:
        try:
            fi = tk.fast_info
            spot = _num(getattr(fi, "last_price", None) or getattr(fi, "lastPrice", None))
            prev = prev or _num(getattr(fi, "previous_close", None))
            day_low = day_low or _num(getattr(fi, "day_low", None))
            day_high = day_high or _num(getattr(fi, "day_high", None))
            wk52_low = wk52_low or _num(getattr(fi, "year_low", None))
            wk52_high = wk52_high or _num(getattr(fi, "year_high", None))
        except Exception:
            pass

    return Quote(spot, prev, day_low, day_high, wk52_low, wk52_high)


def _yahoo_call(operation: Callable[[], Any], what: str, sleep: Sleep) -> Any:
    """Run one Yahoo request with the shared classify-and-retry policy."""

    def attempt() -> Any:
        try:
            return operation()
        except DataFetchError:
            raise
        except Exception as exc:
            raise classify_fetch_error(exc, f"{what}: {exc}") from exc

    return retry_with_backoff(attempt, describe=what, sleep=sleep)


def fetch_option_chain(
    ticker: str,
    expirations: int = 3,
    *,
    ticker_factory: Callable[[str], Any] | None = None,
    sleep: Sleep = time.sleep,
) -> ChainSnapshot:
    """Fetch the nearest ``expirations`` chains for ``ticker``.

    Raises ``DataFetchError`` (``TransientFetchError`` when retryable) if the
    expiry list cannot be read, or if every listed expiry fails. A ticker with
    no listed options is not an error: it returns an empty snapshot.
    """
    symbol = ticker.upper()
    tk = (ticker_factory or yf.Ticker)(symbol)

    expiries = list(
        _yahoo_call(lambda: tk.options or (), f"Option expiries for {symbol}", sleep)
    )[: max(0, expirations)]
    quote = fetch_quote(tk)

    snapshot = ChainSnapshot(ticker=symbol, quote=quote)
    errors: list[DataFetchError] = []
    for exp_str in expiries:
        try:
            chain = _yahoo_call(
                lambda e=exp_str: tk.option_chain(e),
                f"{symbol} chain {exp_str}",
                sleep,
            )
        except DataFetchError as exc:
            logger.warning("Skipping %s expiry %s: %s", symbol, exp_str, exc)
            snapshot.failed_expiries[exp_str] = str(exc)
            errors.append(exc)
            continue
        snapshot.chains.append(
            ExpiryChain(
                expiry=datetime.strptime(exp_str, "%Y-%m-%d").date(),
                calls=chain.calls,
                puts=chain.puts,
            )
        )

    if errors and not snapshot.chains:
        message = f"All {len(errors)} expiries failed for {symbol}: {errors[-1]}"
        if any(isinstance(e, TransientFetchError) for e in errors):
            raise TransientFetchError(message)
        raise DataFetchError(message)
    return snapshot


def fetch_most_active_symbols(n: int = 50, *, sleep: Sleep = time.sleep) -> list[str]:
    """Most-active US symbols from Yahoo's screener, or ``FALLBACK_SYMBOLS``.

    Goes through ``yfinance.screen`` rather than the raw screener URL, so the
    cookie-and-crumb handshake Yahoo requires stays yfinance's problem.
    """
    try:
        result = _yahoo_call(
            lambda: yf.screen("most_actives", count=n),
            "Most-actives screener",
            sleep,
        )
        symbols = [q["symbol"] for q in (result or {}).get("quotes", []) if q.get("symbol")]
        if symbols:
            return symbols[:n]
        logger.warning("Most-actives screener returned no symbols; using fallback list")
    except DataFetchError as exc:
        logger.warning("Most-actives screener failed (%s); using fallback list", exc)
    return FALLBACK_SYMBOLS[:n]
