"""Flow strategy panel: chain legs, what-if edits, Greeks and the paper hand-off."""

from __future__ import annotations

import pytest

from lib.dash.flow_strategy import (
    add_chain_leg, analyze, apply_edit, days_between, iv_percent, paper_selection, preset_rows,
)


def _quote(**over):
    base = {"ticker": "AMZN", "expiry": "2026-12-18", "cp": "C", "strike": 270.0, "bid": 9.8, "ask": 10.2,
            "iv": "0.31", "multiplier": 100, "spot": 266.66, "observed": "", "trade_date": ""}
    base.update(over)
    base["key"] = f"{base['expiry']}|{base['cp']}|{base['strike']:g}"
    return base


def test_chain_leg_is_a_bought_contract_at_the_ask_with_chain_iv():
    rows, context, fresh = add_chain_leg([], {}, _quote())
    assert fresh
    assert rows == [{"quantity": 1, "kind": "call", "strike": 270.0, "premium": 10.2, "iv": 31.0,
                     "key": "2026-12-18|C|270", "bid": 9.8, "ask": 10.2, "multiplier": 100}]
    assert context["ticker"] == "AMZN" and context["spot"] == 266.66


def test_chain_rules_same_expiry_observation_no_duplicates_max_four():
    rows, context, _ = add_chain_leg([], {}, _quote())
    with pytest.raises(ValueError, match="same expiry"):
        add_chain_leg(rows, context, _quote(expiry="2027-01-15", strike=280.0))
    with pytest.raises(ValueError, match="same observation"):
        add_chain_leg(rows, context, _quote(strike=280.0, observed="2026-10-01T20:00:00Z"))
    with pytest.raises(ValueError, match="already"):
        add_chain_leg(rows, context, _quote())
    for strike in (275.0, 280.0, 285.0):
        rows, context, _ = add_chain_leg(rows, context, _quote(strike=strike))
    with pytest.raises(ValueError, match="up to 4"):
        add_chain_leg(rows, context, _quote(strike=290.0))


def test_another_ticker_or_only_typed_legs_start_over():
    rows, context, _ = add_chain_leg([], {}, _quote())
    rows, context, fresh = add_chain_leg(rows, context, _quote(ticker="TSLA", strike=400.0))
    assert fresh and len(rows) == 1 and context["ticker"] == "TSLA"
    typed = [{"quantity": 1, "kind": "call", "strike": 100, "premium": 1, "iv": 20, "key": None}]
    rows, _, fresh = add_chain_leg(typed, {"ticker": "AMZN"}, _quote())
    assert fresh and [r["key"] for r in rows] == ["2026-12-18|C|270"]


def test_selling_a_chain_leg_reprices_at_bid_and_editing_strike_detaches_it():
    rows, _, _ = add_chain_leg([], {}, _quote())
    sold = apply_edit([{**rows[0], "quantity": -2}], rows)
    assert sold[0]["premium"] == 9.8 and sold[0]["key"]
    moved = apply_edit([{**rows[0], "strike": 275.0}], rows)
    assert moved[0]["key"] is None and moved[0]["premium"] == 10.2


def test_analyze_greeks_and_solved_iv():
    rows, _, _ = add_chain_leg([], {}, _quote(iv=""))
    result = analyze(rows, spot=266.66, days=33, rate_pct=5, yield_pct=0)
    assert result["net_premium"] == pytest.approx(1020)
    assert result["summary"]["break_evens"] == [280.2]
    assert result["priced"][0]["solved"] and result["priced"][0]["greeks"]["value"] == pytest.approx(10.2, abs=1e-4)
    assert 0 < result["totals"]["delta"] < 100
    assert any("solved" in note for note in result["notes"])
    with pytest.raises(ValueError, match="quantity"):
        analyze([{**rows[0], "quantity": 0.5}], spot=266.66, days=33, rate_pct=5, yield_pct=0)


def test_paper_selection_needs_chain_legs_only():
    rows, context, _ = add_chain_leg([], {}, _quote())
    rows = apply_edit([{**rows[0], "quantity": -3}], rows)
    selection = paper_selection(rows, context, 7)
    assert selection == {"ticker": "AMZN", "expiry": "2026-12-18", "nonce": 7, "source": "current",
                         "legs": [{"key": "2026-12-18|C|270", "side": "sell", "qty": 3}],
                         "trade_date": None, "observed_at": None}
    with pytest.raises(ValueError, match="option chain"):
        paper_selection(rows + [{"quantity": 1, "kind": "put", "strike": 250, "premium": 3, "key": None}],
                        context, 7)


def test_historical_leg_carries_its_observation_to_paper():
    quote = _quote(observed="2026-10-01T20:00:00Z", trade_date="2026-10-01", spot=220.0)
    rows, context, _ = add_chain_leg([], {}, quote)
    selection = paper_selection(rows, context, 1)
    assert selection["source"] == "historical" and selection["trade_date"] == "2026-10-01"


def test_helpers():
    from datetime import date
    assert iv_percent("0.315") == 31.5 and iv_percent(45) == 45 and iv_percent("") is None
    assert days_between("2026-12-18", date(2026, 11, 15)) == 33
    assert days_between("2026-11-01", date(2026, 11, 15)) == 0
    condor = preset_rows("iron_condor", spot=100, days=30, rate_pct=5, yield_pct=0)
    assert [r["quantity"] for r in condor] == [1, -1, -1, 1] and all(r["premium"] > 0 for r in condor)
