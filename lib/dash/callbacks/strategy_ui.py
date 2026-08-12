"""
Strategy configuration callbacks.
"""

from dash import callback_context
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_THEME, get_theme


def register_strategy_callbacks(app) -> None:
    @app.callback(
        [Output('accumulation-options', 'style'),
         Output('rebalancing-options', 'style'),
         Output('preset-options', 'style'),
         Output('holding-period-options', 'style'),
         Output('trailing-stop-options', 'style'),
         Output('position-scaling-options', 'style'),
         Output('take-profit-options', 'style'),
         Output('kelly-options', 'style')],
        [Input('strategy-mode', 'value')],
        [State('theme-store', 'data')]
    )
    def toggle_strategy_options(strategy_mode, theme_name):
        """Show/hide mode-specific options based on selected strategy mode."""
        theme = get_theme(theme_name or DEFAULT_THEME)

        # Match Transaction Costs density: no per-field hairlines / extra padding.
        # Paired rows (hold|trail, scale|tp) keep flex so mode toggles don't stack them.
        def panel_style(show: bool, *, flex: bool = False) -> dict:
            style = {
                'marginBottom': '0' if flex else '8px',
                'display': 'block' if show else 'none',
                'padding': '0',
                'backgroundColor': 'transparent',
                'border': 'none',
                'color': theme['text_primary'],
            }
            if flex:
                style['flex'] = '1'
                style['minWidth'] = 0
            return style

        is_trading = strategy_mode == 'trading'
        is_accumulation = strategy_mode == 'accumulation'
        is_rebalancing = strategy_mode == 'rebalancing'

        accumulation_style = panel_style(is_accumulation)
        rebalancing_style = panel_style(is_rebalancing)
        preset_style = panel_style(is_trading)
        holding_style = panel_style(is_trading or is_rebalancing, flex=True)
        trailing_style = panel_style(is_trading or is_rebalancing, flex=True)
        scaling_style = panel_style(is_trading, flex=True)
        take_profit_style = panel_style(is_trading or is_rebalancing, flex=True)
        kelly_style = panel_style(is_trading)

        return (accumulation_style, rebalancing_style, preset_style,
                holding_style, trailing_style, scaling_style, take_profit_style,
                kelly_style)

    @app.callback(
        [Output('min-holding-period', 'value'),
         Output('trailing-stop-pct', 'value'),
         Output('position-scaling-pct', 'value'),
         Output('take-profit-pct', 'value'),
         Output('signal-cooldown-bars', 'value'),
         Output('signal-cooldown-container', 'style'),
         Output('consecutive-signal-help', 'children')],
        [Input('strategy-preset', 'value'),
         Input('consecutive-signal-mode', 'value'),
         Input('preset-apply-store', 'data')],
        [State('min-holding-period', 'value'),
         State('trailing-stop-pct', 'value'),
         State('position-scaling-pct', 'value'),
         State('take-profit-pct', 'value'),
         State('signal-cooldown-bars', 'value')],
        prevent_initial_call=True
    )
    def update_trade_setup_controls(strategy_preset, consecutive_mode, preset_data,
                                    current_min_hold, current_trailing,
                                    current_scaling, current_take_profit,
                                    current_cooldown):
        """Apply strategy presets and consecutive-signal defaults in one place."""
        ctx = callback_context
        trigger = getattr(ctx, "triggered_id", None)

        min_hold = current_min_hold
        trailing = current_trailing
        scaling = current_scaling
        take_profit = current_take_profit
        cooldown_value = current_cooldown

        if trigger == 'preset-apply-store' and preset_data:
            trade_setup = preset_data.get("trade_setup", {})
            min_hold = trade_setup.get("min_holding_period", min_hold)
            trailing = trade_setup.get("trailing_stop_pct", trailing)
            scaling = trade_setup.get("position_scaling_pct", scaling)
            take_profit = trade_setup.get("take_profit_pct", take_profit)
            cooldown_value = trade_setup.get("signal_cooldown_bars", cooldown_value)

        if trigger == 'strategy-preset':
            presets = {
                'swing': {'min_hold': 5, 'trailing': 8, 'scaling': 25, 'take_profit': 12},
                'position': {'min_hold': 20, 'trailing': 15, 'scaling': 15, 'take_profit': 25},
                'trend': {'min_hold': 10, 'trailing': 12, 'scaling': 20, 'take_profit': 20},
            }

            if strategy_preset and strategy_preset != 'custom':
                preset_values = presets.get(strategy_preset)
                if preset_values:
                    min_hold = preset_values['min_hold']
                    trailing = preset_values['trailing']
                    scaling = preset_values['scaling']
                    take_profit = preset_values['take_profit']

        mode = (consecutive_mode or 'scale_in').lower()
        cooldown_style = {'display': 'none'}
        help_text = (
            "When the same buy/sell fires on several bars in a row, this chooses "
            "whether to act every time or skip repeats."
        )

        if mode == 'edge':
            help_text = (
                "Edge: act only the moment a signal turns on (0→1). Ignores bars "
                "where it stays on — stops piling in on the same run."
            )
        elif mode == 'cooldown':
            cooldown_style = {'display': 'block'}
            help_text = (
                "Cooldown: after you act, wait N bars before another trade can "
                "fire from the same side."
            )
            if not cooldown_value or cooldown_value <= 0:
                cooldown_value = 5
        elif mode == 'reset_cooldown':
            cooldown_style = {'display': 'block'}
            help_text = (
                "Reset + Cooldown: the signal must switch fully off, then wait "
                "N more bars, before another trade is allowed."
            )
            if not cooldown_value or cooldown_value <= 0:
                cooldown_value = 5
        else:
            help_text = (
                "Scale-in: every repeat counts. Each accepted buy adds more size "
                "(default behaviour)."
            )
            if cooldown_value is None:
                cooldown_value = 0

        return min_hold, trailing, scaling, take_profit, cooldown_value, cooldown_style, help_text

    @app.callback(
        [Output('strategy-mode', 'value'),
         Output('strategy-preset', 'value'),
         Output('amount-per-buy', 'value'),
         Output('position-size-pct', 'value'),
         Output('kelly-win-rate', 'value'),
         Output('kelly-win-loss-ratio', 'value'),
         Output('consecutive-signal-mode', 'value'),
         Output('fx-fee-pct', 'value'),
         Output('slippage-pct', 'value'),
         Output('commission-pct', 'value')],
        [Input('preset-apply-store', 'data')],
        prevent_initial_call=True
    )
    def apply_execution_preset(preset_data):
        if not preset_data:
            raise PreventUpdate

        execution = preset_data.get("execution", {})
        trade_setup = preset_data.get("trade_setup", {})
        costs = preset_data.get("costs", {})

        return (
            execution.get("strategy_mode"),
            trade_setup.get("strategy_preset"),
            trade_setup.get("amount_per_buy"),
            trade_setup.get("position_size_pct"),
            trade_setup.get("kelly_win_rate", 0.5),
            trade_setup.get("kelly_win_loss_ratio", 1.5),
            trade_setup.get("consecutive_signal_mode"),
            costs.get("fx_fee_pct"),
            costs.get("slippage_pct"),
            costs.get("commission_pct"),
        )
