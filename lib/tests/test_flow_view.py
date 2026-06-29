"""Tests for Flow Scanner glossary and Dash view rendering."""

from __future__ import annotations

from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.flow_glossary import (
    FLAG_DEFINITIONS,
    FLAG_KINDS,
    interpretive_banner,
    score_breakdown,
)
from lib.dash.flow_view import render_flow_reports, render_ticker_card


def _sample_report(**overrides):
    base = {
        "ticker": "NVDA",
        "spot": 205.19,
        "prev_close": 204.87,
        "day_low": 203.44,
        "day_high": 207.07,
        "wk52_low": 142.03,
        "wk52_high": 236.54,
        "pc_vol_ratio": 0.70,
        "pc_oi_ratio": 0.85,
        "call_pct": 58.8,
        "put_pct": 41.2,
        "unusual_score": 756,
        "error": None,
        "top_call_strikes": [[210.0, 55471]],
        "top_put_strikes": [[200.0, 12000]],
        "flags": [{"kind": "unusual", "message": "C 210 vol>5000"}],
        "contracts": [{
            "strike": 210.0,
            "cp": "C",
            "last": 4.10,
            "bid": 4.05,
            "ask": 4.15,
            "volume": 55471,
            "open_interest": 5000,
            "iv": 0.315,
            "premium": 2274311.0,
            "expiry": "2026-06-20",
            "is_weekly": True,
            "is_otm": True,
            "flags": [
                {"kind": "unusual", "message": "C 210 vol>5000"},
                {"kind": "block_premium", "message": "premium $2,274,311"},
            ],
        }],
    }
    base.update(overrides)
    return base


def test_glossary_covers_all_flag_kinds():
    assert FLAG_KINDS == frozenset(FLAG_DEFINITIONS)
    for kind in ("unusual", "high_unusual", "block_premium", "repeat_call"):
        assert kind in FLAG_DEFINITIONS
        assert FLAG_DEFINITIONS[kind]["label"]
        assert FLAG_DEFINITIONS[kind]["long"]


def test_score_breakdown_formula():
    report = _sample_report(flags=[
        {"kind": "high_unusual", "message": "a"},
        {"kind": "high_unusual", "message": "b"},
        {"kind": "block_premium", "message": "c"},
        {"kind": "unusual", "message": "d"},
        {"kind": "repeat_call", "message": "e"},
    ], unusual_score=25)
    text = score_breakdown(report)
    assert "2 HU × 5" in text or "2 HU" in text
    assert "1 B × 3" in text or "1 B" in text
    assert "1 U × 2" in text or "1 U" in text
    assert "1 RC × 10" in text or "1 RC" in text
    assert "= 25" in text


def test_interpretive_banner_repeat_call():
    report = _sample_report(flags=[{"kind": "repeat_call", "message": "3 strikes"}])
    msg = interpretive_banner(report)
    assert msg is not None
    assert "bullish" in msg.lower()


def test_interpretive_banner_high_put_volume():
    report = _sample_report(pc_vol_ratio=1.5, flags=[])
    msg = interpretive_banner(report)
    assert msg is not None
    assert "put" in msg.lower()


def test_interpretive_banner_block_premium_dominant():
    report = _sample_report(flags=[
        {"kind": "block_premium", "message": "a"},
        {"kind": "block_premium", "message": "b"},
    ])
    msg = interpretive_banner(report)
    assert msg is not None
    assert "institutional" in msg.lower()


def test_render_ticker_card_returns_div_with_table():
    theme = get_theme(DEFAULT_THEME)
    card = render_ticker_card(_sample_report(), theme, index=0)
    assert card.__class__.__name__ == "Div"
    serialized = str(card)
    assert "NVDA" in serialized
    assert "flow-table-0-NVDA" in serialized


def test_render_flow_reports_composes_summary_and_cards():
    theme = get_theme(DEFAULT_THEME)
    payload = {"generated_at": "2026-06-14T12:00:00", "reports": [_sample_report()]}
    root = render_flow_reports(payload, theme)
    serialized = str(root)
    assert "Tickers: 1" in serialized
    assert "Educational/research use only" in serialized
