"""Flow Scanner page callbacks (route + native Dash render + rescan)."""

from __future__ import annotations

from datetime import datetime
import base64
import json
from urllib.parse import quote

from dash import ALL, MATCH, callback_context, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash import flow_store
from lib.dash import flow_paper
from lib.dash.callbacks.flow_paper_ui import register_flow_paper_ui_callbacks
from lib.dash.flow_paper_view import contract_label
from lib.dash.dash_config import (
    DEFAULT_THEME,
    DEFAULT_TICKER,
    FLOW_REFRESH_MINUTES,
    ROUTE_TERMINAL,
    get_theme,
)
from lib.dash.flow_chain import DEFAULT_CHAIN_VIEW, table_from_report
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


def _flow_ticker(pathname: str | None, selected_ticker: str | None) -> str:
    return flow_store.normalize_ticker(extract_path_ticker(pathname) or selected_ticker or DEFAULT_TICKER)


def _report_time(payload: dict | None) -> str:
    """``generated_at`` as HH:MM today, or with the date when older."""
    raw = (payload or {}).get("generated_at")
    try:
        stamp = datetime.fromisoformat(str(raw))
    except (TypeError, ValueError):
        return "an earlier scan"
    return stamp.strftime("%H:%M" if stamp.date() == datetime.now().date() else "%d/%m/%Y %H:%M")


def _loaded_status(payload: dict) -> str:
    """Toolbar note on a plain load. The report's age is the #flow-data-age badge."""
    _ = payload
    return f"Auto-refresh every {FLOW_REFRESH_MINUTES} min" if FLOW_REFRESH_MINUTES > 0 else ""


def _with_epoch(payload: dict | None) -> dict | None:
    """Add ``generated_epoch`` so the browser can age the report without timezone guesswork.

    ``generated_at`` is the server's naive local time; on a hosted server in UTC a
    browser in Rome would read it an hour off.
    """
    if not payload:
        return payload
    try:
        epoch = datetime.fromisoformat(str(payload.get("generated_at"))).timestamp()
    except (TypeError, ValueError):
        return payload
    return {**payload, "generated_epoch": epoch}


def _render_from_payload(payload: dict | None, theme: dict, *, show_glossary: bool = False):
    if not payload:
        return render_flow_placeholder(theme)
    reports = payload.get("reports")
    if not reports:
        return render_flow_placeholder(theme, "Report file is empty. Click RESCAN NOW.")
    return render_flow_reports(payload, theme, show_glossary=show_glossary)


