"""Full-screen Optimizer workspace: navigate + overlay visibility + chart host."""

from __future__ import annotations

from dash import callback_context, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_THEME, DEFAULT_TICKER, get_theme
from lib.dash.routes import (
    build_optimize_path,
    build_ticker_terminal_path,
    extract_path_ticker,
    is_optimize_route,
)


def register_optimize_workspace_callbacks(app) -> None:
    # Reparent the singleton chart area into the optimizer slot (or home).
    # Must stay clientside — no second #financial-chart / payload store.
    app.clientside_callback(
        """
        function(pathname) {
            var home = document.getElementById('chart-area-home');
            var slot = document.getElementById('optimize-chart-slot');
            if (!home || !slot) { return ''; }
            var onOptimize = !!(pathname && String(pathname).indexOf('/optimize') === 0);
            if (onOptimize) {
                if (home.parentElement !== slot) { slot.appendChild(home); }
            } else {
                var terminalMain = document.querySelector('#terminal-shell main');
                if (terminalMain && home.parentElement !== terminalMain) {
                    terminalMain.appendChild(home);
                }
            }
            if (window.sfaChart && typeof window.sfaChart.nudge === 'function') {
                window.sfaChart.nudge();
            }
            return onOptimize ? 'optimize' : 'terminal';
        }
        """,
        Output('optimize-chart-reparent-sync', 'children'),
        Input('app-url', 'pathname'),
        prevent_initial_call=False,
    )

    @app.callback(
        Output("app-url", "pathname", allow_duplicate=True),
        [
            Input("open-optimizer-button", "n_clicks"),
            Input("open-optimizer-from-teaser", "n_clicks"),
            Input("close-optimize-button", "n_clicks"),
        ],
        State("ticker-dropdown", "value"),
        prevent_initial_call=True,
    )
    def navigate_optimize(open_bt, open_teaser, close_clicks, ticker):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        symbol = str(ticker or DEFAULT_TICKER).strip().upper()
        if trigger in ("open-optimizer-button", "open-optimizer-from-teaser"):
            return build_optimize_path(symbol)
        if trigger == "close-optimize-button":
            return build_ticker_terminal_path(symbol)
        raise PreventUpdate

    @app.callback(
        [Output("optimize-overlay", "style"), Output("optimize-overlay", "className")],
        [Input("app-url", "pathname"), Input("theme-store", "data")],
        [State("optimize-overlay", "style"), State("optimize-overlay", "className")],
        prevent_initial_call=False,
    )
    def apply_optimize_route(pathname, theme_name, overlay_style, overlay_class):
        theme = get_theme(theme_name or DEFAULT_THEME)
        on_optimize = is_optimize_route(pathname)

        style = dict(overlay_style or {})
        style.update(
            {
                "backgroundColor": theme["bg_primary"],
                "border": f'1px solid {theme["border_primary"]}',
                "display": "flex" if on_optimize else "none",
                "flexDirection": "column",
                "position": "fixed",
                "zIndex": 20,
                "overflow": "hidden",
            }
        )
        if on_optimize:
            style.update({"inset": "0", "boxShadow": "none"})
        else:
            style.update(
                {
                    "inset": "42px 6px 24px 6px",
                    "boxShadow": "0 18px 60px rgba(0, 0, 0, 0.45)",
                }
            )

        base_class = "sfa-optimize-overlay"
        class_name = f"{base_class} sfa-optimize-route" if on_optimize else base_class
        if overlay_class == class_name:
            class_name = no_update
        return style, class_name

    @app.callback(
        Output("optimize-overlay-title", "children"),
        Input("app-url", "pathname"),
        State("ticker-dropdown", "value"),
        prevent_initial_call=False,
    )
    def sync_optimize_title(pathname, ticker):
        if not is_optimize_route(pathname):
            raise PreventUpdate
        symbol = extract_path_ticker(pathname) or ticker or DEFAULT_TICKER
        return f"{str(symbol).upper()} · signal combination search"
