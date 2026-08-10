"""Flow Scanner page callbacks (route + native Dash render + rescan)."""

from __future__ import annotations

import json
import os
from datetime import datetime

from dash import MATCH, callback_context, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_THEME, DEFAULT_TICKER, ROUTE_TERMINAL, get_theme
from lib.dash.flow_inventory import figure_from_report
from lib.dash.flow_gex import figure_from_gex_report
from lib.dash.flow_vanna import figure_from_vanna_report
from lib.dash.flow_view import (
    render_flow_placeholder,
    render_flow_reports,
    render_glossary_panel,
    render_learn_modal_content,
)
from lib.dash.routes import build_flow_path, extract_path_ticker, is_flow_route, is_fundamentals_route, ticker_from_search
from lib.dash.state import dashboard_state
from scripts.flow_runner import run_flow_scan

_FLOW_REPORT = os.path.join(os.getcwd(), "flow_report.html")
_FLOW_JSON = os.path.join(os.getcwd(), "flow_report.json")


def _load_flow_json() -> dict | None:
    if not os.path.exists(_FLOW_JSON):
        return None
    try:
        with open(_FLOW_JSON, encoding="utf-8") as fh:
            return json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None


def _render_from_payload(payload: dict | None, theme: dict, *, show_glossary: bool = False):
    if not payload:
        return render_flow_placeholder(theme)
    reports = payload.get("reports")
    if not reports:
        return render_flow_placeholder(theme, "Report file is empty. Click RESCAN NOW.")
    return render_flow_reports(payload, theme, show_glossary=show_glossary)


