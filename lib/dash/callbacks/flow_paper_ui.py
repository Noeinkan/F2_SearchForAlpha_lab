"""Paper options display callbacks, kept separate from order actions."""

from __future__ import annotations

from dash import html
from dash.dependencies import Input, Output, State

from lib.dash import flow_paper
from lib.dash.flow_paper_view import contract_label
from lib.dash.flow_dates import display_date


def _money(value):
    return f"${value:,.2f}" if value is not None else "missing"


def register_flow_paper_ui_callbacks(app) -> None:
    @app.callback(
        Output("flow-paper-observation", "children"),
        Output("flow-paper-contract", "options"),
        Output("flow-paper-contract", "value"),
        Output("flow-paper-position", "options"),
        Output("flow-paper-position", "value"),
        Output("flow-paper-positions", "children"),
        Output("flow-paper-next", "disabled"),
        Output("flow-paper-next", "style"),
        Input("flow-paper-state", "data"), Input("flow-paper-revision", "data"),
        Input("flow-paper-mode", "value"),
        State("flow-paper-contract", "value"), State("flow-paper-position", "value"),
    )
    def render_paper(state, _revision, mode, selected_contract, selected_position):
        ticker = (state or {}).get("ticker")
        next_style = {} if mode == "replay" else {"display": "none"}
        if not ticker:
            return "No snapshot yet", [], None, [], None, "", True, next_style
        data = flow_paper.load(ticker)
        snapshots = data["snapshots"]
        if not snapshots:
            return "No observations yet. Click RESCAN NOW above to begin.", [], None, [], None, "", True, next_style
        index = min(int(state.get("index", 0)), len(snapshots) - 1)
        snap = snapshots[index]
        label = (f"{'Replay' if mode == 'replay' else 'Latest'} observation {index + 1} of {len(snapshots)}"
                 f" · {display_date(snap['observed_at'], time=True)} · underlying {_money(snap.get('underlying'))}")
        if state.get("error"):
            label += f" · {state['error']}"
        options = [{"label": f"{contract_label(c)} · ask {_money(c.get('ask'))} · bid {_money(c.get('bid'))}",
                    "value": c["key"]} for c in snap["contracts"]]
        keys = {o["value"] for o in options}
        contract_value = selected_contract if selected_contract in keys else (options[0]["value"] if options else None)
        visible = [p for p in data["positions"] if mode != "replay" or p["opened_at"] <= snap["observed_at"]]
        def exit_in_future(p):
            return mode == "replay" and (p.get("closed_at") or p.get("settlement_verified_at") or "") > snap["observed_at"]
        open_positions = [p for p in visible if p["status"] == "open" or exit_in_future(p)]
        position_options = [{"label": f"{'Call' if p['cp'] == 'C' else 'Put'} {p['strike']:g} · {display_date(p['opened_at'], time=True)}",
                             "value": p["id"]} for p in open_positions]
        position_ids = {o["value"] for o in position_options}
        position_value = selected_position if selected_position in position_ids else (position_options[0]["value"] if position_options else None)
        cards = []
        for p in reversed(visible):
            q = flow_paper.quote(snap, p["contract"])
            future_exit = exit_in_future(p)
            status = "open" if future_exit else p["status"]
            mark = flow_paper.valuation(p, q.get("bid") if q else None) if status == "open" else p.get("pnl")
            pnl_label = "Open P&L before closing fee" if status == "open" else "Realised P&L"
            cards.append(html.Div([
                html.Div(f"{'Call' if p['cp'] == 'C' else 'Put'} {p['strike']:g} · expires {display_date(p['expiry'])} · {status.title()}",
                         className="sfa-flow-paper-position-title"),
                html.Div(f"Entry {display_date(p['opened_at'], time=True)} at {'known premium' if p.get('entry_source') else 'observed ask'} "
                         f"{_money(p['entry_ask'])} × {p['multiplier']} · fee {_money(p['entry_fee'])} · maximum loss {_money(p['max_loss'])}",
                         className="sfa-flow-paper-position-meta"),
                html.Div(f"Expiry break-even {_money(flow_paper.break_even(p))} · "
                         + (f"{pnl_label} {_money(mark)}" if mark is not None else "P&L unavailable: no observed bid")
                         + (f" · settlement {_money(p['settlement_price'])} ({p['settlement_source']})" if status == "expired" else ""),
                         className="sfa-flow-paper-position-meta"),
            ], className="sfa-flow-paper-position-card"))
        if not cards:
            cards = [html.Div("No positions yet. Choose a contract and use Buy 1 contract at ask.", className="sfa-flow-paper-position-meta")]
        return label, options, contract_value, position_options, position_value, cards, (mode != "replay" or index >= len(snapshots) - 1), next_style

    @app.callback(
        Output("flow-paper-quote-preview", "children"), Output("flow-paper-buy", "disabled"),
        Output("flow-paper-close-preview", "children"), Output("flow-paper-close", "disabled"),
        Output("flow-paper-record-entry", "disabled"), Output("flow-paper-settle", "disabled"),
        Input("flow-paper-state", "data"), Input("flow-paper-contract", "value"),
        Input("flow-paper-position", "value"), Input("flow-paper-fee", "value"),
        Input("flow-paper-entry-premium", "value"), Input("flow-paper-mode", "value"),
    )
    def preview_paper(state, key, position_id, fee, entry_premium, mode):
        ticker = (state or {}).get("ticker")
        data = flow_paper.load(ticker) if ticker else {"snapshots": [], "positions": []}
        if not data["snapshots"]:
            return "Rescan to load contracts and quotes.", True, "No open position yet.", True, True, True
        snap = data["snapshots"][min(int(state.get("index", 0)), len(data["snapshots"]) - 1)]
        contract = flow_paper.quote(snap, key)
        ask = contract.get("ask") if contract else None
        charge = fee if isinstance(fee, (int, float)) and fee >= 0 else 0
        buy_preview = (f"Observed ask {_money(ask)} × 100 + {_money(charge)} fee = {_money(ask * 100 + charge)} maximum loss."
                       if ask else "Observed ask missing. This contract cannot be paper bought.")
        p = next((row for row in data["positions"] if row["id"] == position_id), None)
        q = flow_paper.quote(snap, p["contract"]) if p else None
        bid = q.get("bid") if q else None
        closable = bool(p and p["status"] == "open" and snap["observed_at"] > p["opened_at"] and bid)
        close_preview = (f"Observed bid {_money(bid)} × {p['multiplier']} · estimated realised P&L "
                         f"{_money((bid - p['entry_ask']) * p['multiplier'] - p['entry_fee'] - charge)} including closing fee."
                         if closable else "Select an open position. A later observation with a bid is required to close.")
        historical = bool(mode == "replay" and contract and not ask and isinstance(entry_premium, (int, float)) and entry_premium > 0)
        return buy_preview, not bool(ask), close_preview, not closable, not historical, not bool(p and p["status"] == "open")
