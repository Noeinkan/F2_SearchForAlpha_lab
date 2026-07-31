"""
Plotly chart callbacks — single figure writer for sidebar-driven updates.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
from dash import html
from dash.dcc.express import send_data_frame
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate

from lib.dash.bootstrap import build_default_chart_config
from lib.dash.chart_builder import create_chart, create_empty_chart
from lib.dash.components import ticker_pill
from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS, get_theme
from lib.dash.state import dashboard_state
from lib.dash.callbacks.shared import (
    _collect_selected_plots,
    _build_plot_toggle_values,
    _compute_trigger_counts,
    get_enriched,
)

logger = logging.getLogger(__name__)


def _build_chart_config(
    plot_values,
    chart_elements,
    selected_signals,
    buy_signals,
    sell_signals,
    consecutive_signal_mode,
    signal_cooldown_bars,
    signal_logic,
    signal_window,
    indicator_settings,
) -> dict:
    """Assemble the chart config dict from current sidebar state."""
    defaults = build_default_chart_config(indicator_settings or DEFAULT_INDICATOR_SETTINGS)
    chart_elements = (
        chart_elements
        if chart_elements is not None
        else ['candlesticks', 'signals', 'bollinger']
    )
    selected_plots = _collect_selected_plots(plot_values) or defaults['selected_plots']
    return {
        'selected_plots': selected_plots,
        'show_candlesticks': 'candlesticks' in chart_elements,
        'show_bollinger': 'bollinger' in chart_elements,
        'show_sma': 'sma' in chart_elements,
        'show_ema': 'ema' in chart_elements,
        'show_buy_sell_signals': 'signals' in chart_elements,
        'show_legend': 'legend' in chart_elements,
        'selected_signals': selected_signals or [],
        'buy_signal_columns': buy_signals or [],
        'sell_signal_columns': sell_signals or [],
        'consecutive_signal_mode': consecutive_signal_mode or 'scale_in',
        'cooldown_bars': signal_cooldown_bars or 0,
        'signal_logic': signal_logic or 'or',
        'signal_window': signal_window or 0,
        'title': '',
        'indicator_settings': indicator_settings or DEFAULT_INDICATOR_SETTINGS,
    }


def register_plotly_callbacks(app) -> None:
    @app.callback(
        [Output({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         Output('chart-elements-checklist', 'value'),
         Output('signal-checklist', 'value')],
        [Input('preset-apply-store', 'data')],
        prevent_initial_call=True
    )
    def apply_chart_preset(preset_data):
        if not preset_data:
            raise PreventUpdate
        chart = preset_data.get("chart", {})
        plot_values = _build_plot_toggle_values(chart.get("plot_toggles", []))
        return plot_values, chart.get("chart_elements", []), chart.get("signal_checklist", [])

    @app.callback(
        Output('financial-chart', 'figure', allow_duplicate=True),
        [Input('data-loaded-store', 'data'),
         Input({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('consecutive-signal-mode', 'value'),
         Input('signal-cooldown-bars', 'value'),
         Input('signal-logic-mode', 'value'),
         Input('signal-window', 'value'),
         Input('indicator-settings-store', 'data')],
        prevent_initial_call='initial_duplicate',
    )
    def update_chart(
        data_loaded,
        plot_values,
        chart_elements,
        selected_signals,
        buy_signals,
        sell_signals,
        consecutive_signal_mode,
        signal_cooldown_bars,
        signal_logic,
        signal_window,
        indicator_settings,
    ):
        """Rebuild the financial chart from sidebar selections / data loads."""
        if not data_loaded or dashboard_state.df is None:
            raise PreventUpdate

        theme = get_theme()
        try:
            df = get_enriched(dashboard_state.df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
            config = _build_chart_config(
                plot_values,
                chart_elements,
                selected_signals,
                buy_signals,
                sell_signals,
                consecutive_signal_mode,
                signal_cooldown_bars,
                signal_logic,
                signal_window,
                indicator_settings,
            )
            return create_chart(df, config, theme)
        except Exception as exc:
            logger.error("update_chart failed: %s", exc)
            return create_empty_chart(theme, f"Chart error: {str(exc)[:50]}")

    @app.callback(
        Output('signal-count-bar', 'children'),
        [Input('data-loaded-store', 'data'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('consecutive-signal-mode', 'value'),
         Input('signal-cooldown-bars', 'value'),
         Input('signal-logic-mode', 'value'),
         Input('signal-window', 'value'),
         Input('indicator-settings-store', 'data')]
    )
    def update_signal_count_bar(
        data_loaded,
        chart_elements,
        selected_signals,
        buy_signals,
        sell_signals,
        consecutive_signal_mode,
        signal_cooldown_bars,
        signal_logic,
        signal_window,
        indicator_settings
    ):
        theme = get_theme()
        if not data_loaded or dashboard_state.df is None:
            return html.Div([
                ticker_pill('TRIG', '--', color='amber'),
                html.Span('|', className='num', style={'color': theme['border_primary']}),
                ticker_pill('REJ', '--', color='down'),
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'})

        df = get_enriched(dashboard_state.df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)

        counts = _compute_trigger_counts(
            df,
            selected_signals or [],
            buy_signals or [],
            sell_signals or [],
            signal_logic or 'or',
            signal_window or 0,
            consecutive_signal_mode or 'scale_in',
            signal_cooldown_bars or 0
        )

        return html.Div([
            ticker_pill('TRIG', counts['accepted'], color='amber'),
            html.Span('|', className='num', style={'color': theme['border_primary']}),
            ticker_pill('REJ', counts['rejected'], color='down'),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'})

    @app.callback(
        Output('download-csv', 'data'),
        [Input('export-csv-btn', 'n_clicks')],
        [State('data-loaded-store', 'data'),
         State('ticker-dropdown', 'value')],
        prevent_initial_call=True
    )
    def export_chart_csv(n_clicks, data_loaded, ticker):
        """Export current chart data (with indicators) to CSV."""
        if not data_loaded or dashboard_state.df is None:
            raise PreventUpdate

        df = dashboard_state.df.copy()
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index().rename(columns={'index': 'Date'})
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            cols = ['Date'] + [col for col in df.columns if col != 'Date']
            df = df.loc[:, cols]

        export_date = datetime.now().strftime('%Y%m%d')
        safe_ticker = (ticker or 'data').replace('/', '-')
        filename = f"{safe_ticker}_chart_data_{export_date}.csv"
        return send_data_frame(df.to_csv, filename, index=False, float_format='%.6f')
