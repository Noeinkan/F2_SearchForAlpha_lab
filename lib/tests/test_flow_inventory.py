"""Tests for options inventory strike ladder + Flow inventory chart."""

from __future__ import annotations

import json
from datetime import date

from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.flow_glossary import LEARN_SECTIONS, TERM_DEFINITIONS
from lib.dash.flow_inventory import (
    build_inventory_figure,
    filter_ladder_window,
    figure_from_report,
    nearest_expiry,
    render_inventory_panel,
)
from lib.dash.flow_view import render_ticker_card
from scripts.flow_scanner import (
    Contract,
    TickerReport,
    UnusualFlag,
    aggregate_strike_ladder,
    call_put_walls,
    compute_metrics,
    max_pain_strike,
    reports_to_json,
)


def _contracts_for_ladder() -> list[Contract]:
    expiry = date(2026, 6, 20)
    rows = [
        (90.0, "P", 100, 500),
        (95.0, "P", 200, 800),
        (100.0, "P", 50, 300),
        (100.0, "C", 80, 400),
        (105.0, "C", 150, 900),
        (110.0, "C", 40, 200),
        (95.0, "C", 10, 50),
        (105.0, "P", 20, 60),
    ]
    out: list[Contract] = []
    for strike, cp, vol, oi in rows:
        out.append(
            Contract(
                ticker="TEST",
                expiry=expiry,
                strike=strike,
                cp=cp,  # type: ignore[arg-type]
                last=1.0,
                bid=0.9,
                ask=1.1,
                volume=vol,
                open_interest=oi,
                iv=0.3,
            )
        )
    return out


def test_aggregate_strike_ladder_sums_call_put():
    ladder = aggregate_strike_ladder(_contracts_for_ladder())
    by_strike = {r["strike"]: r for r in ladder}
    assert by_strike[100.0]["call_oi"] == 400
    assert by_strike[100.0]["put_oi"] == 300
    assert by_strike[100.0]["call_vol"] == 80
    assert by_strike[100.0]["put_vol"] == 50
    assert by_strike[105.0]["call_oi"] == 900
    assert sorted(r["strike"] for r in ladder) == [90.0, 95.0, 100.0, 105.0, 110.0]


def test_aggregate_handles_zero_oi_volume():
    c = Contract(
        ticker="X",
        expiry=date(2026, 1, 1),
        strike=10.0,
        cp="C",
        last=0,
        bid=0,
        ask=0,
        volume=0,
        open_interest=0,
        iv=0,
    )
    ladder = aggregate_strike_ladder([c])
    assert ladder == [{"strike": 10.0, "call_oi": 0, "put_oi": 0, "call_vol": 0, "put_vol": 0}]


def test_max_pain_and_walls():
    ladder = aggregate_strike_ladder(_contracts_for_ladder())
    cw, pw = call_put_walls(ladder)
    assert cw == 105.0
    assert pw == 95.0
    mp = max_pain_strike(ladder)
    assert mp is not None
    assert mp in {r["strike"] for r in ladder}


def test_compute_metrics_fills_strike_ladders():
    contracts = _contracts_for_ladder()
    report = TickerReport(
        ticker="TEST",
        spot=100.0,
        prev_close=99.0,
        day_low=98.0,
        day_high=101.0,
        wk52_low=50.0,
        wk52_high=150.0,
        contracts=contracts,
        flags=[],
    )
    compute_metrics(report)
    assert "2026-06-20" in report.strike_ladders
    assert len(report.strike_ladders["2026-06-20"]) == 5
    meta = report.inventory_meta["2026-06-20"]
    assert meta["call_wall"] == 105.0
    assert meta["put_wall"] == 95.0
    assert meta["max_pain"] is not None


def test_reports_to_json_includes_strike_ladders():
    contracts = _contracts_for_ladder()
    report = TickerReport(
        ticker="TEST",
        spot=100.0,
        prev_close=99.0,
        day_low=98.0,
        day_high=101.0,
        wk52_low=50.0,
        wk52_high=150.0,
        contracts=contracts,
        flags=[UnusualFlag(kind="unusual", contract=contracts[0], message="x")],
    )
    compute_metrics(report)
    payload = json.loads(reports_to_json([report], today=date(2026, 6, 14)))
    row = payload["reports"][0]
    assert "strike_ladders" in row
    assert "inventory_meta" in row
    assert "2026-06-20" in row["strike_ladders"]


def test_filter_ladder_window():
    ladder = [
        {"strike": 50.0, "call_oi": 1, "put_oi": 1, "call_vol": 0, "put_vol": 0},
        {"strike": 100.0, "call_oi": 2, "put_oi": 2, "call_vol": 0, "put_vol": 0},
        {"strike": 200.0, "call_oi": 3, "put_oi": 3, "call_vol": 0, "put_vol": 0},
    ]
    filtered = filter_ladder_window(ladder, spot=100.0, window_pct=0.12)
    strikes = [r["strike"] for r in filtered]
    assert 50.0 not in strikes
    assert 200.0 not in strikes
    assert 100.0 in strikes


def test_nearest_expiry():
    assert nearest_expiry({"2026-07-01": [], "2026-06-20": []}) == "2026-06-20"
    assert nearest_expiry({}) is None


def test_build_inventory_figure_has_call_put_traces():
    theme = get_theme(DEFAULT_THEME)
    ladder = aggregate_strike_ladder(_contracts_for_ladder())
    fig = build_inventory_figure(
        ladder,
        spot=100.0,
        meta={"max_pain": 100.0, "call_wall": 105.0, "put_wall": 95.0},
        metric="oi",
        theme=theme,
    )
    assert len(fig.data) == 2
    assert fig.data[0].name == "Puts"
    assert fig.data[1].name == "Calls"
    assert all(x <= 0 for x in fig.data[0].x)


def test_render_inventory_panel_and_ticker_card():
    theme = get_theme(DEFAULT_THEME)
    ladder = aggregate_strike_ladder(_contracts_for_ladder())
    report = {
        "ticker": "TEST",
        "spot": 100.0,
        "prev_close": 99.0,
        "day_low": 98.0,
        "day_high": 101.0,
        "wk52_low": 50.0,
        "wk52_high": 150.0,
        "pc_vol_ratio": 0.8,
        "pc_oi_ratio": 0.9,
        "call_pct": 55.0,
        "put_pct": 45.0,
        "unusual_score": 2,
        "error": None,
        "top_call_strikes": [[105.0, 150]],
        "top_put_strikes": [[95.0, 200]],
        "flags": [],
        "contracts": [],
        "strike_ladders": {"2026-06-20": ladder},
        "inventory_meta": {
            "2026-06-20": {"max_pain": 100.0, "call_wall": 105.0, "put_wall": 95.0},
        },
    }
    panel = render_inventory_panel(report, theme)
    assert panel is not None
    card = render_ticker_card(report, theme, index=0)
    blob = str(card)
    assert "flow-inv-graph" in blob or "Options inventory" in blob

    fig, caption = figure_from_report(report, expiry="2026-06-20", metric="vol", theme=theme)
    assert len(fig.data) == 2
    assert "volume" in caption.lower() or "Today" in caption


def test_glossary_inventory_terms_and_learn():
    for key in ("inventory", "call_wall", "put_wall", "max_pain", "oi_vs_volume"):
        assert key in TERM_DEFINITIONS
        assert TERM_DEFINITIONS[key]
    titles = {s["title"].lower() for s in LEARN_SECTIONS}
    assert any("inventory" in t for t in titles)
