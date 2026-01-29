"""
Backtest callbacks.
"""

import logging

from dash import html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.data_processing import create_backtest_results
from lib.dash.components import build_alert, build_metric_card
from lib.dash.dash_config import get_theme
from lib.dash.state import dashboard_state
from lib.strategy import run_backtest

logger = logging.getLogger(__name__)


def register_backtest_callbacks(app) -> None:
    @app.callback(
        Output('backtest-results', 'children'),
        [Input('run-backtest-btn', 'n_clicks')],
        [State('ticker-dropdown', 'value'),
         State('initial-capital', 'value'),
         State('buy-signals', 'value'),
         State('sell-signals', 'value'),
         State('strategy-mode', 'value'),
         State('amount-per-buy', 'value'),
         State('position-size-pct', 'value'),
         State('kelly-win-rate', 'value'),
         State('kelly-win-loss-ratio', 'value'),
         State('min-holding-period', 'value'),
         State('trailing-stop-pct', 'value'),
         State('position-scaling-pct', 'value'),
         State('take-profit-pct', 'value'),
         State('consecutive-signal-mode', 'value'),
         State('signal-cooldown-bars', 'value'),
         State('signal-logic-mode', 'value'),
         State('signal-window', 'value'),
         State('fx-fee-pct', 'value'),
         State('slippage-pct', 'value'),
         State('commission-pct', 'value')]
    )
    def run_backtest_callback(n_clicks, ticker, initial_capital, buy_signals, sell_signals,
                              strategy_mode, amount_per_buy, position_size_pct,
                              kelly_win_rate, kelly_win_loss_ratio,
                              min_holding_period, trailing_stop_pct, position_scaling_pct,
                              take_profit_pct, consecutive_signal_mode, signal_cooldown_bars,
                              signal_logic, signal_window, fx_fee_pct, slippage_pct, commission_pct):
        """Run backtest and display results."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()

        df = dashboard_state.df
        if df is None:
            return build_alert("Please load market data first", "warning", theme=theme)

        # Validation based on strategy mode
        if not buy_signals:
            return build_alert("Select at least one buy signal", "warning", theme=theme)

        if strategy_mode == 'trading' and not sell_signals:
            return build_alert("Trading mode requires at least one sell signal", "warning", theme=theme)

        # Use empty list for sell signals if not provided in accumulation/rebalancing modes
        sell_signals = sell_signals or []

        min_holding_period = int(min_holding_period or 0)
        trailing_stop_loss = max(0.0, float(trailing_stop_pct or 0)) / 100.0
        position_scaling = max(0.0, float(position_scaling_pct or 0)) / 100.0
        take_profit = max(0.0, float(take_profit_pct or 0)) / 100.0
        fx_fee_pct = max(0.0, float(fx_fee_pct or 0)) / 100.0
        slippage_pct = max(0.0, float(slippage_pct or 0)) / 100.0
        commission_per_trade = max(0.0, float(commission_pct or 0)) / 100.0
        kelly_win_rate = float(kelly_win_rate) if kelly_win_rate is not None else 0.5
        kelly_win_rate = min(1.0, max(0.0, kelly_win_rate))
        kelly_win_loss_ratio = float(kelly_win_loss_ratio) if kelly_win_loss_ratio is not None else 1.5
        kelly_win_loss_ratio = max(0.01, kelly_win_loss_ratio)

        try:
            results = run_backtest(
                df, initial_capital, buy_signals, sell_signals,
                strategy_mode=strategy_mode,
                amount_per_buy=amount_per_buy,
                position_size_pct=position_size_pct,
                kelly_win_rate=kelly_win_rate,
                kelly_win_loss_ratio=kelly_win_loss_ratio,
                min_holding_period=min_holding_period,
                trailing_stop_loss=trailing_stop_loss,
                position_scaling=position_scaling,
                take_profit=take_profit,
                consecutive_signal_mode=consecutive_signal_mode,
                cooldown_bars=signal_cooldown_bars,
                signal_logic=signal_logic or 'or',
                signal_window=signal_window or 0,
                commission_per_trade=commission_per_trade,
                slippage_pct=slippage_pct,
                fx_fee_pct=fx_fee_pct
            )
            backtest_results = create_backtest_results(results, ticker, initial_capital, buy_signals, sell_signals)
            dashboard_state.backtest_results = backtest_results

            baseline_results = None
            if fx_fee_pct > 0 or slippage_pct > 0 or commission_per_trade > 0:
                baseline_results = run_backtest(
                    df, initial_capital, buy_signals, sell_signals,
                    strategy_mode=strategy_mode,
                    amount_per_buy=amount_per_buy,
                    position_size_pct=position_size_pct,
                    kelly_win_rate=kelly_win_rate,
                    kelly_win_loss_ratio=kelly_win_loss_ratio,
                    min_holding_period=min_holding_period,
                    trailing_stop_loss=trailing_stop_loss,
                    position_scaling=position_scaling,
                    take_profit=take_profit,
                    consecutive_signal_mode=consecutive_signal_mode,
                    cooldown_bars=signal_cooldown_bars,
                    signal_logic=signal_logic or 'or',
                    signal_window=signal_window or 0,
                    commission_per_trade=0.0,
                    slippage_pct=0.0,
                    fx_fee_pct=0.0
                )

            baseline_metrics = (
                create_backtest_results(baseline_results, ticker, initial_capital, buy_signals, sell_signals)
                if baseline_results is not None
                else backtest_results
            )
            cost_drag_pct = backtest_results['total_return'] - baseline_metrics['total_return']
            cost_drag_value = backtest_results['final_portfolio_value'] - baseline_metrics['final_portfolio_value']

            # Calculate metrics
            total_return = backtest_results['total_return']
            is_positive = total_return >= 0
            metric_help = {
                "Portfolio Value": "Final account value after the backtest period.",
                "Total Return": "Percent gain/loss from initial capital.",
                "Sharpe Ratio": "Risk-adjusted return (higher is better).",
                "Max Drawdown": "Largest peak-to-trough loss during the period.",
                "Win Rate": "Percent of trades that were profitable.",
            }

            return html.Div([
                build_alert("Backtest completed successfully!", "success", dismissable=False, theme=theme),
                html.Div([
                    build_metric_card(
                        "Return Before Costs",
                        f"{baseline_metrics['total_return']:+.2f}%",
                        baseline_metrics['total_return'] >= 0,
                        theme,
                        info_text="Backtest return with 0% fees and 0% slippage."
                    ),
                    build_metric_card(
                        "Cost Drag",
                        f"{cost_drag_pct:+.2f}%",
                        cost_drag_pct >= 0,
                        theme,
                        info_text="Difference between net return and zero-cost return."
                    ),
                    build_metric_card(
                        "Cost Impact",
                        f"${cost_drag_value:,.2f}",
                        cost_drag_value >= 0,
                        theme,
                        info_text="Final portfolio impact of fees and slippage."
                    ),
                ], style={'marginTop': '10px'}),
                html.Div([
                    build_metric_card(
                        "Portfolio Value",
                        f"${backtest_results['final_portfolio_value']:,.2f}",
                        None,
                        theme,
                        info_text=metric_help["Portfolio Value"]
                    ),
                    build_metric_card(
                        "Total Return",
                        f"{total_return:+.2f}%",
                        is_positive,
                        theme,
                        info_text=metric_help["Total Return"]
                    ),
                    build_metric_card("Sharpe Ratio", f"{backtest_results['sharpe_ratio']:.2f}",
                                     backtest_results['sharpe_ratio'] > 1, theme,
                                     info_text=metric_help["Sharpe Ratio"]),
                    build_metric_card("Max Drawdown", f"{backtest_results['max_drawdown']:.2f}%",
                                     backtest_results['max_drawdown'] > -20, theme,
                                     info_text=metric_help["Max Drawdown"]),
                    build_metric_card("Win Rate", f"{backtest_results['win_rate']:.1f}%",
                                     backtest_results['win_rate'] > 50, theme,
                                     info_text=metric_help["Win Rate"]),
                ], style={'marginTop': '12px'}),
            ], className='fade-in')

        except Exception as e:
            logger.error(f"Backtest error: {e}")
            return build_alert(f"Backtest failed: {str(e)[:60]}", "error", theme=theme)
