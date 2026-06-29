"""
Data loading callbacks.
"""

import logging

from dash import callback_context, html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from datetime import date

from lib.dash.dash_config import (
    DEFAULT_INDICATOR_SETTINGS,
    DEFAULT_TICKER,
    START_DATE,
    get_theme,
)
from lib.dash.chart_builder import create_empty_chart
from lib.dash.state import dashboard_state

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
         Output('strategy-order-status', 'children'),
         Output('data-loaded-store', 'data'),
         Output('buy-signals', 'options'),
         Output('sell-signals', 'options'),
         Output('signals-unified-store', 'data'),
         Output('chart-title', 'children'),
         Output('chart-subtitle', 'children'),
         Output('header-ticker-symbol', 'children'),
         Output('header-ticker-price', 'children'),
         Output('header-ticker-change', 'children'),
         Output('data-table-container', 'children'),
         Output('financial-chart', 'figure', allow_duplicate=True)],
        [Input('load-data-button', 'n_clicks'),
         Input('autoload-interval', 'n_intervals'),
         Input('ticker-dropdown', 'value')],
        [State('start-date', 'date'),
         State('end-date', 'date'),
         State('indicator-settings-store', 'data'),
         State('data-loaded-store', 'data')],
        # Dash 4: financial-chart uses allow_duplicate=True alongside
        # chart_plotly + startup writers — initial_duplicate keeps autoload
        # eligible on the first interval tick.
        prevent_initial_call='initial_duplicate',
    )
    def load_data(
        n_clicks,
        n_intervals,
        ticker,
        start_date,
        end_date,
        indicator_settings,
        load_generation,
    ):
        """Load market data on startup, manual refresh, or ticker selection."""
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        next_generation = int(load_generation or 0) + 1

        if trigger_id == 'autoload-interval':
            if n_intervals is None or n_intervals < 1:
                raise PreventUpdate
            if dashboard_state.df is not None:
                raise PreventUpdate
            ticker = ticker or DEFAULT_TICKER
            start_date = start_date or START_DATE
            end_date = end_date or date.today().isoformat()
        elif trigger_id == 'load-data-button':
            if not n_clicks:
                raise PreventUpdate
            ticker = str(ticker or DEFAULT_TICKER).strip().upper()
        elif trigger_id == 'ticker-dropdown':
            if not ticker:
                raise PreventUpdate
            ticker = str(ticker).strip().upper()
        else:
            raise PreventUpdate

        theme = get_theme()

        try:
            # Lazy import avoids bootstrap ↔ callbacks circular import on startup.
            from lib.dash.bootstrap import load_market_session

            snapshot = load_market_session(
                ticker,
                start_date,
                end_date,
                indicator_settings or DEFAULT_INDICATOR_SETTINGS,
            )
            return (
                snapshot.data_status,
                snapshot.strategy_order,
                next_generation,
                snapshot.buy_options,
                snapshot.sell_options,
                snapshot.unified_rows,
                snapshot.chart_title,
                snapshot.chart_subtitle,
                snapshot.header_symbol,
                snapshot.header_price,
                snapshot.header_change,
                snapshot.data_table,
                snapshot.chart_figure,
            )

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return (
                "ERROR",
                "--",
                0,
                [],
                [],
                [],
                "Error",
                "",
                (ticker or DEFAULT_TICKER).upper(),
                "$--",
                html.Span(str(e)[:40].upper(), style={'color': theme['accent_red']}),
                None,
                create_empty_chart(theme, str(e)[:60]),
            )

    app.clientside_callback(
        """
        function(nIntervals, nClicks, tickerValue) {
            if (!nIntervals && !nClicks && !tickerValue) {
                return window.dash_clientside.no_update;
            }
            var ticker = tickerValue
                ? String(tickerValue).trim().toUpperCase()
                : 'TSLA';
            return 'Loading ' + ticker + '\\u2026';
        }
        """,
        Output('chart-title', 'children', allow_duplicate=True),
        [Input('autoload-interval', 'n_intervals'),
         Input('load-data-button', 'n_clicks'),
         Input('ticker-dropdown', 'value')],
        prevent_initial_call=True,
    )
