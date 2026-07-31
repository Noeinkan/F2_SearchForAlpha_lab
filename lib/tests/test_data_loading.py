"""Tests for market data auto-load on ticker selection."""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc

from lib.dash.callbacks import register_callbacks
from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.integrated_dashboard import create_dashboard_layout


def _load_data_spec(app):
    for spec in app.callback_map.values():
        inputs = spec.get("inputs", [])
        ids = {item["id"] for item in inputs}
        if {"load-data-button", "ticker-dropdown"}.issubset(ids):
            return spec
    raise AssertionError("load_data callback not found")


def test_load_data_listens_to_ticker_dropdown():
    theme = get_theme(DEFAULT_THEME)
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
    app.layout = create_dashboard_layout(theme, bootstrap=None)
    register_callbacks(app)

    spec = _load_data_spec(app)
    input_ids = [item["id"] for item in spec["inputs"]]
    state_ids = [item["id"] for item in spec.get("state", [])]

    assert input_ids == ["load-data-button", "autoload-interval", "ticker-dropdown", "bar-interval"]
    assert "ticker-dropdown" not in state_ids
    assert "user-ticker-store" not in input_ids
