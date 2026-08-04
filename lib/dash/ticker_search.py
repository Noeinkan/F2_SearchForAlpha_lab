"""Symbol search index and ranking.

Backs two consumers:

* The symbol-search modal (:mod:`lib.dash.callbacks.symbol_search`) via
  :func:`search_symbols`, which ranks the full ~14k-row universe server-side and
  matches on symbol, company name, aliases, **sector and industry** — the last
  two are what make "semiconductors" or "biotech" useful queries.
* The hidden ``ticker-dropdown`` state carrier in the sidebar, via the legacy
  ``build_ticker_options`` / ``dmc_ticker_select_data`` helpers. That Select is
  no longer user-facing, so it only receives a bounded popular-symbol list
  (:func:`dmc_ticker_select_data`) instead of the whole universe — shipping
  14k options to the browser on every boot is not worth it.

Data comes from :mod:`lib.ticker_universe` (the committed CSV), never the
network.
"""

from __future__ import annotations

import logging
import re
import threading
from typing import Any, Dict, List, Optional

import pandas as pd

from lib.dash.dash_config import DEFAULT_TICKER
from lib.ticker_universe import UNIVERSE_COLUMNS, load_universe

logger = logging.getLogger(__name__)

# Common nicknames / former names that do not appear in official index listings.
SYMBOL_SEARCH_ALIASES: Dict[str, str] = {
    "GOOG": "google",
    "GOOGL": "google",
    "META": "facebook fb",
    "BRK.A": "berkshire berkshire hathaway",
    "BRK.B": "berkshire berkshire hathaway",
    "BRK-A": "berkshire berkshire hathaway",
    "BRK-B": "berkshire berkshire hathaway",
    "TSLA": "tesla",
    "RKLB": "rocket lab",
    "MSTR": "microstrategy strategy",
    "RIVN": "rivian",
    "SOFI": "sofi",
    "SNOW": "snowflake",
    "^GSPC": "spx s&p500 sp500",
    "^IXIC": "nasdaq composite",
    "^DJI": "dow jones djia",
    "^RUT": "russell 2000",
    "^VIX": "vix fear index volatility",
    "^TNX": "10 year yield tnx",
    "DX-Y.NYB": "dxy dollar index",
    "ES=F": "emini spx futures",
    "NQ=F": "emini nasdaq futures",
    "CL=F": "wti oil crude futures",
    "GC=F": "gold futures",
}

# How many symbols the hidden ticker-dropdown carries. Large enough that the
# "dropdown not populated yet" guard in callbacks/flow.py sees a real list,
# small enough to keep the boot payload trivial.
POPULAR_LIMIT = 400

# Ranking tiers — lower is better.
#
# Whole-word tiers sit above bare substring tiers so that a query like "gold"
# surfaces "SPDR Gold Shares" ahead of the dozen "Goldman Sachs" funds, and
# "apple" beats "Pineapple". Without them, alphabetical tie-breaking inside a
# single substring tier buries the obvious answer.
_RANK_EXACT_SYMBOL = 0
_RANK_SYMBOL_PREFIX = 1
_RANK_SYMBOL_SUBSTR = 2
_RANK_NAME_WORD = 3
_RANK_NAME_PREFIX = 4
_RANK_NAME_SUBSTR = 5
_RANK_CATEGORY_WORD = 6
_RANK_CATEGORY = 7

# Non-equities carry no market cap, so they need a synthetic prominence. Two
# levels, because "every ETF is equally prominent" makes the default ETF view
# a list of whatever sorts first alphabetically:
#
#   * Rows from config/tickers_curated.csv — the hand-picked flagships (SPY,
#     GLD, XLK, ^VIX, ES=F). They are the only non-Stock rows that carry a
#     Sector value, which is what identifies them here.
#   * Everything else from the bulk ETF screener.
#
# Both sit below the mega-caps a user is most likely reaching for, and above
# the micro-caps they are not.
_CURATED_PROMINENCE = 5e10
_NON_STOCK_PROMINENCE = 5e9

_INDEX: Optional[pd.DataFrame] = None
_INDEX_LOCK = threading.Lock()


def _search_text(symbol: str, security_name: str, sector: str = "", industry: str = "") -> str:
    """Build the haystack for one symbol: identifiers plus business category."""
    aliases = SYMBOL_SEARCH_ALIASES.get(symbol, "")
    parts = [symbol, security_name, sector, industry, aliases]
    return " ".join(part for part in parts if part).strip().lower()


