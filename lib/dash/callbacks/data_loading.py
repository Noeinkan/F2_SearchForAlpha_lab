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
    FONT_SIZES,
    START_DATE,
    get_theme,
    merge_indicator_settings,
)
from lib.dash.helpers import fetch_data_with_cache, format_df_for_display
from lib.dash.state import dashboard_state
from lib.signals.indicators import (
    add_indicators,
    classify_signal_columns,
    format_strategy_order_debug_text,
    generate_signals,
)
from lib.dash.callbacks.shared import (
    _build_signal_options,
    _build_unified_signal_rows,
    _create_data_table,
    _create_price_subtitle,
    clear_enriched_cache,
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
         Output('data-table-container', 'children')],
        [Input('load-data-button', 'n_clicks'),
         Input('autoload-interval', 'n_intervals')],
        [State('ticker-dropdown', 'value'),
         State('start-date', 'date'),
         State('end-date', 'date'),
         State('indicator-settings-store', 'data')]
    )
    def load_data(n_clicks, n_intervals, ticker, start_date, end_date, indicator_settings):
        """Load market data. Auto-loads the default ticker (TSLA) on startup."""
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # On startup, auto-load default ticker (SPY)
        if trigger_id == 'autoload-interval':
            if n_intervals is None or n_intervals < 1:
                raise PreventUpdate
            # State may not be populated yet on the single autoload tick — fall back to layout defaults
            ticker = ticker or DEFAULT_TICKER
            start_date = start_date or START_DATE
            end_date = end_date or date.today().isoformat()
        elif trigger_id == 'load-data-button':
            if not n_clicks:
                raise PreventUpdate

        theme = get_theme()

        try:
            df = fetch_data_with_cache(ticker, start_date, end_date)
            if df.empty:
                return (
                    "NO DATA",
                    "--",
                    False,
                    [],
                    [],
                    [],
                    "No data",
                    "",
                    (ticker or DEFAULT_TICKER).upper(),
                    "$--",
                    html.Span("NO CHANGE", className='muted'),
                    None,
                )

            effective_settings = merge_indicator_settings(indicator_settings or DEFAULT_INDICATOR_SETTINGS)
            df = add_indicators(df, effective_settings)
            df, _ = generate_signals(df, effective_settings)
            clear_enriched_cache()
            dashboard_state.df = df

            classified = classify_signal_columns(df.columns.tolist())
            buy_columns = classified['buy']
            sell_columns = classified['sell']
            buy_options = _build_signal_options(buy_columns)
            sell_options = _build_signal_options(sell_columns)
            unified_rows = _build_unified_signal_rows(buy_columns, sell_columns)

            # Create data table
            display_df = format_df_for_display(df.tail(50)).reset_index()
            data_table = _create_data_table(display_df, theme)

            # Calculate subtitle info
            subtitle = _create_price_subtitle(df, theme)
            latest_close = df['Close'].iloc[-1]
            prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
            change = latest_close - prev_close
            change_pct = (change / prev_close) * 100 if prev_close else 0
            change_prefix = '\u25b2' if change >= 0 else '\u25bc'
            change_sign = '+' if change >= 0 else ''
            change_color = theme['accent_green'] if change >= 0 else theme['accent_red']

            strategy_order_text = format_strategy_order_debug_text()
            return (
                f"{len(df)} ROWS",
                strategy_order_text,
                True,
                buy_options,
                sell_options,
                unified_rows,
                ticker,
                subtitle,
                (ticker or DEFAULT_TICKER).upper(),
                f"${latest_close:.2f}",
                html.Span(
                    f"{change_prefix} {change_sign}{change:.2f} ({change_sign}{change_pct:.2f}%)",
                    className='num',
                    style={'color': change_color}
                ),
                data_table,
            )

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return (
                "ERROR",
                "--",
                False,
                [],
                [],
                [],
                "Error",
                "",
                (ticker or DEFAULT_TICKER).upper(),
                "$--",
                html.Span(str(e)[:40].upper(), style={'color': theme['accent_red']}),
                None,
            )

    # Loading affordance. The `load_data` server callback above can take a
    # few seconds (yfinance fetch), during which the chart title would still
    # read "Select a symbol to begin" — making a fresh page load look dead.
    # This clientside callback fires the instant a load is triggered (the
    # one-shot autoload tick on startup, or a manual Load Data click) and
    # flips the title to "Loading <ticker>…" immediately. The server callback
    # then overwrites the title with the ticker (or "No data"/"Error") when
    # the fetch resolves. Uses allow_duplicate since `load_data` is the base
    # writer of chart-title.children.
    app.clientside_callback(
        """
        function(nIntervals, nClicks) {
            // Only react to a real trigger, not the initial render.
            if (!nIntervals && !nClicks) {
                return window.dash_clientside.no_update;
            }
            var ticker = 'TSLA';
            var sel = document.getElementById('ticker-dropdown');
            if (sel) {
                var input = sel.querySelector('input');
                if (input && input.value) {
                    // dmc.Select may show "TSLA - Tesla, Inc." — grab the
                    // leading ticker symbol only.
                    var m = String(input.value).trim().toUpperCase()
                        .match(/^[A-Z]{1,6}(\\.[A-Z])?/);
                    if (m) { ticker = m[0]; }
                }
            }
            return 'Loading ' + ticker + '\\u2026';
        }
        """,
        Output('chart-title', 'children', allow_duplicate=True),
        [Input('autoload-interval', 'n_intervals'),
         Input('load-data-button', 'n_clicks')],
        prevent_initial_call=True,
    )
