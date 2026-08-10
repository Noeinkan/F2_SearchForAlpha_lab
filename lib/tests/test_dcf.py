"""Tests for the two-stage FCFE model.

The flat-growth case is pinned to a hand-computed example so any refactor that
moves the number fails loudly.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.dcf import (
    DcfAssumptions,
    build_dcf,
    cost_of_equity,
    growth_path,
    sensitivity_grid,
    two_stage_fcfe,
)


def test_cost_of_equity_is_capm():
    rate, beta = cost_of_equity(
        DcfAssumptions(risk_free=0.04, equity_risk_premium=0.05, beta=1.0)
    )
    assert rate == pytest.approx(0.09)
    assert beta == pytest.approx(1.0)


def test_beta_is_clamped_to_bounds():
    _, low = cost_of_equity(DcfAssumptions(beta=0.2, beta_floor=0.8))
    _, high = cost_of_equity(DcfAssumptions(beta=4.0, beta_cap=2.0))
    assert low == pytest.approx(0.8)
    assert high == pytest.approx(2.0)


def test_flat_two_stage_matches_hand_calculation():
    """FCFE0=1000, g1=8% flat, r=9%, g2=2.5%, 10 years."""
    result = two_stage_fcfe(1000.0, 0.08, 0.09, 0.025, years=10, fade=False)
    assert result["pv_stage1"] == pytest.approx(9_508.6, rel=1e-3)
    assert result["pv_terminal"] == pytest.approx(14_381.0, rel=1e-3)
    assert result["equity_value"] == pytest.approx(23_889.6, rel=1e-3)
    assert result["terminal_share"] == pytest.approx(0.602, abs=0.005)


def test_terminal_value_dominates():
    """The structural point: one line of algebra outweighs ten forecast years."""
    result = two_stage_fcfe(1000.0, 0.08, 0.09, 0.025, years=10, fade=False)
    assert result["pv_terminal"] > result["pv_stage1"]


def test_discount_rate_must_exceed_terminal_growth():
    with pytest.raises(ValueError, match="must exceed terminal growth"):
        two_stage_fcfe(1000.0, 0.08, 0.02, 0.025, years=10)


def test_growth_path_fades_linearly_to_terminal():
    path = growth_path(0.10, 0.02, 5, fade=True)
    assert path[0] == pytest.approx(0.10)
    assert path[-1] == pytest.approx(0.02)
    steps = np.diff(path)
    assert np.allclose(steps, steps[0])


def test_sensitivity_spans_a_wide_range():
    grid = sensitivity_grid(
        1000.0, 0.08, 0.09, 0.025, years=10, fade=False, shares=1000.0
    )
    values = [
        cell["value_per_share"] for row in grid for cell in row["cells"]
    ]
    assert min(values) == pytest.approx(18.99, abs=0.05)
    assert max(values) == pytest.approx(33.00, abs=0.05)
    # A one-point move in each soft input swings the answer by well over half.
    assert max(values) / min(values) > 1.5


def _fixture_map(fcf_values, price=20.0):
    index = list(range(2016, 2016 + len(fcf_values)))
    return {
        "fcf": {"values": pd.Series(fcf_values, index=index, dtype="float64")},
        "stock_price": {
            "values": pd.Series([price] * len(fcf_values), index=index, dtype="float64")
        },
    }


def test_build_dcf_produces_a_per_share_value():
    info = {"beta": 1.0, "sharesOutstanding": 1_000_000_000, "earningsGrowth": 0.08}
    financial_map = _fixture_map([800, 900, 950, 1000, 1050])
    result = build_dcf(info, financial_map, DcfAssumptions())
    assert result.fair_value_per_share > 0
    assert 0 < result.terminal_share < 1
    assert len(result.projections) == 10
    assert len(result.sensitivity) == 3


def test_build_dcf_rejects_negative_base_cash_flow():
    info = {"beta": 1.0, "sharesOutstanding": 1_000_000_000}
    financial_map = _fixture_map([-200, -300, -250])
    with pytest.raises(ValueError, match="not positive"):
        build_dcf(info, financial_map, DcfAssumptions())


def test_build_dcf_notes_a_clamped_beta():
    info = {"beta": 3.5, "sharesOutstanding": 1_000_000_000, "earningsGrowth": 0.06}
    result = build_dcf(info, _fixture_map([900, 950, 1000]), DcfAssumptions())
    assert any("clamped" in note for note in result.notes)
