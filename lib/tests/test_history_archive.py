"""Bulk option-history archive, with ThetaData faked."""

from __future__ import annotations

from datetime import date

import pytest

from lib.dash import flow_history, flow_store
from lib.options import history_archive, theta_history


@pytest.fixture
def archive(tmp_path, monkeypatch):
    monkeypatch.setattr(history_archive, "ARCHIVE_DIR", tmp_path / "option-history")
    monkeypatch.setattr(flow_store, "FLOW_DIR", tmp_path / "flow")
    monkeypatch.setattr(flow_history, "HISTORY_DIR", tmp_path / "flow-history")
    return tmp_path


def _rows(symbol, start, end, **_):
    days = [d for d in ("2026-03-30", "2026-03-31", "2026-04-01", "2026-04-02")
            if start.isoformat() <= d <= end.isoformat()]
    return [{"date": d, "observed_at": f"{d}T21:15:00+00:00", "expiry": "2026-04-17", "cp": cp,
             "strike": 400.0, "bid": 10.0 + i, "ask": 10.5 + i, "close": None, "volume": 5.0}
            for i, d in enumerate(days) for cp in ("C", "P")]


def test_month_ranges_and_symbols():
    assert history_archive.month_ranges(date(2026, 3, 30), date(2026, 4, 2)) == [
        ("2026-03", date(2026, 3, 30), date(2026, 3, 31)), ("2026-04", date(2026, 4, 1), date(2026, 4, 2))]
    assert history_archive.theta_symbol("brk-b") == "BRK.B"


def test_download_writes_months_skips_final_ones_and_feeds_the_chain(archive):
    calls = []

    def fetch(symbol, start, end, **kw):
        calls.append((symbol, start, end))
        return _rows(symbol, start, end)

    stock = lambda symbol, start, end: {"2026-03-31": 395.0, "2026-04-01": 401.0}
    today = date(2026, 6, 1)
    result = history_archive.download_ticker("TSLA", date(2026, 3, 30), date(2026, 4, 2), today=today,
                                             fetch=fetch, fetch_stock=stock)
    assert (result.months_fetched, result.rows) == (2, 8)
    again = history_archive.download_ticker("TSLA", date(2026, 3, 30), date(2026, 4, 2), today=today,
                                            fetch=fetch, fetch_stock=stock)
    assert (again.months_fetched, again.months_skipped, len(calls)) == (0, 2, 2)

    chain = history_archive.chain_on("TSLA", date(2026, 3, 31))
    assert len(chain) == 2 and chain[0]["bid"] == 11.0 and chain[0]["multiplier"] == 100
    history = history_archive.contract_history("TSLA", "2026-04-17", "C", 400.0, date(2026, 3, 30), date(2026, 4, 2))
    assert [r["date"] for r in history] == ["2026-03-30", "2026-03-31", "2026-04-01", "2026-04-02"]
    assert history_archive.contract_history("TSLA", "2026-04-17", "C", 400.0, date(2026, 2, 27), date(2026, 3, 31)) is None
    assert history_archive.status() == [{"symbol": "TSLA", "months": 2, "first": "2026-03", "last": "2026-04"}]

    # The dashboard reads the archive instead of calling the terminal.
    def refuse(*_a, **_k):
        raise AssertionError("terminal called")

    record_fetch = theta_history.option_eod
    try:
        theta_history.option_eod = refuse
        record = flow_history.load_chain("TSLA", "2026-03-31", today=today)
    finally:
        theta_history.option_eod = record_fetch
    assert record["underlying"] == 395.0 and len(record["contracts"]) == 2


def test_too_large_month_is_split(archive):
    def fetch(symbol, start, end, **_):
        if (end - start).days > 1:
            raise theta_history.ThetaTooLarge("too big")
        return _rows(symbol, start, end)

    result = history_archive.download_ticker("TSLA", date(2026, 3, 30), date(2026, 4, 2), today=date(2026, 6, 1),
                                             fetch=fetch, fetch_stock=lambda *a: {})
    assert result.rows == 8


def test_outage_stops_the_run_and_bad_symbol_does_not(archive):
    def fetch(symbol, start, end, **_):
        if symbol == "BAD":
            raise theta_history.DataFetchError("refused")
        if symbol == "DOWN":
            raise theta_history.ThetaUnavailable("not running")
        return _rows(symbol, start, end)

    summary = history_archive.download(["BAD", "AAPL", "DOWN", "MSFT"], date(2026, 3, 30), date(2026, 3, 31),
                                       today=date(2026, 6, 1), fetch=fetch, fetch_stock=lambda *a: {})
    payload = summary.as_dict()
    assert payload["failed"] == ["BAD"] and summary.stopped == "not running"
    assert [t["symbol"] for t in payload["tickers"]] == ["BAD", "AAPL"]
