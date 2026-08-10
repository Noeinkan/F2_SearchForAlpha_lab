"""Tests for Robinhood-style Flow option chain pivot + panel."""

from __future__ import annotations

import json
from datetime import date

from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.flow_chain import (
    atm_strike_index,
    build_chain_table,
    render_chain_panel,
    table_from_report,
)
from lib.dash.flow_view import FLOW_SECTION_OPTIONS, render_ticker_detail
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
                {
                    "strike": 105.0,
                    "call": {
                        "last": 0.5,
                        "bid": 0.4,
                        "ask": 0.6,
                        "volume": 5,
                        "open_interest": 40,
                        "iv": 0.32,
                        "flagged": False,
                    },
                    "put": None,
                },
            ],
            "2026-07-18": [
                {
                    "strike": 100.0,
                    "call": {
                        "last": 2.0,
                        "bid": 1.9,
                        "ask": 2.1,
                        "volume": 1,
                        "open_interest": 10,
                        "iv": 0.27,
                        "flagged": False,
                    },
                    "put": None,
                }
            ],
        },
    }
    panel = render_chain_panel(report, theme)
    assert panel is not None
    blob = str(panel)
    assert "sfa-flow-chain" in blob
    assert "flow-chain-expiry" in blob
    assert "flow-chain-body" in blob
    assert "100" in blob
    assert "sfa-flow-chain-flagged" in blob or "flagged" in blob.lower() or "0.90" in blob

    # Expiry switch helper rebuilds body for later expiry.
    later = table_from_report(report, expiry="2026-07-18", theme=theme)
    later_blob = str(later)
    assert "2.00" in later_blob or "1.90" in later_blob


def test_build_chain_table_marks_atm_row():
    theme = get_theme(DEFAULT_THEME)
    table = build_chain_table(
        [
            {"strike": 95.0, "call": None, "put": {"bid": 1, "ask": 1.1, "iv": 0.2, "volume": 1, "open_interest": 1, "flagged": False}},
            {"strike": 100.0, "call": {"bid": 1, "ask": 1.1, "iv": 0.2, "volume": 1, "open_interest": 1, "flagged": False}, "put": None},
        ],
        spot=99.5,
        theme=theme,
    )
    assert "sfa-flow-chain-atm" in str(table)


def test_chain_tab_in_section_options_and_detail():
    assert any(o["value"] == "chain" for o in FLOW_SECTION_OPTIONS)
    labels = [o["label"] for o in FLOW_SECTION_OPTIONS]
    assert labels.index("Chain") < labels.index("GEX")
    assert labels.index("Overview") < labels.index("Chain")

    theme = get_theme(DEFAULT_THEME)
    empty = render_ticker_detail(
        {"ticker": "AAA", "spot": 10, "unusual_score": 0, "flags": [], "contracts": []},
        theme,
        section="chain",
    )
    assert "Rescan to load the option chain" in str(empty)

    detail = render_ticker_detail(
        {
            "ticker": "BBB",
            "spot": 50.0,
            "unusual_score": 1,
            "flags": [],
            "contracts": [],
            "option_chains": {
                "2026-06-20": [
                    {
                        "strike": 50.0,
                        "call": {
                            "last": 1,
                            "bid": 1,
                            "ask": 1.1,
                            "volume": 1,
                            "open_interest": 1,
                            "iv": 0.2,
                            "flagged": False,
                        },
                        "put": None,
                    }
                ]
            },
        },
        theme,
        section="chain",
    )
    assert "sfa-flow-chain" in str(detail)
    assert "Option chain" in str(detail)