def register_flow_callbacks(app) -> None:
    register_flow_paper_ui_callbacks(app)
    @app.callback(
        Output("flow-paper-state", "data"),
        Input("app-url", "pathname"), Input("flow-data-store", "data"),
        Input("flow-paper-mode", "value"), Input("flow-paper-next", "n_clicks"),
        Input("flow-paper-import", "contents"),
        State("flow-paper-state", "data"),
        prevent_initial_call=False,
    )
    def advance_paper(pathname, payload, mode, _next, imported, state):
        if not is_flow_route(pathname):
            raise PreventUpdate
        ticker = _flow_ticker(pathname, None)
        state = dict(state or {})
        trigger = callback_context.triggered_id
        error = None
        if trigger == "flow-paper-import" and imported:
            try:
                raw = base64.b64decode(imported.split(",", 1)[1], validate=True)
                if len(raw) > 5_000_000:
                    raise ValueError("Import exceeds 5 MB")
                decoded = json.loads(raw)
                items = decoded if isinstance(decoded, list) else decoded.get("snapshots", [decoded])
                for item in items:
                    if flow_store.normalize_ticker(item.get("ticker")) != ticker:
                        raise ValueError("Imported snapshot ticker differs from this page")
                    flow_paper.add_snapshot(item)
            except (ValueError, TypeError, KeyError, IndexError) as exc:
                error = f"Import failed: {exc}"
        if payload and trigger == "flow-data-store":
            try:
                flow_paper.add_snapshot(flow_paper.snapshot_from_report(payload))
            except (ValueError, TypeError, KeyError):
                pass
        count = len(flow_paper.load(ticker)["snapshots"])
        if state.get("ticker") != ticker or trigger == "flow-paper-mode":
            index = 0 if mode == "replay" else max(count - 1, 0)
        elif trigger == "flow-paper-next" and mode == "replay":
            index = min(int(state.get("index", 0)) + 1, max(count - 1, 0))
        elif mode == "paper":
            index = max(count - 1, 0)
        else:
            index = min(int(state.get("index", 0)), max(count - 1, 0))
        return {"ticker": ticker, "index": index, "error": error}

    @app.callback(
        Output("flow-paper-message", "children"), Output("flow-paper-revision", "data"),
        Input("flow-paper-buy", "n_clicks"), Input("flow-paper-record-entry", "n_clicks"), Input("flow-paper-close", "n_clicks"), Input("flow-paper-settle", "n_clicks"),
        State("flow-paper-state", "data"), State("flow-paper-contract", "value"),
        State("flow-paper-position", "value"), State("flow-paper-fee", "value"),
        State("flow-paper-settlement", "value"), State("flow-paper-source", "value"),
        State("flow-paper-verified-at", "date"), State("flow-paper-verified-time", "value"),
        State("flow-paper-revision", "data"),
        State("flow-paper-entry-premium", "value"), State("flow-paper-mode", "value"),
        prevent_initial_call=True,
    )
    def paper_action(_buy, _entry, _close, _settle, state, key, position_id, fee, settlement, source, verified_date, verified_time, revision, entry_premium, mode):
        trigger = callback_context.triggered_id
        if trigger not in ("flow-paper-buy", "flow-paper-record-entry", "flow-paper-close", "flow-paper-settle"):
            raise PreventUpdate
        ticker = (state or {}).get("ticker")
        if not ticker:
            return "Open a Flow ticker first.", no_update
        data = flow_paper.load(ticker)
        snapshots = data["snapshots"]
        if not snapshots:
            return "No recorded observation is available.", no_update
        snap = snapshots[min(int(state.get("index", 0)), len(snapshots) - 1)]
        try:
            if trigger == "flow-paper-buy":
                p = flow_paper.buy(ticker, snap, key, fee=fee or 0)
                message = f"Paper bought {contract_label(p)} at observed ask ${p['entry_ask']:.2f}."
            elif trigger == "flow-paper-record-entry":
                if mode != "replay":
                    raise ValueError("Historical entries are available in replay mode")
                p = flow_paper.record_historical_entry(ticker, snap, key, entry_premium, fee=fee or 0)
                message = f"Recorded historical entry for {contract_label(p)} at ${p['entry_ask']:.2f}."
            elif trigger == "flow-paper-close":
                p = flow_paper.close(ticker, position_id, snap, fee=fee or 0)
                message = f"Paper closed {contract_label(p)} at observed bid ${p['exit_bid']:.2f}; P&L ${p['pnl']:.2f}."
            else:
                if not verified_date:
                    raise ValueError("Choose the settlement date (DD/MM/YYYY)")
                try:
                    time_part = datetime.strptime(str(verified_time or ""), "%H:%M").strftime("%H:%M")
                except ValueError as exc:
                    raise ValueError("Enter settlement time as HH:MM (UTC)") from exc
                stamp = f"{str(verified_date)[:10]}T{time_part}:00Z"
                p = flow_paper.settle(ticker, position_id, settlement, source or "", stamp)
                message = f"Settled {contract_label(p)}; expiry P&L ${p['pnl']:.2f}."
        except (ValueError, TypeError, KeyError) as exc:
            return str(exc), no_update
        return message, int(revision or 0) + 1

    app.clientside_callback(
        """
        function(nClicksList) {
            var ctx = window.dash_clientside.callback_context;
            if (!ctx || !ctx.triggered || !ctx.triggered.length) {
                return window.dash_clientside.no_update;
            }
            var triggered = ctx.triggered[0];
            if (!triggered || triggered.value === undefined || triggered.value === null || triggered.value === 0) {
                return window.dash_clientside.no_update;
            }
            var btn = document.getElementById(triggered.id);
            if (!btn) {
                try {
                    var idObj = JSON.parse(triggered.prop_id.split('.')[0]);
                    var buttons = document.querySelectorAll('.sfa-flow-fullscreen-btn');
                    for (var i = 0; i < buttons.length; i++) {
                        var bid = buttons[i].getAttribute('id');
                        if (!bid) continue;
                        try {
                            var parsed = JSON.parse(bid);
                            if (parsed && parsed.index === idObj.index) { btn = buttons[i]; break; }
                        } catch (e) {}
                    }
                } catch (e) {}
            }
            if (!btn) { return window.dash_clientside.no_update; }
            var frame = btn.closest('.sfa-flow-diagram-frame');
            if (!frame) { return window.dash_clientside.no_update; }
            function resizePlots() {
                try {
                    if (window.Plotly && frame.querySelectorAll) {
                        frame.querySelectorAll('.js-plotly-plot').forEach(function (el) {
                            window.Plotly.Plots.resize(el);
                        });
                    }
                } catch (e) {}
            }
            if (document.fullscreenElement === frame) {
                if (document.exitFullscreen) { document.exitFullscreen(); }
                return '';
            }
            if (frame.requestFullscreen) {
                frame.requestFullscreen().then(function() {
                    resizePlots();
                    setTimeout(resizePlots, 50);
                }).catch(function() {});
            }
            return '';
        }
        """,
        Output("flow-fullscreen-sync", "children"),
        Input({"type": "flow-fullscreen-btn", "index": ALL}, "n_clicks"),
        prevent_initial_call=True,
    )

    @app.callback(
        Output("app-url", "pathname", allow_duplicate=True),
        [
            Input("close-flow-button", "n_clicks"),
            Input("nav-workspace-flow", "n_clicks"),
        ],
        State("ticker-dropdown", "value"),
        prevent_initial_call=True,
    )
    def navigate_to_flow(close_clicks, nav_flow, ticker):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]["prop_id"].split(".")[0]
        if trigger == "nav-workspace-flow":
            symbol = str(ticker or DEFAULT_TICKER).strip().upper()
            return build_flow_path(symbol)
        if trigger == "close-flow-button":
            return ROUTE_TERMINAL
        raise PreventUpdate

    @app.callback(
        [
            Output("flow-overlay", "style"),
            Output("flow-overlay", "className"),
            Output("flow-open-tab-link", "href"),
            Output("flow-refresh-interval", "disabled"),
        ],
        [Input("app-url", "pathname"), Input("theme-store", "data")],
        [
            State("flow-overlay", "style"),
            State("flow-overlay", "className"),
            State("ticker-dropdown", "value"),
        ],
        prevent_initial_call=False,
    )
    def apply_flow_route(pathname, theme_name, overlay_style, overlay_class, selected_ticker):
        theme = get_theme(theme_name or DEFAULT_THEME)
        on_flow = is_flow_route(pathname)
        href = f"/flow_report.html?ticker={quote(_flow_ticker(pathname, selected_ticker), safe='')}"
        # Poll for a newer stored report only while the page is open and the
        # background refresh can actually produce one.
        poll_disabled = not (on_flow and FLOW_REFRESH_MINUTES > 0)

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
        return style, class_name, href, poll_disabled

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

        ticker = _flow_ticker(pathname, selected_ticker)

        if triggered != "flow-rescan-button" or not rescan_clicks:
            payload = _with_epoch(flow_store.load_report(ticker))
            if payload:
                return _render_from_payload(payload, theme), _loaded_status(payload), payload, False
            message = f"No report for {ticker} yet. Click RESCAN NOW."
            return render_flow_placeholder(theme, message), message, None, False

        outcome = flow_store.scan_into_store(ticker)
        payload = _with_epoch(outcome.payload)
        content = _render_from_payload(payload, theme) if payload else no_update
        store = payload if payload else no_update

        if outcome.error_kind == "scan_failed":
            return content, outcome.message, store, False

        dashboard_state.flow_last_scan_at = datetime.now()
        dashboard_state.flow_last_scan_path = str(flow_store.html_path(ticker))
        if outcome.error_kind is None:
            status = f"Rescanned {ticker} at {datetime.now().strftime('%H:%M:%S')}"
        elif not outcome.promoted:
            # The scan failed but an earlier good report exists: keep showing it.
            reason = "RATE LIMITED" if outcome.error_kind == "rate_limited" else f"Rescan failed: {outcome.message}"
            status = f"{reason} — kept the report from {_report_time(payload)}"
        elif outcome.error_kind == "rate_limited":
            status = f"RATE LIMITED — RESCAN {ticker} in a minute"
        else:
            status = f"Rescan of {ticker} failed"
        return content, status, store, False

    # Two steps so the minute poll never touches flow-content (see the note on
    # flow-refresh-interval in layout/overlays.py): the first only notices a
    # newer stored report, the second renders it.
    @app.callback(
        Output("flow-refresh-signal", "data"),
        Input("flow-refresh-interval", "n_intervals"),
        State("app-url", "pathname"),
        State("ticker-dropdown", "value"),
        State("flow-data-store", "data"),
        prevent_initial_call=True,
    )
    def notice_refreshed_flow_report(_n, pathname, selected_ticker, flow_data):
        if not is_flow_route(pathname):
            raise PreventUpdate
        ticker = _flow_ticker(pathname, selected_ticker)
        payload = flow_store.load_report(ticker)
        generated = (payload or {}).get("generated_at")
        if not generated or generated == (flow_data or {}).get("generated_at"):
            raise PreventUpdate
        return {"ticker": ticker, "generated_at": generated}

    @app.callback(
        Output("flow-content", "children", allow_duplicate=True),
        Output("flow-status", "children", allow_duplicate=True),
        Output("flow-data-store", "data", allow_duplicate=True),
        Input("flow-refresh-signal", "data"),
        State("app-url", "pathname"),
        State("ticker-dropdown", "value"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def render_refreshed_flow_report(signal, pathname, selected_ticker, theme_name):
        ticker = (signal or {}).get("ticker")
        # The visitor may have moved to another symbol since the poll noticed.
        if not is_flow_route(pathname) or ticker != _flow_ticker(pathname, selected_ticker):
            raise PreventUpdate
        payload = _with_epoch(flow_store.load_report(ticker))
        if not payload:
            raise PreventUpdate
        theme = get_theme(theme_name or DEFAULT_THEME)
        return _render_from_payload(payload, theme), _loaded_status(payload), payload

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
            return anyOpen ? 'Expand all' : 'Collapse all';
        }
        """,
        Output("flow-collapse-all", "children"),
        Input("flow-collapse-all", "n_clicks"),
        prevent_initial_call=True,
    )

    # Report age badge: "Data 16:12 · 3 min ago", green → amber → red as it ages.
    app.clientside_callback(
        """
        function(data, _tick) {
            var epoch = data && data.generated_epoch;
            if (!epoch) { return ['', 'sfa-flow-age']; }
            var stamp = new Date(epoch * 1000);
            var mins = Math.max(0, Math.floor((Date.now() - stamp.getTime()) / 60000));
            var ago;
            if (mins < 1) { ago = 'just now'; }
            else if (mins < 60) { ago = mins + ' min ago'; }
            else if (mins < 1440) { ago = Math.floor(mins / 60) + ' h ago'; }
            else { ago = Math.floor(mins / 1440) + ' d ago'; }
            var sameDay = stamp.toDateString() === new Date().toDateString();
            var when = stamp.toLocaleTimeString([], {hour: '2-digit', minute: '2-digit'});
            if (!sameDay) {
                when = stamp.toLocaleDateString('en-GB', {day: '2-digit', month: '2-digit', year: 'numeric'}) + ' ' + when;
            }
            var level = mins < 20 ? 'fresh' : (mins < 120 ? 'aging' : 'stale');
            return ['Data ' + when + ' · ' + ago, 'sfa-flow-age sfa-flow-age-' + level];
        }
        """,
        Output("flow-data-age", "children"),
        Output("flow-data-age", "className"),
        Input("flow-data-store", "data"),
        Input("flow-age-tick", "n_intervals"),
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
        Output({"type": "flow-chain-body", "index": MATCH}, "children"),
        Input({"type": "flow-chain-expiry", "index": MATCH}, "value"),
        Input({"type": "flow-chain-filter", "index": MATCH}, "value"),
        State({"type": "flow-chain-expiry", "index": MATCH}, "id"),
        State("flow-data-store", "data"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def update_chain_table(expiry, filter_value, id_dict, flow_data, theme_name):
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
        return table_from_report(
            report,
            expiry=expiry,
            theme=theme,
            view=str(filter_value or DEFAULT_CHAIN_VIEW).lower(),
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
