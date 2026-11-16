"""Tests for Robinhood-style Flow option chain pivot + panel."""

from __future__ import annotations

import json
from datetime import date

from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.flow_chain import (
    atm_strike_index,
    build_chain_table,
    default_chain_expiry,
    expiry_option_label,
    filter_chain_rows,
    flag_reasons,
    render_chain_panel,
    render_expiry_navigation,
    select_chain_rows,
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


def _side(volume=0, oi=0, flagged=False):
    return {"last": 1.0, "bid": 0.9, "ask": 1.1, "volume": volume,
            "open_interest": oi, "iv": 0.3, "flagged": flagged}


def test_select_chain_rows_drops_dead_strikes_and_windows_around_spot():
    rows = [{"strike": float(s), "call": _side(volume=1), "put": None} for s in range(50, 151, 5)]
    rows.append({"strike": 200.0, "call": _side(), "put": _side()})  # a row of dashes
    assert len(select_chain_rows(rows, view="all", spot=100.0)) == 21
    near = select_chain_rows(rows, view="near", spot=101.0, near=2)
    assert [r["strike"] for r in near] == [90.0, 95.0, 100.0, 105.0, 110.0]
    flagged = select_chain_rows(
        [*rows, {"strike": 300.0, "call": _side(flagged=True), "put": None}], view="flagged", spot=100.0
    )
    assert [r["strike"] for r in flagged] == [300.0]


def test_default_expiry_skips_the_last_week_and_labels_say_days_and_flags():
    chains = {"2026-11-16": [], "2026-11-20": [], "2026-11-27": [{"strike": 1.0, "call": _side(flagged=True)}]}
    today = date(2026, 11, 15)
    assert default_chain_expiry(chains, today=today) == "2026-11-27"
    # Nothing a week out: the furthest listed, not tomorrow's.
    assert default_chain_expiry({"2026-11-16": [], "2026-11-18": [], "2026-11-20": []}, today=today) == "2026-11-20"
    assert expiry_option_label("2026-11-27", chains["2026-11-27"], today=today) == "27 Nov · 12d"


def test_expiry_navigation_shows_exact_horizon_dates_and_available_months():
    chains = {key: [] for key in ("2026-11-16", "2026-11-18", "2026-11-20",
                                    "2026-11-27", "2026-12-18", "2027-02-19",
                                    "2027-05-21", "2027-11-19")}
    nav = str(render_expiry_navigation(chains, "2026-11-20", today=date(2026, 11, 16)))
    assert "Next 7 days" in nav and "Horizon" in nav
    assert "data-expiry='2026-11-27'" in nav
    assert "data-expiry='2027-11-19'" in nav
    assert "Expiry: 20/11/2026" in nav
    assert "data-month='2027-11'" in nav
    assert "2026-11-27" not in str(render_expiry_navigation(
        {"2026-11-16": []}, "2026-11-16", today=date(2026, 11, 16)))


def test_flagged_cells_carry_the_reason_on_hover():
    report = {
        "contracts": [{
            "strike": 105.0, "cp": "C", "expiry": "2026-06-20",
            "flags": [{"kind": "unusual", "message": "vol 500 > OI 50"}],
        }],
    }
    reasons = flag_reasons(report, "2026-06-20")
    assert reasons == {(105.0, "C"): "Unusual: vol 500 > OI 50"}
    assert flag_reasons(report, "2026-06-27") == {}
    table = build_chain_table(
        [{"strike": 105.0, "call": _side(volume=500, oi=50, flagged=True), "put": None}],
        spot=100.0, theme=get_theme(DEFAULT_THEME), reasons=reasons,
    )
    assert "vol 500 > OI 50" in str(table)


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


def test_chain_asks_offer_contract_preview_and_missing_asks_do_not():
    rows = [{
        "strike": 390.0,
        "call": {**_side(volume=1), "ask": 10.15},
        "put": {**_side(volume=1), "ask": 8.25, "multiplier": 50},
    }, {
        "strike": 395.0,
        "call": {**_side(volume=1), "ask": None},
        "put": None,
    }]
    table = build_chain_table(rows, spot=391.0, theme=get_theme(DEFAULT_THEME))
    blob = str(table)
    assert blob.count("sfa-flow-chain-price sfa-flow-chain-quote'") == 2
    assert blob.count("className='sfa-flow-chain-price'") == 3
    assert "data-field='bid'" in blob and "data-field='ask'" in blob
    assert "data-premium='10.15'" in blob
    assert "data-multiplier='100'" in blob
    assert "data-multiplier='50'" in blob
    assert "data-cp='C'" in blob and "data-cp='P'" in blob
    report = {"ticker": "TSLA", "spot": 391.0, "option_chains": {"2026-11-20": rows}}
    body = str(table_from_report(report, expiry="2026-11-20", theme=get_theme(DEFAULT_THEME)))
    # The payoff preview lives in the quote popup; the strategy in the Flow strategy panel.
    assert "sfa-flow-chain-preview" not in body


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
    assert "2 weeks" in blob
    assert "12 months" in blob
    assert "Month / year" in blob
    assert "flow-chain-side" in blob
    assert "Both" in blob
    assert "Flagged only" in blob
    assert "Near spot" in blob
    assert "sfa-flow-chain-key" in blob
    assert "sfa-flow-strategy" not in blob  # one strategy panel per page, not per chain

    body = table_from_report(report, expiry="2026-06-20", theme=theme, flagged_only=True)
    assert "sfa-flow-chain-table" in str(body)
    assert "data-strike='100.0'" in str(body)


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
