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
    DEFAULT_THEME, FONT_SIZES, FONT_MONO, get_theme
)
from lib.dash.state import dashboard_state
from lib.dash.styles import get_styles
from lib.dash.chart_builder import create_chart, create_empty_chart
from lib.dash.tv_chart_builder import (
    convert_df_to_tv_format,
    convert_volume_to_tv_format,
    get_tv_chart_options
)
from lib.dash.components import build_alert, build_metric_card
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
        [Input('strategy-mode', 'value')]
    )
    def toggle_strategy_options(strategy_mode):
        """Show/hide mode-specific options based on selected strategy mode."""
        accumulation_style = {
            'marginBottom': '16px',
            'display': 'block' if strategy_mode == 'accumulation' else 'none'
        }
        rebalancing_style = {
            'marginBottom': '16px',
            'display': 'block' if strategy_mode == 'rebalancing' else 'none'
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
        Output('financial-chart', 'figure'),
        [Input('data-loaded-store', 'data'),
         Input('plot-checklist', 'value'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('chart-library-toggle', 'value')],
        [State('ticker-dropdown', 'value')]
    )
    def update_plotly_chart(data_loaded, selected_plots, chart_elements, selected_signals, chart_library, ticker):
        """Update the Plotly financial chart."""
        if chart_library == 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return create_empty_chart(theme)

        df = dashboard_state.df

        config = {
            'selected_plots': selected_plots or ['candlestick'],
            'show_candlesticks': 'candlesticks' in (chart_elements or []),
            'show_bollinger': 'bollinger' in (chart_elements or []),
            'show_sma': 'sma' in (chart_elements or []),
            'show_ema': 'ema' in (chart_elements or []),
            'show_buy_sell_signals': 'signals' in (chart_elements or []),
            'show_legend': 'legend' in (chart_elements or []),
            'selected_signals': selected_signals or [],
            'title': '',
        }

        return create_chart(df, config, theme)

    @app.callback(
        Output('tv-main-chart', 'children'),
        [Input('data-loaded-store', 'data'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('chart-library-toggle', 'value')],
        [State('ticker-dropdown', 'value')]
    )
    def update_tv_main_chart(data_loaded, chart_elements, selected_signals, chart_library, ticker):
        """Update the TradingView main chart."""
        if chart_library != 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return html.Div("Load data to view chart", style={'color': theme['text_secondary']})

        df = dashboard_state.df

        config = {
            'show_candlesticks': 'candlesticks' in (chart_elements or []),
            'show_bollinger': 'bollinger' in (chart_elements or []),
            'show_sma': 'sma' in (chart_elements or []),
            'show_ema': 'ema' in (chart_elements or []),
            'show_buy_sell_signals': 'signals' in (chart_elements or []),
            'selected_signals': selected_signals or []
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
         State('position-size-pct', 'value')]
    )
    def run_backtest_callback(n_clicks, ticker, initial_capital, buy_signals, sell_signals,
                               strategy_mode, amount_per_buy, position_size_pct):
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
                position_size_pct=position_size_pct
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

    @app.callback(
        Output('optimization-results', 'children'),
        [Input('run-optimization-btn', 'n_clicks')],
        [State('initial-capital', 'value'),
         State('max-signals-slider', 'value'),
         State('max-combos-input', 'value')]
    )
    def run_optimization_callback(n_clicks, initial_capital, max_signals, max_combos):
        """Run signal combination optimization."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()

        df = dashboard_state.df
        if df is None:
            return build_alert("Please load market data first", "warning", theme=theme)

        try:
            results_df = _run_combo_optimization(df, initial_capital, max_signals, max_combos)

            if results_df.empty:
                return build_alert("No valid signal combinations found", "warning", theme=theme)

            display_df = results_df.head(10).round(2)
            best_return = display_df.iloc[0]['Total_Return_%']

            return html.Div([
                build_alert(f"Tested {len(results_df)} combinations successfully!", "success", dismissable=False, theme=theme),
                html.Div([
                    # Best result highlight
                    html.Div([
                        html.Span("\U0001f3c6 ", style={'fontSize': '16px'}),
                        html.Span("Best Strategy: ", style={'color': theme['text_secondary'], 'fontSize': FONT_SIZES['sm']}),
                        html.Span(f"{best_return:+.1f}% return", style={
                            'color': theme['accent_green'] if best_return > 0 else theme['accent_red'],
                            'fontWeight': '600',
                            'fontSize': FONT_SIZES['base'],
                            'fontFamily': FONT_MONO
                        }),
                    ], style={
                        'backgroundColor': theme['bg_tertiary'],
                        'padding': '12px',
                        'borderRadius': '6px',
                        'marginBottom': '12px',
                        'border': f'1px solid {theme["accent_green"]}40'
                    }),
                    _create_optimization_table(display_df, theme),
                ], style={'marginTop': '8px'}),
            ], className='fade-in')

        except Exception as e:
            logger.error(f"Optimization error: {e}")
            return build_alert(f"Optimization failed: {str(e)[:60]}", "error", theme=theme)

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
    """Create optimization results table."""
    return dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in ['Buy_Signals', 'Total_Return_%', 'Sharpe_Ratio']],
        data=display_df[['Buy_Signals', 'Total_Return_%', 'Sharpe_Ratio']].to_dict('records'),
        style_cell={
            'textAlign': 'left',
            'padding': '8px',
            'backgroundColor': theme['bg_tertiary'],
            'color': theme['text_primary'],
            'fontSize': '11px',
            'border': f'1px solid {theme["border_secondary"]}',
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
    )


def _run_combo_optimization(df: pd.DataFrame, initial_capital: float,
                            max_signals: int = 3, max_combinations: int = 100) -> pd.DataFrame:
    """Run signal combination optimization."""
    import itertools
    import numpy as np

    buy_signals, sell_signals = extract_signals(df)
    combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
    combinations = combinations[:max_combinations]

    results = []
    for buy_combo, sell_combo in combinations:
        result = evaluate_signal_combination(df, initial_capital, buy_combo, sell_combo)
        results.append(result)

    results_df = pd.DataFrame(results)
    if 'Total_Return_%' in results_df.columns:
        results_df = results_df.sort_values('Total_Return_%', ascending=False)
    return results_df
