"""URL routing between the trading terminal and fundamentals workspace."""

from __future__ import annotations

from dash import callback_context, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_THEME, ROUTE_FUNDAMENTALS, ROUTE_TERMINAL, get_theme
from lib.dash.routes import is_fundamentals_route


def register_routing_callbacks(app) -> None:
    @app.callback(
        Output('app-url', 'pathname'),
        [Input('open-fundamentals-button', 'n_clicks'),
         Input('close-fundamentals-button', 'n_clicks')],
        prevent_initial_call=True,
    )
    def navigate_between_routes(open_clicks, close_clicks):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id == 'open-fundamentals-button':
            return ROUTE_FUNDAMENTALS
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

        terminal_style = {'display': 'none'} if on_fundamentals else {}

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