def register_flow_callbacks(app) -> None:
    @app.callback(
        Output("app-url", "pathname", allow_duplicate=True),
        [
            Input("open-flow-button", "n_clicks"),
            Input("close-flow-button", "n_clicks"),
            Input("nav-workspace-flow", "n_clicks"),
        ],
        State("ticker-dropdown", "value"),
        prevent_initial_call=True,
    )
    def navigate_to_flow(open_clicks, close_clicks, nav_flow, ticker):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger in ("open-flow-button", "nav-workspace-flow"):
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
                "display": "flex" if on_flow else "none",
                "flexDirection": "column",
                "position": "fixed",
                "zIndex": 20,
                "overflow": "hidden",
            }
        )
        if on_flow:
            # Persistent header is 44px — keep the workspace under it.
            style.update({"inset": "44px 0 0 0", "boxShadow": "none"})
        else:
            style.update(
                {
                    "inset": "44px 6px 24px 6px",
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
            Output("flow-content", "children"),
            Output("flow-status", "children"),
            Output("flow-data-store", "data"),
            Output("flow-rescan-button", "disabled"),
        ],
        [Input("flow-rescan-button", "n_clicks"), Input("app-url", "pathname")],
        [
            State("ticker-dropdown", "value"),
            State("flow-state-store", "data"),
            State("theme-store", "data"),
        ],
        prevent_initial_call=False,
    )
    def rescan_or_render_flow(rescan_clicks, pathname, selected_ticker, flow_state, theme_name):
        ctx = callback_context
        triggered = ctx.triggered[0]["prop_id"].split(".")[0] if ctx.triggered else ""
        theme = get_theme(theme_name or DEFAULT_THEME)

        if not is_flow_route(pathname):
            return no_update, no_update, no_update, False

        if triggered != "flow-rescan-button":
            payload = _load_flow_json()
            if payload:
                return (
                    _render_from_payload(payload, theme),
                    "Last report loaded",
                    payload,
                    False,
                )
            return (
                render_flow_placeholder(theme),
                "No report yet. Click RESCAN NOW.",
                no_update,
                False,
            )

        if not rescan_clicks:
            payload = _load_flow_json()
            if payload:
                return (
                    _render_from_payload(payload, theme),
                    "Last report loaded",
                    payload,
                    False,
                )
            return (
                render_flow_placeholder(theme),
                "No report yet. Click RESCAN NOW.",
                no_update,
                False,
            )

        ticker = str(extract_path_ticker(pathname) or selected_ticker or DEFAULT_TICKER).strip().upper()
        tickers = [ticker]
        rc, tail = run_flow_scan(tickers, _FLOW_REPORT, quiet=True)
        if rc != 0:
            return no_update, f"Scan failed (rc={rc}): {tail}", no_update, False

        dashboard_state.flow_last_scan_at = datetime.now()
        dashboard_state.flow_last_scan_path = _FLOW_REPORT
        payload = _load_flow_json()
        if not payload:
            return (
                no_update,
                f"Rescanned {ticker} but JSON report missing",
                no_update,
                False,
            )

        return (
            _render_from_payload(payload, theme),
            f"Rescanned {ticker} at {datetime.now().strftime('%H:%M:%S')}",
            payload,
            False,
        )

    @app.callback(
        Output("flow-glossary", "children"),
        Output("flow-glossary", "style"),
        Input("flow-glossary-button", "n_clicks"),
        State("flow-glossary", "style"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_flow_glossary(n_clicks, current_style, theme_name):
        if not n_clicks:
            raise PreventUpdate
        theme = get_theme(theme_name or DEFAULT_THEME)
        style = dict(current_style or {})
        visible = style.get("display") == "block"
        if visible:
            return [], {"display": "none"}
        # No maxHeight/own scrollbar: the glossary sits inside #flow-scroll-region
        # and scrolls with the report.
        return (
            render_glossary_panel(theme),
            {"display": "block", "padding": "8px 8px 0"},
        )

    app.clientside_callback(
        """
        function(n_clicks) {
            if (!n_clicks) { return window.dash_clientside.no_update; }
            const overlay = document.getElementById('flow-overlay');
            if (!overlay) { return window.dash_clientside.no_update; }
            const panels = overlay.querySelectorAll('details.sfa-flow-panel, details.sfa-flow-guide');
            if (!panels.length) { return window.dash_clientside.no_update; }
            const anyOpen = Array.prototype.some.call(panels, function (p) { return p.open; });
            Array.prototype.forEach.call(panels, function (p) { p.open = !anyOpen; });
            return anyOpen ? 'EXPAND ALL' : 'COLLAPSE ALL';
        }
        """,
        Output("flow-collapse-all", "children"),
        Input("flow-collapse-all", "n_clicks"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("flow-learn-modal", "is_open"),
        Output("flow-learn-modal-body", "children"),
        Input("flow-learn-button", "n_clicks"),
        Input("flow-learn-close", "n_clicks"),
        State("flow-learn-modal", "is_open"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def toggle_flow_learn_modal(learn_clicks, close_clicks, is_open, theme_name):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        theme = get_theme(theme_name or DEFAULT_THEME)
        body = render_learn_modal_content(theme)
        if trigger == "flow-learn-button":
            return (not bool(is_open)), body
        if trigger == "flow-learn-close":
            return False, body
        raise PreventUpdate

    @app.callback(
        Output("flow-content", "children", allow_duplicate=True),
        Input("theme-store", "data"),
        State("flow-data-store", "data"),
        prevent_initial_call=True,
    )
    def rerender_flow_on_theme(theme_name, flow_data):
        if not flow_data:
            raise PreventUpdate
        theme = get_theme(theme_name or DEFAULT_THEME)
        return _render_from_payload(flow_data, theme)

    @app.callback(
        Output({"type": "flow-inv-graph", "index": MATCH}, "figure"),
        Output({"type": "flow-inv-caption", "index": MATCH}, "children"),
        Input({"type": "flow-inv-expiry", "index": MATCH}, "value"),
        Input({"type": "flow-inv-metric", "index": MATCH}, "value"),
        State({"type": "flow-inv-expiry", "index": MATCH}, "id"),
        State("flow-data-store", "data"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def update_inventory_chart(expiry, metric, id_dict, flow_data, theme_name):
        if not flow_data:
            raise PreventUpdate
        ticker = str((id_dict or {}).get("index") or "").upper()
        report = next(
            (
                r
                for r in (flow_data.get("reports") or [])
                if str(r.get("ticker", "")).upper() == ticker
            ),
            None,
        )
        if not report:
            raise PreventUpdate
        theme = get_theme(theme_name or DEFAULT_THEME)
        return figure_from_report(
            report,
            expiry=expiry,
            metric=metric or "oi",
            theme=theme,
        )

    @app.callback(
        Output({"type": "flow-gex-graph", "index": MATCH}, "figure"),
        Output({"type": "flow-gex-caption", "index": MATCH}, "children"),
        Input({"type": "flow-gex-expiry", "index": MATCH}, "value"),
        State({"type": "flow-gex-expiry", "index": MATCH}, "id"),
        State("flow-data-store", "data"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def update_gex_chart(expiry, id_dict, flow_data, theme_name):
        if not flow_data:
            raise PreventUpdate
        ticker = str((id_dict or {}).get("index") or "").upper()
        report = next(
            (
                r
                for r in (flow_data.get("reports") or [])
                if str(r.get("ticker", "")).upper() == ticker
            ),
            None,
        )
        if not report:
            raise PreventUpdate
        theme = get_theme(theme_name or DEFAULT_THEME)
        return figure_from_gex_report(
            report,
            expiry=expiry,
            theme=theme,
        )

    @app.callback(
        Output({"type": "flow-vanna-graph", "index": MATCH}, "figure"),
        Output({"type": "flow-vanna-caption", "index": MATCH}, "children"),
        Input({"type": "flow-vanna-expiry", "index": MATCH}, "value"),
        State({"type": "flow-vanna-expiry", "index": MATCH}, "id"),
        State("flow-data-store", "data"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def update_vanna_chart(active_expiries, id_dict, flow_data, theme_name):
        if not flow_data:
            raise PreventUpdate
        ticker = str((id_dict or {}).get("index") or "").upper()
        report = next(
            (
                r
                for r in (flow_data.get("reports") or [])
                if str(r.get("ticker", "")).upper() == ticker
            ),
            None,
        )
        if not report:
            raise PreventUpdate
        theme = get_theme(theme_name or DEFAULT_THEME)
        return figure_from_vanna_report(
            report,
            active_expiries=active_expiries or [],
            theme=theme,
        )

    @app.callback(
        Output("ticker-dropdown", "value", allow_duplicate=True),
        [Input("app-url", "search"), Input("app-url", "pathname")],
        [State("ticker-dropdown", "data")],
        prevent_initial_call='initial_duplicate',
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
            raise PreventUpdate
        return ticker
