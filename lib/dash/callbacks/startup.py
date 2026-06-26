"""
Startup callbacks for the dashboard.
"""

import logging

from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate

from lib.data_processing import get_all_tickers
from lib.dash.dash_config import PRESET_FILE_PATH
from lib.dash.preset_storage import load_presets
from lib.dash.state import dashboard_state
from lib.dash.ticker_search import build_ticker_options
from lib.dash.callbacks.shared import _format_preset_options

logger = logging.getLogger(__name__)

# No ticker has been explicitly picked yet — the dropdown's initial value
# is just the page default and must not be treated as a user choice.
_USER_TICKER_STORE = 'user-ticker-store'
_TICKER_DROPDOWN = 'ticker-dropdown'


def _ensure_ticker_options_loaded() -> list:
    """Load (and cache) the full ticker options list for free-text resolution.

    Returns a list of {value, label, search} dicts. Used by fundamentals
    callbacks to map user-typed queries to a known symbol.
    """
    if dashboard_state.ticker_dropdown_options is not None:
        return dashboard_state.ticker_dropdown_options

    try:
        dashboard_state.all_tickers_df = get_all_tickers()
        dashboard_state.ticker_dropdown_options = build_ticker_options(
            dashboard_state.all_tickers_df
        )
        return dashboard_state.ticker_dropdown_options
    except Exception as e:
        logger.error(f"Error fetching tickers: {e}")
        return [{"value": "SPY", "label": "SPY - SPDR S&P 500 ETF", "search": "spy spdr s&p 500 etf"}]


def _ticker_data_for_dmc() -> list:
    """Build the data list for dmc.Select from the loaded tickers index.

    dmc.Select accepts a flat list of {"value", "label"} dicts. The label
    already includes the company name (e.g. "ABT - Abbott Laboratories"),
    so client-side filtering matches by both symbol and company name.
    """
    options = _ensure_ticker_options_loaded()
    return [{"value": opt["value"], "label": opt["label"]} for opt in options]


def register_startup_callbacks(app) -> None:
    @app.callback(
        Output("ticker-dropdown", "data"),
        Input("startup-interval", "n_intervals"),
    )
    def populate_tickers(_n_intervals):
        """Populate the dmc.Select once on startup; filtering is client-side."""
        if _n_intervals is None:
            raise PreventUpdate
        return _ticker_data_for_dmc()

    @app.callback(
        [Output('presets-store', 'data'),
         Output('preset-selector', 'options'),
         Output('preset-selector', 'value')],
        [Input('startup-interval', 'n_intervals')]
    )
    def load_presets_on_startup(n_intervals):
        """Load UI presets from disk on startup."""
        if n_intervals is None:
            raise PreventUpdate

        data = load_presets(PRESET_FILE_PATH)
        presets = data.get("presets", {})
        options = _format_preset_options(presets)
        return data, options, None

    @app.callback(
        Output(_USER_TICKER_STORE, 'data'),
        Input(_TICKER_DROPDOWN, 'value'),
        prevent_initial_call=True,
    )
    def track_user_ticker_selection(ticker):
        """Remember tickers the user explicitly selected.

        prevent_initial_call=True keeps the initial page-default value out
        of the store so cold /fundamentals loads can detect "no user
        selection yet" and fall back to a real company (TSLA) instead of
        the page default (SPY).
        """
        if not ticker:
            raise PreventUpdate
        return str(ticker).strip().upper()