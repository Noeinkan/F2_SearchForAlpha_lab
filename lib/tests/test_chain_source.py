"""Option-chain source: retries, per-expiry tolerance, rate-limit classification."""

from __future__ import annotations

import json
from datetime import date
from types import SimpleNamespace

import pandas as pd
import pytest

from lib.fetch_errors import DataFetchError, TransientFetchError
from lib.options import chain_source
from lib.options.chain_source import (
    FALLBACK_SYMBOLS,
    ChainSnapshot,
    ExpiryChain,
    Quote,
    fetch_most_active_symbols,
    fetch_option_chain,
    fetch_quote,
)


class RateLimited(Exception):
    """Shaped like yfinance's YFRateLimitError: no status code, telling message."""

    def __init__(self) -> None:
        super().__init__("Too Many Requests. Rate limited. Try after a while.")


def _frame(strike: float) -> pd.DataFrame:
    return pd.DataFrame([{
        "strike": strike, "lastPrice": 1.0, "bid": 0.9, "ask": 1.1,
        "volume": 10, "openInterest": 5, "impliedVolatility": 0.3,
    }])


class FakeTicker:
    """``options`` and each expiry's chain are scripted as a queue of outcomes."""

    def __init__(self, expiries, chains=None, *, info=None, fast_info=None):
        self._expiries = list(expiries) if isinstance(expiries, list) else [expiries]
        self._chains = {k: list(v) for k, v in (chains or {}).items()}
        self._info = info if info is not None else {"currentPrice": 100.0, "previousClose": 99.0}
        self.fast_info = fast_info
        self.chain_calls: dict[str, int] = {}

    @staticmethod
    def _play(outcome):
        if isinstance(outcome, BaseException):
            raise outcome
        return outcome

    @property
    def options(self):
        outcome = self._expiries.pop(0) if len(self._expiries) > 1 else self._expiries[0]
        return self._play(outcome)

    @property
    def info(self):
        return self._play(self._info)

    def option_chain(self, expiry):
        self.chain_calls[expiry] = self.chain_calls.get(expiry, 0) + 1
        queue = self._chains[expiry]
        outcome = queue.pop(0) if len(queue) > 1 else queue[0]
        return self._play(outcome)


def _chain(strike: float):
    return SimpleNamespace(calls=_frame(strike), puts=_frame(strike))


def _fetch(tk, expirations=3):
    sleeps: list[float] = []
    snapshot = fetch_option_chain("aapl", expirations, ticker_factory=lambda _s: tk, sleep=sleeps.append)
    return snapshot, sleeps


def test_every_expiry_fetched():
    tk = FakeTicker(("2026-09-18", "2026-09-25"), {
        "2026-09-18": [_chain(100)],
        "2026-09-25": [_chain(105)],
    })
    snapshot, sleeps = _fetch(tk)
    assert snapshot.ticker == "AAPL"
    assert [c.expiry for c in snapshot.chains] == [date(2026, 9, 18), date(2026, 9, 25)]
    assert snapshot.failed_expiries == {}
    assert snapshot.quote.spot == 100.0
    assert sleeps == []


def test_expirations_caps_the_expiry_list():
    tk = FakeTicker(("2026-09-18", "2026-09-25", "2026-10-02"), {
        "2026-09-18": [_chain(100)],
        "2026-09-25": [_chain(105)],
    })
    snapshot, _ = _fetch(tk, expirations=2)
    assert len(snapshot.chains) == 2
    assert "2026-10-02" not in tk.chain_calls


def test_a_bad_expiry_is_skipped_not_fatal_and_not_retried():
    tk = FakeTicker(("2026-09-18", "2026-09-25"), {
        "2026-09-18": [ValueError("malformed chain payload")],
        "2026-09-25": [_chain(105)],
    })
    snapshot, sleeps = _fetch(tk)
    assert [c.expiry for c in snapshot.chains] == [date(2026, 9, 25)]
    assert "malformed chain payload" in snapshot.failed_expiries["2026-09-18"]
    assert tk.chain_calls["2026-09-18"] == 1
    assert sleeps == []


