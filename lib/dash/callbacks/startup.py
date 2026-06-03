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
from lib.dash.ticker_search import build_ticker_options, filter_ticker_options
from lib.dash.callbacks.shared import _format_preset_options

logger = logging.getLogger(__name__)

_FALLBACK_TICKER_OPTIONS = [{"label": "SPY - SPDR S&P 500 ETF", "value": "SPY", "search": "spy spdr s&p 500 etf"}]


def _ensure_ticker_options_loaded() -> list:
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
        return _FALLBACK_TICKER_OPTIONS


def register_startup_callbacks(app) -> None:
    @app.callback(
        Output("ticker-dropdown", "options"),
        [
            Input("startup-interval", "n_intervals"),
            Input("ticker-dropdown", "search_value"),
        ],
    )
    def populate_or_filter_tickers(_n_intervals, search_value):
        """Load tickers on startup; filter by name/alias as the user types."""
        all_options = _ensure_ticker_options_loaded()
        return filter_ticker_options(all_options, search_value)

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
