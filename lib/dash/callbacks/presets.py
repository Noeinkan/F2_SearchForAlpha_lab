"""
Preset management callbacks.
"""

import copy

from dash import callback_context
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import PRESET_FILE_PATH
from lib.dash.preset_storage import load_presets, save_presets
from lib.dash.callbacks.shared import (
    _sanitize_preset_name,
    _build_preset_payload,
    _preset_status,
    _format_preset_options,
)


def register_preset_callbacks(app) -> None:
    @app.callback(
        [Output('preset-apply-store', 'data'),
         Output('active-preset-name', 'data'),
         Output('preset-name-input', 'value')],
        [Input('preset-selector', 'value')],
        [State('presets-store', 'data')],
        prevent_initial_call=True
    )
    def load_preset_to_store(preset_name, presets_data):
        """Load preset data into a store for fan-out callbacks."""
        if not preset_name:
            return None, None, ""

        presets = (presets_data or {}).get("presets", {})
        preset = presets.get(preset_name)
        if not preset:
            return None, None, ""

        return preset, preset_name, preset_name

    @app.callback(
        [Output('presets-store', 'data', allow_duplicate=True),
         Output('preset-selector', 'options', allow_duplicate=True),
         Output('preset-selector', 'value', allow_duplicate=True),
         Output('preset-status', 'children')],
        [Input('preset-save-btn', 'n_clicks'),
         Input('preset-save-as-btn', 'n_clicks'),
         Input('preset-rename-btn', 'n_clicks'),
         Input('preset-delete-btn', 'n_clicks')],
        [State('presets-store', 'data'),
         State('preset-selector', 'value'),
         State('preset-name-input', 'value'),
         State('ticker-dropdown', 'value'),
         State('test-window-start', 'date'),
         State('test-window-end', 'date'),
         State('initial-capital', 'value'),
         State('bar-interval', 'value'),
         State({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         State('chart-elements-checklist', 'value'),
         State('signal-checklist', 'value'),
         State('indicator-settings-store', 'data'),
         State('strategy-mode', 'value'),
         State('strategy-preset', 'value'),
         State('min-holding-period', 'value'),
         State('trailing-stop-pct', 'value'),
         State('position-scaling-pct', 'value'),
         State('take-profit-pct', 'value'),
         State('amount-per-buy', 'value'),
         State('position-size-pct', 'value'),
         State('kelly-win-rate', 'value'),
         State('kelly-win-loss-ratio', 'value'),
         State('consecutive-signal-mode', 'value'),
         State('signal-cooldown-bars', 'value'),
         State('signal-logic-mode', 'value'),
         State('signal-window', 'value'),
         State('buy-signals', 'value'),
         State('sell-signals', 'value'),
         State('fx-fee-pct', 'value'),
         State('slippage-pct', 'value'),
         State('commission-pct', 'value')],
        prevent_initial_call=True
    )
    def manage_presets(save_clicks, save_as_clicks, rename_clicks, delete_clicks,
                       presets_data, preset_selected, preset_name_input,
                       ticker, test_window_start, test_window_end, initial_capital, bar_interval,
                       plot_values, chart_elements, signal_checklist,
                       indicator_settings,
                       strategy_mode, strategy_preset, min_holding_period,
                       trailing_stop_pct, position_scaling_pct, take_profit_pct,
                       amount_per_buy, position_size_pct, kelly_win_rate, kelly_win_loss_ratio,
                       consecutive_signal_mode,
                       signal_cooldown_bars, signal_logic_mode, signal_window,
                       buy_signals, sell_signals,
                       fx_fee_pct, slippage_pct, commission_pct):
        """Handle preset Save/Save As/Rename/Delete actions."""
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        action = ctx.triggered[0]['prop_id'].split('.')[0]
        data = presets_data or load_presets(PRESET_FILE_PATH)
        presets = copy.deepcopy(data.get("presets", {}))

        selected_name = _sanitize_preset_name(preset_selected)
        input_name = _sanitize_preset_name(preset_name_input)

        if action == 'preset-save-btn':
            target_name = selected_name or input_name
            if input_name and input_name != selected_name:
                target_name = input_name
                if target_name in presets:
                    return data, _format_preset_options(presets), preset_selected, _preset_status(
                        f"Preset '{target_name}' already exists. Select it to overwrite or use Save As.",
                        "warning"
                    )
            if not target_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Enter a preset name or select one to save.", "error"
                )
            presets[target_name] = _build_preset_payload(
                ticker, test_window_start, test_window_end, initial_capital,
                plot_values, chart_elements, signal_checklist,
                indicator_settings, 'plotly',
                strategy_mode, strategy_preset, min_holding_period,
                trailing_stop_pct, position_scaling_pct, take_profit_pct,
                amount_per_buy, position_size_pct, kelly_win_rate, kelly_win_loss_ratio,
                consecutive_signal_mode,
                signal_cooldown_bars, signal_logic_mode, signal_window,
                buy_signals, sell_signals,
                fx_fee_pct, slippage_pct, commission_pct,
                interval=bar_interval or "1d",
            )
            data["presets"] = presets
            save_presets(PRESET_FILE_PATH, data)
            refreshed = load_presets(PRESET_FILE_PATH)
            return refreshed, _format_preset_options(refreshed["presets"]), target_name, _preset_status(
                f"Saved preset '{target_name}'.", "success"
            )

        if action == 'preset-save-as-btn':
            target_name = input_name
            if not target_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Enter a name for Save As.", "error"
                )
            if target_name in presets:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    f"Preset '{target_name}' already exists.", "warning"
                )
            presets[target_name] = _build_preset_payload(
                ticker, test_window_start, test_window_end, initial_capital,
                plot_values, chart_elements, signal_checklist,
                indicator_settings, 'plotly',
                strategy_mode, strategy_preset, min_holding_period,
                trailing_stop_pct, position_scaling_pct, take_profit_pct,
                amount_per_buy, position_size_pct, kelly_win_rate, kelly_win_loss_ratio,
                consecutive_signal_mode,
                signal_cooldown_bars, signal_logic_mode, signal_window,
                buy_signals, sell_signals,
                fx_fee_pct, slippage_pct, commission_pct,
                interval=bar_interval or "1d",
            )
            data["presets"] = presets
            save_presets(PRESET_FILE_PATH, data)
            refreshed = load_presets(PRESET_FILE_PATH)
            return refreshed, _format_preset_options(refreshed["presets"]), target_name, _preset_status(
                f"Created preset '{target_name}'.", "success"
            )

        if action == 'preset-rename-btn':
            if not selected_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Select a preset to rename.", "error"
                )
            if not input_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Enter a new name to rename.", "error"
                )
            if input_name == selected_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Preset name unchanged.", "warning"
                )
            if input_name in presets:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    f"Preset '{input_name}' already exists.", "warning"
                )
            presets[input_name] = presets.pop(selected_name)
            data["presets"] = presets
            save_presets(PRESET_FILE_PATH, data)
            refreshed = load_presets(PRESET_FILE_PATH)
            return refreshed, _format_preset_options(refreshed["presets"]), input_name, _preset_status(
                f"Renamed preset to '{input_name}'.", "success"
            )

        if action == 'preset-delete-btn':
            if not selected_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Select a preset to delete.", "error"
                )
            if selected_name in presets:
                presets.pop(selected_name, None)
                data["presets"] = presets
                save_presets(PRESET_FILE_PATH, data)
                refreshed = load_presets(PRESET_FILE_PATH)
                return refreshed, _format_preset_options(refreshed["presets"]), None, _preset_status(
                    f"Deleted preset '{selected_name}'.", "success"
                )

        return data, _format_preset_options(presets), preset_selected, _preset_status(
            "No action performed.", "warning"
        )
