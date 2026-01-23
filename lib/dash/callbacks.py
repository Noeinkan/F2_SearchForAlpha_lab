"""
Dashboard Callbacks
All Dash callback functions for the trading dashboard.
"""

import logging
from datetime import datetime
from typing import Tuple, List, Any

import pandas as pd
from dash import html, dash_table, callback_context
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import plotly.graph_objs as go

from dash_tvlwc import Tvlwc

from lib.dash.dash_config import (
    DEFAULT_THEME, FONT_SIZES, FONT_MONO, BORDER_RADIUS, get_theme
)
from lib.dash.state import dashboard_state
from lib.dash.styles import get_styles
from lib.dash.chart_builder import create_chart, create_empty_chart
from lib.dash.tv_chart_builder import (
    convert_df_to_tv_format,
    convert_volume_to_tv_format,
    get_tv_chart_options
)
from lib.dash.components import build_alert, build_metric_card, build_progress_bar
from lib.dash.helpers import (
    fetch_data_with_cache, format_df_for_display,
    extract_signals, generate_signal_combinations, evaluate_signal_combination
)

from lib.data_processing import get_all_tickers, create_backtest_results
from lib.signals.indicators import add_indicators, generate_signals
from lib.strategy import run_backtest

logger = logging.getLogger(__name__)


