"""Tests for Robinhood-style Flow option chain pivot + panel."""

from __future__ import annotations

import json
from datetime import date

from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.flow_chain import (
    atm_strike_index,
    build_chain_table,
    filter_chain_rows,
    render_chain_panel,
    table_from_report,
)
from lib.dash.flow_view import render_flow_reports, render_ticker_card
from scripts.flow_scanner import (
    Contract,
    TickerReport,
    UnusualFlag,
    build_option_chains,
    reports_to_json,
)


def _contract(**kwargs) -> Contract:
    base = dict(
        ticker="TEST",
        expiry=date(2026, 6, 20),
        strike=100.0,
        cp="C",
        last=1.0,
        bid=0.9,
        ask=1.1,
        volume=10,
        open_interest=100,
        iv=0.25,
    )
    base.update(kwargs)
    return Contract(**base)


def test_build_option_chains_pivots_call_put_and_flagged():
    call = _contract(cp="C", strike=100.0, volume=500)
    put = _contract(cp="P", strike=100.0, volume=20)
    other = _contract(cp="C", strike=105.0, volume=5)
    chains = build_option_chains([call, put, other], frozenset({call}))

    assert "2026-06-20" in chains
    rows = chains["2026-06-20"]
    assert [r["strike"] for r in rows] == [100.0, 105.0]

    row100 = rows[0]
    assert row100["call"]["flagged"] is True
    assert row100["call"]["bid"] == 0.9
    assert row100["put"]["flagged"] is False
    assert row100["put"]["volume"] == 20
    assert rows[1]["put"] is None
    assert rows[1]["call"]["flagged"] is False


def test_reports_to_json_includes_option_chains():
    call = _contract(cp="C", strike=210.0, volume=55471, open_interest=5000, last=4.1)
    put = _contract(cp="P", strike=200.0, volume=100, open_interest=200)
    flag = UnusualFlag(kind="unusual", contract=call, message="C 210 vol>oi")
    report = TickerReport(
        ticker="NVDA",
        spot=205.0,
        prev_close=204.0,
        day_low=203.0,
        day_high=207.0,
        wk52_low=140.0,
        wk52_high=240.0,
        contracts=[call, put],
        flags=[flag],
    )
    payload = json.loads(reports_to_json([report], today=date(2026, 6, 14)))
    chains = payload["reports"][0]["option_chains"]
    assert "2026-06-20" in chains
    strikes = {row["strike"] for row in chains["2026-06-20"]}
    assert 210.0 in strikes and 200.0 in strikes
    flagged_row = next(r for r in chains["2026-06-20"] if r["strike"] == 210.0)
    assert flagged_row["call"]["flagged"] is True


def test_atm_strike_index_nearest_spot():
    rows = [{"strike": 95.0}, {"strike": 100.0}, {"strike": 110.0}]
    assert atm_strike_index(rows, 101.0) == 1
    assert atm_strike_index([], 100.0) is None


def test_filter_chain_rows_flagged_only():
    rows = [
        {"strike": 100.0, "call": {"flagged": True}, "put": None},
        {"strike": 105.0, "call": {"flagged": False}, "put": {"flagged": False}},
    ]
    assert len(filter_chain_rows(rows, flagged_only=False)) == 2
    flagged = filter_chain_rows(rows, flagged_only=True)
    assert len(flagged) == 1
    assert flagged[0]["strike"] == 100.0


def test_build_chain_table_includes_spot_divider():
    theme = get_theme(DEFAULT_THEME)
    rows = [
        {
            "strike": 95.0,
            "call": {
                "last": 1.0, "bid": 0.9, "ask": 1.1, "volume": 10,
                "open_interest": 20, "iv": 0.3, "flagged": False,
            },
            "put": None,
        },
        {
            "strike": 105.0,
            "call": {
                "last": 0.5, "bid": 0.4, "ask": 0.6, "volume": 5,
                "open_interest": 10, "iv": 0.32, "flagged": True,
            },
            "put": None,
        },
    ]
    table = build_chain_table(rows, spot=100.0, theme=theme)
    blob = str(table)
    assert "sfa-flow-chain-spot-divider" in blob
    assert "Spot 100.00" in blob
    assert "sfa-flow-chain-flagged" in blob


def test_render_chain_panel_and_empty_state():
    theme = get_theme(DEFAULT_THEME)
    assert render_chain_panel({"ticker": "X", "spot": 10, "option_chains": {}}, theme) is None
    assert render_chain_panel({"ticker": "X", "spot": 10}, theme) is None

    report = {
        "ticker": "TEST",
        "spot": 100.0,
        "option_chains": {
            "2026-06-20": [
                {
                    "strike": 100.0,
                    "call": {
                        "last": 1.0,
                        "bid": 0.9,
                        "ask": 1.1,
                        "volume": 50,
                        "open_interest": 200,
                        "iv": 0.3,
                        "flagged": True,
                    },
                    "put": {
                        "last": 0.8,
                        "bid": 0.7,
                        "ask": 0.9,
                        "volume": 10,
                        "open_interest": 80,
                        "iv": 0.28,
                        "flagged": False,
                    },
                },
            ],
        },
    }
    panel = render_chain_panel(report, theme)
    assert panel is not None
    blob = str(panel)
    assert "sfa-flow-chain" in blob
    assert "flow-chain-expiry" in blob
    assert "Flagged only" in blob

    body = table_from_report(report, expiry="2026-06-20", theme=theme, flagged_only=True)
    assert "sfa-flow-chain-table" in str(body)


def test_ticker_card_narrative_includes_chain_before_education_order():
    theme = get_theme(DEFAULT_THEME)
    report = {
        "ticker": "TEST",
        "spot": 100.0,
        "prev_close": 99.0,
        "day_low": 98.0,
        "day_high": 101.0,
        "wk52_low": 50.0,
        "wk52_high": 150.0,
        "pc_vol_ratio": 0.5,
        "call_pct": 55.0,
        "put_pct": 45.0,
        "unusual_score": 10,
        "error": None,
        "top_call_strikes": [[105.0, 150]],
        "top_put_strikes": [[95.0, 20]],
        "flags": [{"kind": "repeat_call", "message": "3 strikes"}],
        "contracts": [{
            "strike": 105.0,
            "cp": "C",
            "last": 1.0,
            "bid": 0.9,
            "ask": 1.1,
            "volume": 200,
            "open_interest": 50,
            "iv": 0.3,
            "premium": 20000.0,
            "expiry": "2026-06-20",
            "is_weekly": False,
            "is_otm": True,
            "flags": [{"kind": "unusual", "message": "x"}],
        }],
        "option_chains": {
            "2026-06-20": [{
                "strike": 105.0,
                "call": {
                    "last": 1.0, "bid": 0.9, "ask": 1.1, "volume": 200,
                    "open_interest": 50, "iv": 0.3, "flagged": True,
                },
                "put": None,
            }],
        },
        "strike_ladders": {},
    }
    card = render_ticker_card(report, theme, index=0)
    blob = str(card)
    assert "sfa-flow-chain" in blob
    assert "sfa-flow-insights" in blob
    # Flat flagged DataTable demoted — chain is primary.
    assert "flow-table-" not in blob

    root = render_flow_reports({"generated_at": "2026-06-14T12:00:00", "reports": [report]}, theme)
    serialized = str(root)
    assert "sfa-flow-summary-strip" in serialized
    assert "sfa-flow-education" in serialized
    # Education comes after ticker card content in the composed tree.
    assert serialized.index("sfa-flow-ticker-card") < serialized.index("sfa-flow-education")
    assert "Tickers: 1" in serialized
