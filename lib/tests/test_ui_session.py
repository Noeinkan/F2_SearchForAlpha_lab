"""Last-session persistence (ROADMAP 5.15) — the workspace survives a restart."""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import patch

import dash
import dash_bootstrap_components as dbc
import pytest

from _dash_post import callback_key, post_callback
from lib.dash import bootstrap as bootstrap_module
from lib.dash.callbacks import register_callbacks
from lib.dash.callbacks import ui_session as ui_session_callbacks
from lib.dash.callbacks.ui_session import build_session_payload, session_to_apply
from lib.dash.dash_config import DEFAULT_TICKER, DEFAULT_THEME, get_theme
from lib.dash.integrated_dashboard import _default_browser_path
from lib.dash.layout.shell import create_dashboard_layout
from lib.dash.ui_session_storage import (
    RESTORE_ENV_VAR,
    UI_SESSION_SCHEMA_VERSION,
    load_ui_session,
    save_ui_session,
    session_ticker,
)


def _payload(**overrides):
    values = dict(
        ticker='NVDA', test_window_start='2022-01-03', test_window_end='2024-06-28',
        initial_capital=25000, bar_interval='1h',
        plot_values=[['candlestick'], ['rsi']], chart_elements=['candlesticks'],
        signal_checklist=['buy'], indicator_settings={'rsi': {'period': 9}},
        strategy_mode='trading', strategy_preset='custom', min_holding_period=3,
        trailing_stop_pct=7.5, position_scaling_pct=20, take_profit_pct=15,
        amount_per_buy=500, position_size_pct=50, kelly_win_rate=0.55,
        kelly_win_loss_ratio=1.8, consecutive_signal_mode='edge',
        signal_cooldown_bars=0, signal_logic_mode='and', signal_window=4,
        buy_signals=['RSI_Oversold_Buy'], sell_signals=['RSI_Overbought_Sell'],
        fx_fee_pct=0.15, slippage_pct=0.05, commission_pct=0.0,
        stop_mode='atr', order_type='limit', order_offset_pct=0.4,
        order_tif='day', exit_order_mode='bracket',
    )
    values.update(overrides)
    return build_session_payload(**values)


@pytest.fixture
def session_path(tmp_path, monkeypatch):
    monkeypatch.delenv(RESTORE_ENV_VAR, raising=False)
    return str(tmp_path / 'state' / 'ui_session.json')


@pytest.fixture(scope='module')
def app():
    application = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP],
                            suppress_callback_exceptions=True)
    application.layout = create_dashboard_layout(get_theme(DEFAULT_THEME))
    register_callbacks(application)
    return application


# --- storage -----------------------------------------------------------------

def test_round_trip_keeps_every_section(session_path):
    assert save_ui_session(session_path, _payload()) is True
    session = load_ui_session(session_path)

    assert session['market_data']['ticker'] == 'NVDA'
    assert session['market_data']['interval'] == '1h'
    assert session['market_data']['test_window'] == {'start': '2022-01-03', 'end': '2024-06-28'}
    assert session['signals']['buy_signals'] == ['RSI_Oversold_Buy']
    assert session['chart']['indicator_settings'] == {'rsi': {'period': 9}}
    assert session['orders'] == {
        'stop_mode': 'atr', 'order_type': 'limit', 'order_offset_pct': 0.4,
        'order_tif': 'day', 'exit_order_mode': 'bracket',
    }


def test_missing_corrupt_or_foreign_files_load_as_nothing(session_path, tmp_path):
    assert load_ui_session(session_path) is None

    corrupt = tmp_path / 'corrupt.json'
    corrupt.write_text('{not json', encoding='utf-8')
    assert load_ui_session(str(corrupt)) is None

    future = tmp_path / 'future.json'
    future.write_text(json.dumps({'version': UI_SESSION_SCHEMA_VERSION + 1, 'session': {}}), encoding='utf-8')
    assert load_ui_session(str(future)) is None


def test_env_switch_turns_off_reading_and_writing(session_path, monkeypatch):
    save_ui_session(session_path, _payload())
    monkeypatch.setenv(RESTORE_ENV_VAR, '0')
    assert load_ui_session(session_path) is None
    assert save_ui_session(session_path, _payload(ticker='AMD')) is False
    monkeypatch.delenv(RESTORE_ENV_VAR)
    assert session_ticker(load_ui_session(session_path)) == 'NVDA'


def test_a_failed_write_is_reported_not_raised(tmp_path, monkeypatch):
    monkeypatch.delenv(RESTORE_ENV_VAR, raising=False)
    blocker = tmp_path / 'not-a-dir'
    blocker.write_text('x', encoding='utf-8')
    assert save_ui_session(str(blocker / 'ui_session.json'), _payload()) is False


# --- startup ticker ----------------------------------------------------------

def test_startup_ticker_prefers_the_saved_session(session_path, monkeypatch):
    monkeypatch.setattr(bootstrap_module, 'UI_SESSION_FILE_PATH', session_path)
    assert bootstrap_module.startup_ticker() == DEFAULT_TICKER
    save_ui_session(session_path, _payload(ticker='nvda'))
    assert bootstrap_module.startup_ticker() == 'NVDA'


