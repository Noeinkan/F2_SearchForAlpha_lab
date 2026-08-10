"""Tests for the symbol-search universe, ranking, and modal rendering."""

from __future__ import annotations

import pandas as pd
import pytest

import lib.ticker_universe as tu
from lib.dash import ticker_search
from lib.dash.layout.symbol_search import build_result_rows
from lib.dash.ticker_search import search_symbols


FIXTURE_ROWS = [
    # Symbol, Security, AssetClass, Exchange, Sector, Industry, Index, Country, MarketCap
    ("NVDA", "NVIDIA Corporation", "Stock", "NASDAQ", "Technology", "Semiconductors", "S&P 500", "United States", "5000000000000"),
    ("AMD", "Advanced Micro Devices Inc.", "Stock", "NASDAQ", "Technology", "Semiconductors", "S&P 500", "United States", "300000000000"),
    ("NVMI", "Nova Ltd.", "Stock", "NASDAQ", "Technology", "Semiconductors", "", "Israel", "8000000000"),
    ("AAPL", "Apple Inc.", "Stock", "NASDAQ", "Technology", "Computer Manufacturing", "S&P 500", "United States", "4000000000000"),
    ("MRNA", "Moderna Inc.", "Stock", "NASDAQ", "Health Care", "Biotechnology", "S&P 500", "United States", "10000000000"),
    ("TINY", "Tiny Holdings Corp", "Stock", "NASDAQ", "Industrials", "Shell Companies", "", "United States", "40000000"),
    ("TSLA", "Tesla Inc.", "Stock", "NASDAQ", "Industrials", "Auto Manufacturing", "S&P 500", "United States", "1200000000000"),
    ("SOXX", "iShares Semiconductor ETF", "ETF", "NASDAQ", "Sector", "Semiconductors", "", "United States", ""),
    ("SPY", "SPDR S&P 500 ETF Trust", "ETF", "NYSE ARCA", "Equity", "US Large Cap Blend", "", "United States", ""),
    ("GLD", "SPDR Gold Shares", "ETF", "NYSE ARCA", "Commodity", "Gold", "", "United States", ""),
    # Bulk-screener ETFs: no Sector, so no curated prominence boost. These
    # stand in for the ~5000 rows the ETF screener contributes.
    # Symbols deliberately do NOT contain "gold" — a symbol match outranks
    # every name match, which is correct but would mask what these exercise.
    ("AAAU", "Goldman Sachs Physical Gold ETF Shares", "ETF", "", "", "", "", "United States", ""),
    ("FTVG", "FT Vest Gold Strategy Quarterly Buffer Fund", "ETF", "", "", "", "", "United States", ""),
    ("ZZBULK", "AAA Bulk ETF", "ETF", "", "", "", "", "United States", ""),
    ("PAPL", "Pineapple Holdings Inc.", "Stock", "NASDAQ", "Finance", "Finance Services", "", "United States", "20000000"),
    ("^VIX", "CBOE Volatility Index", "Index", "INDEX", "Volatility Index", "S&P 500 Implied Volatility", "", "United States", ""),
    ("EURUSD=X", "Euro / US Dollar", "FX", "FOREX", "Major Pair", "EUR/USD", "", "", ""),
    ("GC=F", "Gold Futures", "Future", "COMEX", "Metals Future", "Gold", "", "", ""),
]


@pytest.fixture(autouse=True)
def fixture_universe(monkeypatch):
    """Swap the real 14k-row CSV for a small deterministic universe."""
    frame = pd.DataFrame(FIXTURE_ROWS, columns=tu.UNIVERSE_COLUMNS)
    monkeypatch.setattr(tu, "_CACHE", tu._normalise(frame))
    ticker_search.clear_index_cache()
    yield
    ticker_search.clear_index_cache()
    tu.clear_cache()


def _symbols(rows):
    return [row["Symbol"] for row in rows]


# --- Universe loader ------------------------------------------------------


def test_universe_exposes_asset_classes_in_tab_order():
    assert tu.asset_classes() == ["Stock", "ETF", "Index", "FX", "Future"]


def test_sectors_scoped_to_asset_class():
    assert "Technology" in tu.sectors("Stock")
    assert "Technology" not in tu.sectors("ETF")
    assert "Commodity" in tu.sectors("ETF")


