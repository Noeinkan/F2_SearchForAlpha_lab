"""
Backtest callbacks.
"""

import logging

from dash import html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.callbacks.shared import slice_df_to_window
from lib.dash.components import build_alert, kpi_cell
from lib.dash.dash_config import get_theme
from lib.dash.state import dashboard_state
from lib.metrics import compute_metrics, format_canonical
from lib.strategy import run_backtest

logger = logging.getLogger(__name__)

# Badge thresholds, in canonical units. A drawdown is a positive magnitude
# here, so 'controlled' means at or below 20%, not 'greater than -20'.
MAX_DRAWDOWN_CONTROLLED = 0.20
WIN_RATE_TARGET = 0.50


def register_backtest_callbacks(app) -> None:
    @app.callback(
        Output('backtest-results', 'children'),
        [Input('run-backtest-btn', 'n_clicks')],
        [State('ticker-dropdown', 'value'),
         State('initial-capital', 'value'),
         State('test-window-start', 'date'),
         State('test-window-end', 'date'),
         State('buy-signals', 'value'),
         State('sell-signals', 'value'),
         State('strategy-mode', 'value'),
         State('amount-per-buy', 'value'),
         State('position-size-pct', 'value'),
         State('kelly-win-rate', 'value'),
         State('kelly-win-loss-ratio', 'value'),
         State('min-holding-period', 'value'),
         State('trailing-stop-pct', 'value'),
         State('stop-mode', 'value'),
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
    def run_backtest_callback(n_clicks, ticker, initial_capital,
                              test_window_start, test_window_end,
                              buy_signals, sell_signals,
                              strategy_mode, amount_per_buy, position_size_pct,
                              kelly_win_rate, kelly_win_loss_ratio,
                              min_holding_period, trailing_stop_pct, stop_mode, position_scaling_pct,
                              take_profit_pct, consecutive_signal_mode, signal_cooldown_bars,
                              signal_logic, signal_window, fx_fee_pct, slippage_pct, commission_pct):
        """Run backtest and display results."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()

        full_df = dashboard_state.df
        if full_df is None:
            return build_alert("Please load market data first", "warning", theme=theme)

        # Same slice the optimizer takes, from the same helper. Skipping this is
        # what let the optimizer rank combinations over the test window while
        # the backtest reported metrics for the entire fetched history.
        df, window_label = slice_df_to_window(full_df, test_window_start, test_window_end)

        # Validation based on strategy mode
        if not buy_signals:
            return build_alert("Select at least one buy signal", "warning", theme=theme)

        if strategy_mode == 'trading' and not sell_signals:
            return build_alert("Trading mode requires at least one sell signal", "warning", theme=theme)

        # Use empty list for sell signals if not provided in accumulation/rebalancing modes
        sell_signals = sell_signals or []

        min_holding_period = int(min_holding_period or 0)
        trailing_stop_loss = max(0.0, float(trailing_stop_pct or 0)) / 100.0
        stop_mode = stop_mode or 'percent'
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
                stop_mode=stop_mode,
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
            metrics = compute_metrics(
                results,
                initial_capital,
                interval=dashboard_state.interval,
                context='dash backtest tab',
            )
            dashboard_state.backtest_results = {
                'ticker': ticker,
                'initial_capital': initial_capital,
                'final_portfolio_value': float(results['Portfolio_Value'].iloc[-1]),
                'buy_strategy': buy_signals,
                'sell_strategy': sell_signals,
                **metrics.as_dict(),
            }

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
                    stop_mode=stop_mode,
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
                compute_metrics(
                    baseline_results,
                    initial_capital,
                    interval=dashboard_state.interval,
                    context='dash backtest tab (no-cost baseline)',
                )
                if baseline_results is not None
                else metrics
            )
            final_value = float(results['Portfolio_Value'].iloc[-1])
            baseline_final_value = (
                float(baseline_results['Portfolio_Value'].iloc[-1])
                if baseline_results is not None
                else final_value
            )
            # Both are fractions; the display multiplies once, at the end.
            cost_drag = metrics.total_return - baseline_metrics.total_return
            cost_drag_value = final_value - baseline_final_value

            # The engine downgrades an ATR stop to the percentage trail when the
            # ATR columns are missing, so report what it actually applied.
            effective_stop_mode = results.attrs.get('stop_mode', 'percent')
            stop_label = (
                'ATR STOP' if effective_stop_mode == 'atr'
                else f"{trailing_stop_loss * 100:.1f}% STOP"
            )
            stop_color = (
                theme['accent_orange'] if effective_stop_mode != stop_mode
                else theme['text_primary']
            )

            # Every threshold below compares against a metrics-engine value, so
            # they are all in canonical units: fractions, and a drawdown that is
            # a positive magnitude. Formatting is the registry's job.
            metric_help = {
                "Total Return": "Percent gain/loss from initial capital.",
                "Sharpe Ratio": "Risk-adjusted return (higher is better).",
                "Max Drawdown": "Largest peak-to-trough loss during the period.",
                "Trade Count": "Completed round trips — an entry and its matching "
                               "exit. A position still open at the end is not counted.",
                "Win Rate": "Percent of closed round trips that were profitable.",
                "Profit Factor": "Gross profits divided by gross losses.",
            }
            drawdown_controlled = metrics.max_drawdown <= MAX_DRAWDOWN_CONTROLLED
            win_rate_healthy = metrics.win_rate >= WIN_RATE_TARGET
            profit_factor_healthy = metrics.profit_factor >= 1
            sharpe_robust = metrics.sharpe >= 1

            return_color = theme['accent_green'] if metrics.total_return >= 0 else theme['accent_red']
            sharpe_color = theme['accent_green'] if sharpe_robust else theme['accent_red']
            drawdown_color = theme['accent_green'] if drawdown_controlled else theme['accent_red']
            win_rate_color = theme['accent_green'] if win_rate_healthy else theme['accent_red']
            profit_factor_color = theme['accent_green'] if profit_factor_healthy else theme['accent_red']
            cost_color = theme['accent_green'] if cost_drag >= 0 else theme['accent_red']

            return html.Div([
                build_alert("Backtest completed successfully!", "success", dismissable=False, theme=theme),
                # State the evaluated window explicitly. The metrics below mean
                # nothing without it, and it is what the optimizer prints too —
                # if the two ever disagree again it is now visible on screen.
                html.Div(
                    [
                        html.Span("WINDOW", style={'color': theme['text_secondary'], 'letterSpacing': '1.5px'}),
                        html.Span(
                            f"{window_label} · {len(df):,} bars",
                            className='num',
                            style={'color': theme['text_primary']},
                        ),
                    ],
                    id='backtest-window-label',
                    style={
                        'display': 'flex',
                        'justifyContent': 'space-between',
                        'alignItems': 'center',
                        'gap': '8px',
                        'fontSize': '10px',
                        'marginBottom': '8px',
                    },
                ),
                html.Div([
                    html.Span("PORTFOLIO", style={'color': theme['text_secondary'], 'letterSpacing': '1.5px'}),
                    html.Span(
                        "Portfolio Value",
                        style={'display': 'none'}
                    ),
                    html.Span(
                        f"${final_value:,.2f}",
                        className='num',
                        style={'color': theme['text_primary'], 'fontSize': '16px', 'fontWeight': '600'}
                    ),
                    html.Span("|", style={'color': theme['border_primary']}),
                    html.Span("NO COSTS", style={'color': theme['text_secondary'], 'letterSpacing': '1.5px'}),
                    html.Span(
                        format_canonical('total_return', baseline_metrics.total_return),
                        className='num',
                        style={'color': theme['accent_blue'], 'fontWeight': '600'}
                    ),
                    html.Span("|", style={'color': theme['border_primary']}),
                    html.Span("COST DRAG", style={'color': theme['text_secondary'], 'letterSpacing': '1.5px'}),
                    html.Span(
                        f"{format_canonical('total_return', cost_drag)} / ${cost_drag_value:,.2f}",
                        className='num',
                        style={'color': cost_color, 'fontWeight': '600'}
                    ),
                    html.Span("|", style={'color': theme['border_primary']}),
                    html.Span("EXIT", style={'color': theme['text_secondary'], 'letterSpacing': '1.5px'}),
                    html.Span(
                        stop_label + (' (FALLBACK)' if effective_stop_mode != stop_mode else ''),
                        className='num',
                        style={'color': stop_color, 'fontWeight': '600'}
                    ),
                ], style={
                    'display': 'flex',
                    'alignItems': 'center',
                    'gap': '8px',
                    'marginTop': '10px',
                    'padding': '6px 8px',
                    'border': f'1px solid {theme["border_primary"]}',
                    'backgroundColor': theme['bg_secondary'],
                    'fontFamily': '"JetBrains Mono", "IBM Plex Mono", ui-monospace, monospace',
                    'fontSize': '11px',
                    'flexWrap': 'wrap',
                }),
                html.Div([
                    kpi_cell(
                        "Total Return",
                        format_canonical('total_return', metrics.total_return),
                        delta="NO COSTS " + format_canonical(
                            'total_return', baseline_metrics.total_return
                        ),
                        delta_color=theme['accent_blue'],
                        theme=theme,
                        info_text=metric_help["Total Return"],
                        is_positive=metrics.total_return >= 0,
                    ),
                    kpi_cell(
                        "Sharpe",
                        format_canonical('sharpe', metrics.sharpe),
                        delta='ROBUST' if sharpe_robust else 'WEAK',
                        delta_color=sharpe_color,
                        theme=theme,
                        info_text=metric_help["Sharpe Ratio"],
                        is_positive=sharpe_robust,
                    ),
                    kpi_cell(
                        "Max DD",
                        format_canonical('max_drawdown', metrics.max_drawdown),
                        delta='CONTROLLED' if drawdown_controlled else 'ELEVATED',
                        delta_color=drawdown_color,
                        theme=theme,
                        info_text=metric_help["Max Drawdown"],
                        # Max DD is "controlled" = positive outcome, not
                        # the raw sign of the number. A -10% drawdown
                        # is *better* than -25%, so we anchor the
                        # color/glyph to the threshold check, not the
                        # number sign.
                        is_positive=drawdown_controlled,
                    ),
                    kpi_cell(
                        "Trade Count",
                        format_canonical('num_trades', metrics.num_trades),
                        delta=str(strategy_mode or 'trading').replace('_', ' ').upper(),
                        delta_color=theme['accent_blue'],
                        theme=theme,
                        info_text=metric_help["Trade Count"],
                    ),
                    kpi_cell(
                        "Win Rate",
                        format_canonical('win_rate', metrics.win_rate),
                        delta='ABOVE 50%' if win_rate_healthy else 'BELOW 50%',
                        delta_color=win_rate_color,
                        theme=theme,
                        info_text=metric_help["Win Rate"],
                        is_positive=win_rate_healthy,
                    ),
                    kpi_cell(
                        "Profit Factor",
                        format_canonical('profit_factor', metrics.profit_factor),
                        delta='ABOVE 1.00' if profit_factor_healthy else 'BELOW 1.00',
                        delta_color=profit_factor_color,
                        theme=theme,
                        info_text=metric_help["Profit Factor"],
                        is_positive=profit_factor_healthy,
                    ),
                ], style={
                    'marginTop': '12px',
                    'display': 'grid',
                    'gridTemplateColumns': 'repeat(2, minmax(0, 1fr))',
                    'gap': '6px',
                }),
            ], className='fade-in')

        except Exception as e:
            logger.error(f"Backtest error: {e}")
            return build_alert(f"Backtest failed: {str(e)[:60]}", "error", theme=theme)
