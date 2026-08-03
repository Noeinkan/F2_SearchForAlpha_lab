"""
Data loading callbacks.
"""

import logging

from dash import callback_context, html, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from datetime import date

from lib.dash.dash_config import (
    DEFAULT_BAR_INTERVAL,
    DEFAULT_INDICATOR_SETTINGS,
    DEFAULT_TICKER,
    START_DATE,
    get_theme,
)
from lib.dash.state import dashboard_state
from lib.timeframes import IntervalError, clamp_window, normalize_interval

logger = logging.getLogger(__name__)


def _resolve_preset_end_date(saved_value) -> str:
    """
    Roll a stale preset end_date forward to today.

    Presets snapshot the picker's literal date at save time. Without this,
    loading a preset months later clamps yfinance to the save-day boundary
    and the chart appears to "freeze" in the past. Treat any missing value,
    the explicit "today" sentinel, or a date strictly before today as a
    rolling anchor. Future-dated values are preserved verbatim so a user
    can still freeze a preset to a chosen window by setting end_date ahead
    of today.
    """
    today_iso = date.today().isoformat()
    if not saved_value or saved_value == "today":
        return today_iso
    try:
        return today_iso if date.fromisoformat(str(saved_value)[:10]) < date.today() else saved_value
    except ValueError:
        return today_iso


def register_data_loading_callbacks(app) -> None:
    @app.callback(
        [Output('ticker-dropdown', 'value'),
         Output('start-date', 'date'),
         Output('end-date', 'date'),
         Output('initial-capital', 'value'),
         Output('bar-interval', 'value')],
        [Input('preset-apply-store', 'data')],
        prevent_initial_call=True
    )
    def apply_market_preset(preset_data):
        if not preset_data:
            raise PreventUpdate

        market = preset_data.get("market_data", {})
        try:
            interval = normalize_interval(market.get("interval") or DEFAULT_BAR_INTERVAL)
        except Exception:
            interval = DEFAULT_BAR_INTERVAL
        return (
            market.get("ticker"),
            market.get("start_date"),
            _resolve_preset_end_date(market.get("end_date")),
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

    @app.callback(
        [Output('start-date', 'date', allow_duplicate=True),
         Output('end-date', 'date', allow_duplicate=True)],
        Input('bar-interval', 'value'),
        State('start-date', 'date'),
        State('end-date', 'date'),
        prevent_initial_call=True,
    )
    def adjust_dates_for_interval(interval, start_date, end_date):
        """Fit date pickers into Yahoo's rolling lookback when switching to 1h/4h."""
        if not start_date or not end_date:
            raise PreventUpdate
        try:
            canon = normalize_interval(interval or DEFAULT_BAR_INTERVAL)
        except Exception:
            raise PreventUpdate
        if canon == "1d":
            raise PreventUpdate
        try:
            new_start, new_end = clamp_window(
                str(start_date)[:10],
                str(end_date)[:10],
                canon,
                relocate=True,
            )
        except IntervalError:
            raise PreventUpdate
        start_out = new_start if new_start != str(start_date)[:10] else no_update
        end_out = new_end if new_end != str(end_date)[:10] else no_update
        if start_out is no_update and end_out is no_update:
            raise PreventUpdate
        return start_out, end_out

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
        [State('start-date', 'date'),
         State('end-date', 'date'),
         State('indicator-settings-store', 'data'),
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
        start_date,
        end_date,
        indicator_settings,
        load_generation,
    ):
        """Load market data on startup, manual refresh, ticker, or interval change.

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
        elif trigger_id == 'bar-interval':
            if not ticker:
                raise PreventUpdate
            ticker = str(ticker).strip().upper()
            start_date = start_date or START_DATE
            end_date = end_date or date.today().isoformat()
        else:
            raise PreventUpdate

        theme = get_theme()
        orig_start = str(start_date)[:10] if start_date else None
        orig_end = str(end_date)[:10] if end_date else None
        window_adjusted = False

        try:
            if start_date and end_date:
                # UI relocates stale windows into Yahoo's rolling lookback so
                # switching D→1H/4H with an old End Date still refreshes the chart.
                start_date, end_date = clamp_window(
                    str(start_date)[:10],
                    str(end_date)[:10],
                    canon,
                    relocate=True,
                )
                window_adjusted = (
                    canon != "1d"
                    and (start_date != orig_start or end_date != orig_end)
                )

            # Lazy import avoids bootstrap ↔ callbacks circular import on startup.
            from lib.dash.bootstrap import load_market_session

            snapshot = load_market_session(
                ticker,
                start_date,
                end_date,
                indicator_settings or DEFAULT_INDICATOR_SETTINGS,
                interval=canon,
            )
            status = snapshot.data_status
            if canon != "1d":
                status = f"{status} · {canon.upper()}"
            if window_adjusted:
                status = f"{status} · WINDOW ADJUSTED (YAHOO INTRADAY LIMIT)"

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