def test_bootstrap_falls_back_to_the_default_when_the_saved_symbol_fails(session_path, monkeypatch):
    monkeypatch.setattr(bootstrap_module, 'UI_SESSION_FILE_PATH', session_path)
    save_ui_session(session_path, _payload(ticker='DELISTED'))
    attempted = []
    snapshot = SimpleNamespace(header_symbol=DEFAULT_TICKER, data_status='80 ROWS')

    def fake_load(ticker, *args, **kwargs):
        attempted.append(ticker)
        if ticker == 'DELISTED':
            raise ValueError('No data available for DELISTED')
        return snapshot

    with patch.object(bootstrap_module, 'load_market_session', side_effect=fake_load):
        assert bootstrap_module.try_bootstrap_default_session() is snapshot
    assert attempted == ['DELISTED', DEFAULT_TICKER]


def test_landing_url_names_the_bootstrapped_symbol():
    assert _default_browser_path('nvda') == '/ticker/NVDA'
    assert _default_browser_path() == f'/ticker/{DEFAULT_TICKER}'


# --- callbacks ---------------------------------------------------------------

def test_restore_never_sets_the_symbol():
    applied = session_to_apply(_payload())
    assert applied['market_data']['ticker'] is None
    assert applied['market_data']['interval'] == '1h'
    assert session_to_apply(None) is None


def test_restore_replays_the_file_and_marks_the_page(app, session_path, monkeypatch):
    monkeypatch.setattr(ui_session_callbacks, 'UI_SESSION_FILE_PATH', session_path)
    key = callback_key(app, 'ui-session-restored.data')

    status, body = post_callback(app, key, 'startup-interval.n_intervals', {'startup-interval.n_intervals': 1})
    assert status == 200
    assert body['response'] == {'ui-session-restored': {'data': True}}

    save_ui_session(session_path, _payload())
    status, body = post_callback(app, key, 'startup-interval.n_intervals', {'startup-interval.n_intervals': 1})
    applied = body['response']['preset-apply-store']['data']
    assert applied['market_data']['ticker'] is None
    assert applied['orders']['order_type'] == 'limit'


def test_saving_waits_for_the_restore(app, session_path, monkeypatch):
    monkeypatch.setattr(ui_session_callbacks, 'UI_SESSION_FILE_PATH', session_path)
    key = callback_key(app, 'ui-session-saved-at.data')
    values = {'ticker-dropdown.value': 'AMD', 'bar-interval.value': '1d', 'ui-session-restored.data': False}

    status, _ = post_callback(app, key, 'ticker-dropdown.value', values)
    assert status == 204
    assert load_ui_session(session_path) is None

    status, body = post_callback(app, key, 'ticker-dropdown.value', {**values, 'ui-session-restored.data': True})
    assert status == 200 and body['response']['ui-session-saved-at']['data']
    assert session_ticker(load_ui_session(session_path)) == 'AMD'


def test_clearing_the_preset_selector_does_not_wipe_a_restore(app):
    """Found in the browser: the selector resets on every page load, and its
    ``None`` used to land on preset-apply-store right after the restore wrote
    it, so no control was ever set."""
    key = callback_key(app, 'active-preset-name.data', 'preset-selector.value')
    status, body = post_callback(app, key, 'preset-selector.value', {'preset-selector.value': None})
    assert status == 200
    assert 'preset-apply-store' not in body['response']
    assert body['response']['active-preset-name'] == {'data': None}


def test_market_preset_without_a_symbol_leaves_the_dropdown_alone(app):
    key = callback_key(app, 'ticker-dropdown.value', 'preset-apply-store.data')
    applied = session_to_apply(_payload())
    status, body = post_callback(app, key, 'preset-apply-store.data', {'preset-apply-store.data': applied})
    assert status == 200
    assert 'ticker-dropdown' not in body['response']
    assert body['response']['initial-capital'] == {'value': 25000}
    assert body['response']['bar-interval'] == {'value': '1h'}


def test_order_model_is_restored_but_ignored_for_old_presets(app):
    key = callback_key(app, 'order-type.value', 'preset-apply-store.data')
    status, body = post_callback(app, key, 'preset-apply-store.data', {'preset-apply-store.data': session_to_apply(_payload())})
    assert status == 200
    assert body['response']['order-type'] == {'value': 'limit'}
    assert body['response']['exit-order-mode'] == {'value': 'bracket'}

    preset_without_orders = {'market_data': {'ticker': 'SPY'}, 'signals': {}}
    status, _ = post_callback(app, key, 'preset-apply-store.data', {'preset-apply-store.data': preset_without_orders})
    assert status == 204


def test_sidebar_starts_on_the_bootstrapped_symbol():
    from lib.dash.layout.sidebar import _create_sidebar
    from lib.dash.styles import get_styles

    class _Snapshot:
        ticker = 'nvda'

    theme = get_theme()
    tree = str(_create_sidebar(get_styles(theme), theme, bootstrap=_Snapshot()).to_plotly_json())
    assert "'value': 'NVDA'" in tree