def _build_index() -> pd.DataFrame:
    """Universe plus the precomputed lowercase columns the ranker needs."""
    frame = load_universe().copy()
    frame["_symbol_lc"] = frame["Symbol"].str.lower()
    frame["_name_lc"] = frame["Security"].str.lower()
    frame["_search"] = [
        _search_text(row.Symbol, row.Security, row.Sector, row.Industry)
        for row in frame.itertuples(index=False)
    ]
    cap = pd.to_numeric(frame["MarketCap"], errors="coerce").fillna(0.0)
    is_stock = frame["AssetClass"] == "Stock"
    synthetic = pd.Series(_NON_STOCK_PROMINENCE, index=frame.index, dtype=float)
    synthetic = synthetic.mask(frame["Sector"] != "", _CURATED_PROMINENCE)
    frame["_prominence"] = cap.where(is_stock | (cap > 0), other=synthetic)
    # Tiebreak for rows that share a relevance tier *and* a prominence — in
    # practice every ETF, since none of them carry a market cap. Flagship
    # products have terse names ("SPDR Gold Shares") while the derivative
    # ones are verbose ("FT Vest Gold Strategy Quarterly Buffer"), so short
    # names are a decent proxy for "the one they meant". Alphabetical order,
    # the alternative, is meaningless here.
    frame["_name_len"] = frame["Security"].str.len()
    return frame


def _index() -> pd.DataFrame:
    global _INDEX
    if _INDEX is not None:
        return _INDEX
    with _INDEX_LOCK:
        if _INDEX is None:
            _INDEX = _build_index()
    return _INDEX


def clear_index_cache() -> None:
    """Drop the cached search index. Used by tests."""
    global _INDEX
    with _INDEX_LOCK:
        _INDEX = None


def _row_to_dict(row: pd.Series) -> Dict[str, Any]:
    return {column: row[column] for column in UNIVERSE_COLUMNS}


def search_symbols(
    query: Optional[str] = None,
    *,
    asset_class: Optional[str] = None,
    sector: Optional[str] = None,
    symbols: Optional[List[str]] = None,
    limit: int = 200,
) -> List[Dict[str, Any]]:
    """Rank the universe against ``query`` under the given filters.

    Args:
        query: Free text — matched against symbol, name, sector, industry and
            aliases. Empty shows the most prominent symbols for the filters.
        asset_class: Restrict to one of Stock / ETF / Index / FX / Future.
        sector: Restrict to an exact sector value.
        symbols: Restrict to this symbol list (used for watchlist-only mode).
        limit: Maximum rows returned.

    Returns:
        Universe row dicts, best match first.
    """
    frame = _index()

    if asset_class:
        frame = frame[frame["AssetClass"] == asset_class]
    if sector:
        frame = frame[frame["Sector"] == sector]
    if symbols is not None:
        wanted = {str(sym).strip().upper() for sym in symbols if str(sym).strip()}
        frame = frame[frame["Symbol"].isin(wanted)]

    if frame.empty:
        return []

    text = str(query or "").strip().lower()
    if not text:
        ordered = frame.sort_values(
            ["_prominence", "_name_len", "Symbol"], ascending=[False, True, True]
        )
        return [_row_to_dict(row) for _, row in ordered.head(limit).iterrows()]

    symbol_lc = frame["_symbol_lc"]
    name_lc = frame["_name_lc"]
    # Whole-word form of the query. Symbols carry '^', '=' and '-', so this is
    # only applied to the name and category text where word breaks mean
    # something.
    word_re = rf"\b{re.escape(text)}\b"

    # Assign every row its best (lowest) tier; NaN means "no match at all".
    rank = pd.Series(float("nan"), index=frame.index)
    for tier, mask in (
        (_RANK_EXACT_SYMBOL, symbol_lc == text),
        (_RANK_SYMBOL_PREFIX, symbol_lc.str.startswith(text)),
        (_RANK_SYMBOL_SUBSTR, symbol_lc.str.contains(text, regex=False)),
        (_RANK_NAME_WORD, name_lc.str.contains(word_re, regex=True)),
        (_RANK_NAME_PREFIX, name_lc.str.startswith(text)),
        (_RANK_NAME_SUBSTR, name_lc.str.contains(text, regex=False)),
        (_RANK_CATEGORY_WORD, frame["_search"].str.contains(word_re, regex=True)),
        (_RANK_CATEGORY, frame["_search"].str.contains(text, regex=False)),
    ):
        rank = rank.mask(rank.isna() & mask, tier)

    matched = frame[rank.notna()].assign(_rank=rank[rank.notna()])
    if matched.empty:
        return []

    ordered = matched.sort_values(
        ["_rank", "_prominence", "_name_len", "Symbol"],
        ascending=[True, False, True, True],
    )
    return [_row_to_dict(row) for _, row in ordered.head(limit).iterrows()]


