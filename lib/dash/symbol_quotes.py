"""Live quotes for the symbol-search modal.

Fetches a small batch of last prices for the visible top of the result list via
``yfinance.download``, with an in-process TTL cache so typing in the modal does
not hammer the network. Failures degrade to empty quotes — search itself must
stay responsive offline.
"""

from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from typing import Iterable, Sequence

import pandas as pd

logger = logging.getLogger(__name__)

# How many leading search hits get live prices. Enough for the first scroll
# page; the rest stay as placeholders so a long result list stays fast.
QUOTE_LIMIT = 40

# Cache TTL — quotes are for glanceability, not trading.
QUOTE_TTL_SEC = 60.0

_LOCK = threading.Lock()
_CACHE: dict[str, tuple[float, "SymbolQuote"]] = {}


@dataclass(frozen=True)
class SymbolQuote:
    """Last price + session change for one symbol."""

    symbol: str
    price: float | None = None
    change_pct: float | None = None  # percent points, e.g. 1.24 == +1.24%
    currency: str = "USD"

    @property
    def ok(self) -> bool:
        return self.price is not None


def clear_quote_cache() -> None:
    """Drop the in-process cache (tests / forced refresh)."""
    with _LOCK:
        _CACHE.clear()


def fetch_quotes(
    symbols: Sequence[str] | Iterable[str],
    *,
    limit: int = QUOTE_LIMIT,
    ttl: float = QUOTE_TTL_SEC,
) -> dict[str, SymbolQuote]:
    """Return quotes for up to ``limit`` symbols, preferring cache hits.

    Missing / failed symbols are omitted from the result (callers render a
    placeholder). Never raises — network errors are logged and skipped.
    """
    ordered: list[str] = []
    seen: set[str] = set()
    for raw in symbols:
        symbol = str(raw or "").strip().upper()
        if not symbol or symbol in seen:
            continue
        seen.add(symbol)
        ordered.append(symbol)
        if len(ordered) >= max(0, int(limit)):
            break

    if not ordered:
        return {}

    now = time.monotonic()
    out: dict[str, SymbolQuote] = {}
    missing: list[str] = []

    with _LOCK:
        for symbol in ordered:
            hit = _CACHE.get(symbol)
            if hit and (now - hit[0]) <= ttl:
                out[symbol] = hit[1]
            else:
                missing.append(symbol)

    if missing:
        try:
            fetched = _fetch_yfinance_quotes(missing)
        except Exception as exc:
            logger.warning("Symbol quote enrichment failed: %s", exc)
            fetched = {}
        now = time.monotonic()
        with _LOCK:
            for symbol, quote in fetched.items():
                _CACHE[symbol] = (now, quote)
                out[symbol] = quote

    return out


def _fetch_yfinance_quotes(symbols: Sequence[str]) -> dict[str, SymbolQuote]:
    """Batch last close + day change via ``yfinance.download``."""
    try:
        import yfinance as yf
    except ImportError:
        logger.warning("yfinance unavailable — symbol quotes disabled")
        return {}

    try:
        frame = yf.download(
            tickers=list(symbols),
            period="5d",
            interval="1d",
            group_by="ticker",
            auto_adjust=True,
            threads=True,
            progress=False,
            timeout=6,
        )
    except TypeError:
        # Older yfinance builds lack ``timeout``.
        try:
            frame = yf.download(
                tickers=list(symbols),
                period="5d",
                interval="1d",
                group_by="ticker",
                auto_adjust=True,
                threads=True,
                progress=False,
            )
        except Exception as exc:
            logger.warning("Symbol quote download failed: %s", exc)
            return {}
    except Exception as exc:
        logger.warning("Symbol quote download failed: %s", exc)
        return {}

    if frame is None or getattr(frame, "empty", True):
        return {}

    return _quotes_from_download(frame, symbols)


def _quotes_from_download(
    frame: pd.DataFrame,
    symbols: Sequence[str],
) -> dict[str, SymbolQuote]:
    """Parse a ``yf.download(..., group_by='ticker')`` frame into quotes."""
    out: dict[str, SymbolQuote] = {}

    # Single-ticker download drops the ticker level and returns plain OHLCV.
    if not isinstance(frame.columns, pd.MultiIndex):
        symbol = str(symbols[0]).upper()
        quote = _quote_from_close_series(symbol, frame.get("Close"))
        if quote is not None:
            out[symbol] = quote
        return out

    # Multi-ticker: columns are (Ticker, Price) with group_by='ticker'.
    level0 = {str(value).upper() for value in frame.columns.get_level_values(0)}
    for symbol in symbols:
        key = str(symbol).upper()
        if key not in level0:
            continue
        try:
            close = frame[(key, "Close")]
        except Exception:
            continue
        quote = _quote_from_close_series(key, close)
        if quote is not None:
            out[key] = quote
    return out


def _quote_from_close_series(symbol: str, close: object) -> SymbolQuote | None:
    if close is None:
        return None
    series = close.dropna() if hasattr(close, "dropna") else close
    if series is None or len(series) == 0:
        return None
    try:
        last = float(series.iloc[-1])
    except Exception:
        return None
    if last != last:  # NaN
        return None

    change_pct = None
    if len(series) >= 2:
        try:
            prev = float(series.iloc[-2])
            if prev and prev == prev:
                change_pct = ((last - prev) / prev) * 100.0
        except Exception:
            change_pct = None

    return SymbolQuote(
        symbol=symbol,
        price=last,
        change_pct=change_pct,
        currency="USD",
    )


def format_price(quote: SymbolQuote | None) -> str:
    """Human price text for the modal cell."""
    if quote is None or quote.price is None:
        return "—"
    price = quote.price
    currency = quote.currency or "USD"
    if currency == "USD":
        if abs(price) >= 1:
            return f"${price:,.2f}"
        return f"${price:.4f}"
    if abs(price) >= 1:
        return f"{price:,.2f} {currency}"
    return f"{price:.4f} {currency}"


def format_change_pct(quote: SymbolQuote | None) -> str:
    """Signed percent change, or empty when unknown."""
    if quote is None or quote.change_pct is None:
        return ""
    return f"{quote.change_pct:+.2f}%"


def change_class(quote: SymbolQuote | None) -> str:
    """CSS modifier for up / down / flat change colouring."""
    if quote is None or quote.change_pct is None:
        return "flat"
    if quote.change_pct > 0.005:
        return "up"
    if quote.change_pct < -0.005:
        return "down"
    return "flat"


__all__ = [
    "QUOTE_LIMIT",
    "QUOTE_TTL_SEC",
    "SymbolQuote",
    "change_class",
    "clear_quote_cache",
    "fetch_quotes",
    "format_change_pct",
    "format_price",
]
