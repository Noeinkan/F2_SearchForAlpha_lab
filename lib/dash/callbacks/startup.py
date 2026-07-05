"""
Startup callbacks for the dashboard.
"""

import logging

from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_TICKER, PRESET_FILE_PATH
from lib.dash.routes import is_flow_route, is_fundamentals_route, is_ticker_terminal_route
from lib.dash.preset_storage import load_presets
from lib.dash.ticker_search import dmc_ticker_select_data, ensure_ticker_options_loaded
from lib.dash.callbacks.shared import _format_preset_options

logger = logging.getLogger(__name__)

# No ticker has been explicitly picked yet — the dropdown's initial value
# is just the page default and must not be treated as a user choice.
_USER_TICKER_STORE = 'user-ticker-store'
_TICKER_DROPDOWN = 'ticker-dropdown'


def _ensure_ticker_options_loaded() -> list:
    """Back-compat alias used by fundamentals callbacks."""
    return ensure_ticker_options_loaded()


def register_startup_callbacks(app) -> None:
    @app.callback(
        [Output("ticker-dropdown", "data"),
         Output("ticker-dropdown", "value", allow_duplicate=True)],
        Input("startup-interval", "n_intervals"),
        [State("ticker-dropdown", "value"),
         State("route-ticker-store", "data")],
        # Dash 4.x: allow_duplicate=True requires an explicit
        # prevent_initial_call sentinel so the framework can acknowledge
        # that two callbacks may write the same Output on the first tick.
        # 'initial_duplicate' matches the sibling callback below.
        prevent_initial_call='initial_duplicate',
    )
    def populate_tickers(_n_intervals, current_value, route_ticker):
        """Populate the dmc.Select once on startup; restore value after data refresh."""
        if _n_intervals is None:
            raise PreventUpdate
        data = dmc_ticker_select_data()
        known = {str(row.get("value", "")).upper() for row in data}
        if route_ticker:
            value = str(route_ticker).strip().upper()
        else:
            # Preserve an in-flight user pick; only fall back to the page default
            # when the dropdown is still empty on first populate.
            value = str(current_value or DEFAULT_TICKER).strip().upper()
        if value not in known:
            value = DEFAULT_TICKER if DEFAULT_TICKER in known else data[0]["value"]
        return data, value

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
        the page default (TSLA).
        """
        if not ticker:
            raise PreventUpdate
        return str(ticker).strip().upper()

    @app.callback(
        Output(_TICKER_DROPDOWN, 'value', allow_duplicate=True),
        Input('route-ticker-store', 'data'),
        State('app-url', 'pathname'),
        prevent_initial_call='initial_duplicate',
    )
    def apply_route_ticker_to_dropdown(path_ticker, pathname):
        """Sync sidebar dropdown from /ticker|/fundamentals|/flow/<sym> deep-links."""
        if not path_ticker:
            raise PreventUpdate
        on_deep_link = (
            is_ticker_terminal_route(pathname)
            or is_fundamentals_route(pathname)
            or is_flow_route(pathname)
        )
        if not on_deep_link:
            raise PreventUpdate
        return str(path_ticker).strip().upper()

    @app.callback(
        Output(_TICKER_DROPDOWN, 'value', allow_duplicate=True),
        [Input(_TICKER_DROPDOWN, 'searchValue'),
         Input(_TICKER_DROPDOWN, 'dropdownOpened')],
        State(_TICKER_DROPDOWN, 'value'),
        prevent_initial_call=True,
    )
    def clear_preselected_ticker_on_first_focus(search_value, dropdown_opened, current_value):
        """Clear the preselected ticker the moment the user focuses / types.

        Accelerates research: the field opens with the page default so the chart
        loads with the correct symbol, but the moment the user clicks/opens the
        dropdown or starts typing, the field goes blank so they can immediately
        enter a new ticker without backspacing.
        """
        if str(current_value or '').strip().upper() != DEFAULT_TICKER:
            raise PreventUpdate
        user_focused = bool(dropdown_opened) or bool((search_value or '').strip())
        if not user_focused:
            raise PreventUpdate
        return None