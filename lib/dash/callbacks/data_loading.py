"""
Data loading callbacks.
"""

import logging

from dash import callback_context, html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS, FONT_SIZES, get_theme
from lib.dash.helpers import fetch_data_with_cache, format_df_for_display
from lib.dash.state import dashboard_state
from lib.signals.indicators import add_indicators, generate_signals
from lib.dash.callbacks.shared import (
    _build_signal_options,
    _build_unified_signal_rows,
    _create_data_table,
    _create_price_subtitle,
)

logger = logging.getLogger(__name__)


def register_data_loading_callbacks(app) -> None:
    @app.callback(
        [Output('ticker-dropdown', 'value'),
         Output('start-date', 'date'),
         Output('end-date', 'date'),
         Output('initial-capital', 'value')],
        [Input('preset-apply-store', 'data')],
        prevent_initial_call=True
    )
    def apply_market_preset(preset_data):
        if not preset_data:
            raise PreventUpdate

        market = preset_data.get("market_data", {})
        return (
            market.get("ticker"),
            market.get("start_date"),
            market.get("end_date"),
            market.get("initial_capital"),
        )

    @app.callback(
        [Output('data-status', 'children'),
         Output('data-loaded-store', 'data'),
         Output('buy-signals', 'options'),
         Output('sell-signals', 'options'),
         Output('signals-unified-store', 'data'),
         Output('chart-title', 'children'),
         Output('chart-subtitle', 'children'),
         Output('data-table-container', 'children')],
        [Input('load-data-button', 'n_clicks'),
         Input('autoload-interval', 'n_intervals')],
        [State('ticker-dropdown', 'value'),
         State('start-date', 'date'),
         State('end-date', 'date'),
         State('indicator-settings-store', 'data')]
    )
    def load_data(n_clicks, n_intervals, ticker, start_date, end_date, indicator_settings):
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
                    False, [], [], [], "No data", "", None
                )

            df = add_indicators(df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
            df, _ = generate_signals(df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
            dashboard_state.df = df

            buy_columns = [col for col in df.columns if 'buy' in col.lower()]
            sell_columns = [col for col in df.columns if 'sell' in col.lower()]
            buy_options = _build_signal_options(buy_columns)
            sell_options = _build_signal_options(sell_columns)
            unified_rows = _build_unified_signal_rows(buy_columns, sell_columns)

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

            return status, True, buy_options, sell_options, unified_rows, ticker, subtitle, data_table

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return (
                html.Div([
                    html.Span("\u2715", style={'color': theme['accent_red'], 'marginRight': '6px', 'fontWeight': 'bold'}),
                    html.Span(str(e)[:40], style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_red']})
                ]),
                False, [], [], [], "Error", "", None
            )
