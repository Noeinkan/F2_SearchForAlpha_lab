"""
TradingView chart callbacks.
"""

from dash import html
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate

# TradingView lightweight chart wrapper is optional. Provide a fallback so
# callbacks can still run when the package is not installed.
try:
    from dash_tvlwc import Tvlwc
except Exception:
    def Tvlwc(*args, **kwargs):
        return html.Div("TradingView component not installed. Install 'dash-tvlwc' to enable.", style={'color': '#888'})

from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS, get_theme
from lib.dash.overlay_registry import build_overlay_visibility
from lib.dash.state import dashboard_state
from lib.dash.tv_chart_builder import (
    convert_df_to_tv_format,
    convert_volume_to_tv_format,
    get_tv_chart_options
)
from lib.dash.callbacks.shared import _collect_selected_plots, _rebuild_indicator_dataframe


def register_tv_callbacks(app) -> None:
    @app.callback(
        Output('tv-main-chart', 'children'),
        [Input('data-loaded-store', 'data'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('chart-library-toggle', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('indicator-settings-store', 'data')],
        [State('ticker-dropdown', 'value')]
    )
    def update_tv_main_chart(data_loaded, chart_elements, selected_signals, chart_library,
                             buy_signals, sell_signals, indicator_settings, ticker):
        """Update the TradingView main chart."""
        if chart_library != 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return html.Div("Load data to view chart", style={'color': theme['text_secondary']})

        df = dashboard_state.df
        df = df.copy()
        df = _rebuild_indicator_dataframe(df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
        dashboard_state.df = df

        buy_signals = buy_signals or []
        sell_signals = sell_signals or []

        config = {
            'show_candlesticks': 'candlesticks' in (chart_elements or []),
            'overlay_visibility': build_overlay_visibility(chart_elements),
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
         Input({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         Input('chart-library-toggle', 'value')]
    )
    def update_tv_volume_chart(data_loaded, plot_values, chart_library):
        """Update the TradingView volume chart."""
        if chart_library != 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return html.Div()

        selected_plots = _collect_selected_plots(plot_values)
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