def register_callbacks(app):
    """
    Register all callbacks for the dashboard application.

    Args:
        app: Dash application instance
    """

    @app.callback(
        Output('ticker-dropdown', 'options'),
        [Input('startup-interval', 'n_intervals')]
    )
    def populate_tickers(_):
        """Populate ticker dropdown on startup."""
        if dashboard_state.all_tickers_df is None:
            try:
                dashboard_state.all_tickers_df = get_all_tickers()
            except Exception as e:
                logger.error(f"Error fetching tickers: {e}")
                return [{'label': 'SPY - SPDR S&P 500 ETF', 'value': 'SPY'}]
        return [
            {'label': f"{row['Symbol']} - {row['Security'][:30]}", 'value': row['Symbol']}
            for _, row in dashboard_state.all_tickers_df.iterrows()
        ]

    @app.callback(
        [Output('data-status', 'children'),
         Output('data-loaded-store', 'data'),
         Output('buy-signals', 'options'),
         Output('sell-signals', 'options'),
         Output('chart-title', 'children'),
         Output('chart-subtitle', 'children'),
         Output('data-table-container', 'children')],
        [Input('load-data-button', 'n_clicks'),
         Input('autoload-interval', 'n_intervals')],
        [State('ticker-dropdown', 'value'),
         State('start-date', 'date'),
         State('end-date', 'date')]
    )
    def load_data(n_clicks, n_intervals, ticker, start_date, end_date):
        """Load market data. Auto-loads SPY on startup."""
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # On startup, auto-load default ticker (SPY)
        if trigger_id == 'autoload-interval':
            if n_intervals is None or n_intervals < 1:
                raise PreventUpdate
        elif trigger_id == 'load-data-button':
            if not n_clicks:
                raise PreventUpdate

        theme = get_theme()

        try:
            df = fetch_data_with_cache(ticker, start_date, end_date)
            if df.empty:
                return (
                    html.Div([
                        html.Span("\u26a0", style={'color': theme['accent_orange'], 'marginRight': '6px'}),
                        html.Span("No data available for this symbol",
                                  style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_orange']})
                    ]),
                    False, [], [], "No data", "", None
                )

            df = add_indicators(df)
            df, _ = generate_signals(df)
            dashboard_state.df = df

            buy_options = [
                {'label': html.Span(col.replace('_', ' '), style={'marginLeft': '8px'}), 'value': col}
                for col in df.columns if 'buy' in col.lower()
            ]
            sell_options = [
                {'label': html.Span(col.replace('_', ' '), style={'marginLeft': '8px'}), 'value': col}
                for col in df.columns if 'sell' in col.lower()
            ]

            # Create data table
            display_df = format_df_for_display(df.tail(50)).reset_index()
            data_table = _create_data_table(display_df, theme)

            # Calculate subtitle info
            subtitle = _create_price_subtitle(df, theme)

            # Success status with animation
            status = html.Div([
                html.Span("\u2713", style={'color': theme['accent_green'], 'marginRight': '6px', 'fontWeight': 'bold'}),
                html.Span(f"{len(df)} rows loaded", style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_green']})
            ], className='fade-in')

            return status, True, buy_options, sell_options, ticker, subtitle, data_table

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return (
                html.Div([
                    html.Span("\u2715", style={'color': theme['accent_red'], 'marginRight': '6px', 'fontWeight': 'bold'}),
                    html.Span(str(e)[:40], style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_red']})
                ]),
                False, [], [], "Error", "", None
            )

    @app.callback(
        [Output('accumulation-options', 'style'),
         Output('rebalancing-options', 'style')],
        [Input('strategy-mode', 'value')],
        [State('theme-store', 'data')]
    )
    def toggle_strategy_options(strategy_mode, theme_name):
        """Show/hide mode-specific options based on selected strategy mode."""
        theme = get_theme(theme_name or DEFAULT_THEME)

        accumulation_style = {
            'marginBottom': '12px',
            'display': 'block' if strategy_mode == 'accumulation' else 'none',
            'padding': '10px',
            'backgroundColor': f'{theme["accent_green"]}10',
            'borderRadius': BORDER_RADIUS['md'],
            'border': f'1px solid {theme["accent_green"]}40',
        }
        rebalancing_style = {
            'marginBottom': '12px',
            'display': 'block' if strategy_mode == 'rebalancing' else 'none',
            'padding': '10px',
            'backgroundColor': f'{theme["accent_blue"]}10',
            'borderRadius': BORDER_RADIUS['md'],
            'border': f'1px solid {theme["accent_blue"]}40',
        }
        return accumulation_style, rebalancing_style

    @app.callback(
        [Output('plotly-chart-container', 'style'),
         Output('tv-chart-container', 'style')],
        [Input('chart-library-toggle', 'value')]
    )
    def toggle_chart_visibility(chart_library):
        """Show/hide Plotly vs TradingView containers."""
        base_style = {
            'position': 'absolute',
            'inset': 0,
            'height': '100%',
            'width': '100%'
        }
        plotly_style = {**base_style, 'visibility': 'visible', 'opacity': 1, 'pointerEvents': 'auto', 'zIndex': 1}
        tv_style = {**base_style, 'display': 'flex', 'flexDirection': 'column', 'visibility': 'hidden',
                    'opacity': 0, 'pointerEvents': 'none', 'zIndex': 0}
        if chart_library == 'tradingview':
            return {**plotly_style, 'visibility': 'hidden', 'opacity': 0, 'pointerEvents': 'none'}, \
                {**tv_style, 'visibility': 'visible', 'opacity': 1, 'pointerEvents': 'auto', 'zIndex': 2}
        return plotly_style, tv_style

    @app.callback(
        Output('chart-library-toggle', 'value'),
        [Input('plot-checklist', 'value'),
         Input('chart-elements-checklist', 'value')],
        [State('chart-library-toggle', 'value')]
    )
    def enforce_plotly_for_indicators(selected_plots, chart_elements, current_library):
        """Ensure Plotly is used when indicators/overlays are requested."""
        return 'plotly'

    @app.callback(
        Output('financial-chart', 'figure'),
        [Input('data-loaded-store', 'data'),
         Input('plot-checklist', 'value'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('chart-library-toggle', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('signal-logic-mode', 'value')],
        [State('ticker-dropdown', 'value')]
    )
    def update_plotly_chart(data_loaded, selected_plots, chart_elements, selected_signals, chart_library,
                            buy_signals, sell_signals, signal_logic, ticker):
        """Update the Plotly financial chart."""
        if chart_library == 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return create_empty_chart(theme)

        df = dashboard_state.df
        df = df.copy()

        buy_signals = buy_signals or []
        sell_signals = sell_signals or []

        config = {
            'selected_plots': selected_plots or ['candlestick'],
            'show_candlesticks': 'candlesticks' in (chart_elements or []),
            'show_bollinger': 'bollinger' in (chart_elements or []),
            'show_sma': 'sma' in (chart_elements or []),
            'show_ema': 'ema' in (chart_elements or []),
            'show_buy_sell_signals': 'signals' in (chart_elements or []),
            'show_legend': 'legend' in (chart_elements or []),
            'selected_signals': selected_signals or [],
            'buy_signal_columns': buy_signals,
            'sell_signal_columns': sell_signals,
            'signal_logic': signal_logic or 'or',
            'title': '',
        }

        return create_chart(df, config, theme)

    @app.callback(
        Output('tv-main-chart', 'children'),
        [Input('data-loaded-store', 'data'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('chart-library-toggle', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value')],
        [State('ticker-dropdown', 'value')]
    )
    def update_tv_main_chart(data_loaded, chart_elements, selected_signals, chart_library,
                             buy_signals, sell_signals, ticker):
        """Update the TradingView main chart."""
        if chart_library != 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return html.Div("Load data to view chart", style={'color': theme['text_secondary']})

        df = dashboard_state.df
        df = df.copy()

        buy_signals = buy_signals or []
        sell_signals = sell_signals or []

        config = {
            'show_candlesticks': 'candlesticks' in (chart_elements or []),
            'show_bollinger': 'bollinger' in (chart_elements or []),
            'show_sma': 'sma' in (chart_elements or []),
            'show_ema': 'ema' in (chart_elements or []),
            'show_buy_sell_signals': 'signals' in (chart_elements or []),
            'selected_signals': selected_signals or [],
            'buy_signal_columns': buy_signals,
            'sell_signal_columns': sell_signals
        }

        series_data, series_types, series_options, series_markers = convert_df_to_tv_format(df, config, theme)
        if not series_data or not series_types:
            return html.Div("No series selected for TradingView", style={'color': theme['text_secondary']})
        chart_options = get_tv_chart_options(theme)

        return Tvlwc(
            chartOptions=chart_options,
            seriesData=series_data,
            seriesTypes=series_types,
            seriesOptions=series_options,
            seriesMarkers=series_markers,
            height=420,
            width='100%'
        )

    @app.callback(
        Output('tv-volume-chart', 'children'),
        [Input('data-loaded-store', 'data'),
         Input('plot-checklist', 'value'),
         Input('chart-library-toggle', 'value')]
    )
    def update_tv_volume_chart(data_loaded, selected_plots, chart_library):
        """Update the TradingView volume chart."""
        if chart_library != 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return html.Div()

        if 'volume' not in (selected_plots or []):
            return html.Div()

        df = dashboard_state.df
        series_data, series_type, series_options = convert_volume_to_tv_format(df, theme)
        chart_options = get_tv_chart_options(theme)

        return Tvlwc(
            chartOptions=chart_options,
            seriesData=[series_data],
            seriesTypes=[series_type],
            seriesOptions=[series_options],
            seriesMarkers=[[]],
            height=200,
            width='100%'
        )

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
         State('signal-logic-mode', 'value')]
    )
    def run_backtest_callback(n_clicks, ticker, initial_capital, buy_signals, sell_signals,
                               strategy_mode, amount_per_buy, position_size_pct, signal_logic):
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

        try:
            results = run_backtest(
                df, initial_capital, buy_signals, sell_signals,
                strategy_mode=strategy_mode,
                amount_per_buy=amount_per_buy,
                position_size_pct=position_size_pct,
                signal_logic=signal_logic or 'or'
            )
            backtest_results = create_backtest_results(results, ticker, initial_capital, buy_signals, sell_signals)
            dashboard_state.backtest_results = backtest_results

            # Calculate metrics
            total_return = backtest_results['total_return']
            is_positive = total_return >= 0

            return html.Div([
                build_alert("Backtest completed successfully!", "success", dismissable=False, theme=theme),
                html.Div([
                    build_metric_card("Portfolio Value", f"${backtest_results['final_portfolio_value']:,.2f}", None, theme),
                    build_metric_card("Total Return", f"{total_return:+.2f}%", is_positive, theme),
                    build_metric_card("Sharpe Ratio", f"{backtest_results['sharpe_ratio']:.2f}",
                                     backtest_results['sharpe_ratio'] > 1, theme),
                    build_metric_card("Max Drawdown", f"{backtest_results['max_drawdown']:.2f}%",
                                     backtest_results['max_drawdown'] > -20, theme),
                    build_metric_card("Win Rate", f"{backtest_results['win_rate']:.1f}%",
                                     backtest_results['win_rate'] > 50, theme),
                ], style={'marginTop': '12px'}),
            ], className='fade-in')

        except Exception as e:
            logger.error(f"Backtest error: {e}")
            return build_alert(f"Backtest failed: {str(e)[:60]}", "error", theme=theme)

    # ==================== OPTIMIZATION CALLBACKS ====================

    @app.callback(
        [Output('preview-buy-count', 'children'),
         Output('preview-sell-count', 'children'),
         Output('preview-combo-count', 'children')],
        [Input('data-loaded-store', 'data'),
         Input('max-signals-slider', 'value'),
         Input('max-combos-input', 'value')]
    )
    def update_signal_preview(data_loaded, max_signals, max_combos):
        """Show preview of available signals and estimated combinations."""
        if not data_loaded or dashboard_state.df is None:
            return "0", "0", "0"

        df = dashboard_state.df
        buy_signals, sell_signals = extract_signals(df)

        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        actual_combos = min(len(combinations), max_combos or 100)

        return str(len(buy_signals)), str(len(sell_signals)), str(actual_combos)

    @app.callback(
        [Output('optimization-state', 'data'),
         Output('optimization-interval', 'disabled'),
         Output('optimization-progress', 'children'),
         Output('run-optimization-btn', 'disabled'),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True)],
        [Input('run-optimization-btn', 'n_clicks')],
        [State('initial-capital', 'value'),
         State('max-signals-slider', 'value'),
         State('max-combos-input', 'value'),
         State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def start_optimization(n_clicks, initial_capital, max_signals, max_combos, current_state):
        """Initialize optimization run and enable interval for progress updates."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()
        df = dashboard_state.df

        if df is None:
            return (
                current_state,
                True,
                build_alert("Please load market data first", "warning", theme=theme),
                False,
                html.Div(),
                {'display': 'none'}
            )

        buy_signals, sell_signals = extract_signals(df)
        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        combinations = combinations[:max_combos]

        if not combinations:
            return (
                current_state,
                True,
                build_alert("No valid signal combinations found", "warning", theme=theme),
                False,
                html.Div(),
                {'display': 'none'}
            )

        # Convert tuples to lists for JSON serialization
        combinations_serializable = [[list(buy), list(sell)] for buy, sell in combinations]

        # Reset state in dashboard_state
        dashboard_state.reset_optimization()
        dashboard_state.update_optimization_state(
            running=True,
            total_combinations=len(combinations),
            combinations=combinations_serializable,
            initial_capital=initial_capital
        )

        new_state = {
            'running': True,
            'current_index': 0,
            'total_combinations': len(combinations),
            'completed': False,
            'sort_by': 'Total_Return_%',
            'sort_ascending': False
        }

        progress_ui = html.Div([
            build_progress_bar(0, f"Testing 0/{len(combinations)} combinations...", theme=theme),
            html.Div("Starting optimization...",
                     style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginTop': '4px'})
        ])

        return (
            new_state,
            False,  # Enable interval
            progress_ui,
            True,   # Disable button
            html.Div(),  # Clear previous results
            {'display': 'none'}  # Hide apply button
        )

    @app.callback(
        [Output('optimization-state', 'data', allow_duplicate=True),
         Output('optimization-progress', 'children', allow_duplicate=True),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('optimization-interval', 'disabled', allow_duplicate=True),
         Output('run-optimization-btn', 'disabled', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True),
         Output('optimization-results-store', 'data')],
        [Input('optimization-interval', 'n_intervals')],
        [State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def process_optimization_batch(n_intervals, state):
        """Process a batch of combinations on each interval tick."""
        theme = get_theme()

        if not state or not state.get('running'):
            raise PreventUpdate

        df = dashboard_state.df
        if df is None:
            raise PreventUpdate

        opt_state = dashboard_state.optimization_state
        current_idx = opt_state.get('current_index', 0)
        total = opt_state.get('total_combinations', 0)
        combinations = opt_state.get('combinations', [])
        results = opt_state.get('results', [])
        initial_capital = opt_state.get('initial_capital', 10000)

        if not combinations or current_idx >= total:
            raise PreventUpdate

        # Process batch
        end_idx = min(current_idx + OPTIMIZATION_BATCH_SIZE, total)

        for i in range(current_idx, end_idx):
            buy_combo, sell_combo = combinations[i]
            result = evaluate_signal_combination(df, initial_capital, tuple(buy_combo), tuple(sell_combo))
            results.append(result)

        # Update state
        dashboard_state.update_optimization_state(
            current_index=end_idx,
            results=results
        )

        progress_pct = int((end_idx / total) * 100)

        # Check if complete
        if end_idx >= total:
            dashboard_state.update_optimization_state(running=False, completed=True)

            results_df = pd.DataFrame(results)
            if 'Total_Return_%' in results_df.columns:
                results_df = results_df[results_df['Total_Return_%'].notna()]
                results_df = results_df.sort_values(state.get('sort_by', 'Total_Return_%'),
                                                    ascending=state.get('sort_ascending', False))

            if results_df.empty:
                state['running'] = False
                state['completed'] = True
                return (
                    state,
                    build_alert("All combinations failed", "warning", theme=theme),
                    html.Div(),
                    True,
                    False,
                    {'display': 'none'},
                    []
                )

            state['running'] = False
            state['completed'] = True

            final_progress = html.Div([
                html.Span("\u2713 ", style={'color': theme['accent_green']}),
                html.Span(f"Completed! Tested {total} combinations",
                         style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_green']})
            ])

            results_ui = html.Div([
                _create_best_strategy_highlight(results_df.iloc[0], theme),
                _create_optimization_table(results_df.head(10), theme),
            ], className='fade-in')

            return (
                state,
                final_progress,
                results_ui,
                True,   # Disable interval
                False,  # Re-enable button
                {'display': 'block'},  # Show apply button
                results_df.to_dict('records')
            )

        # Still processing - update progress
        state['current_index'] = end_idx

        progress_ui = html.Div([
            build_progress_bar(progress_pct, f"Testing {end_idx}/{total} combinations...", theme=theme),
            html.Div(f"Found {len([r for r in results if 'Total_Return_%' in r])} valid strategies so far...",
                     style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginTop': '4px'})
        ])

        # Show partial results (top 5 so far)
        valid_results = [r for r in results if 'Total_Return_%' in r]
        partial_results = html.Div()
        if len(valid_results) >= 5:
            partial_df = pd.DataFrame(valid_results).sort_values('Total_Return_%', ascending=False).head(5)
            partial_results = html.Div([
                html.Div("Top strategies so far:",
                        style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '8px'}),
                _create_optimization_table_mini(partial_df, theme)
            ], style={'marginTop': '12px'})

        return (
            state,
            progress_ui,
            partial_results,
            False,  # Keep interval enabled
            True,   # Keep button disabled
            {'display': 'none'},
            []
        )

    @app.callback(
        Output('optimization-results', 'children', allow_duplicate=True),
        [Input('sort-metric-dropdown', 'value')],
        [State('optimization-results-store', 'data'),
         State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def sort_optimization_results(sort_by, results_data, state):
        """Re-sort results when sort metric changes."""
        if not results_data or not state.get('completed'):
            raise PreventUpdate

        theme = get_theme()
        results_df = pd.DataFrame(results_data)

        # Ascending for drawdown (less negative is better), descending for others
        ascending = sort_by == 'Max_Drawdown_%'
        results_df = results_df.sort_values(sort_by, ascending=ascending)

        return html.Div([
            _create_best_strategy_highlight(results_df.iloc[0], theme),
            _create_optimization_table(results_df.head(10), theme),
        ], className='fade-in')

    @app.callback(
        [Output('buy-signals', 'value', allow_duplicate=True),
         Output('sell-signals', 'value', allow_duplicate=True),
         Output('tab-backtest', 'n_clicks', allow_duplicate=True)],
        [Input('apply-strategy-btn', 'n_clicks')],
        [State('optimization-results-store', 'data'),
         State('sort-metric-dropdown', 'value'),
         State('tab-backtest', 'n_clicks')],
        prevent_initial_call=True
    )
    def apply_best_strategy(n_clicks, results_data, sort_by, current_backtest_clicks):
        """Apply the best strategy from optimization to the backtest panel."""
        if not n_clicks or not results_data:
            raise PreventUpdate

        results_df = pd.DataFrame(results_data)
        ascending = sort_by == 'Max_Drawdown_%'
        results_df = results_df.sort_values(sort_by, ascending=ascending)

        best = results_df.iloc[0]

        # Parse signal strings back to lists
        buy_signals = [s.strip() for s in str(best['Buy_Signals']).split(',') if s.strip()]
        sell_signals_str = str(best.get('Sell_Signals', ''))
        sell_signals = [s.strip() for s in sell_signals_str.split(',') if s.strip()]

        # Return values to populate checklists and switch to backtest tab
        return buy_signals, sell_signals, (current_backtest_clicks or 0) + 1

    # ==================== END OPTIMIZATION CALLBACKS ====================

    @app.callback(
        [Output('panel-backtest', 'style'),
         Output('panel-optimizer', 'style'),
         Output('panel-data', 'style'),
         Output('tab-backtest', 'style'),
         Output('tab-optimizer', 'style'),
         Output('tab-data', 'style')],
        [Input('tab-backtest', 'n_clicks'),
         Input('tab-optimizer', 'n_clicks'),
         Input('tab-data', 'n_clicks')]
    )
    def switch_panel(backtest_clicks, optimizer_clicks, data_clicks):
        """Switch between right panel tabs."""
        theme = get_theme()
        styles = get_styles(theme)

        ctx = callback_context
        if not ctx.triggered:
            # Default to backtest tab
            return (
                {'display': 'block'},
                {'display': 'none'},
                {'display': 'none'},
                {**styles['tab'], **styles['tab_active']},
                styles['tab'],
                styles['tab']
            )

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'tab-backtest':
            return (
                {'display': 'block'},
                {'display': 'none'},
                {'display': 'none'},
                {**styles['tab'], **styles['tab_active']},
                styles['tab'],
                styles['tab']
            )
        elif button_id == 'tab-optimizer':
            return (
                {'display': 'none'},
                {'display': 'block'},
                {'display': 'none'},
                styles['tab'],
                {**styles['tab'], **styles['tab_active']},
                styles['tab']
            )
        else:  # tab-data
            return (
                {'display': 'none'},
                {'display': 'none'},
                {'display': 'block'},
                styles['tab'],
                styles['tab'],
                {**styles['tab'], **styles['tab_active']}
            )

    @app.callback(
        Output('header-status', 'children'),
        [Input('startup-interval', 'n_intervals')]
    )
    def update_header_status(_):
        """Update header status."""
        return datetime.now().strftime("%H:%M:%S")

    @app.callback(
        [Output('theme-store', 'data'),
         Output('theme-label', 'children')],
        [Input('theme-toggle', 'n_clicks')],
        [State('theme-store', 'data')]
    )
    def toggle_theme(n_clicks, current_theme):
        """Toggle between dark and light themes."""
        if not n_clicks:
            return DEFAULT_THEME, "\u2600\ufe0f"

        new_theme = 'light' if current_theme == 'dark' else 'dark'
        icon = "\U0001f319" if new_theme == 'light' else "\u2600\ufe0f"
        dashboard_state.set_theme(new_theme)
        return new_theme, icon

    # Register clientside callback for keyboard shortcuts
    app.clientside_callback(
        """
        function(id) {
            document.addEventListener('keydown', function(e) {
                // Ctrl+Enter to load data
                if (e.ctrlKey && e.key === 'Enter') {
                    var loadBtn = document.getElementById('load-data-button');
                    if (loadBtn) {
                        loadBtn.click();
                    }
                }
                // Ctrl+B to run backtest
                if (e.ctrlKey && e.key === 'b') {
                    e.preventDefault();
                    var backtestBtn = document.getElementById('run-backtest-btn');
                    if (backtestBtn) {
                        backtestBtn.click();
                    }
                }
                // Escape to close any modals/alerts
                if (e.key === 'Escape') {
                    var alerts = document.querySelectorAll('.alert-dismissible .btn-close');
                    alerts.forEach(function(btn) { btn.click(); });
                }
            });
            return window.dash_clientside.no_update;
        }
        """,
        Output('keyboard-listener', 'children'),
        Input('startup-interval', 'n_intervals')
    )


# Helper functions for callbacks

def _create_data_table(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create a styled data table."""
    return dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in display_df.columns],
        data=display_df.to_dict('records'),
        style_table={'height': '400px', 'overflowY': 'auto'},
        style_cell={
            'textAlign': 'right',
            'padding': '8px',
            'backgroundColor': theme['bg_tertiary'],
            'color': theme['text_primary'],
            'border': f'1px solid {theme["border_secondary"]}',
            'fontSize': '11px',
            'fontFamily': FONT_MONO,
        },
        style_header={
            'fontWeight': '600',
            'backgroundColor': theme['bg_secondary'],
            'color': theme['text_secondary'],
            'textTransform': 'uppercase',
            'fontSize': '10px',
        },
        style_data_conditional=[
            {'if': {'row_index': 'odd'}, 'backgroundColor': theme['table_row_alt']}
        ],
        page_size=50,
        fixed_rows={'headers': True}
    )


def _create_price_subtitle(df: pd.DataFrame, theme: dict) -> html.Span:
    """Create price change subtitle."""
    latest_close = df['Close'].iloc[-1]
    prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
    change = latest_close - prev_close
    change_pct = (change / prev_close) * 100
    change_color = theme['accent_green'] if change >= 0 else theme['accent_red']
    change_sign = '+' if change >= 0 else ''

    return html.Span([
        html.Span(f"${latest_close:.2f}", style={'fontFamily': FONT_MONO, 'color': theme['text_primary']}),
        html.Span(f" {change_sign}{change:.2f} ({change_sign}{change_pct:.2f}%)",
                 style={'fontFamily': FONT_MONO, 'color': change_color, 'marginLeft': '8px'}),
    ])


def _create_optimization_table(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create enhanced optimization results table with all columns."""
    columns = ['Buy_Signals', 'Sell_Signals', 'Total_Return_%', 'Sharpe_Ratio', 'Max_Drawdown_%', 'Trades']
    available_cols = [c for c in columns if c in display_df.columns]

    return dash_table.DataTable(
        id='optimization-table',
        columns=[{"name": c.replace('_', ' '), "id": c} for c in available_cols],
        data=display_df[available_cols].round(2).to_dict('records'),
        style_cell={
            'textAlign': 'left',
            'padding': '8px',
            'backgroundColor': theme['bg_tertiary'],
            'color': theme['text_primary'],
            'fontSize': '11px',
            'border': f'1px solid {theme["border_secondary"]}',
            'maxWidth': '150px',
            'overflow': 'hidden',
            'textOverflow': 'ellipsis',
        },
        style_header={
            'fontWeight': '600',
            'backgroundColor': theme['bg_secondary'],
            'fontSize': '10px',
            'textTransform': 'uppercase',
        },
        style_data_conditional=[
            {'if': {'row_index': 0}, 'backgroundColor': f'{theme["accent_green"]}15'},
            {'if': {'row_index': 1}, 'backgroundColor': f'{theme["accent_blue"]}10'},
            {'if': {'row_index': 2}, 'backgroundColor': f'{theme["accent_blue"]}05'},
        ],
        page_size=10,
    )


def _create_optimization_table_mini(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create compact mini-table for partial results during optimization."""
    return dash_table.DataTable(
        columns=[
            {"name": "Buy Signals", "id": "Buy_Signals"},
            {"name": "Return %", "id": "Total_Return_%"},
        ],
        data=display_df[['Buy_Signals', 'Total_Return_%']].round(1).to_dict('records'),
        style_cell={
            'textAlign': 'left',
            'padding': '4px 6px',
            'backgroundColor': theme['bg_tertiary'],
            'color': theme['text_primary'],
            'fontSize': '10px',
            'border': 'none',
        },
        style_header={'display': 'none'},
    )


def _create_best_strategy_highlight(best_row: pd.Series, theme: dict) -> html.Div:
    """Create highlight card for the best strategy."""
    total_return = best_row.get('Total_Return_%', 0)
    sharpe = best_row.get('Sharpe_Ratio', 0)
    drawdown = best_row.get('Max_Drawdown_%', 0)

    return html.Div([
        html.Div([
            html.Span("\U0001f3c6 ", style={'fontSize': '16px'}),
            html.Span("Best Strategy", style={
                'color': theme['text_secondary'],
                'fontSize': FONT_SIZES['sm'],
                'fontWeight': '600'
            }),
        ], style={'marginBottom': '8px'}),
        html.Div([
            html.Div([
                html.Span("Buy: ", style={'color': theme['text_secondary'], 'fontSize': FONT_SIZES['xs']}),
                html.Span(str(best_row.get('Buy_Signals', '')), style={
                    'color': theme['accent_green'],
                    'fontSize': FONT_SIZES['xs']
                }),
            ], style={'marginBottom': '4px'}),
            html.Div([
                html.Span("Sell: ", style={'color': theme['text_secondary'], 'fontSize': FONT_SIZES['xs']}),
                html.Span(str(best_row.get('Sell_Signals', '')), style={
                    'color': theme['accent_red'],
                    'fontSize': FONT_SIZES['xs']
                }),
            ], style={'marginBottom': '8px'}),
            html.Div([
                html.Span(f"{total_return:+.1f}% return", style={
                    'color': theme['accent_green'] if total_return > 0 else theme['accent_red'],
                    'fontWeight': '600',
                    'fontSize': FONT_SIZES['base'],
                    'fontFamily': FONT_MONO
                }),
                html.Span(f" | Sharpe: {sharpe:.2f}", style={
                    'color': theme['text_secondary'],
                    'fontSize': FONT_SIZES['xs'],
                    'marginLeft': '8px'
                }),
                html.Span(f" | DD: {drawdown:.1f}%", style={
                    'color': theme['text_secondary'],
                    'fontSize': FONT_SIZES['xs'],
                    'marginLeft': '8px'
                }),
            ]),
        ]),
    ], style={
        'backgroundColor': theme['bg_tertiary'],
        'padding': '12px',
        'borderRadius': '6px',
        'marginBottom': '12px',
        'border': f'1px solid {theme["accent_green"]}40'
    })


# Batch size for optimization processing (combinations per interval tick)
OPTIMIZATION_BATCH_SIZE = 5
