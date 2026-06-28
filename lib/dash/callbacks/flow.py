"""Flow Scanner page callbacks (route + iframe + rescan)."""

from __future__ import annotations

import os
from datetime import datetime

from dash import callback_context, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_THEME, DEFAULT_TICKER, ROUTE_TERMINAL, get_theme
from lib.dash.routes import build_flow_path, extract_path_ticker, is_flow_route, is_fundamentals_route, ticker_from_search
from lib.dash.state import dashboard_state
from scripts.flow_runner import run_flow_scan

_FLOW_REPORT = os.path.join(os.getcwd(), "flow_report.html")


def _iframe_src() -> str:
    if os.path.exists(_FLOW_REPORT):
        ts = int(os.path.getmtime(_FLOW_REPORT))
        return f"/flow_report.html?v={ts}"
    return ""


def register_flow_callbacks(app) -> None:
    @app.callback(
        Output("app-url", "pathname", allow_duplicate=True),
        [Input("open-flow-button", "n_clicks"), Input("close-flow-button", "n_clicks")],
        State("ticker-dropdown", "value"),
        prevent_initial_call=True,
    )
    def navigate_to_flow(open_clicks, close_clicks, ticker):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "open-flow-button":
            symbol = str(ticker or DEFAULT_TICKER).strip().upper()
            return build_flow_path(symbol)
        if trigger == "close-flow-button":
            return ROUTE_TERMINAL
        raise PreventUpdate

    @app.callback(
        [Output("flow-overlay", "style"), Output("flow-overlay", "className")],
        [Input("app-url", "pathname"), Input("theme-store", "data")],
        [State("flow-overlay", "style"), State("flow-overlay", "className")],
        prevent_initial_call=False,
    )
    def apply_flow_route(pathname, theme_name, overlay_style, overlay_class):
        theme = get_theme(theme_name or DEFAULT_THEME)
        on_flow = is_flow_route(pathname)

        style = dict(overlay_style or {})
        style.update(
            {
                "backgroundColor": theme["bg_primary"],
                "border": f'1px solid {theme["border_primary"]}',
                "display": "block" if on_flow else "none",
                "position": "fixed",
                "zIndex": 20,
                "overflow": "hidden",
            }
        )
        if on_flow:
            style.update({"inset": "0", "boxShadow": "none"})
        else:
            style.update(
                {
                    "inset": "42px 6px 24px 6px",
                    "boxShadow": "0 18px 60px rgba(0, 0, 0, 0.45)",
                }
            )

        base_class = "sfa-flow-overlay"
        class_name = f"{base_class} sfa-flow-route" if on_flow else base_class
        if overlay_class == class_name:
            class_name = no_update
        return style, class_name

    @app.callback(
        [
            Output("flow-iframe", "src"),
            Output("flow-status", "children"),
            Output("flow-state-store", "data"),
            Output("flow-rescan-button", "disabled"),
        ],
        [Input("flow-rescan-button", "n_clicks"), Input("app-url", "pathname")],
        [State("ticker-dropdown", "value"), State("flow-state-store", "data")],
        prevent_initial_call=False,
    )
    def rescan_or_show_iframe(rescan_clicks, pathname, selected_ticker, flow_state):
        ctx = callback_context
        triggered = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else ""

        if not is_flow_route(pathname):
            return "", no_update, no_update, False

        if triggered != "flow-rescan-button":
            src = _iframe_src()
            if src:
                return src, "Last report loaded", no_update, False
            return "", "No report yet. Click RESCAN NOW.", no_update, False

        if not rescan_clicks:
            src = _iframe_src()
            if src:
                return src, "Last report loaded", no_update, False
            return "", "No report yet. Click RESCAN NOW.", no_update, False

        ticker = str(extract_path_ticker(pathname) or selected_ticker or DEFAULT_TICKER).strip().upper()
        tickers = [ticker]
        rc, tail = run_flow_scan(tickers, _FLOW_REPORT, quiet=True)
        if rc != 0:
            return no_update, f"Scan failed (rc={rc}): {tail}", no_update, False

        dashboard_state.flow_last_scan_at = datetime.now()
        dashboard_state.flow_last_scan_path = _FLOW_REPORT
        ts = int(os.path.getmtime(_FLOW_REPORT))
        return (
            f"/flow_report.html?v={ts}",
            f"Rescanned {ticker} at {datetime.now().strftime('%H:%M:%S')}",
            {"last_scan_at": ts, "tickers": tickers},
            False,
        )

    @app.callback(
        [
            Output("ticker-dropdown", "value", allow_duplicate=True),
            Output("fundamentals-ticker-input", "value", allow_duplicate=True),
        ],
        [Input("app-url", "search"), Input("app-url", "pathname")],
        [State("ticker-dropdown", "data")],
        prevent_initial_call=True,
    )
    def apply_ticker_from_flow_link(search, pathname, ticker_data):
        """Pre-select ticker from path (/fundamentals/TSLA) or ?ticker= query."""
        if not (is_fundamentals_route(pathname) or is_flow_route(pathname)):
            raise PreventUpdate
        ticker = ticker_from_search(search) or extract_path_ticker(pathname)
        if not ticker:
            raise PreventUpdate
        known = {str(row.get("value", "")).upper() for row in (ticker_data or [])}
        if known and ticker not in known and len(known) <= 1:
            # Dropdown options not loaded yet — load_fundamentals handles fundamentals.
            raise PreventUpdate
        return ticker, ticker
