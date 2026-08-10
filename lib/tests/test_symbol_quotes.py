"""Tests for symbol-search live quote enrichment."""

from __future__ import annotations

import pandas as pd
import pytest

from lib.dash import symbol_quotes as sq


@pytest.fixture(autouse=True)
def _clear_cache():
    sq.clear_quote_cache()
    yield
    sq.clear_quote_cache()


def test_format_price_and_change():
    quote = sq.SymbolQuote(symbol="AAPL", price=190.5, change_pct=-0.8, currency="USD")
    assert sq.format_price(quote) == "$190.50"
    assert sq.format_change_pct(quote) == "-0.80%"
    assert sq.change_class(quote) == "down"
    assert sq.format_price(None) == "—"
    assert sq.format_change_pct(None) == ""
    assert sq.change_class(None) == "flat"


def test_fetch_quotes_uses_cache(monkeypatch):
    calls = {"n": 0}

    def fake_fetch(symbols):
        calls["n"] += 1
        return {
            symbol: sq.SymbolQuote(symbol=symbol, price=10.0, change_pct=1.0)
            for symbol in symbols
        }

    monkeypatch.setattr(sq, "_fetch_yfinance_quotes", fake_fetch)

    first = sq.fetch_quotes(["AAPL", "MSFT"], ttl=60)
    second = sq.fetch_quotes(["AAPL", "MSFT"], ttl=60)
    assert first["AAPL"].price == 10.0
    assert second["MSFT"].change_pct == 1.0
    assert calls["n"] == 1


def test_quotes_from_multi_ticker_download():
    idx = pd.to_datetime(["2026-08-07", "2026-08-10"])
    columns = pd.MultiIndex.from_product(
        [["AAPL", "TSLA"], ["Open", "High", "Low", "Close", "Volume"]],
        names=["Ticker", "Price"],
    )
    data = {
        ("AAPL", "Close"): [200.0, 210.0],
        ("TSLA", "Close"): [300.0, 291.0],
    }
    frame = pd.DataFrame(
        {col: data.get(col, [1.0, 1.0]) for col in columns},
        index=idx,
    )
    quotes = sq._quotes_from_download(frame, ["AAPL", "TSLA", "MSFT"])
    assert quotes["AAPL"].price == 210.0
    assert quotes["AAPL"].change_pct == pytest.approx(5.0)
    assert quotes["TSLA"].price == 291.0
    assert quotes["TSLA"].change_pct == pytest.approx(-3.0)
    assert "MSFT" not in quotes


def test_quotes_from_single_ticker_download():
    idx = pd.to_datetime(["2026-08-07", "2026-08-10"])
    frame = pd.DataFrame({"Close": [50.0, 55.0]}, index=idx)
    quotes = sq._quotes_from_download(frame, ["AMD"])
    assert quotes["AMD"].price == 55.0
    assert quotes["AMD"].change_pct == pytest.approx(10.0)


def test_fetch_quotes_swallows_network_errors(monkeypatch):
    def boom(symbols):
        raise TimeoutError("offline")

    monkeypatch.setattr(sq, "_fetch_yfinance_quotes", boom)
    assert sq.fetch_quotes(["AAPL"]) == {}
