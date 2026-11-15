from __future__ import annotations

import pytest

from lib.dash import flow_paper, flow_store
from lib.dash.flow_dates import display_date
from lib.dash.flow_paper_view import contract_label


def _snapshot(stamp, *, ask=2.1, bid=1.9):
    return {"ticker": "TEST", "observed_at": stamp, "underlying": 101,
            "contracts": [{"expiry": "2026-11-20", "cp": "C", "strike": 100,
                           "ask": ask, "bid": bid, "volume": 10, "open_interest": 20}]}


def test_archived_quotes_and_paper_position(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_store, "FLOW_DIR", tmp_path / "flow")
    assert flow_paper.add_snapshot(_snapshot("2026-11-16T10:00:00Z"))
    assert not flow_paper.add_snapshot(_snapshot("2026-11-16T10:00:00Z"))
    first = flow_paper.load("TEST")["snapshots"][0]
    key = "2026-11-20|C|100"
    p = flow_paper.buy("TEST", first, key, fee=0.65)
    assert p["entry_ask"] == 2.1
    assert p["max_loss"] == 210.65
    assert flow_paper.break_even(p) == pytest.approx(102.1065)
    assert flow_paper.valuation(p, 1.9) == -20.65
    assert flow_paper.expiry_pnl(p, 105) == 289.35
    assert flow_paper.valuation(p, None) is None
    with pytest.raises(ValueError, match="later observation"):
        flow_paper.close("TEST", p["id"], first)
    flow_paper.add_snapshot(_snapshot("2026-11-17T10:00:00Z", bid=3))
    second = flow_paper.load("TEST")["snapshots"][1]
    closed = flow_paper.close("TEST", p["id"], second, fee=0.65)
    assert closed["exit_bid"] == 3
    assert closed["pnl"] == 88.7


def test_missing_quote_and_verified_expiry(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_store, "FLOW_DIR", tmp_path / "flow")
    flow_paper.add_snapshot(_snapshot("2026-11-16T10:00:00Z", ask=None, bid=None))
    snap = flow_paper.load("TEST")["snapshots"][0]
    key = "2026-11-20|C|100"
    with pytest.raises(ValueError, match="ask is missing"):
        flow_paper.buy("TEST", snap, key)
    p = flow_paper.record_historical_entry("TEST", snap, key, 2, fee=1)
    with pytest.raises(ValueError, match="source is required"):
        flow_paper.settle("TEST", p["id"], 103, "", "2026-11-20T21:00:00Z")
    with pytest.raises(ValueError, match="predates expiry"):
        flow_paper.settle("TEST", p["id"], 103, "exchange", "2026-11-19T21:00:00Z")
    settled = flow_paper.settle("TEST", p["id"], 103, "exchange", "2026-11-20T21:00:00Z")
    assert settled["pnl"] == 99


def test_put_expiry_payoff(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_store, "FLOW_DIR", tmp_path / "flow")
    snap = _snapshot("2026-11-16T10:00:00Z")
    snap["contracts"][0]["cp"] = "P"
    flow_paper.add_snapshot(snap)
    observed = flow_paper.load("TEST")["snapshots"][0]
    p = flow_paper.buy("TEST", observed, "2026-11-20|P|100", fee=1)
    assert flow_paper.break_even(p) == pytest.approx(97.89)
    assert flow_paper.expiry_pnl(p, 95) == 289
    assert flow_paper.expiry_pnl(p, 105) == -211


def test_flow_dates_are_european_in_display_only():
    assert display_date("2026-11-20") == "20/11/2026"
    assert display_date("2026-11-20T21:00:00Z", time=True) == "20/11/2026 21:00 UTC"
    assert contract_label({"cp": "P", "strike": 95.0, "expiry": "2026-11-20"}) == "Put 95 · expires 20/11/2026"