def test_a_throttled_expiry_is_retried_until_it_answers():
    tk = FakeTicker(("2026-09-18",), {
        "2026-09-18": [RateLimited(), RateLimited(), _chain(100)],
    })
    snapshot, sleeps = _fetch(tk)
    assert len(snapshot.chains) == 1
    assert tk.chain_calls["2026-09-18"] == 3
    assert len(sleeps) == 2


def test_every_expiry_throttled_raises_transient():
    tk = FakeTicker(("2026-09-18", "2026-09-25"), {
        "2026-09-18": [RateLimited()],
        "2026-09-25": [RateLimited()],
    })
    with pytest.raises(TransientFetchError, match="All 2 expiries failed for AAPL"):
        _fetch(tk)


def test_every_expiry_broken_raises_permanent():
    tk = FakeTicker(("2026-09-18",), {"2026-09-18": [ValueError("nope")]})
    with pytest.raises(DataFetchError) as info:
        _fetch(tk)
    assert not isinstance(info.value, TransientFetchError)


def test_throttled_expiry_list_raises_transient():
    tk = FakeTicker([RateLimited()])
    with pytest.raises(TransientFetchError):
        _fetch(tk)


def test_no_listed_options_is_an_empty_snapshot():
    snapshot, _ = _fetch(FakeTicker(()))
    assert snapshot.chains == []
    assert snapshot.failed_expiries == {}


def test_quote_falls_back_to_fast_info():
    tk = FakeTicker((), info=RuntimeError("info endpoint down"),
                    fast_info=SimpleNamespace(last_price=42.5, previous_close=41.0))
    quote = fetch_quote(tk)
    assert quote.spot == 42.5
    assert quote.prev_close == 41.0
    assert quote.day_high == 0.0


def test_most_actives_uses_the_screener(monkeypatch):
    monkeypatch.setattr(chain_source.yf, "screen", lambda *_a, **_k: {
        "quotes": [{"symbol": "NVDA"}, {"symbol": "INTC"}, {}],
    })
    assert fetch_most_active_symbols(5, sleep=lambda _s: None) == ["NVDA", "INTC"]


def test_most_actives_falls_back_when_the_screener_fails(monkeypatch):
    def boom(*_a, **_k):
        raise RateLimited()

    monkeypatch.setattr(chain_source.yf, "screen", boom)
    assert fetch_most_active_symbols(4, sleep=lambda _s: None) == FALLBACK_SYMBOLS[:4]


# --- the scanner on top of the source -------------------------------------------------


def test_scanner_marks_a_throttled_ticker_rate_limited(monkeypatch):
    from scripts import flow_scanner

    def throttled(ticker, expirations):
        raise TransientFetchError(f"Option expiries for {ticker}: Too Many Requests")

    monkeypatch.setattr(flow_scanner, "fetch_option_chain", throttled)
    report = flow_scanner.fetch_ticker_report("AAPL")
    assert report.error_kind == "rate_limited"
    payload = json.loads(flow_scanner.reports_to_json([report]))["reports"][0]
    assert payload["error_kind"] == "rate_limited"


def test_scanner_marks_other_failures_as_errors(monkeypatch):
    from scripts import flow_scanner

    def broken(ticker, expirations):
        raise DataFetchError("no such symbol")

    monkeypatch.setattr(flow_scanner, "fetch_option_chain", broken)
    assert flow_scanner.fetch_ticker_report("ZZZZ").error_kind == "error"


def test_scanner_keeps_a_partial_chain_and_says_what_is_missing(monkeypatch):
    from scripts import flow_scanner

    snapshot = ChainSnapshot(
        ticker="AAPL",
        quote=Quote(spot=100.0),
        chains=[ExpiryChain(date(2026, 9, 25), _frame(100), _frame(95))],
        failed_expiries={"2026-09-18": "Too Many Requests"},
    )
    monkeypatch.setattr(flow_scanner, "fetch_option_chain", lambda *_a: snapshot)
    report = flow_scanner.fetch_ticker_report("AAPL")
    assert report.error is None
    assert len(report.contracts) == 2
    payload = json.loads(flow_scanner.reports_to_json([report]))["reports"][0]
    assert payload["failed_expiries"] == {"2026-09-18": "Too Many Requests"}
