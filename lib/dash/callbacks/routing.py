"""URL routing between the trading terminal and fundamentals workspace."""

from __future__ import annotations

from dash import callback_context, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_THEME, DEFAULT_TICKER, ROUTE_TERMINAL, get_theme
from lib.dash.routes import (
    build_fundamentals_path,
    extract_path_ticker,
    is_fundamentals_route,
    is_flow_route,
)


def register_routing_callbacks(app) -> None:
    # Flask serves the same Dash shell for /fundamentals/TSLA etc. The server
    # renders app-url.pathname as "/" before hydration; sync from the browser
    # URL on mount so deep-links open the correct workspace immediately.
    app.clientside_callback(
        """
        function(_id) {
            var boot = window.__SFA_BOOT_URL__;
            if (boot && boot.pathname) {
                return [boot.pathname, boot.search || ''];
            }
            return [window.location.pathname, window.location.search || ''];
        }
        """,
        [Output('app-url', 'pathname', allow_duplicate=True),
         Output('app-url', 'search', allow_duplicate=True)],
        Input('app-url', 'id'),
        # Dash 4.x: allow_duplicate=True paired with the default
        # prevent_initial_call=False is rejected. This callback must fire on
        # mount so deep-links land on the right workspace, so we use the
        # explicit 'initial_duplicate' sentinel.
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
        [Input('open-fundamentals-button', 'n_clicks'),
         Input('close-fundamentals-button', 'n_clicks')],
        [State('ticker-dropdown', 'value'),
         State('fundamentals-ticker-input', 'value')],
        prevent_initial_call=True,
    )
    def navigate_between_routes(open_clicks, close_clicks, ticker, fundamentals_ticker):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id == 'open-fundamentals-button':
            symbol = str(fundamentals_ticker or ticker or DEFAULT_TICKER).strip().upper()
            return build_fundamentals_path(symbol)
        if trigger_id == 'close-fundamentals-button':
            return ROUTE_TERMINAL
        raise PreventUpdate

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
        on_alt_page = on_fundamentals or is_flow_route(pathname)

        terminal_style = {'display': 'none'} if on_alt_page else {}

        style = dict(overlay_style or {})
        style.update({
            'backgroundColor': theme['bg_primary'],
            'border': f'1px solid {theme["border_primary"]}',
            'display': 'block' if on_fundamentals else 'none',
            'position': 'fixed',
            'zIndex': 20,
            'overflow': 'hidden',
        })
        if on_fundamentals:
            style.update({
                'inset': '0',
                'boxShadow': 'none',
            })
        else:
            style.update({
                'inset': '42px 6px 24px 6px',
                'boxShadow': '0 18px 60px rgba(0, 0, 0, 0.45)',
            })

        base_class = 'sfa-fundamentals-overlay'
        class_name = f'{base_class} sfa-fundamentals-route' if on_fundamentals else base_class
        if overlay_class == class_name:
            class_name = no_update

        return terminal_style, style, class_name
