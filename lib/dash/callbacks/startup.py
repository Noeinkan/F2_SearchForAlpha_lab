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
from lib.dash.callbacks.shared import _format_preset_options

logger = logging.getLogger(__name__)


def register_startup_callbacks(app) -> None:
    @app.callback(
        Output('ticker-dropdown', 'options'),
        [Input('startup-interval', 'n_intervals')]
    )
    def populate_tickers(_):
        """Populate ticker dropdown on startup."""
        if dashboard_state.all_tickers_df is None:
            try:
                dashboard_state.all_tickers_df = get_all_tickers()
            except Exception as e:
                logger.error(f"Error fetching tickers: {e}")
                return [{'label': 'SPY - SPDR S&P 500 ETF', 'value': 'SPY'}]
        options = []
        for _, row in dashboard_state.all_tickers_df.iterrows():
            symbol = str(row.get('Symbol', '')).strip().upper()
            security_name = str(row.get('Security', '')).strip()
            if not symbol:
                continue

            # Keep labels compact while allowing search over full company names.
            compact_name = security_name if len(security_name) <= 30 else f"{security_name[:30]}..."
            options.append({
                'label': f"{symbol} - {compact_name}" if compact_name else symbol,
                'value': symbol,
                'search': f"{symbol} {security_name}".strip(),
            })

        return options

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
