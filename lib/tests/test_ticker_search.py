"""Tests for ticker dropdown search helpers."""

import pandas as pd

from lib.dash.ticker_search import (
    build_ticker_options,
    filter_ticker_options,
    resolve_ticker_symbol,
)


def test_build_ticker_options_includes_search_index():
    df = pd.DataFrame(
        [
            {"Symbol": "GOOGL", "Security": "Alphabet Inc. Class A"},
            {"Symbol": "SPY", "Security": "SPDR S&P 500 ETF"},
        ]
    )
    options = build_ticker_options(df)

    googl = next(opt for opt in options if opt["value"] == "GOOGL")
    assert "alphabet" in googl["search"]
    assert "google" in googl["search"]


def test_filter_finds_google_by_nickname():
    df = pd.DataFrame(
        [
            {"Symbol": "GOOGL", "Security": "Alphabet Inc. Class A"},
            {"Symbol": "GOOG", "Security": "Alphabet Inc. Class C"},
            {"Symbol": "SPY", "Security": "SPDR S&P 500 ETF"},
        ]
    )
    options = build_ticker_options(df)
    filtered = filter_ticker_options(options, "google")

    values = {opt["value"] for opt in filtered}
    assert "GOOGL" in values
    assert "GOOG" in values
    assert "SPY" not in values


def test_filter_finds_by_company_name():
    df = pd.DataFrame([{"Symbol": "AAPL", "Security": "Apple Inc."}])
    options = build_ticker_options(df)
    filtered = filter_ticker_options(options, "apple")

    assert len(filtered) == 1
    assert filtered[0]["value"] == "AAPL"


def test_filter_empty_search_returns_all():
    df = pd.DataFrame(
        [
            {"Symbol": "AAPL", "Security": "Apple Inc."},
            {"Symbol": "MSFT", "Security": "Microsoft Corp."},
        ]
    )
    options = build_ticker_options(df)

    assert filter_ticker_options(options, "") == options
    assert filter_ticker_options(options, None) == options


def test_filter_prefers_symbol_prefix_matches():
    df = pd.DataFrame(
        [
            {"Symbol": "G", "Security": "Genpact Limited"},
            {"Symbol": "GOOGL", "Security": "Alphabet Inc. Class A"},
        ]
    )
    options = build_ticker_options(df)
    filtered = filter_ticker_options(options, "go")

    assert filtered[0]["value"] == "GOOGL"


def test_resolve_keeps_exact_symbol():
    df = pd.DataFrame([{"Symbol": "TSLA", "Security": "Tesla, Inc."}])
    options = build_ticker_options(df)

    assert resolve_ticker_symbol("TSLA", options) == "TSLA"


def test_resolve_company_name_to_symbol():
    df = pd.DataFrame([{"Symbol": "TSLA", "Security": "Tesla, Inc."}])
    options = build_ticker_options(df)

    assert resolve_ticker_symbol("TESLA", options) == "TSLA"
    assert resolve_ticker_symbol("tesla", options) == "TSLA"


def test_resolve_ambiguous_input_unchanged():
    df = pd.DataFrame(
        [
            {"Symbol": "T", "Security": "AT&T Inc."},
            {"Symbol": "TSLA", "Security": "Tesla, Inc."},
        ]
    )
    options = build_ticker_options(df)

    assert resolve_ticker_symbol("T", options) == "T"
