"""Tests for Flow Scanner Net GEX chart panel."""

from __future__ import annotations

import json
from datetime import date

from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.flow_glossary import GEX_PANEL, LEARN_SECTIONS, TERM_DEFINITIONS
from lib.dash.flow_gex import (
    build_gex_figure,
    default_gex_expiry,
    figure_from_gex_report,
    render_gex_panel,
)
from lib.dash.flow_view import render_ticker_card
from lib.options.greeks import ALL_EXPIRIES_KEY, build_gex_ladders
from scripts.flow_scanner import Contract, TickerReport, UnusualFlag, compute_metrics, reports_to_json


def _contracts() -> list[Contract]:
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


def test_glossary_gex_terms_and_learn():
    for key in (
        "gex",
        "net_gex",
        "dex",
        "gex_profile",
        "dex_profile",
        "call_resistance",
        "put_support",
        "hvl",
        "estimated_greeks",
    ):
        assert key in TERM_DEFINITIONS
        assert TERM_DEFINITIONS[key]
    assert GEX_PANEL["title"]
    assert GEX_PANEL["caption"]
    titles = {s["title"] for s in LEARN_SECTIONS}
    assert "How to read Net GEX" in titles


def test_compute_metrics_fills_gex_ladders():
    report = TickerReport(
        ticker="TEST",
        spot=100.0,
        prev_close=99.0,
        day_low=98.0,
        day_high=101.0,
        wk52_low=50.0,
        wk52_high=150.0,
        contracts=_contracts(),
        flags=[],
    )
    compute_metrics(report)
    assert "2026-06-20" in report.gex_ladders
    assert ALL_EXPIRIES_KEY in report.gex_ladders
    meta = report.gex_meta[ALL_EXPIRIES_KEY]
    assert "call_resistance" in meta
    assert "put_support" in meta
    assert "hvl" in meta
    assert "net_gex_total" in meta


def test_reports_to_json_includes_gex():
    contracts = _contracts()
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
    assert "gex_ladders" in row
    assert "gex_meta" in row
    assert ALL_EXPIRIES_KEY in row["gex_ladders"]


def test_build_gex_figure_has_bars_and_profiles():
    theme = get_theme(DEFAULT_THEME)
    ladders, meta = build_gex_ladders(_contracts(), spot=100.0, as_of=date(2026, 6, 1))
    fig = build_gex_figure(
        ladders[ALL_EXPIRIES_KEY],
        spot=100.0,
        meta=meta[ALL_EXPIRIES_KEY],
        theme=theme,
    )
    names = {t.name for t in fig.data}
    assert "Positive GEX" in names
    assert "Negative GEX" in names
    assert "GEX Profile" in names
    assert "DEX Profile" in names


def test_default_gex_expiry_prefers_all():
    assert default_gex_expiry({ALL_EXPIRIES_KEY: [], "2026-06-20": []}) == ALL_EXPIRIES_KEY
    assert default_gex_expiry({"2026-07-01": [], "2026-06-20": []}) == "2026-06-20"
    assert default_gex_expiry({}) is None


def test_render_gex_panel_and_ticker_card():
    theme = get_theme(DEFAULT_THEME)
    ladders, meta = build_gex_ladders(_contracts(), spot=100.0, as_of=date(2026, 6, 1))
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
        "unusual_score": 0,
        "top_call_strikes": [],
        "top_put_strikes": [],
        "flags": [],
        "contracts": [],
        "gex_ladders": ladders,
        "gex_meta": meta,
        "strike_ladders": {},
        "inventory_meta": {},
    }
    panel = render_gex_panel(report, theme)
    assert panel is not None
    blob = str(panel)
    assert "flow-gex-graph" in blob or GEX_PANEL["title"] in blob
    assert "sfa-flow-diagram-frame" in blob
    assert "flow-fullscreen-btn" in blob

    fig, caption = figure_from_gex_report(report, expiry=ALL_EXPIRIES_KEY, theme=theme)
    assert len(fig.data) >= 4
    assert "GEX" in caption or "Spot" in caption

    card = render_ticker_card(report, theme)
    assert card is not None