# --------------------------------------------------------------------------
# Legacy option-list helpers. The sidebar Select is hidden now, but these are
# still called by callbacks/startup.py and callbacks/fundamentals.py.
# --------------------------------------------------------------------------


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
                "search": _search_text(
                    symbol,
                    security_name,
                    str(row.get("Sector", "") or ""),
                    str(row.get("Industry", "") or ""),
                ),
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
    all_options: Optional[List[Dict[str, Any]]] = None,
) -> str:
    """Map free-text input to a symbol.

    Two modes, because the two call sites want different things:

    * **Universe mode** (``all_options`` omitted) — what the symbol-search
      modal uses for Enter. Search-box semantics: the best-ranked hit wins.
      Requiring a *unique* match would strand ordinary queries, since "tesla"
      matches TSLA plus a dozen leveraged Tesla ETFs.
    * **Scoped mode** (``all_options`` given) — what the fundamentals overlay
      uses. Conservative: only an unambiguous match is resolved, so a vague
      entry is left for the user to correct rather than silently guessed.

    Either way, unresolvable text comes back uppercased rather than empty —
    yfinance serves plenty of symbols this universe does not list, so a miss
    here must not block the user.
    """
    text = str(query or "").strip()
    if not text:
        return ""

    upper = text.upper()

    if all_options is None:
        if (_index()["Symbol"] == upper).any():
            return upper
        matches = search_symbols(text, limit=5)
        return str(matches[0]["Symbol"]).upper() if matches else upper

    known = {str(opt.get("value", "")).upper() for opt in all_options}
    if upper in known:
        return upper

    filtered = filter_ticker_options(all_options, text, max_results=5)
    candidates = [str(opt.get("value", "")).upper() for opt in filtered]

    if len(candidates) == 1:
        return candidates[0]

    prefix_matches = [sym for sym in candidates if sym.startswith(upper)]
    if len(prefix_matches) == 1:
        return prefix_matches[0]

    return upper


def popular_symbols(limit: int = POPULAR_LIMIT) -> List[Dict[str, Any]]:
    """The most prominent symbols — what the hidden Select is seeded with."""
    return search_symbols(None, limit=limit)


def ensure_ticker_options_loaded() -> List[Dict[str, Any]]:
    """Load the option list used for free-text resolution and the hidden Select."""
    from lib.dash.state import dashboard_state

    if dashboard_state.ticker_dropdown_options is not None:
        return dashboard_state.ticker_dropdown_options

    try:
        frame = load_universe()
        dashboard_state.all_tickers_df = frame
        dashboard_state.ticker_dropdown_options = build_ticker_options(
            pd.DataFrame(popular_symbols())
        )
        return dashboard_state.ticker_dropdown_options
    except Exception as exc:
        logger.error("Error loading ticker universe: %s", exc)
        fallback = [{
            "value": DEFAULT_TICKER,
            "label": DEFAULT_TICKER,
            "search": DEFAULT_TICKER.lower(),
        }]
        dashboard_state.ticker_dropdown_options = fallback
        return fallback


def dmc_ticker_select_data(active: Optional[str] = None) -> List[Dict[str, str]]:
    """Build the bounded `data` prop for the hidden ``ticker-dropdown`` Select.

    The Select is a state carrier, not a user-facing control, so this ships a
    popular-symbol list rather than the whole universe. ``active`` is always
    included so a deep-linked symbol outside the popular set still validates.
    """
    rows = [
        {"value": row["Symbol"], "label": f"{row['Symbol']} - {row['Security']}".strip(" -")}
        for row in popular_symbols()
    ]

    key = str(active or "").strip().upper()
    if key and not any(row["value"] == key for row in rows):
        from lib.ticker_universe import lookup

        found = lookup(key)
        label = f"{key} - {found['Security']}" if found and found.get("Security") else key
        rows.insert(0, {"value": key, "label": label})

    return rows


def is_known_symbol(symbol: str) -> bool:
    """True when the symbol appears in the universe CSV."""
    key = str(symbol or "").strip().upper()
    if not key:
        return False
    return bool((_index()["Symbol"] == key).any())
