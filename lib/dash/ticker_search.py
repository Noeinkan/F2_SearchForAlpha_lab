"""
Ticker dropdown search helpers.

Dash filters dcc.Dropdown options by label only. These helpers build a separate
search index (symbol + full company name + common aliases) and filter client-side
via a search_value callback.
"""

from __future__ import annotations

from typing import Any, Dict, List, Optional

import pandas as pd

# Common nicknames / former names that do not appear in official index listings.
SYMBOL_SEARCH_ALIASES: Dict[str, str] = {
    "GOOG": "google",
    "GOOGL": "google",
    "META": "facebook fb",
    "BRK.A": "berkshire berkshire hathaway",
    "BRK.B": "berkshire berkshire hathaway",
    "TSLA": "tesla",
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
