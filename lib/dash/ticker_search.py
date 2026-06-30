"""
Ticker dropdown search helpers.

Dash filters dcc.Dropdown options by label only. These helpers build a separate
search index (symbol + full company name + common aliases) and filter client-side
via a search_value callback.
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import pandas as pd

from lib.dash.dash_config import DEFAULT_TICKER

logger = logging.getLogger(__name__)

# Common nicknames / former names that do not appear in official index listings.
SYMBOL_SEARCH_ALIASES: Dict[str, str] = {
    "GOOG": "google",
    "GOOGL": "google",
    "META": "facebook fb",
    "BRK.A": "berkshire berkshire hathaway",
    "BRK.B": "berkshire berkshire hathaway",
    "TSLA": "tesla",
    "RKLB": "rocket lab",
    "MSTR": "microstrategy",
    "RIVN": "rivian",
    "SOFI": "sofi",
    "SNOW": "snowflake",
}


def _search_text(symbol: str, security_name: str) -> str:
    aliases = SYMBOL_SEARCH_ALIASES.get(symbol, "")
    return f"{symbol} {security_name} {aliases}".strip().lower()


def build_ticker_options(tickers_df: pd.DataFrame) -> List[Dict[str, Any]]:
    """Build dropdown options with a hidden search index for each ticker."""
    options: List[Dict[str, Any]] = []
    for _, row in tickers_df.iterrows():
        symbol = str(row.get("Symbol", "")).strip().upper()
        security_name = str(row.get("Security", "")).strip()
        if not symbol:
            continue

        compact_name = (
            security_name if len(security_name) <= 30 else f"{security_name[:30]}..."
        )
        options.append(
            {
                "label": f"{symbol} - {compact_name}" if compact_name else symbol,
                "value": symbol,
                "search": _search_text(symbol, security_name),
            }
        )
    return options


def _match_rank(symbol: str, search: str, query: str) -> Optional[int]:
    sym = symbol.lower()
    if sym.startswith(query):
        return 0
    if query in sym:
        return 1
    if query in search:
        return 2
    return None


def filter_ticker_options(
    all_options: List[Dict[str, Any]],
    search_value: Optional[str],
    *,
    max_results: int = 100,
) -> List[Dict[str, Any]]:
    """Filter ticker options by symbol, company name, or aliases."""
    if not search_value or not str(search_value).strip():
        return all_options

    query = str(search_value).strip().lower()
    ranked: List[tuple[int, str, Dict[str, Any]]] = []
    for option in all_options:
        rank = _match_rank(
            str(option.get("value", "")),
            str(option.get("search", "")),
            query,
        )
        if rank is not None:
            ranked.append((rank, str(option.get("value", "")), option))

    ranked.sort(key=lambda item: (item[0], item[1]))
    return [option for _, _, option in ranked[:max_results]]


def resolve_ticker_symbol(
    query: str,
    all_options: List[Dict[str, Any]],
) -> str:
    """Map free-text input to a listed symbol when the match is unambiguous."""
    text = str(query or "").strip()
    if not text:
        return ""

    upper = text.upper()
    known = {str(opt.get("value", "")).upper() for opt in all_options}
    if upper in known:
        return upper

    filtered = filter_ticker_options(all_options, text, max_results=5)
    if len(filtered) == 1:
        return str(filtered[0]["value"]).upper()

    prefix_matches = [
        opt
        for opt in filtered
        if str(opt.get("value", "")).upper().startswith(upper)
    ]
    if len(prefix_matches) == 1:
        return str(prefix_matches[0]["value"]).upper()

    return upper


def ensure_ticker_options_loaded() -> List[Dict[str, Any]]:
    """Load (and cache) the full ticker options list for dropdowns and resolution."""
    from lib.data_processing import get_all_tickers
    from lib.dash.state import dashboard_state

    if dashboard_state.ticker_dropdown_options is not None:
        return dashboard_state.ticker_dropdown_options

    try:
        dashboard_state.all_tickers_df = get_all_tickers()
        dashboard_state.ticker_dropdown_options = build_ticker_options(
            dashboard_state.all_tickers_df
        )
        return dashboard_state.ticker_dropdown_options
    except Exception as exc:
        logger.error("Error fetching tickers: %s", exc)
        fallback = [{
            "value": DEFAULT_TICKER,
            "label": f"{DEFAULT_TICKER} - SPDR S&P 500 ETF",
            "search": "spy spdr s&p 500 etf",
        }]
        dashboard_state.ticker_dropdown_options = fallback
        return fallback


def dmc_ticker_select_data() -> List[Dict[str, str]]:
    """Build the `data` prop for dmc.Select.

    Mantine filters client-side on the visible label only, so we append alias
    tokens (e.g. "tesla" for TSLA) to improve nickname search.
    """
    options = ensure_ticker_options_loaded()
    rows: List[Dict[str, str]] = []
    for opt in options:
        label = str(opt.get("label", opt.get("value", "")))
        search = str(opt.get("search", "")).strip()
        if search:
            extras = " ".join(
                token for token in search.split()
                if token and token not in label.lower()
            )
            if extras:
                label = f"{label} · {extras}"
        rows.append({"value": str(opt["value"]), "label": label})
    return rows
