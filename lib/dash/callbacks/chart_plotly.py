"""
Plotly chart callbacks.
"""

from datetime import datetime

import pandas as pd
from dash import html, callback_context
from dash.dcc.express import send_data_frame
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate

from lib.dash.chart_builder import create_chart, create_empty_chart
from lib.dash.components import ticker_pill
from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS, FONT_SIZES, FONT_FAMILY, get_theme
from lib.dash.state import dashboard_state
from lib.dash.callbacks.shared import (
    _collect_selected_plots,
    _build_plot_toggle_values,
    _rebuild_indicator_dataframe,
    get_enriched,
    _normalize_timestamp,
    _compute_y_ranges_by_axis,
    _pad_range,
    _axis_layout_key,
    _apply_layout_updates,
    _compute_trigger_counts,
    _resolve_x_range,
)


def register_plotly_callbacks(app) -> None:
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
        Output('chart-library-toggle', 'value'),
        [Input({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         Input('chart-elements-checklist', 'value'),
         Input('preset-apply-store', 'data')],
        [State('chart-library-toggle', 'value')]
    )
    def resolve_chart_library(plot_values, chart_elements, preset_data, current_library):
        """Ensure Plotly is used when indicators/overlays are requested."""
        ctx = callback_context
        if getattr(ctx, "triggered_id", None) == 'preset-apply-store' and preset_data:
            requested = preset_data.get("chart", {}).get("chart_library")
            if requested:
                return requested
        return 'plotly'

    @app.callback(
        Output('financial-chart', 'figure'),
        [Input('data-loaded-store', 'data'),
         Input({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('chart-library-toggle', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('consecutive-signal-mode', 'value'),
         Input('signal-cooldown-bars', 'value'),
         Input('signal-logic-mode', 'value'),
         Input('signal-window', 'value'),
         Input('indicator-settings-store', 'data')],
        [State('ticker-dropdown', 'value'),
         State('layout-store', 'data')]
    )
    def update_plotly_chart(data_loaded, plot_values, chart_elements, selected_signals, chart_library,
                            buy_signals, sell_signals, consecutive_signal_mode, signal_cooldown_bars,
                            signal_logic, signal_window, indicator_settings, ticker, layout_state):
        """Update the Plotly financial chart."""
        if chart_library == 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return create_empty_chart(theme)

        df = get_enriched(dashboard_state.df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)

        buy_signals = buy_signals or []
        sell_signals = sell_signals or []

        config = {
            'selected_plots': _collect_selected_plots(plot_values) or ['candlestick'],
            'show_candlesticks': 'candlesticks' in (chart_elements or []),
            'show_bollinger': 'bollinger' in (chart_elements or []),
            'show_sma': 'sma' in (chart_elements or []),
            'show_ema': 'ema' in (chart_elements or []),
            'show_buy_sell_signals': 'signals' in (chart_elements or []),
            'show_legend': 'legend' in (chart_elements or []),
            'selected_signals': selected_signals or [],
            'buy_signal_columns': buy_signals,
            'sell_signal_columns': sell_signals,
            'consecutive_signal_mode': consecutive_signal_mode or 'scale_in',
            'cooldown_bars': signal_cooldown_bars or 0,
            'signal_logic': signal_logic or 'or',
            'signal_window': signal_window or 0,
            'title': '',
            'indicator_settings': indicator_settings or DEFAULT_INDICATOR_SETTINGS,
        }

        fig = create_chart(df, config, theme)
        if layout_state and layout_state.get('x_range'):
            fig.update_xaxes(range=layout_state['x_range'], autorange=False)
            x_start = _normalize_timestamp(layout_state['x_range'][0])
            x_end = _normalize_timestamp(layout_state['x_range'][1])
            if x_start and x_end:
                axis_ranges = _compute_y_ranges_by_axis(fig, x_start, x_end, df)
                layout_updates = {}
                for axis_id, (y_min, y_max) in axis_ranges.items():
                    padded_min, padded_max = _pad_range(y_min, y_max)
                    axis_key = _axis_layout_key(axis_id)
                    layout_updates[axis_key] = {'range': [padded_min, padded_max], 'autorange': False}
                _apply_layout_updates(fig, layout_updates)
        elif layout_state and layout_state.get('autorange'):
            fig.update_xaxes(autorange=True)

        return fig

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

    @app.callback(
        Output('layout-store', 'data'),
        [Input('financial-chart', 'relayoutData')],
        [State('layout-store', 'data')],
        prevent_initial_call=True
    )
    def persist_timeframe(relayout_data, current_layout):
        """Persist selected timeframe so chart refresh keeps x-range."""
        if not relayout_data:
            raise PreventUpdate

        layout_state = current_layout or {}
        if 'xaxis.range[0]' in relayout_data or 'xaxis.range[1]' in relayout_data:
            start = relayout_data.get('xaxis.range[0]')
            end = relayout_data.get('xaxis.range[1]')
            current_range = layout_state.get('x_range') or [None, None]
            if start is None:
                start = current_range[0]
            if end is None:
                end = current_range[1]
            if start is not None and end is not None:
                layout_state['x_range'] = [start, end]
                layout_state['autorange'] = False
                return layout_state
            layout_state['autorange'] = False
        if 'xaxis.range' in relayout_data and isinstance(relayout_data['xaxis.range'], list):
            layout_state['x_range'] = relayout_data['xaxis.range'][:2]
            layout_state['autorange'] = False
            return layout_state
        if relayout_data.get('xaxis.autorange') is True:
            layout_state['x_range'] = None
            layout_state['autorange'] = True
            return layout_state

        raise PreventUpdate

    @app.callback(
        Output('financial-chart', 'figure', allow_duplicate=True),
        [Input('financial-chart', 'relayoutData')],
        [State('financial-chart', 'figure'),
         State('chart-library-toggle', 'value')],
        prevent_initial_call=True
    )
    def autoscale_chart_to_timerange(relayout_data, fig, chart_library):
        """Autoscale y-axes to the visible x-axis timeframe."""
        if chart_library == 'tradingview':
            raise PreventUpdate
        if not relayout_data or not fig or dashboard_state.df is None:
            raise PreventUpdate

        df = dashboard_state.df
        x_range = _resolve_x_range(relayout_data, df, fig)
        if not x_range:
            raise PreventUpdate

        x_start, x_end = x_range
        axis_ranges = _compute_y_ranges_by_axis(fig, x_start, x_end, df)
        if not axis_ranges:
            raise PreventUpdate

        layout_updates = {}
        for axis_id, (y_min, y_max) in axis_ranges.items():
            padded_min, padded_max = _pad_range(y_min, y_max)
            axis_key = _axis_layout_key(axis_id)
            layout_updates[axis_key] = {'range': [padded_min, padded_max], 'autorange': False}
        _apply_layout_updates(fig, layout_updates)

        return fig
