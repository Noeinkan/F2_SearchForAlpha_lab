"""Tests for Flow Scanner glossary and Dash view rendering."""

from __future__ import annotations

from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.flow_glossary import (
    FLAG_DEFINITIONS,
    FLAG_KINDS,
    LEARN_SECTIONS,
    contract_signal,
    interpretive_banner,
    interpretive_insights,
    score_breakdown,
    score_parts,
    ticker_sentiment,
)
from lib.dash.flow_view import (
    _table_conditional_styles,
    render_flow_guide,
    render_flow_reports,
    render_learn_modal_content,
    render_ticker_card,
)
from lib.dash.layout.overlays import _create_flow_overlay
from lib.dash.styles import get_styles


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


def test_learn_sections_cover_beginner_topics():
    titles = {s["title"].lower() for s in LEARN_SECTIONS}
    assert any("call" in t for t in titles)
    assert any("volume" in t or "open interest" in t for t in titles)
    assert any("score" in t for t in titles)
    assert all(s["body"] for s in LEARN_SECTIONS)


def test_score_parts_and_breakdown():
    report = _sample_report(flags=[
        {"kind": "high_unusual", "message": "a"},
        {"kind": "high_unusual", "message": "b"},
        {"kind": "block_premium", "message": "c"},
        {"kind": "unusual", "message": "d"},
        {"kind": "repeat_call", "message": "e"},
    ], unusual_score=25)
    parts = score_parts(report)
    labels = {p[0] for p in parts}
    assert labels == {"HU", "B", "U", "RC"}
    text = score_breakdown(report)
    assert "2 HU × 5" in text or "2 HU" in text
    assert "1 B × 3" in text or "1 B" in text
    assert "1 U × 2" in text or "1 U" in text
    assert "1 RC × 10" in text or "1 RC" in text
    assert "= 25" in text


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


def test_ticker_sentiment_bullish():
    report = _sample_report(
        flags=[{"kind": "repeat_call", "message": "3 strikes"}],
        pc_vol_ratio=0.5,
        call_pct=70,
    )
    label, color, reason = ticker_sentiment(report)
    assert label == "Bullish"
    assert color
    assert reason


def test_ticker_sentiment_bearish():
    report = _sample_report(pc_vol_ratio=1.5, call_pct=30, flags=[])
    label, _, _ = ticker_sentiment(report)
    assert label == "Bearish"


def test_ticker_sentiment_neutral():
    report = _sample_report(
        pc_vol_ratio=0.85,
        call_pct=50,
        flags=[],
        unusual_score=0,
    )
    label, _, _ = ticker_sentiment(report)
    assert label == "Neutral"


def test_ticker_sentiment_mixed():
    report = _sample_report(
        flags=[{"kind": "repeat_call", "message": "x"}],
        pc_vol_ratio=1.5,
        call_pct=70,
    )
    label, _, _ = ticker_sentiment(report)
    assert label == "Mixed"


def test_contract_signal_block():
    contract = {"cp": "C", "is_otm": True, "is_weekly": False, "flags": [
        {"kind": "block_premium", "message": "big"},
    ]}
    label, color = contract_signal(contract)
    assert label == "Block"
    assert color == FLAG_DEFINITIONS["block_premium"]["color"]


def test_contract_signal_otm_weekly_call():
    contract = {"cp": "C", "is_otm": True, "is_weekly": True, "flags": [
        {"kind": "high_unusual", "message": "spec"},
    ]}
    label, color = contract_signal(contract)
    assert label == "Speculative"
    assert color == FLAG_DEFINITIONS["high_unusual"]["color"]


def test_contract_signal_unusual_put():
    contract = {"cp": "P", "is_otm": True, "is_weekly": False, "flags": [
        {"kind": "unusual", "message": "hedge"},
    ]}
    label, _ = contract_signal(contract)
    assert label == "Hedge"


def test_interpretive_insights_returns_categories():
    report = _sample_report(
        flags=[
            {"kind": "repeat_call", "message": "a"},
            {"kind": "block_premium", "message": "b"},
            {"kind": "block_premium", "message": "c"},
        ],
        pc_vol_ratio=0.5,
    )
    insights = interpretive_insights(report)
    categories = {cat for cat, _ in insights}
    assert "Bullish" in categories
    assert "Institutional" in categories


