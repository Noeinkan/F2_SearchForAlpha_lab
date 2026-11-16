"""URL routing between the trading terminal and fundamentals workspace."""

from __future__ import annotations

from dash import callback_context, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_THEME, DEFAULT_TICKER, get_theme
from lib.dash.routes import (
    build_flow_path,
    build_fundamentals_path,
    build_optimize_path,
    build_ticker_terminal_path,
    extract_path_ticker,
    is_fundamentals_route,
    is_flow_route,
    is_optimize_route,
    normalize_pathname,
)


def register_routing_callbacks(app) -> None:
    # Flask serves the same Dash shell for /fundamentals/TSLA etc. Dash still
    # hydrates dcc.Location with pathname "/" until we sync from the browser.
    # Input('app-url', 'id') does not reliably fire on mount in Dash 4.x, so
    # url-boot-interval (1ms, once) is the trigger instead.
    app.clientside_callback(
        """
        function(_n) {
            var boot = window.__SFA_BOOT_URL__;
            var path = (boot && boot.pathname)
                ? boot.pathname
                : (window.location.pathname || '/');
            var search = (boot && boot.search !== undefined)
                ? boot.search
                : (window.location.search || '');
            return [path, search || ''];
        }
        """,
        [Output('app-url', 'pathname', allow_duplicate=True),
         Output('app-url', 'search', allow_duplicate=True)],
        Input('url-boot-interval', 'n_intervals'),
        prevent_initial_call='initial_duplicate',
    )

    @app.callback(
        Output('route-ticker-store', 'data'),
        Input('app-url', 'pathname'),
        prevent_initial_call=False,
    )
    def sync_route_ticker(pathname):
        return extract_path_ticker(pathname)

    @app.callback(
        Output('app-url', 'pathname', allow_duplicate=True),
        Input('ticker-dropdown', 'value'),
        State('app-url', 'pathname'),
        prevent_initial_call=True,
    )
    def sync_dropdown_to_url(ticker, pathname):
        """Reflect the current symbol in the browser URL.

        On the terminal this is ``/ticker/<sym>``. On fundamentals / flow /
        optimize it stays on that workspace and only swaps the ticker segment,
        so the shared symbol-search modal can change symbols without bouncing
        back to the chart shell.
        """
        if not ticker:
            raise PreventUpdate
        symbol = str(ticker).strip().upper()
        if is_fundamentals_route(pathname):
            new_path = build_fundamentals_path(symbol)
        elif is_flow_route(pathname):
            new_path = build_flow_path(symbol)
        elif is_optimize_route(pathname):
            new_path = build_optimize_path(symbol)
        else:
            new_path = build_ticker_terminal_path(symbol)
        if normalize_pathname(pathname) == normalize_pathname(new_path):
            raise PreventUpdate
        return new_path

    @app.callback(
        Output('app-url', 'pathname', allow_duplicate=True),
        [Input('close-fundamentals-button', 'n_clicks'),
         Input('nav-workspace-sfa', 'n_clicks'),
         Input('nav-workspace-fundamentals', 'n_clicks')],
        State('ticker-dropdown', 'value'),
        prevent_initial_call=True,
    )
    def navigate_between_routes(close_clicks, nav_sfa, nav_fund, ticker):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        symbol = str(ticker or DEFAULT_TICKER).strip().upper()
        if trigger_id == 'nav-workspace-fundamentals':
            return build_fundamentals_path(symbol)
        if trigger_id in ('close-fundamentals-button', 'nav-workspace-sfa'):
            return build_ticker_terminal_path(symbol)
        raise PreventUpdate

    @app.callback(
        [Output('nav-workspace-sfa', 'className'),
         Output('nav-workspace-fundamentals', 'className'),
         Output('nav-workspace-flow', 'className')],
        Input('app-url', 'pathname'),
        prevent_initial_call=False,
    )
    def sync_workspace_nav_active(pathname):
        base = 'sfa-workspace-nav-btn'
        active = f'{base} is-active'
        if is_fundamentals_route(pathname):
            return base, active, base
        if is_flow_route(pathname):
            return base, base, active
        return active, base, base

    @app.callback(
        [Output('terminal-shell', 'style'),
         Output('fundamentals-overlay', 'style'),
         Output('fundamentals-overlay', 'className')],
        [Input('app-url', 'pathname'),
         Input('theme-store', 'data')],
        [State('fundamentals-overlay', 'style'),
         State('fundamentals-overlay', 'className')],
        prevent_initial_call=False,
    )
    def apply_route_layout(pathname, theme_name, overlay_style, overlay_class):
        theme = get_theme(theme_name or DEFAULT_THEME)
        on_fundamentals = is_fundamentals_route(pathname)
        on_alt_page = (
            on_fundamentals
            or is_flow_route(pathname)
            or is_optimize_route(pathname)
        )

        terminal_style = {'display': 'none'} if on_alt_page else {}

        style = dict(overlay_style or {})
        # Must be flex (not block): #fundamentals-scroll-region needs a flex
        # parent + min-height:0 to form a scrollport. display:block overrides
        # the CSS column and clips Big Five / charts with no scrollbar.
        style.update({
            'backgroundColor': theme['bg_primary'],
            'border': f'1px solid {theme["border_primary"]}',
            'display': 'flex' if on_fundamentals else 'none',
            'flexDirection': 'column',
            'position': 'fixed',
            'zIndex': 20,
            'overflow': 'hidden',
        })
        if on_fundamentals:
            # Persistent header is 44px — keep the workspace under it.
            style.update({
                'inset': '44px 0 0 0',
                'boxShadow': 'none',
            })
        else:
            style.update({
                'inset': '44px 6px 24px 6px',
                'boxShadow': '0 18px 60px rgba(0, 0, 0, 0.45)',
            })

        base_class = 'sfa-fundamentals-overlay'
        class_name = f'{base_class} sfa-fundamentals-route' if on_fundamentals else base_class
        if overlay_class == class_name:
            class_name = no_update

        return terminal_style, style, class_name
