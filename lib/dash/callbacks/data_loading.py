"""
Data loading callbacks.
"""

import logging

from dash import callback_context, html, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import (
    DEFAULT_BAR_INTERVAL,
    DEFAULT_INDICATOR_SETTINGS,
    DEFAULT_TICKER,
    get_theme,
)
from lib.dash.state import dashboard_state
from lib.timeframes import full_history_window, normalize_interval

logger = logging.getLogger(__name__)


def register_data_loading_callbacks(app) -> None:
    @app.callback(
        [Output('ticker-dropdown', 'value'),
         Output('initial-capital', 'value'),
         Output('bar-interval', 'value')],
        [Input('preset-apply-store', 'data')],
        prevent_initial_call=True
    )
    def apply_market_preset(preset_data):
        """Restore the symbol/capital/interval a preset captured.

        Presets no longer carry a fetch window — there is nothing to restore,
        since the fetch always takes the maximum. The test window is restored
        separately in callbacks/test_window.py, after the data it has to be
        validated against has actually loaded.
        """
        if not preset_data:
            raise PreventUpdate

        market = preset_data.get("market_data", {})
        try:
            interval = normalize_interval(market.get("interval") or DEFAULT_BAR_INTERVAL)
        except Exception:
            interval = DEFAULT_BAR_INTERVAL
        return (
            market.get("ticker"),
            market.get("initial_capital"),
            interval,
        )

    @app.callback(
        Output('bar-interval-store', 'data'),
        Input('bar-interval', 'value'),
        prevent_initial_call=False,
    )
    def sync_bar_interval_store(interval):
        try:
            return normalize_interval(interval or DEFAULT_BAR_INTERVAL)
        except Exception:
            return DEFAULT_BAR_INTERVAL

    # `adjust_dates_for_interval` used to live here, nudging the sidebar date
    # pickers back inside Yahoo's 728-day intraday lookback whenever the user
    # switched D→1H with an old window selected. `full_history_window` now
    # derives the fetch window from the interval in the first place, so there is
    # no stale user input left to correct.

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
         Output('data-display-store', 'data')],
        [Input('load-data-button', 'n_clicks'),
         Input('autoload-interval', 'n_intervals'),
         Input('ticker-dropdown', 'value'),
         Input('bar-interval', 'value')],
        [State('indicator-settings-store', 'data'),
         State('data-loaded-store', 'data')],
        # Dash 4: the chart payload is owned solely by
        # callbacks.chart.update_chart_payload, reached via data-loaded-store.
        # initial_duplicate keeps autoload eligible.
        prevent_initial_call='initial_duplicate',
    )
    def load_data(
        n_clicks,
        n_intervals,
        ticker,
        bar_interval,
        indicator_settings,
        load_generation,
    ):
        """Load market data on startup, manual refresh, ticker, or interval change.

        The window is never taken from the UI: it is derived from the interval
        by ``full_history_window``, so the loaded frame is always the widest
        Yahoo will serve. Narrowing is the backtest panel's test window, applied
        downstream on this frame without re-fetching.

        Writes ``data-loaded-store`` and nothing chart-related;
        ``callbacks.chart.update_chart_payload`` owns the payload and picks the
        load up from that store. Two callbacks writing the chart in one dispatch
        layer is what Dash 4 rejects outright.
        """
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        next_generation = int(load_generation or 0) + 1

        try:
            canon = normalize_interval(bar_interval or DEFAULT_BAR_INTERVAL)
        except Exception:
            canon = DEFAULT_BAR_INTERVAL

        # Only an explicit click means "go and see if there are new bars"; the
        # other triggers are happy with a cache hit for a window they have
        # already pulled. Without this the stable max-history cache key would
        # make the refresh button a no-op for the rest of the trading day.
        force = False

        if trigger_id == 'autoload-interval':
            if n_intervals is None or n_intervals < 1:
                raise PreventUpdate
            if dashboard_state.df is not None:
                raise PreventUpdate
            ticker = ticker or DEFAULT_TICKER
        elif trigger_id == 'load-data-button':
            if not n_clicks:
                raise PreventUpdate
            ticker = str(ticker or DEFAULT_TICKER).strip().upper()
            force = True
        elif trigger_id in ('ticker-dropdown', 'bar-interval'):
            if not ticker:
                raise PreventUpdate
            ticker = str(ticker).strip().upper()
        else:
            raise PreventUpdate

        theme = get_theme()
        start_date, end_date = full_history_window(canon)

        try:
            # Lazy import avoids bootstrap ↔ callbacks circular import on startup.
            from lib.dash.bootstrap import load_market_session

            snapshot = load_market_session(
                ticker,
                start_date,
                end_date,
                indicator_settings or DEFAULT_INDICATOR_SETTINGS,
                interval=canon,
                force=force,
            )
            status = snapshot.data_status
            if canon != "1d":
                status = f"{status} · {canon.upper()}"

            return (
                status,
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
                snapshot.data_display,
            )

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            # Keep previous dashboard_state.df so a failed 1H fetch doesn't blank a good daily chart.
            return (
                f"ERROR: {str(e)[:48]}",
                "--",
                load_generation or 0,
                no_update,
                no_update,
                no_update,
                no_update,
                no_update,
                (ticker or DEFAULT_TICKER).upper(),
                no_update,
                html.Span(str(e)[:40].upper(), style={'color': theme['accent_red']}),
                no_update,
            )