def test_table_styles_include_type_bg_and_vol_oi_purple():
    theme = get_theme(DEFAULT_THEME)
    styles = _table_conditional_styles(theme)
    type_c = next(
        s for s in styles
        if s.get("if", {}).get("column_id") == "type"
        and 'C' in str(s.get("if", {}).get("filter_query", ""))
    )
    assert "backgroundColor" in type_c
    assert theme["accent_green"] in type_c["backgroundColor"]

    vol_oi = next(
        s for s in styles
        if "{vol_raw} > {oi_raw}" in str(s.get("if", {}).get("filter_query", ""))
    )
    purple = theme.get("accent_purple", FLAG_DEFINITIONS["unusual"]["color"])
    assert purple in vol_oi["backgroundColor"]

    signal_block = next(
        s for s in styles
        if s.get("if", {}).get("column_id") == "signal"
        and "Block" in str(s.get("if", {}).get("filter_query", ""))
    )
    assert "backgroundColor" in signal_block


def test_render_flow_guide_has_diagram_and_legend():
    theme = get_theme(DEFAULT_THEME)
    guide = render_flow_guide(theme)
    assert guide.__class__.__name__ == "Details"
    assert guide.open is True
    serialized = str(guide)
    assert "sfa-flow-guide" in serialized
    assert "sfa-flow-diagram" in serialized
    assert "How to read this page" in serialized
    assert "OTM puts" in serialized or "OTM" in serialized


def test_render_learn_modal_content_has_sections():
    theme = get_theme(DEFAULT_THEME)
    body = render_learn_modal_content(theme)
    serialized = str(body)
    assert "sfa-flow-learn-body" in serialized
    assert "Calls vs puts" in serialized
    assert "score" in serialized.lower()


def test_render_ticker_card_returns_div_with_table():
    theme = get_theme(DEFAULT_THEME)
    card = render_ticker_card(_sample_report(), theme, index=0)
    assert card.__class__.__name__ == "Div"
    serialized = str(card)
    assert "NVDA" in serialized
    assert "flow-table-0-NVDA" in serialized


def test_render_ticker_card_has_sentiment_badge():
    theme = get_theme(DEFAULT_THEME)
    card = render_ticker_card(_sample_report(), theme, index=0)
    serialized = str(card)
    assert "sfa-flow-sentiment-badge" in serialized
    assert "BULLISH" in serialized or "NEUTRAL" in serialized or "MIXED" in serialized


def test_render_ticker_card_has_insight_list():
    theme = get_theme(DEFAULT_THEME)
    card = render_ticker_card(
        _sample_report(flags=[{"kind": "repeat_call", "message": "3"}]),
        theme,
        index=0,
    )
    serialized = str(card)
    assert "sfa-flow-insights" in serialized
    assert "sfa-flow-insight-chip" in serialized


def test_render_ticker_card_has_score_chips_and_strike_map():
    theme = get_theme(DEFAULT_THEME)
    card = render_ticker_card(_sample_report(), theme, index=0)
    serialized = str(card)
    assert "sfa-flow-score-chips" in serialized
    assert "sfa-flow-strike-map" in serialized
    assert "sfa-flow-color-legend" in serialized


def test_render_flow_reports_composes_summary_and_cards():
    theme = get_theme(DEFAULT_THEME)
    payload = {"generated_at": "2026-06-14T12:00:00", "reports": [_sample_report()]}
    root = render_flow_reports(payload, theme)
    serialized = str(root)
    assert "Tickers: 1" in serialized
    assert "Educational/research use only" in serialized
    assert "sfa-flow-guide" in serialized
    assert "How to read this page" in serialized


def test_flow_overlay_has_learn_modal_ids():
    theme = get_theme(DEFAULT_THEME)
    styles = get_styles(theme)
    overlay = _create_flow_overlay(styles, theme)
    serialized = str(overlay)
    assert "flow-learn-button" in serialized
    assert "flow-learn-modal" in serialized
    assert "flow-learn-close" in serialized
    assert "flow-glossary-button" in serialized
