"""Tests for expanded ticker universe (S&P 500 + NASDAQ-100 + Russell 2000)."""

from __future__ import annotations

import pandas as pd
import pytest
from unittest.mock import patch

import lib.data_processing as dp
from lib.data_processing import (
    _fetch_nasdaq100_from_wikipedia,
    _fetch_russell2000_from_github,
    _fetch_russell2000_from_wikipedia,
    get_all_tickers,
)


@pytest.fixture(autouse=True)
def clear_ticker_cache():
    """Ensure each test starts with an empty ticker cache."""
    dp._TICKER_CACHE = None
    dp._TICKER_CACHE_TIME = None
    yield
    dp._TICKER_CACHE = None
    dp._TICKER_CACHE_TIME = None


def test_fetch_nasdaq100_from_wikipedia_parses_constituents_table():
    html = """
    <html><body>
    <table>
      <tr><th>Ticker</th><th>Company</th><th>ICB Industry</th></tr>
      <tr><td>AAPL</td><td>Apple Inc.</td><td>Technology</td></tr>
      <tr><td>MSFT</td><td>Microsoft Corporation</td><td>Technology</td></tr>
    </table>
    </body></html>
  """
    mock_response = type("Resp", (), {"text": html, "raise_for_status": lambda self: None})()

    with patch("requests.get", return_value=mock_response):
        result = _fetch_nasdaq100_from_wikipedia()

    assert result is not None
    assert list(result.columns) == ["Symbol", "Security", "Index", "Exchange"]
    assert set(result["Symbol"]) == {"AAPL", "MSFT"}
    assert (result["Index"] == "NASDAQ-100").all()
    assert (result["Exchange"] == "NASDAQ").all()


def test_fetch_russell2000_from_github_parses_csv():
    csv_text = "Ticker,Name\nRKLB,Rocket Lab Corporation\nIONQ,IonQ Inc.\n"
    mock_response = type(
        "Resp",
        (),
        {"text": csv_text, "raise_for_status": lambda self: None},
    )()

    with patch("requests.get", return_value=mock_response):
        result = _fetch_russell2000_from_github()

    assert result is not None
    assert set(result["Symbol"]) == {"RKLB", "IONQ"}
    assert (result["Index"] == "Russell 2000").all()


def test_fetch_russell2000_prefers_github_over_wikipedia():
    github_df = pd.DataFrame(
        {
            "Symbol": ["RKLB"],
            "Security": ["Rocket Lab Corporation"],
            "Index": ["Russell 2000"],
            "Exchange": ["NASDAQ"],
        }
    )

    with patch(
        "lib.data_processing._fetch_russell2000_from_github",
        return_value=github_df,
    ) as mock_github, patch("requests.get") as mock_get:
        result = _fetch_russell2000_from_wikipedia()

    assert result is not None
    assert result.iloc[0]["Symbol"] == "RKLB"
    mock_github.assert_called_once()
    mock_get.assert_not_called()


def test_get_all_tickers_merges_sources_and_dedupes_by_symbol():
    sp500_df = pd.DataFrame(
        {
            "Symbol": ["AAPL", "MSFT"],
            "Security": ["Apple Inc.", "Microsoft Corp."],
            "Index": ["S&P 500", "S&P 500"],
            "Exchange": ["NASDAQ", "NASDAQ"],
        }
    )
    nasdaq100_df = pd.DataFrame(
        {
            "Symbol": ["AAPL", "GOOGL"],
            "Security": ["Apple Inc.", "Alphabet Inc."],
            "Index": ["NASDAQ-100", "NASDAQ-100"],
            "Exchange": ["NASDAQ", "NASDAQ"],
        }
    )
    russell_df = pd.DataFrame(
        {
            "Symbol": ["RKLB", "AAPL"],
            "Security": ["Rocket Lab Corporation", "Apple Inc."],
            "Index": ["Russell 2000", "Russell 2000"],
            "Exchange": ["NASDAQ", "NASDAQ"],
        }
    )

    with patch(
        "lib.data_processing._fetch_sp500_from_github",
        return_value=sp500_df,
    ), patch(
        "lib.data_processing._fetch_nasdaq100_from_wikipedia",
        return_value=nasdaq100_df,
    ), patch(
        "lib.data_processing._fetch_russell2000_from_wikipedia",
        return_value=russell_df,
    ), patch(
        "lib.data_processing._get_default_tickers",
        return_value=pd.DataFrame(
            columns=["Symbol", "Security", "Index", "Exchange"]
        ),
    ):
        result = get_all_tickers()

    symbols = set(result["Symbol"])
    assert symbols == {"AAPL", "MSFT", "GOOGL", "RKLB"}

    aapl = result.loc[result["Symbol"] == "AAPL"].iloc[0]
    assert aapl["Index"] == "S&P 500"


def test_get_all_tickers_includes_curated_rklb_when_network_missing():
    curated = pd.DataFrame(
        {
            "Symbol": ["RKLB"],
            "Security": ["Rocket Lab Corporation"],
            "Index": ["Russell 2000"],
            "Exchange": ["NASDAQ"],
        }
    )

    with patch(
        "lib.data_processing._fetch_sp500_from_github",
        return_value=None,
    ), patch(
        "lib.data_processing._fetch_from_wikipedia",
        return_value=None,
    ), patch(
        "lib.data_processing._fetch_nasdaq100_from_wikipedia",
        return_value=None,
    ), patch(
        "lib.data_processing._fetch_russell2000_from_wikipedia",
        return_value=None,
    ), patch(
        "lib.data_processing._get_default_tickers",
        return_value=curated,
    ):
        result = get_all_tickers()

    assert "RKLB" in result["Symbol"].values
