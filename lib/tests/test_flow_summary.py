"""Plain-language Flow card summary: score, mix, ranges, top strikes."""

from __future__ import annotations

from lib.dash.flow_summary import render_flow_mix, render_ranges, render_score_row, render_top_strikes


def test_score_row_spells_out_the_flag_codes():
    report = {
        "unusual_score": 882,
        "flags": [{"kind": "high_unusual"}] * 27 + [{"kind": "block_premium"}] * 65,
    }
    text = str(render_score_row(report))
    assert "882" in text
    assert "high unusual" in text and "block premium" in text
    assert "×5" in text and "×3" in text
    assert render_score_row({"flags": []}) is None


def test_top_strikes_show_distance_from_spot_and_moneyness():
    report = {"spot": 400.0, "top_call_strikes": [[420.0, 1000], [380.0, 500]], "top_put_strikes": [[360.0, 800]]}
    text = str(render_top_strikes(report))
    assert "+5.0% · OTM" in text   # call above spot
    assert "-5.0% · ITM" in text   # call below spot
    assert "-10.0% · OTM" in text  # put below spot
    assert "1,000" in text
    assert render_top_strikes({"spot": 1.0}) is None
    # One row per strike, volumes summed across expiries.
    merged = str(render_top_strikes({"spot": 400.0, "top_call_strikes": [[410.0, 100], [410.0, 50]]}))
    assert merged.count("$410") == 1 and "150" in merged


def test_mix_carries_the_put_call_ratio_and_ranges_mark_spot():
    mix = str(render_flow_mix({"call_pct": 50.5, "put_pct": 49.5, "pc_vol_ratio": 0.98}))
    assert "Calls 50.5%" in mix and "P/C 0.98" in mix
    ranges = str(render_ranges({"spot": 390.0, "day_low": 385.0, "day_high": 405.0,
                                "wk52_low": 297.0, "wk52_high": 499.0}))
    assert "52-week" in ranges and "sfa-flow-range-dot" in ranges
    assert render_ranges({"spot": 1.0}) is None
