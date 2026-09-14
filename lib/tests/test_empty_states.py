"""Empty states (ROADMAP 5.14) — chart area, backtest results and signal list before first load."""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import pytest

from _dash_post import callback_key, post_callback
from lib.dash.callbacks import register_callbacks
from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.layout.empty_states import (
    BACKTEST_EMPTY_TITLE,
    CHART_EMPTY_TITLE,
    SIGNALS_NO_DATA_TITLE,
    SIGNALS_NO_MATCH_TITLE,
    empty_state,
)
from lib.dash.layout.shell import create_dashboard_layout


def _find(component, target):
    if getattr(component, 'id', None) == target:
        return component
    children = getattr(component, 'children', None)
    if children is None:
        return None
    for child in children if isinstance(children, (list, tuple)) else [children]:
        found = _find(child, target)
        if found is not None:
            return found
    return None


@pytest.fixture(scope='module')
def app():
    application = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP],
                            suppress_callback_exceptions=True)
    application.layout = create_dashboard_layout(get_theme(DEFAULT_THEME))
    register_callbacks(application)
    return application


def test_empty_state_has_title_hint_and_glyph():
    tree = str(empty_state("Nothing here", "Do this").to_plotly_json())
    assert "Nothing here" in tree and "Do this" in tree
    assert "sfa-empty-state__glyph" in tree
    assert "sfa-empty-state__glyph" not in str(empty_state("x", compact=True).to_plotly_json())


def test_chart_empty_state_is_visible_without_a_bootstrap():
    layout = create_dashboard_layout(get_theme())
    overlay = _find(layout, 'chart-empty-state')
    assert overlay is not None
    assert overlay.hidden is False
    assert CHART_EMPTY_TITLE in str(overlay.to_plotly_json())
    # The hint is addressable so the chart callback can swap in a failure reason.
    assert _find(layout, 'chart-empty-hint') is not None


def test_backtest_results_start_on_the_empty_state():
    layout = create_dashboard_layout(get_theme())
    results = _find(layout, 'backtest-results')
    assert BACKTEST_EMPTY_TITLE in str(results.to_plotly_json())


def test_chart_empty_state_is_toggled_by_the_payload(app):
    """One clientside writer for the overlay; the renderer never sees it."""
    specs = [spec for key, spec in app.callback_map.items() if 'chart-empty-state.hidden' in key]
    assert len(specs) == 1
    assert [i['id'] for i in specs[0]['inputs']] == ['chart-payload-store']


def test_signal_list_before_data(app):
    key = callback_key(app, 'signals-unified-list.children', 'signals-unified-store.data')
    status, body = post_callback(app, key, 'signals-unified-store.data', {'signals-unified-store.data': []})
    assert status == 200
    assert SIGNALS_NO_DATA_TITLE in str(body)


def test_signal_list_when_the_filter_matches_nothing(app):
    key = callback_key(app, 'signals-unified-list.children', 'signals-unified-store.data')
    rows = [{'label': 'RSI Oversold', 'category': 'Momentum', 'buy': 'RSI_Oversold_Buy', 'sell': None}]
    status, body = post_callback(app, key, 'signals-search.value', {
        'signals-unified-store.data': rows,
        'signals-search.value': 'no such signal',
    })
    assert status == 200
    assert SIGNALS_NO_MATCH_TITLE in str(body)
