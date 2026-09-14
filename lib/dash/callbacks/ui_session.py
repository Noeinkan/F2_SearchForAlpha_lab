"""Last-session callbacks — save the workspace as it changes, restore it on the next page load.

Storage and the reasoning about what is kept: ``lib/dash/ui_session_storage.py``.

Restoring reuses the preset machinery rather than a second fan-out: the saved
session has a preset's shape, so writing it to ``preset-apply-store`` sets every
control a preset sets, and a restored test window is parked until its data has
loaded exactly as a preset's is (callbacks/test_window.py). The one control a
preset does not carry is the order model, which ``apply_order_model_preset``
below covers for sessions.

The symbol is deliberately *not* restored here. It has already been restored
by the time this runs — the server bootstrapped the last session's ticker, and
the sidebar and landing URL start on it (``bootstrap.startup_ticker``). Setting
it again from the browser would override a deep link to another symbol, and
race a second fetch against the first.

Output ownership:

  preset-apply-store.data   <- load_preset_to_store (presets.py)
                               + restore_ui_session (this file, allow_duplicate)
  ui-session-restored.data  <- restore_ui_session (only writer)
  ui-session-saved-at.data  <- save_ui_session_callback (only writer)
  stop-mode / order-* value <- apply_order_model_preset (only writer)
"""

from __future__ import annotations

import copy
import logging
from datetime import datetime, timezone

from dash import no_update
from dash.dependencies import ALL, Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.callbacks.shared import _build_preset_payload
from lib.dash.dash_config import UI_SESSION_FILE_PATH
from lib.dash.ui_session_storage import load_ui_session, save_ui_session

logger = logging.getLogger(__name__)

# Every control the session captures, in build_session_payload's argument order.
_SESSION_INPUTS = [
    Input('ticker-dropdown', 'value'),
    Input('test-window-start', 'date'),
    Input('test-window-end', 'date'),
    Input('initial-capital', 'value'),
    Input('bar-interval', 'value'),
    Input({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
    Input('chart-elements-checklist', 'value'),
    Input('signal-checklist', 'value'),
    Input('indicator-settings-store', 'data'),
    Input('strategy-mode', 'value'),
    Input('strategy-preset', 'value'),
    Input('min-holding-period', 'value'),
    Input('trailing-stop-pct', 'value'),
    Input('position-scaling-pct', 'value'),
    Input('take-profit-pct', 'value'),
    Input('amount-per-buy', 'value'),
    Input('position-size-pct', 'value'),
    Input('kelly-win-rate', 'value'),
    Input('kelly-win-loss-ratio', 'value'),
    Input('consecutive-signal-mode', 'value'),
    Input('signal-cooldown-bars', 'value'),
    Input('signal-logic-mode', 'value'),
    Input('signal-window', 'value'),
    Input('buy-signals', 'value'),
    Input('sell-signals', 'value'),
    Input('fx-fee-pct', 'value'),
    Input('slippage-pct', 'value'),
    Input('commission-pct', 'value'),
    Input('stop-mode', 'value'),
    Input('order-type', 'value'),
    Input('order-offset-pct', 'value'),
    Input('order-tif', 'value'),
    Input('exit-order-mode', 'value'),
]

# Session key -> control id, for the order model section.
ORDER_CONTROLS = {
    'stop_mode': 'stop-mode',
    'order_type': 'order-type',
    'order_offset_pct': 'order-offset-pct',
    'order_tif': 'order-tif',
    'exit_order_mode': 'exit-order-mode',
}


def build_session_payload(
    ticker, test_window_start, test_window_end, initial_capital, bar_interval,
    plot_values, chart_elements, signal_checklist, indicator_settings,
    strategy_mode, strategy_preset, min_holding_period, trailing_stop_pct,
    position_scaling_pct, take_profit_pct, amount_per_buy, position_size_pct,
    kelly_win_rate, kelly_win_loss_ratio, consecutive_signal_mode,
    signal_cooldown_bars, signal_logic_mode, signal_window,
    buy_signals, sell_signals, fx_fee_pct, slippage_pct, commission_pct,
    stop_mode, order_type, order_offset_pct, order_tif, exit_order_mode,
) -> dict:
    """A preset payload for the current controls, plus the order model."""
    payload = _build_preset_payload(
        ticker, test_window_start, test_window_end, initial_capital,
        plot_values, chart_elements, signal_checklist,
        indicator_settings, 'lightweight',
        strategy_mode, strategy_preset, min_holding_period,
        trailing_stop_pct, position_scaling_pct, take_profit_pct,
        amount_per_buy, position_size_pct, kelly_win_rate, kelly_win_loss_ratio,
        consecutive_signal_mode,
        signal_cooldown_bars, signal_logic_mode, signal_window,
        buy_signals, sell_signals,
        fx_fee_pct, slippage_pct, commission_pct,
        interval=bar_interval or '1d',
    )
    payload['orders'] = {
        'stop_mode': stop_mode,
        'order_type': order_type,
        'order_offset_pct': order_offset_pct,
        'order_tif': order_tif,
        'exit_order_mode': exit_order_mode,
    }
    return payload


def session_to_apply(session: dict | None) -> dict | None:
    """What a restore writes to ``preset-apply-store``: the session minus its symbol."""
    if not session:
        return None
    applied = copy.deepcopy(session)
    applied.setdefault('market_data', {})['ticker'] = None
    return applied


def register_ui_session_callbacks(app) -> None:
    @app.callback(
        [Output('preset-apply-store', 'data', allow_duplicate=True),
         Output('ui-session-restored', 'data')],
        Input('startup-interval', 'n_intervals'),
        prevent_initial_call=True,
    )
    def restore_ui_session(n_intervals):
        """Replay the saved session into the controls, once per page load.

        Always marks the page as restored — even with nothing to restore — so
        saving starts either way.
        """
        if not n_intervals:
            raise PreventUpdate
        session = load_ui_session(UI_SESSION_FILE_PATH)
        applied = session_to_apply(session)
        if applied is None:
            return no_update, True
        logger.info("Restoring last UI session from %s", UI_SESSION_FILE_PATH)
        return applied, True

    @app.callback(
        Output('ui-session-saved-at', 'data'),
        _SESSION_INPUTS,
        State('ui-session-restored', 'data'),
        prevent_initial_call=True,
    )
    def save_ui_session_callback(*values):
        """Write the workspace to disk whenever one of its controls changes.

        Refused until the restore has run: the page's own defaults settle
        first, and saving those would overwrite the session before it is read.
        """
        *control_values, restored = values
        if not restored:
            raise PreventUpdate
        payload = build_session_payload(*control_values)
        if not save_ui_session(UI_SESSION_FILE_PATH, payload):
            raise PreventUpdate
        return datetime.now(timezone.utc).replace(microsecond=0).isoformat()

    @app.callback(
        [Output(control_id, 'value') for control_id in ORDER_CONTROLS.values()],
        Input('preset-apply-store', 'data'),
        prevent_initial_call=True,
    )
    def apply_order_model_preset(preset_data):
        """Restore the order model. Presets predate it, so only sessions carry ``orders``."""
        orders = (preset_data or {}).get('orders') or {}
        if not orders:
            raise PreventUpdate
        return [
            orders[key] if orders.get(key) is not None else no_update
            for key in ORDER_CONTROLS
        ]