def test_lookup_returns_row_and_none_for_unknown():
    assert tu.lookup("nvda")["Security"] == "NVIDIA Corporation"
    assert tu.lookup("NOPE") is None
    assert tu.lookup("") is None


def test_describe_falls_back_to_symbol():
    assert tu.describe("NVDA") == "NVIDIA Corporation"
    assert tu.describe("NOPE") == "NOPE"


def test_normalise_defaults_missing_asset_class_to_stock():
    frame = pd.DataFrame([{"Symbol": "x", "Security": "X Corp"}])
    assert tu._normalise(frame).iloc[0]["AssetClass"] == "Stock"
    assert tu._normalise(frame).iloc[0]["Symbol"] == "X"


# --- Ranking --------------------------------------------------------------


def test_exact_symbol_match_ranks_first():
    assert _symbols(search_symbols("amd"))[0] == "AMD"


def test_symbol_prefix_beats_name_match():
    results = _symbols(search_symbols("nv"))
    # NVDA and NVMI are symbol-prefix matches; both precede any name-only hit.
    assert results[:2] == ["NVDA", "NVMI"]


def test_market_cap_orders_within_a_tier():
    # Both are symbol-prefix matches for "nv"; the larger company wins.
    results = _symbols(search_symbols("nv"))
    assert results.index("NVDA") < results.index("NVMI")


def test_company_name_search():
    assert "AAPL" in _symbols(search_symbols("apple"))


def test_search_by_business_category_finds_sector_peers():
    """The headline feature: category words are searchable, not just tickers."""
    results = _symbols(search_symbols("semiconductor"))

    assert "NVDA" in results
    assert "AMD" in results
    assert "SOXX" in results
    assert "MRNA" not in results


def test_search_by_industry_term():
    assert "MRNA" in _symbols(search_symbols("biotechnology"))


def test_whole_word_name_match_beats_midword_match():
    """'apple' must find Apple Inc. before Pineapple Holdings."""
    results = _symbols(search_symbols("apple"))
    assert results.index("AAPL") < results.index("PAPL")


def test_whole_word_match_beats_longer_word_containing_it():
    # "gold" is a whole word in "SPDR Gold Shares" but not in "Goldman".
    results = _symbols(search_symbols("gold", asset_class="ETF"))
    assert results.index("GLD") < results.index("AAAU")


def test_curated_rows_outrank_bulk_etfs_on_empty_query():
    # Otherwise the default ETF view is whatever sorts first alphabetically.
    results = _symbols(search_symbols("", asset_class="ETF"))
    assert results.index("SPY") < results.index("ZZBULK")


def test_shorter_name_wins_when_relevance_and_prominence_tie():
    results = _symbols(search_symbols("gold", asset_class="ETF"))
    assert results.index("GLD") < results.index("FTVG")


def test_search_matches_across_asset_classes():
    results = _symbols(search_symbols("gold"))
    assert "GLD" in results
    assert "GC=F" in results


def test_alias_search_still_works():
    assert "TSLA" in _symbols(search_symbols("tesla"))


def test_asset_class_filter():
    results = search_symbols("", asset_class="ETF")
    assert {row["AssetClass"] for row in results} == {"ETF"}
    assert "NVDA" not in _symbols(results)


def test_sector_filter():
    results = search_symbols("", asset_class="Stock", sector="Health Care")
    assert _symbols(results) == ["MRNA"]


def test_symbols_filter_restricts_to_watchlist():
    results = search_symbols("", symbols=["SPY", "NVDA"])
    assert sorted(_symbols(results)) == ["NVDA", "SPY"]


def test_symbols_filter_ignores_blank_entries():
    results = search_symbols("", symbols=["SPY", "", None])
    assert _symbols(results) == ["SPY"]


def test_empty_query_returns_prominence_ordered_results():
    results = _symbols(search_symbols(""))
    assert results[0] == "NVDA"  # largest market cap in the fixture


def test_non_equities_outrank_microcaps_on_empty_query():
    # Curated instruments carry no market cap. Without synthetic prominence
    # they would sort last and SPY would sit below every shell company.
    results = _symbols(search_symbols(""))
    assert results.index("SPY") < results.index("TINY")


def test_no_match_returns_empty():
    assert search_symbols("zzzznotathing") == []


def test_limit_is_respected():
    assert len(search_symbols("", limit=3)) == 3


def test_special_characters_do_not_crash_regex():
    # Query text is matched literally; a stray bracket must not raise.
    for query in ["^VIX", "=X", "GC=F", "S&P", "(", "[", "a+b", "*"]:
        search_symbols(query)


