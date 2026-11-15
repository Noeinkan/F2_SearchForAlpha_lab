from __future__ import annotations

import pytest

from lib.dash import flow_paper, flow_store
from lib.dash.flow_dates import display_date, localize_html_text
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


def test_multi_contract_position_scales_cost_and_pnl(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_store, "FLOW_DIR", tmp_path / "flow")
    flow_paper.add_snapshot(_snapshot("2026-11-16T10:00:00Z"))
    first = flow_paper.load("TEST")["snapshots"][0]
    key = "2026-11-20|C|100"
    p = flow_paper.buy("TEST", first, key, fee=0.5, quantity=3)
    assert p["quantity"] == 3
    assert p["entry_fee"] == 1.5
    assert p["max_loss"] == 631.5            # (2.10 × 100 + 0.50) × 3
    assert flow_paper.break_even(p) == pytest.approx(102.105)  # per-share cost unchanged by size
    assert flow_paper.valuation(p, 1.9) == -61.5
    assert flow_paper.expiry_pnl(p, 105) == 868.5
    for bad in (0, 101, 1.5, True):
        with pytest.raises(ValueError, match="1–100 contracts"):
            flow_paper.buy("TEST", first, key, quantity=bad)
    flow_paper.add_snapshot(_snapshot("2026-11-17T10:00:00Z", bid=3))
    second = flow_paper.load("TEST")["snapshots"][1]
    closed = flow_paper.close("TEST", p["id"], second, fee=0.5)
    assert closed["exit_fee"] == 1.5
    assert closed["pnl"] == 267.0             # (3 − 2.1) × 300 − 1.5 − 1.5


def test_legacy_position_without_quantity_counts_as_one():
    legacy = {"cp": "C", "strike": 100, "entry_ask": 2.1, "multiplier": 100,
              "entry_fee": 0.65, "max_loss": 210.65}
    assert flow_paper.valuation(legacy, 1.9) == -20.65
    assert flow_paper.break_even(legacy) == pytest.approx(102.1065)


def test_order_ticket_quantity_and_summary():
    from lib.dash.callbacks.flow_paper_ui import order_quantity, order_summary
    assert order_quantity(5) == 5 and order_quantity(5.0) == 5
    assert [order_quantity(v) for v in (None, 0, 101, 2.5, True, "3")] == [None] * 6
    contract = {"cp": "C", "strike": 100, "ask": 2.1, "multiplier": 100}
    text = str(order_summary(contract, 3, 0.5))
    assert "$631.50" in text and "$102.11" in text and "Unlimited" in text


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


def test_paper_strategy_uses_recorded_quotes_and_can_be_closed_or_deleted(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_store, "FLOW_DIR", tmp_path / "flow")
    contracts = [
        {"expiry": "2026-11-20", "cp": cp, "strike": strike, "ask": premium, "bid": premium,
         "volume": 1, "open_interest": 1}
        for cp, strike, premium in (("P", 50, 2.55), ("C", 50, 2.4), ("C", 55, 0.8), ("P", 45, 0.85))
    ]
    first = {"ticker": "TEST", "observed_at": "2026-11-16T10:00:00Z", "underlying": 50,
             "contracts": contracts}
    flow_paper.add_snapshot(first)
    snap = flow_paper.load("TEST")["snapshots"][0]
    selections = [
        {"key": flow_paper.contract_key("2026-11-20", cp, strike), "side": side, "qty": 5}
        for cp, strike, side in (("P", 50, "sell"), ("C", 50, "sell"),
                                 ("C", 55, "buy"), ("P", 45, "buy"))
    ]
    strategy = flow_paper.open_strategy("TEST", snap, selections, fee_per_contract=0.54)
    assert strategy["entry_cashflow"] == pytest.approx(1639.2)
    assert flow_paper.strategy_expiry_pnl(strategy, 40) == pytest.approx(-860.8)
    assert flow_paper.strategy_expiry_pnl(strategy, 50) == pytest.approx(1639.2)
    assert flow_paper.strategy_expiry_pnl(strategy, 60) == pytest.approx(-860.8)
    with pytest.raises(ValueError, match="later observation"):
        flow_paper.close_strategy("TEST", strategy["id"], snap)
    second = {**first, "observed_at": "2026-11-17T10:00:00Z"}
    flow_paper.add_snapshot(second)
    newer = flow_paper.load("TEST")["snapshots"][1]
    assert flow_paper.strategy_valuation(strategy, newer) == pytest.approx(-10.8)
    closed = flow_paper.close_strategy("TEST", strategy["id"], newer, fee_per_contract=0.54)
    assert closed["pnl"] == pytest.approx(-21.6)
    flow_paper.delete_strategy("TEST", strategy["id"])
    assert flow_paper.load("TEST")["strategies"] == []
    assert len(flow_paper.load("TEST")["snapshots"]) == 2
    another = flow_paper.open_strategy("TEST", snap, selections, fee_per_contract=0.54)
    with pytest.raises(ValueError, match="predates expiry"):
        flow_paper.settle_strategy("TEST", another["id"], 50, "exchange", "2026-11-19T21:00:00Z")
    settled = flow_paper.settle_strategy("TEST", another["id"], 50, "exchange", "2026-11-20T21:00:00Z")
    assert settled["pnl"] == pytest.approx(1639.2)
    flow_paper.delete_strategy("TEST", another["id"])


def test_delete_paper_purchase_preserves_snapshots(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_store, "FLOW_DIR", tmp_path / "flow")
    flow_paper.add_snapshot(_snapshot("2026-11-16T10:00:00Z"))
    snap = flow_paper.load("TEST")["snapshots"][0]
    p = flow_paper.buy("TEST", snap, "2026-11-20|C|100")
    flow_paper.delete_position("TEST", p["id"])
    assert flow_paper.load("TEST")["positions"] == []
    assert len(flow_paper.load("TEST")["snapshots"]) == 1
    with pytest.raises(ValueError, match="not found"):
        flow_paper.delete_position("TEST", p["id"])


def test_paper_entry_uses_recorded_contract_multiplier(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_store, "FLOW_DIR", tmp_path / "flow")
    raw = _snapshot("2026-11-16T10:00:00Z")
    raw["contracts"][0]["multiplier"] = 50
    flow_paper.add_snapshot(raw)
    snap = flow_paper.load("TEST")["snapshots"][0]
    key = "2026-11-20|C|100"
    assert snap["contracts"][0]["multiplier"] == 50
    single = flow_paper.buy("TEST", snap, key, fee=0.54)
    assert single["max_loss"] == pytest.approx(105.54)
    strategy = flow_paper.open_strategy("TEST", snap, [{"key": key, "side": "buy", "qty": 2}], fee_per_contract=0.54)
    assert strategy["entry_cashflow"] == pytest.approx(-211.08)
    short = flow_paper.open_strategy("TEST", snap, [{"key": key, "side": "sell", "qty": 2}], fee_per_contract=0.54)
    assert short["entry_cashflow"] == pytest.approx(188.92)


def test_flow_dates_are_european_in_display_only():
    assert display_date("2026-11-20") == "20/11/2026"
    assert display_date("2026-11-20T21:00:00Z", time=True) == "20/11/2026 21:00 UTC"
    assert contract_label({"cp": "P", "strike": 95.0, "expiry": "2026-11-20"}) == "Put 95 · expires 20/11/2026"
    assert localize_html_text('<td data-expiry="2026-11-20">2026-11-20</td>') == '<td data-expiry="2026-11-20">20/11/2026</td>'
