"""Tests for OI Vanna Model (Delta Notional vs Strike) Flow chart."""

from __future__ import annotations

import json
from datetime import date

from lib.dash.dash_config import get_theme
from lib.dash.flow_glossary import LEARN_SECTIONS, TERM_DEFINITIONS, VANNA_PANEL
from lib.dash.flow_vanna import (
    build_vanna_figure,
    figure_from_vanna_report,
    render_vanna_panel,
)
from lib.dash.flow_view import render_ticker_card
from lib.options.greeks import bs_delta, build_vanna_model
from scripts.flow_scanner import Contract, TickerReport, compute_metrics, reports_to_json


def _contract(
    strike: float,
    cp: str,
    oi: int,
    *,
    expiry: date = date(2026, 6, 20),
    iv: float = 0.30,
    vol: int = 10,
) -> Contract:
    return Contract(
        ticker="TEST",
        expiry=expiry,
        strike=strike,
        cp=cp,  # type: ignore[arg-type]
        last=1.0,
        bid=0.9,
        ask=1.1,
        volume=vol,
        open_interest=oi,
        iv=iv,
    )


def _contracts() -> list[Contract]:
    e1 = date(2026, 6, 20)
    e2 = date(2026, 7, 18)
    rows = [
        (90.0, "P", 500, e1),
        (95.0, "P", 800, e1),
        (100.0, "P", 300, e1),
        (100.0, "C", 400, e1),
        (105.0, "C", 900, e1),
        (110.0, "C", 200, e1),
        (95.0, "P", 200, e2),
        (100.0, "C", 250, e2),
        (105.0, "C", 180, e2),
    ]
    return [_contract(s, cp, oi, expiry=exp) for s, cp, oi, exp in rows]


def test_bs_delta_call_atm_near_half():
    T = 30 / 365.0
    d = bs_delta(100.0, 100.0, T, 0.25, call=True)
    assert 0.45 < d < 0.55


def test_glossary_vanna_terms_and_learn():
    for key in ("vanna", "delta_notional", "vanna_flow", "dealer_hedging"):
        assert key in TERM_DEFINITIONS
        assert TERM_DEFINITIONS[key]
    assert VANNA_PANEL["title"]
    assert VANNA_PANEL["caption"]
    assert any("vanna flow" in s["title"].lower() for s in LEARN_SECTIONS)


def test_build_vanna_model_shape():
    model = build_vanna_model(_contracts(), spot=100.0, as_of=date(2026, 6, 1))
    assert "2026-06-20" in model
    assert "2026-07-18" in model
    curve = model["2026-06-20"]
    assert len(curve["strikes"]) == len(curve["delta_notional"])
    assert len(curve["strikes"]) >= 3
    # Skips zero-OI / zero-IV — all mocked have both, so notionals should move.
    assert any(abs(v) > 0 for v in curve["delta_notional"])


def test_build_vanna_model_skips_bad_contracts():
    bad = [
        _contract(100.0, "C", 0, iv=0.3),
        _contract(100.0, "P", 100, iv=0.0),
        _contract(105.0, "C", 50, iv=0.25),
    ]
    model = build_vanna_model(bad, spot=100.0, as_of=date(2026, 6, 1))
    assert "2026-06-20" in model
    # Only the last contract contributes; curve still built on eval strikes.
    assert len(model["2026-06-20"]["strikes"]) >= 1


def test_compute_metrics_fills_vanna_model():
    report = TickerReport(
        ticker="TEST",
        spot=100.0,
        prev_close=99.0,
        day_low=98.0,
        day_high=101.0,
        wk52_low=80.0,
        wk52_high=120.0,
        contracts=_contracts(),
    )
    compute_metrics(report)
    assert "2026-06-20" in report.vanna_model
    assert "delta_notional" in report.vanna_model["2026-06-20"]


def test_reports_to_json_includes_vanna_model():
    report = TickerReport(
        ticker="TEST",
        spot=100.0,
        prev_close=99.0,
        day_low=98.0,
        day_high=101.0,
        wk52_low=80.0,
        wk52_high=120.0,
        contracts=_contracts(),
    )
    compute_metrics(report)
    payload = json.loads(reports_to_json([report]))
    row = payload["reports"][0]
    assert "vanna_model" in row
    assert "2026-06-20" in row["vanna_model"]


def test_build_vanna_figure_multi_expiry():
    theme = get_theme()
    model = build_vanna_model(_contracts(), spot=100.0, as_of=date(2026, 6, 1))
    fig = build_vanna_figure(
        model,
        100.0,
        ["2026-06-20", "2026-07-18"],
        theme=theme,
    )
    assert len(fig.data) == 2


def test_render_vanna_panel_and_ticker_card():
    theme = get_theme()
    model = build_vanna_model(_contracts(), spot=100.0, as_of=date(2026, 6, 1))
    report = {
        "ticker": "TEST",
        "spot": 100.0,
        "prev_close": 99.0,
        "day_low": 98.0,
        "day_high": 101.0,
        "wk52_low": 80.0,
        "wk52_high": 120.0,
        "pc_vol_ratio": 0.8,
        "unusual_score": 0,
        "call_pct": 55.0,
        "put_pct": 45.0,
        "flags": [],
        "contracts": [],
        "top_call_strikes": [],
        "top_put_strikes": [],
        "vanna_model": model,
    }
    panel = render_vanna_panel(report, theme)
    assert panel is not None
    blob = str(panel)
    assert "flow-vanna-graph" in blob or VANNA_PANEL["title"] in blob
    assert "sfa-flow-diagram-frame" in blob
    assert "flow-fullscreen-btn" in blob

    fig, caption = figure_from_vanna_report(
        report,
        active_expiries=["2026-06-20"],
        theme=theme,
    )
    assert len(fig.data) == 1
    assert "Vanna" in caption or "delta" in caption.lower()

    card = render_ticker_card(report, theme)
    assert card is not None