def test_caret_and_suffix_symbols_are_findable():
    assert "^VIX" in _symbols(search_symbols("^VIX"))
    assert "EURUSD=X" in _symbols(search_symbols("eurusd"))


# --- Free-text resolution -------------------------------------------------


def test_resolve_exact_symbol_against_universe():
    assert ticker_search.resolve_ticker_symbol("nvda") == "NVDA"


def test_resolve_unique_company_name_against_universe():
    assert ticker_search.resolve_ticker_symbol("Moderna") == "MRNA"


def test_resolve_ambiguous_company_name_takes_best_match():
    # "semiconductor" matches several rows; the search box must still load
    # something sensible rather than handing yfinance the literal words.
    assert ticker_search.resolve_ticker_symbol("semiconductor") in {
        "NVDA", "AMD", "NVMI", "SOXX",
    }


def test_resolve_prefers_exact_symbol_over_name_hits():
    # AMD is a listed symbol, so it wins outright even though several
    # companies mention "AMD" adjacent terms.
    assert ticker_search.resolve_ticker_symbol("amd") == "AMD"


def test_resolve_unknown_text_passes_through_uppercased():
    # yfinance serves symbols this universe does not list, so never block.
    assert ticker_search.resolve_ticker_symbol("zzzz") == "ZZZZ"


def test_resolve_empty_is_empty():
    assert ticker_search.resolve_ticker_symbol("") == ""


def test_is_known_symbol():
    assert ticker_search.is_known_symbol("spy")
    assert not ticker_search.is_known_symbol("nope")
    assert not ticker_search.is_known_symbol("")


# --- Hidden dropdown seeding ---------------------------------------------


def test_select_data_is_bounded_and_includes_active():
    data = ticker_search.dmc_ticker_select_data("GC=F")

    assert len(data) <= ticker_search.POPULAR_LIMIT + 1
    assert any(row["value"] == "GC=F" for row in data)


def test_select_data_does_not_duplicate_active_symbol():
    data = ticker_search.dmc_ticker_select_data("NVDA")
    assert [row["value"] for row in data].count("NVDA") == 1


def test_select_data_accepts_unlisted_active_symbol():
    data = ticker_search.dmc_ticker_select_data("WEIRD")
    assert data[0]["value"] == "WEIRD"


# --- Row rendering --------------------------------------------------------


def test_build_result_rows_marks_starred_and_current():
    rows = search_symbols("", asset_class="ETF")
    children = build_result_rows(rows, starred={"SPY"}, active="GLD")

    def _body(row):
        return row.children[1]

    ids = [_body(child).id["index"] for child in children]
    assert "SPY" in ids and "GLD" in ids

    spy = next(c for c in children if _body(c).id["index"] == "SPY")
    gld = next(c for c in children if _body(c).id["index"] == "GLD")

    assert spy.children[0].children == "★"
    assert gld.children[0].children == "☆"
    assert "current" in gld.className
    assert "current" not in spy.className
    # Star is a sibling of the selectable body so clicks do not select.
    assert _body(spy).id["type"] == "sym-row"
    assert spy.children[0].id["type"] == "sym-star"


def test_build_result_rows_empty_state():
    children = build_result_rows([], starred=set())
    assert len(children) == 1
    assert "sfa-symsearch-empty" in children[0].className


def test_build_result_rows_joins_sector_and_industry():
    rows = [row for row in search_symbols("nvda") if row["Symbol"] == "NVDA"]
    children = build_result_rows(rows, starred=set())
    categories = [
        child.children[1].children[4].children for child in children
    ]
    assert categories == ["Technology · Semiconductors"]


def test_build_result_rows_shows_quote_column():
    from lib.dash.symbol_quotes import SymbolQuote

    rows = [row for row in search_symbols("aapl") if row["Symbol"] == "AAPL"]
    quotes = {
        "AAPL": SymbolQuote(
            symbol="AAPL", price=190.25, change_pct=1.25, currency="USD"
        )
    }
    children = build_result_rows(rows, starred=set(), quotes=quotes)
    quote_cell = children[0].children[1].children[2]
    assert "sfa-symsearch-quote" in quote_cell.className
    assert quote_cell.children[0].children == "$190.25"
    assert quote_cell.children[1].children == "+1.25%"
    assert "up" in quote_cell.children[1].className
