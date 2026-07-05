"""
Signal selection and indicator settings callbacks.
"""

import copy
import json
import time

from dash import callback_context, html, dcc, no_update
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS, FONT_SIZES, get_theme, merge_indicator_settings
from lib.dash.styles import get_styles
from lib.dash.state import dashboard_state
from lib.dash.callbacks.shared import (
    _format_signal_label,
    _build_indicator_settings_panel,
    _build_signal_options,
    _build_unified_signal_rows,
    build_data_display_payload,
    get_enriched,
)


def register_signal_callbacks(app) -> None:
    @app.callback(
        Output('signals-unified-list', 'children'),
        [Input('signals-unified-store', 'data'),
         Input('signals-search', 'value'),
         Input('signals-category-filter', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value')]
    )
    def render_unified_signal_list(signal_rows, search_value, category_values, buy_values, sell_values):
        """Render unified BUY/SELL signal rows."""
        theme = get_theme()
        header = html.Div([
            html.Span("BUY SIGNAL", className='signals-unified-header__col signals-unified-header__col--buy', style={
                'fontSize': FONT_SIZES['xs'],
                'fontWeight': '600',
                'color': theme['accent_green']
            }),
            html.Span("SIGNAL", className='signals-unified-header__col signals-unified-header__col--name', style={
                'fontSize': FONT_SIZES['xs'],
                'fontWeight': '600',
                'color': theme['text_secondary']
            }),
            html.Span("SELL SIGNAL", className='signals-unified-header__col signals-unified-header__col--sell', style={
                'fontSize': FONT_SIZES['xs'],
                'fontWeight': '600',
                'color': theme['accent_red']
            }),
        ], className='signals-unified-header')
        if not signal_rows:
            return [
                header,
                html.Div(
                    "Load data to view signals.",
                    style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'padding': '6px'}
                )
            ]

        search_value = (search_value or '').lower()
        category_values = set(category_values or [])
        selected_buy = set(buy_values or [])
        selected_sell = set(sell_values or [])

        rows = []
        for row in signal_rows:
            label = row.get('label') or ''
            category = row.get('category') or ''
            if search_value and search_value not in label.lower():
                continue
            if category_values and category not in category_values:
                continue

            buy_signal = row.get('buy')
            sell_signal = row.get('sell')
            buy_toggle = dcc.Checklist(
                id={'type': 'signal-toggle', 'side': 'buy', 'value': buy_signal or ''},
                options=[{'label': '', 'value': buy_signal or ''}],
                value=[buy_signal] if buy_signal in selected_buy else [],
                className='signal-toggle buy-toggle signal-toggle--buy'
            )
            sell_toggle = dcc.Checklist(
                id={'type': 'signal-toggle', 'side': 'sell', 'value': sell_signal or ''},
                options=[{'label': '', 'value': sell_signal or ''}],
                value=[sell_signal] if sell_signal in selected_sell else [],
                className='signal-toggle sell-toggle signal-toggle--sell'
            )

            rows.append(
                html.Div(
                    [
                        buy_toggle,
                        html.Span(label, className='signal-name'),
                        sell_toggle,
                    ],
                    className='signal-row'
                )
            )

        if not rows:
            return [
                header,
                html.Div(
                    "No signals match the filter.",
                    style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'padding': '6px'}
                )
            ]

        return [header, *rows]

    @app.callback(
        [Output('signal-window', 'disabled'),
         Output('signal-window-container', 'style')],
        [Input('signal-logic-mode', 'value')]
    )
    def toggle_signal_window(signal_logic):
        """Disable AND window control unless AND logic is selected."""
        base_style = {'marginBottom': '10px'}
        if signal_logic != 'and':
            return True, {**base_style, 'opacity': 0.55}
        return False, {**base_style, 'opacity': 1}

    @app.callback(
        [Output('signal-logic-mode', 'value'),
         Output('signal-window', 'value')],
        [Input('preset-apply-store', 'data')],
        prevent_initial_call=True
    )
    def apply_signal_preset(preset_data):
        if not preset_data:
            raise PreventUpdate
        signals = preset_data.get("signals", {})
        return signals.get("signal_logic_mode"), signals.get("signal_window")

    @app.callback(
        [Output('buy-signals', 'value'),
         Output('sell-signals', 'value'),
         Output('optimizer-autorun', 'data')],
        [Input('preset-apply-store', 'data'),
         Input('optimizer-apply-store', 'data'),
         Input({'type': 'signal-toggle', 'side': 'buy', 'value': ALL}, 'value'),
         Input({'type': 'signal-toggle', 'side': 'sell', 'value': ALL}, 'value')],
        [State({'type': 'signal-toggle', 'side': 'buy', 'value': ALL}, 'id'),
         State({'type': 'signal-toggle', 'side': 'sell', 'value': ALL}, 'id')]
    )
    def sync_signal_selection(preset_data, optimizer_data, buy_values, sell_values, buy_ids, sell_ids):
        """Sync row toggles to unified buy/sell selections.

        Also the single source of truth for programmatic selection: presets and
        the Optimizer's "Apply Best Strategy" both write here so the visible
        toggle rows stay in sync. On an Optimizer apply we additionally emit an
        ``optimizer-autorun`` nonce — in the same return as the committed
        signals — which a clientside callback turns into a RUN BACKTEST click.
        """
        ctx = callback_context
        triggered = getattr(ctx, "triggered_id", None)

        if triggered == 'preset-apply-store':
            if not preset_data:
                raise PreventUpdate
            signals = preset_data.get("signals", {})
            return (
                list(signals.get("buy_signals", []) or []),
                list(signals.get("sell_signals", []) or []),
                no_update,
            )

        if triggered == 'optimizer-apply-store':
            if not optimizer_data:
                raise PreventUpdate
            # Emit the autorun nonce alongside the committed signals so the
            # backtest fires only after buy/sell-signals are set.
            return (
                list(optimizer_data.get("buy", []) or []),
                list(optimizer_data.get("sell", []) or []),
                {'nonce': time.time()},
            )

        if not buy_ids and not sell_ids:
            return [], [], no_update

        selected_buy = [
            item_id['value']
            for item_id, value in zip(buy_ids, buy_values)
            if value
        ]
        selected_sell = [
            item_id['value']
            for item_id, value in zip(sell_ids, sell_values)
            if value
        ]

        return selected_buy, selected_sell, no_update

    @app.callback(
        [Output('summary-strategy-mode', 'children'),
         Output('summary-position-sizing', 'children'),
         Output('summary-signal-settings', 'children')],
        [Input('strategy-mode', 'value'),
         Input('strategy-preset', 'value'),
         Input('amount-per-buy', 'value'),
         Input('position-size-pct', 'value'),
         Input('kelly-win-rate', 'value'),
         Input('kelly-win-loss-ratio', 'value'),
         Input('min-holding-period', 'value'),
         Input('trailing-stop-pct', 'value'),
         Input('position-scaling-pct', 'value'),
         Input('take-profit-pct', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('signal-logic-mode', 'value'),
         Input('signal-window', 'value')]
    )
    def update_backtest_panel_summaries(strategy_mode, strategy_preset, amount_per_buy, position_size_pct,
                                        kelly_win_rate, kelly_win_loss_ratio, min_holding_period,
                                        trailing_stop_pct, position_scaling_pct, take_profit_pct,
                                        buy_signals, sell_signals, signal_logic, signal_window):
        """Update accordion titles with selected options when collapsed."""
        strategy_labels = {
            'trading': 'Trading (Full)',
            'accumulation': 'Accumulation (DCA)',
            'rebalancing': 'Rebalancing (Partial)',
        }
        strategy_summary = strategy_labels.get(strategy_mode, 'Trading (Full)')

        if strategy_mode == 'trading' and strategy_preset and strategy_preset != 'custom':
            strategy_summary = f"{strategy_summary} ({strategy_preset.title()})"

        if strategy_mode == 'accumulation':
            if amount_per_buy is None:
                sizing_summary = '$- per buy'
            else:
                sizing_summary = f'${amount_per_buy:,.0f} per buy'
        else:
            sizing_parts = []
            if strategy_mode == 'rebalancing':
                if position_size_pct is None:
                    sizing_parts.append('% per trade')
                else:
                    sizing_parts.append(f'{position_size_pct:.0f}% per trade')

            if strategy_mode == 'trading':
                kelly_win_rate = 0.5 if kelly_win_rate is None else kelly_win_rate
                kelly_win_loss_ratio = 1.5 if kelly_win_loss_ratio is None else kelly_win_loss_ratio

            if strategy_mode == 'trading' and kelly_win_rate is not None and kelly_win_loss_ratio is not None:
                sizing_parts.append(f'Kelly {kelly_win_rate:.2f}/{kelly_win_loss_ratio:.2f}')

            if min_holding_period is not None:
                sizing_parts.append(f'Hold {int(min_holding_period)}')
            if trailing_stop_pct is not None and trailing_stop_pct > 0:
                sizing_parts.append(f'TS {trailing_stop_pct:.1f}%')
            if strategy_mode == 'trading' and position_scaling_pct is not None:
                sizing_parts.append(f'Scale {position_scaling_pct:.0f}%')
            if take_profit_pct is not None and take_profit_pct > 0:
                sizing_parts.append(f'TP {take_profit_pct:.1f}%')

            sizing_summary = ' | '.join(sizing_parts) if sizing_parts else 'N/A'

        buy_signals = buy_signals or []
        sell_signals = sell_signals or []

        def _summarize_signals(values, max_items=2):
            labels = [_format_signal_label(v) for v in values]
            if not labels:
                return 'None'
            if len(labels) <= max_items:
                return ', '.join(labels)
            extra = len(labels) - max_items
            return f"{', '.join(labels[:max_items])} +{extra}"

        if not buy_signals and not sell_signals:
            signals_summary = 'No signals'
        else:
            signals_summary = (
                f"Buy: {_summarize_signals(buy_signals)} | "
                f"Sell: {_summarize_signals(sell_signals)}"
            )
            if signal_logic == 'and':
                if signal_window:
                    signals_summary += f" | AND W={signal_window}"
                else:
                    signals_summary += " | AND"
            else:
                signals_summary += " | OR"

        return strategy_summary, sizing_summary, signals_summary

    @app.callback(
        Output('active-indicator-store', 'data'),
        [Input({'type': 'indicator-gear', 'indicator': ALL}, 'n_clicks_timestamp')],
        prevent_initial_call=True
    )
    def set_active_indicator_settings(_timestamps):
        """Update active indicator when a gear icon is clicked."""
        ctx = callback_context
        triggered_id = getattr(ctx, "triggered_id", None)
        if isinstance(triggered_id, dict) and triggered_id.get('indicator'):
            return triggered_id['indicator']

        if ctx.triggered:
            prop_id = ctx.triggered[0].get("prop_id", "")
            if prop_id and prop_id != ".":
                raw_id = prop_id.split(".")[0]
                try:
                    parsed_id = json.loads(raw_id)
                except json.JSONDecodeError:
                    parsed_id = None
                if isinstance(parsed_id, dict) and parsed_id.get("indicator"):
                    return parsed_id["indicator"]

        inputs = ctx.inputs or {}
        if inputs:
            latest_indicator = None
            latest_ts = -1
            for key, value in inputs.items():
                if not key.startswith("{"):
                    continue
                try:
                    parsed = json.loads(key.split(".")[0])
                except json.JSONDecodeError:
                    continue
                if parsed.get("type") == "indicator-gear" and isinstance(value, (int, float)):
                    if value > latest_ts:
                        latest_ts = value
                        latest_indicator = parsed.get("indicator")
            if latest_indicator:
                return latest_indicator

        raise PreventUpdate

    @app.callback(
        Output({'type': 'indicator-settings-panel', 'indicator': ALL}, 'children'),
        [Input('active-indicator-store', 'data')],
        [State('indicator-settings-store', 'data')]
    )
    def render_indicator_settings_panel(active_indicator, settings_store):
        """Render indicator settings panel for the active indicator."""
        theme = get_theme()
        styles = get_styles(theme)
        settings_store = merge_indicator_settings(settings_store)
        indicator_ids = [item['id']['indicator'] for item in callback_context.outputs_list]
        panels = []
        for indicator in indicator_ids:
            if indicator == active_indicator:
                panels.append(_build_indicator_settings_panel(indicator, settings_store, styles))
            else:
                panels.append(html.Div())
        return panels

    @app.callback(
        Output('indicator-settings-store', 'data'),
        [Input('preset-apply-store', 'data'),
         Input({'type': 'indicator-setting', 'indicator': ALL, 'key': ALL}, 'value')],
        [State('indicator-settings-store', 'data')],
        prevent_initial_call=True
    )
    def persist_indicator_settings(preset_data, _values, current_settings):
        """Persist indicator settings from the sidebar inputs."""
        ctx = callback_context
        if getattr(ctx, "triggered_id", None) == 'preset-apply-store':
            if not preset_data:
                raise PreventUpdate
            indicator_settings = preset_data.get("chart", {}).get("indicator_settings")
            if indicator_settings is None:
                raise PreventUpdate
            return merge_indicator_settings(indicator_settings)

        if current_settings is None:
            current_settings = merge_indicator_settings()
        if not callback_context.inputs_list:
            raise PreventUpdate

        updated = copy.deepcopy(current_settings)
        settings_inputs = callback_context.inputs_list[1] if len(callback_context.inputs_list) > 1 else []
        for item in settings_inputs:
            field_id = item.get('id', {})
            indicator = field_id.get('indicator')
            key = field_id.get('key')
            if not indicator or not key:
                continue
            value = item.get('value')
            if value is None:
                continue
            updated.setdefault(indicator, {})[key] = value
        return updated

    @app.callback(
        [Output('buy-signals', 'options', allow_duplicate=True),
         Output('sell-signals', 'options', allow_duplicate=True),
         Output('signals-unified-store', 'data', allow_duplicate=True),
         Output('data-display-store', 'data', allow_duplicate=True)],
        [Input('indicator-settings-store', 'data')],
        [State('data-loaded-store', 'data')],
        prevent_initial_call=True
    )
    def refresh_signals_with_settings(indicator_settings, data_loaded):
        """Recompute signals when indicator parameters change."""
        if not data_loaded or dashboard_state.df is None:
            raise PreventUpdate

        indicator_settings = merge_indicator_settings(indicator_settings)
        df = get_enriched(dashboard_state.df, indicator_settings)
        if df is None or df.empty:
            raise PreventUpdate

        buy_columns = [col for col in df.columns if 'buy' in col.lower()]
        sell_columns = [col for col in df.columns if 'sell' in col.lower()]
        buy_options = _build_signal_options(buy_columns)
        sell_options = _build_signal_options(sell_columns)
        unified_rows = _build_unified_signal_rows(buy_columns, sell_columns)

        data_display = build_data_display_payload(df)
        return buy_options, sell_options, unified_rows, data_display
