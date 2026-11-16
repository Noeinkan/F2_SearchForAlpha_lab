"""Historical option chain (ThetaData EOD) and historical replay callbacks for the Flow page."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping

from dash import MATCH, callback_context, html, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash import flow_history, flow_paper, flow_store
from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.flow_chain import (DEFAULT_CHAIN_VIEW, default_chain_expiry, expiry_option_label,
                                 render_expiry_navigation, table_from_report)
from lib.dash.flow_dates import display_date
from lib.dash.routes import extract_path_ticker, is_flow_route
from lib.fetch_errors import DataFetchError
from lib.options.theta_history import ThetaUnavailable

RECORDED = "recorded"


def _money(value: Any) -> str:
    return f"${value:,.2f}" if isinstance(value, (int, float)) else "missing"


def _current_report(flow_data: Mapping[str, Any] | None, ticker: str) -> dict | None:
    return next((r for r in (flow_data or {}).get("reports") or []
                 if str(r.get("ticker", "")).upper() == ticker), None)


def _historical_report(ticker: str, history: Mapping[str, Any] | None) -> dict | None:
    if not history or not history.get("date"):
        return None
    record = flow_history.cached_chain(ticker, history["date"])
    return flow_history.chain_report(record) if record else None


def _load_error(exc: Exception) -> str:
    if isinstance(exc, ThetaUnavailable):
        return str(exc)
    return f"Could not load history: {exc}"


def replay_options(ticker: str | None) -> list[dict]:
    options = [{"label": "Recorded scans", "value": RECORDED}]
    if ticker:
        options += [{"label": flow_history.replay_label(r), "value": r["id"]}
                    for r in reversed(flow_history.list_replays(ticker))]
    return options


def selection_problem(selection: Mapping[str, Any], mode: str | None, replay_id: str | None,
                      ticker: str) -> str | None:
    """Why a strategy sent from the chain cannot be priced here, or None.

    A strategy built from current quotes opens in Paper trading; one built from a
    historical chain opens only inside the replay loaded for it, so its legs are
    priced at the same observation the chain showed.
    """
    if selection.get("source") == "historical":
        replay = flow_history.load_replay(ticker, replay_id)
        if not replay or replay.get("nonce") != selection.get("nonce"):
            return ("This strategy uses historical quotes. Wait for its replay to load, "
                    "or choose it under Replay source.")
        return None
    if mode != "paper" or replay_id:
        return "Switch to Paper trading to open a strategy priced from the latest scan."
    return None


def ledger(ticker: str, replay: Mapping[str, Any], index: int) -> html.Div:
    """Day-by-day observed bid/ask and paper P&L, revealed up to the current observation."""
    data = flow_paper.load(ticker)
    positions = [p for p in data["positions"] if flow_paper.in_context(p, replay["id"])]
    strategies = [p for p in data["strategies"] if flow_paper.in_context(p, replay["id"])]
    legs = replay["legs"]
    header = html.Tr([html.Th("Date"), html.Th("Underlying close"),
                      *[html.Th(f"{'Call' if leg['cp'] == 'C' else 'Put'} {leg['strike']:g} bid / ask") for leg in legs],
                      html.Th("Paper P&L at observed quotes"), html.Th("Quote check")])
    rows = []
    for snap in replay["snapshots"][: index + 1]:
        stamp = snap["observed_at"]
        cells = [html.Td(display_date(snap["date"])), html.Td(_money(snap.get("underlying")))]
        for leg in legs:
            q = flow_paper.quote(snap, leg["key"])
            cells.append(html.Td(f"{_money(q.get('bid'))} / {_money(q.get('ask'))}" if q else "no quote",
                                 className="" if q and q.get("bid") and q.get("ask") else "sfa-flow-replay-missing"))
        marks = []
        for p in positions:
            if p["opened_at"] > stamp or (p.get("closed_at") and p["closed_at"] < stamp):
                continue
            if p.get("closed_at") == stamp:
                marks.append(f"closed {_money(p.get('pnl'))}")
                continue
            q = flow_paper.quote(snap, p["contract"])
            mark = flow_paper.valuation(p, q.get("bid") if q else None)
            marks.append(_money(mark) if mark is not None else "no bid")
        for p in strategies:
            if p["opened_at"] > stamp or (p.get("closed_at") and p["closed_at"] < stamp):
                continue
            if p.get("closed_at") == stamp:
                marks.append(f"closed {_money(p.get('pnl'))}")
                continue
            mark = flow_paper.strategy_valuation(p, snap)
            marks.append(_money(mark) if mark is not None else "quote missing")
        cells.append(html.Td(" · ".join(marks) if marks else "—"))
        missing = snap.get("missing") or []
        cells.append(html.Td(
            "; ".join(f"{m['key'].split('|')[1]} {m['key'].split('|')[2]}: {m['what']}" for m in missing) or "OK",
            className="sfa-flow-replay-missing" if missing else "",
        ))
        rows.append(html.Tr(cells))
    notes = [html.Div(
        f"{replay.get('source')} · entry {display_date(replay['trade_date'])} · "
        f"{len(replay['snapshots'])} trading days loaded · contract expires {display_date(replay['expiry'])}",
        className="sfa-flow-replay-note")]
    if replay.get("ended_early"):
        notes.append(html.Div(
            f"Replay ends early: the last available observation is {display_date(replay['last_available'])}, "
            f"before the contract expiry on {display_date(replay['expiry'])}.",
            className="sfa-flow-replay-early"))
    notes.append(html.Div("P&L marks long legs at the observed bid and short legs at the observed ask, "
                          "after entry fees and before closing fees.", className="sfa-flow-replay-note"))
    return html.Div([*notes, html.Div(html.Table([html.Thead(header), html.Tbody(rows)],
                                                 className="sfa-flow-replay-table"),
                                      className="sfa-flow-replay-scroll")])


def register_flow_history_callbacks(app) -> None:
    @app.callback(
        Output({"type": "flow-chain-history-controls", "index": MATCH}, "style"),
        Input({"type": "flow-chain-source", "index": MATCH}, "value"),
    )
    def toggle_history_controls(source):
        return {} if source == "historical" else {"display": "none"}

    @app.callback(
        Output({"type": "flow-chain-history", "index": MATCH}, "data"),
        Output({"type": "flow-chain-history-status", "index": MATCH}, "children"),
        Input({"type": "flow-chain-history-load", "index": MATCH}, "n_clicks"),
        State({"type": "flow-chain-history-date", "index": MATCH}, "date"),
        State({"type": "flow-chain-history-load", "index": MATCH}, "id"),
        prevent_initial_call=True,
    )
    def load_history(clicks, trade_date, id_dict):
        if not clicks:
            raise PreventUpdate
        ticker = flow_store.normalize_ticker((id_dict or {}).get("index"))
        if not trade_date:
            return no_update, "Choose a past trading date first."
        try:
            record = flow_history.load_chain(ticker, trade_date)
        except (ValueError, DataFetchError) as exc:
            return no_update, _load_error(exc)
        expiries = {c["expiry"] for c in record["contracts"]}
        return ({"date": record["date"], "observed_at": record["observed_at"]},
                f"Loaded {len(record['contracts']):,} contracts across {len(expiries)} expiries quoted on "
                f"{display_date(record['date'])}, observed {display_date(record['observed_at'], time=True)}.")

    @app.callback(
        Output({"type": "flow-chain-expiry", "index": MATCH}, "options"),
        Output({"type": "flow-chain-expiry", "index": MATCH}, "value"),
        Output({"type": "flow-chain-expiry-nav", "index": MATCH}, "children"),
        Input({"type": "flow-chain-source", "index": MATCH}, "value"),
        Input({"type": "flow-chain-history", "index": MATCH}, "data"),
        State({"type": "flow-chain-source", "index": MATCH}, "id"),
        State("flow-data-store", "data"),
        prevent_initial_call=True,
    )
    def chain_expiries(source, history, id_dict, flow_data):
        ticker = str((id_dict or {}).get("index") or "").upper()
        if source == "historical":
            report = _historical_report(ticker, history)
            if not report:
                return [], None, render_expiry_navigation({}, None)
            day = date.fromisoformat(report["historical"]["date"])
        else:
            report = _current_report(flow_data, ticker)
            if not report:
                raise PreventUpdate
            day = None
        chains = report.get("option_chains") or {}
        options = [{"label": expiry_option_label(k, chains.get(k) or [], today=day), "value": k}
                   for k in sorted(chains)]
        selected = default_chain_expiry(chains, today=day)
        return options, selected, render_expiry_navigation(chains, selected, today=day)

    @app.callback(
        Output({"type": "flow-chain-body", "index": MATCH}, "children"),
        Input({"type": "flow-chain-expiry", "index": MATCH}, "value"),
        Input({"type": "flow-chain-filter", "index": MATCH}, "value"),
        Input({"type": "flow-chain-source", "index": MATCH}, "value"),
        Input({"type": "flow-chain-history", "index": MATCH}, "data"),
        State({"type": "flow-chain-expiry", "index": MATCH}, "id"),
        State("flow-data-store", "data"),
        State("theme-store", "data"),
        prevent_initial_call=True,
    )
    def update_chain_table(expiry, filter_value, source, history, id_dict, flow_data, theme_name):
        ticker = str((id_dict or {}).get("index") or "").upper()
        if source == "historical":
            report = _historical_report(ticker, history)
            if not report:
                return [html.Div("Choose a past trading date and click Load history to see the contracts quoted that day.",
                                 className="sfa-flow-section-empty")]
        else:
            report = _current_report(flow_data, ticker)
            if not report:
                raise PreventUpdate
        theme = get_theme(theme_name or DEFAULT_THEME)
        return table_from_report(report, expiry=expiry, theme=theme,
                                 view=str(filter_value or DEFAULT_CHAIN_VIEW).lower())

    # --- historical replay in the paper panel -------------------------------

    @app.callback(
        Output("flow-paper-replay-built", "data"),
        Output("flow-paper-message", "children", allow_duplicate=True),
        Input("flow-paper-strategy-selection", "data"),
        State("app-url", "pathname"),
        prevent_initial_call=True,
    )
    def build_historical_replay(selection, pathname):
        if not selection or selection.get("source") != "historical" or not is_flow_route(pathname):
            raise PreventUpdate
        ticker = flow_store.normalize_ticker(extract_path_ticker(pathname))
        if flow_store.normalize_ticker(selection.get("ticker")) != ticker:
            raise PreventUpdate
        existing = flow_history.find_replay_by_nonce(ticker, selection.get("nonce"))
        if existing:
            return {"id": existing["id"], "nonce": selection.get("nonce")}, no_update
        try:
            replay = flow_history.build_replay(ticker, selection.get("trade_date"), selection.get("legs") or [],
                                               nonce=selection.get("nonce"))
        except (ValueError, DataFetchError) as exc:
            return no_update, _load_error(exc)
        days = len(replay["snapshots"])
        message = (f"Loaded {days} trading day{'s' if days != 1 else ''} of {replay['source']} quotes from "
                   f"{display_date(replay['trade_date'])} to {display_date(replay['last_available'])}. "
                   "Review the entry prices, then open the strategy.")
        if replay["ended_early"]:
            message += (f" History ends before the contract expiry ({display_date(replay['expiry'])}).")
        return {"id": replay["id"], "nonce": selection.get("nonce")}, message

    @app.callback(
        Output("flow-paper-replay-source", "options"),
        Output("flow-paper-replay-source", "value"),
        Output("flow-paper-mode", "value"),
        Input("app-url", "pathname"),
        Input("flow-paper-replay-built", "data"),
        State("flow-paper-replay-source", "value"),
    )
    def replay_sources(pathname, built, current):
        if not is_flow_route(pathname):
            raise PreventUpdate
        ticker = flow_store.normalize_ticker(extract_path_ticker(pathname))
        options = replay_options(ticker)
        if callback_context.triggered_id == "flow-paper-replay-built" and built:
            return options, built["id"], "replay"
        values = {o["value"] for o in options}
        return options, current if current in values else RECORDED, no_update

    @app.callback(
        Output("flow-paper-replay-source-wrap", "style"),
        Input("flow-paper-mode", "value"),
    )
    def toggle_replay_source(mode):
        return {} if mode == "replay" else {"display": "none"}

    @app.callback(
        Output("flow-paper-replay-ledger", "children"),
        Input("flow-paper-state", "data"), Input("flow-paper-revision", "data"),
    )
    def render_replay_ledger(state, _revision):
        ticker = (state or {}).get("ticker")
        replay = flow_history.load_replay(ticker, (state or {}).get("replay")) if ticker else None
        if not replay:
            return None
        index = min(int(state.get("index", 0)), len(replay["snapshots"]) - 1)
        return ledger(ticker, replay, index)
