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


def _output_ids(spec) -> list:
    outputs = spec.get("output", [])
    if not isinstance(outputs, list):
        outputs = [outputs]
    ids = []
    for item in outputs:
        if isinstance(item, dict):
            ids.append(item.get("id"))
        else:
            # Dash may store Output objects
            ids.append(getattr(item, "component_id", None) or getattr(item, "id", None))
    return ids


def test_load_data_listens_to_ticker_dropdown():
    theme = get_theme(DEFAULT_THEME)
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP], suppress_callback_exceptions=True)
    app.layout = create_dashboard_layout(theme, bootstrap=None)
    register_callbacks(app)

    spec = _load_data_spec(app)
    input_ids = [item["id"] for item in spec["inputs"]]
    state_ids = [item["id"] for item in spec.get("state", [])]
    out_ids = _output_ids(spec)

    assert input_ids == ["load-data-button", "autoload-interval", "ticker-dropdown", "bar-interval"]
    assert "ticker-dropdown" not in state_ids
    assert "user-ticker-store" not in input_ids
    # The chart is owned by callbacks.chart.update_chart_payload, reached via
    # data-loaded-store. load_data writing any chart output would put two
    # writers in one dispatch layer, which Dash 4 rejects outright — that is
    # what previously froze every control in the app.
    assert "financial-chart" not in out_ids
    assert "chart-payload-store" not in out_ids
    assert "data-loaded-store" in out_ids


def test_chart_payload_has_a_trigger_independent_of_load_data():
    """The payload callback must not depend solely on `load_data`'s outputs.

    When the server bootstrap already loaded the data, `load_data` raises
    PreventUpdate — and Dash then never dispatches a callback that sits
    downstream of it, not even through that callback's other inputs. A payload
    callback keyed only on `data-loaded-store` therefore never runs on a
    bootstrapped page and the chart stays blank forever. The Plotly chart hid
    this because its figure was serialised straight into the layout.

    `chart-boot-btn` is clicked by the chart glue once the container exists,
    which is a fresh dispatch and cannot be pruned.
    """
    import dash

    from lib.dash.callbacks.chart import register_chart_callbacks

    app = dash.Dash(__name__, suppress_callback_exceptions=True)
    register_chart_callbacks(app)

    spec = next(
        cb for cb in app.callback_map.values()
        if "chart-payload-store.data" in str(cb["output"])
    )
    input_ids = {i["id"] for i in spec["inputs"] if isinstance(i["id"], str)}
    assert "data-loaded-store" in input_ids
    assert "chart-boot-btn" in input_ids


def test_chart_glue_clicks_the_boot_button():
    """The other half of the contract above lives in JavaScript."""
    from pathlib import Path

    glue = (Path(__file__).resolve().parents[1]
            / "dash" / "assets" / "10-sfa-chart.js").read_text(encoding="utf-8")
    assert "chart-boot-btn" in glue
    assert "requestFirstPayload" in glue
