"""Global error boundary (ROADMAP 5.13) — an unhandled callback exception is shown, not swallowed."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import dash
from dash import html
from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate

from _dash_post import post_callback
from lib.dash.dash_config import get_theme
from lib.dash.error_boundary import (
    ERROR_BOUNDARY_ID,
    MAX_DETAIL_CHARS,
    _detail,
    build_error_boundary,
    handle_callback_error,
)
from lib.dash.layout.shell import create_dashboard_layout


def _app_with(callback_body):
    app = dash.Dash(__name__, on_error=handle_callback_error, suppress_callback_exceptions=True)
    app.layout = html.Div([
        build_error_boundary(),
        html.Span(id='status-activity-label'),
        html.Span(id='status-activity-dot'),
        html.Button(id='boom-btn'),
        html.Div(id='boom-out'),
    ])

    @app.callback(Output('boom-out', 'children'), Input('boom-btn', 'n_clicks'))
    def boom(n_clicks):
        return callback_body(n_clicks)

    return app


def _raise(_n):
    raise ValueError("bad frame")


def test_unhandled_exception_renders_in_the_boundary_and_flags_the_status_bar():
    app = _app_with(_raise)
    status, body = post_callback(app, 'boom-out.children', 'boom-btn.n_clicks', {'boom-btn.n_clicks': 1})

    assert status == 200
    side = body['sideUpdate']
    alert = str(side[ERROR_BOUNDARY_ID]['children'])
    assert 'boom-out.children' in alert
    assert 'ValueError: bad frame' in alert
    assert side['status-activity-label'] == {'children': 'ERROR'}
    assert side['status-activity-dot'] == {'className': 'dot dot-down'}
    # The failed callback's own output is left untouched, not half-written.
    assert 'boom-out' not in body.get('response', {})


def test_prevent_update_is_not_an_error():
    def _prevent(_n):
        raise PreventUpdate

    app = _app_with(_prevent)
    status, _body = post_callback(app, 'boom-out.children', 'boom-btn.n_clicks', {'boom-btn.n_clicks': 1})
    assert status == 204


def test_a_healthy_callback_does_not_touch_the_boundary():
    app = _app_with(lambda n: f"clicked {n}")
    status, body = post_callback(app, 'boom-out.children', 'boom-btn.n_clicks', {'boom-btn.n_clicks': 2})
    assert status == 200
    assert body['response']['boom-out']['children'] == 'clicked 2'
    assert 'sideUpdate' not in body


def test_detail_is_capped_so_a_frame_repr_cannot_fill_the_screen():
    detail = _detail(RuntimeError("x" * 5000))
    assert detail.startswith("RuntimeError: ")
    assert len(detail) <= len("RuntimeError: ") + MAX_DETAIL_CHARS


def test_boundary_is_mounted_in_the_dashboard_layout():
    layout = create_dashboard_layout(get_theme())
    assert ERROR_BOUNDARY_ID in str(layout.to_plotly_json())


@patch("lib.dash.integrated_dashboard.try_bootstrap_default_session", return_value=None)
@patch("lib.dash.integrated_dashboard.register_callbacks")
@patch("lib.dash.integrated_dashboard.wire_command_palette_is_open")
@patch("lib.dash.integrated_dashboard.dash.Dash")
def test_create_app_installs_the_handler(mock_dash_cls, _wire, _register, _bootstrap):
    mock_dash_cls.return_value = MagicMock()
    from lib.dash.integrated_dashboard import create_app

    create_app()
    assert mock_dash_cls.call_args.kwargs['on_error'] is handle_callback_error
