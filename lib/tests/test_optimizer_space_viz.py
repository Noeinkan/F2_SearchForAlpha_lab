"""Unit tests for Optimizer Grid Search visual builders."""

from __future__ import annotations

import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.dash.dash_config import get_theme
from lib.dash.optimizer_space_viz import (
    build_combo_estimate_card,
    build_param_landscape_figure,
    build_param_range_figure,
)


@pytest.fixture
def theme():
    return get_theme("bloomberg")


def test_combo_estimate_within_cap(theme):
    card = build_combo_estimate_card(12, 250, theme, space_keys=["a", "b"])
    html = str(card)
    assert "12" in html or "12," in html
    assert "within cap" in html
    assert "sfa-grid-estimate-ok" in html


def test_combo_estimate_over_cap(theme):
    card = build_combo_estimate_card(900, 250, theme)
    html = str(card)
    assert "over cap" in html
    assert "sfa-grid-estimate-over" in html


def test_param_range_figure_has_traces(theme):
    space = {
        "rsi_window": {"type": "int", "low": 5, "high": 30, "step": 5},
        "stop_mode": {"type": "categorical", "choices": ["percent", "atr"]},
    }
    fig = build_param_range_figure(space, theme)
    assert len(fig.data) >= 2
    assert fig.layout.height >= 160


def test_param_range_figure_empty(theme):
    fig = build_param_range_figure({}, theme)
    assert fig.layout.annotations


def test_param_landscape_1d_bar(theme):
    trials = [
        {"index": 0, "params": {"rsi_window": 5}, "value": 0.1},
        {"index": 1, "params": {"rsi_window": 10}, "value": 0.4},
        {"index": 2, "params": {"rsi_window": 15}, "value": 0.2},
    ]
    fig = build_param_landscape_figure(trials, ["rsi_window"], "sortino", theme)
    assert fig.data[0].type == "bar"


def test_param_landscape_2d_heatmap(theme):
    trials = []
    for x in (5, 10):
        for y in (0.03, 0.05):
            trials.append({
                "index": len(trials),
                "params": {"rsi_window": x, "trailing_stop_loss": y},
                "value": float(x) * y,
            })
    fig = build_param_landscape_figure(
        trials, ["rsi_window", "trailing_stop_loss"], "sharpe", theme
    )
    assert fig.data[0].type == "heatmap"


def test_param_landscape_fallback_scatter(theme):
    trials = [
        {"index": 0, "params": {"mode": "a"}, "value": 0.1},
        {"index": 1, "params": {"mode": "b"}, "value": 0.5},
    ]
    fig = build_param_landscape_figure(trials, ["mode"], "sortino", theme)
    assert any(t.mode and "markers" in str(t.mode) for t in fig.data)
