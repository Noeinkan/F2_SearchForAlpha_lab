"""Paper options display callbacks, kept separate from order actions."""

from __future__ import annotations

from dash import html
from dash.dependencies import Input, Output, State

from lib.dash import flow_history, flow_paper
from lib.dash.callbacks.flow_history import selection_problem
from lib.dash.flow_paper_view import contract_label
from lib.dash.flow_dates import display_date


def _money(value):
    return f"${value:,.2f}" if value is not None else "missing"


def order_quantity(value) -> int | None:
    """Whole contracts 1–100 from the ticket input; anything else is not orderable."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    if value != int(value) or not 1 <= value <= 100:
        return None
    return int(value)


def order_summary(contract: dict, qty: int, fee: float):
    """Robinhood-style order review: each line of what the paper buy will cost."""
    ask = contract["ask"]
    multiplier = contract.get("multiplier", 100)
    premium = ask * multiplier * qty
    fees = fee * qty
    total = premium + fees
    per_share = total / (multiplier * qty)
    strike = contract["strike"]
    call = contract["cp"] == "C"
    break_even = strike + per_share if call else strike - per_share
    max_gain = "Unlimited" if call else _money(max(strike - per_share, 0) * multiplier * qty)
    rows = [
        ("Limit price (observed ask)", f"{_money(ask)} / share"),
        ("Contracts", f"{qty} × {multiplier} shares"),
        ("Premium", _money(premium)),
        ("Fees", f"{_money(fees)}  ({_money(fee)} × {qty})"),
        ("Estimated cost", _money(total)),
        ("Break-even at expiry", f"{_money(break_even)}"),
        ("Max loss", _money(total)),
        ("Max gain", max_gain),
    ]
    return html.Dl([
        html.Div([html.Dt(label), html.Dd(value)],
                 className="sfa-flow-ticket-row" + (" total" if label == "Estimated cost" else ""))
        for label, value in rows
    ], className="sfa-flow-ticket-rows")


def _delete_button(kind: str, record_id: str):
    return html.Button("Delete", id={"type": "flow-paper-delete", "index": f"{kind}:{record_id}"},
                       n_clicks=0, className="sfa-flow-paper-delete",
                       title="Permanently remove this paper trade")


def register_flow_paper_ui_callbacks(app) -> None:
    @app.callback(
        Output("flow-paper-observation", "children"),
        Output("flow-paper-contract", "options"),
        Output("flow-paper-contract", "value"),
        Output("flow-paper-position", "options"),
        Output("flow-paper-position", "value"),
        Output("flow-paper-strategy-position", "options"),
        Output("flow-paper-strategy-position", "value"),
        Output("flow-paper-positions", "children"),
        Output("flow-paper-next", "disabled"),
        Output("flow-paper-next", "style"),
        Input("flow-paper-state", "data"), Input("flow-paper-revision", "data"),
        Input("flow-paper-mode", "value"),
        State("flow-paper-contract", "value"), State("flow-paper-position", "value"),
        State("flow-paper-strategy-position", "value"),
    )
    def render_paper(state, _revision, mode, selected_contract, selected_position, selected_strategy):
        ticker = (state or {}).get("ticker")
        next_style = {} if mode == "replay" else {"display": "none"}
        if not ticker:
            return "No snapshot yet", [], None, [], None, [], None, "", True, next_style
        replay_id = state.get("replay")
        data = flow_paper.load(ticker)
        snapshots = flow_paper.timeline(ticker, replay_id)
        if not snapshots:
            empty = ("This historical replay has no observations." if replay_id
                     else "No observations yet. Click RESCAN NOW above to begin.")
            return empty, [], None, [], None, [], None, "", True, next_style
        index = min(int(state.get("index", 0)), len(snapshots) - 1)
        snap = snapshots[index]
        kind = "Historical replay (ThetaData end of day)" if replay_id else ("Replay" if mode == "replay" else "Latest")
        label = (f"{kind} observation {index + 1} of {len(snapshots)}"
                 f" · {display_date(snap['observed_at'], time=True)} · underlying {_money(snap.get('underlying'))}")
        for gap in snap.get("missing") or []:
            _, cp, strike = gap["key"].split("|")
            label += f" · ⚠ {'Call' if cp == 'C' else 'Put'} {strike}: {gap['what']} on this day"
        if replay_id and index == len(snapshots) - 1:
            replay = flow_history.load_replay(ticker, replay_id) or {}
            if replay.get("ended_early"):
                label += (f" · Replay ended early: last available {display_date(replay['last_available'])}, "
                          f"contract expires {display_date(replay['expiry'])}")
            else:
                label += " · Last observation: the contract expiry"
        if state.get("error"):
            label += f" · {state['error']}"
        options = [{"label": f"{contract_label(c)} · ask {_money(c.get('ask'))} · bid {_money(c.get('bid'))}",
                    "value": c["key"]} for c in snap["contracts"]]
        keys = {o["value"] for o in options}
        contract_value = selected_contract if selected_contract in keys else (options[0]["value"] if options else None)
        data["positions"] = [p for p in data["positions"] if flow_paper.in_context(p, replay_id)]
        data["strategies"] = [p for p in data["strategies"] if flow_paper.in_context(p, replay_id)]
        visible = [p for p in data["positions"] if mode != "replay" or p["opened_at"] <= snap["observed_at"]]
        def exit_in_future(p):
            return mode == "replay" and (p.get("closed_at") or p.get("settlement_verified_at") or "") > snap["observed_at"]
        open_positions = [p for p in visible if p["status"] == "open" or exit_in_future(p)]
        position_options = [{"label": f"{p.get('quantity', 1)} × {'Call' if p['cp'] == 'C' else 'Put'} {p['strike']:g} · {display_date(p['opened_at'], time=True)}",
                             "value": p["id"]} for p in open_positions]
        position_ids = {o["value"] for o in position_options}
        position_value = selected_position if selected_position in position_ids else (position_options[0]["value"] if position_options else None)
        visible_strategies = [p for p in data["strategies"] if mode != "replay" or p["opened_at"] <= snap["observed_at"]]
        open_strategies = [p for p in visible_strategies if p["status"] == "open" or exit_in_future(p)]
        strategy_options = [{"label": f"{len(p['legs'])} options · expires {display_date(p['expiry'])} · {display_date(p['opened_at'], time=True)}",
                             "value": p["id"]} for p in open_strategies]
        strategy_ids = {o["value"] for o in strategy_options}
        strategy_value = selected_strategy if selected_strategy in strategy_ids else (strategy_options[0]["value"] if strategy_options else None)
        cards = []
        for p in visible:
            q = flow_paper.quote(snap, p["contract"])
            future_exit = exit_in_future(p)
            status = "open" if future_exit else p["status"]
            mark = flow_paper.valuation(p, q.get("bid") if q else None) if status == "open" else p.get("pnl")
            pnl_label = "Open P&L before closing fee" if status == "open" else "Realised P&L"
            cards.append((p["opened_at"], html.Div([
                html.Div([
                    html.Div(f"{'Call' if p['cp'] == 'C' else 'Put'} {p['strike']:g} · expires {display_date(p['expiry'])} · {status.title()}",
                             className="sfa-flow-paper-position-title"),
                    _delete_button("position", p["id"]),
                ], className="sfa-flow-paper-position-head"),
                html.Div(f"Entry {display_date(p['opened_at'], time=True)} at {'known premium' if p.get('entry_source') else 'observed ask'} "
                         f"{_money(p['entry_ask'])} × {p['multiplier']} × {p.get('quantity', 1)} contract{'s' if p.get('quantity', 1) != 1 else ''}"
                         f" · fees {_money(p['entry_fee'])} · maximum loss {_money(p['max_loss'])}",
                         className="sfa-flow-paper-position-meta"),
                html.Div(f"Expiry break-even {_money(flow_paper.break_even(p))} · "
                         + (f"{pnl_label} {_money(mark)}" if mark is not None else "P&L unavailable: no observed bid")
                         + (f" · settlement {_money(p['settlement_price'])} ({p['settlement_source']})" if status == "expired" else ""),
                         className="sfa-flow-paper-position-meta"),
            ], className="sfa-flow-paper-position-card")))
        for p in visible_strategies:
            future_exit = exit_in_future(p)
            status = "open" if future_exit else p["status"]
            mark = flow_paper.strategy_valuation(p, snap) if status == "open" else p.get("pnl")
            legs_text = " · ".join(
                f"{'Buy' if leg['side'] == 'buy' else 'Sell'} {leg['qty']} {'Call' if leg['cp'] == 'C' else 'Put'} {leg['strike']:g}"
                for leg in p["legs"]
            )
            cash = p["entry_cashflow"]
            cards.append((p["opened_at"], html.Div([
                html.Div([
                    html.Div(f"Paper strategy · {len(p['legs'])} options · expires {display_date(p['expiry'])} · {status.title()}",
                             className="sfa-flow-paper-position-title"),
                    _delete_button("strategy", p["id"]),
                ], className="sfa-flow-paper-position-head"),
                html.Div(legs_text, className="sfa-flow-paper-position-meta"),
                html.Div(f"Opened {display_date(p['opened_at'], time=True)} · "
                         f"{'received' if cash >= 0 else 'paid'} {_money(abs(cash))} including entry fees",
                         className="sfa-flow-paper-position-meta"),
                html.Div((f"{'Open P&L before closing fees' if status == 'open' else 'Realised P&L'} {_money(mark)}"
                          if mark is not None else "P&L unavailable: a closing quote is missing")
                         + (f" · settlement {_money(p['settlement_price'])} ({p['settlement_source']})" if status == "expired" else ""),
                         className="sfa-flow-paper-position-meta"),
            ], className="sfa-flow-paper-position-card")))
        if not cards:
            card_children = [html.Div("No paper trades yet. Choose one option or send a strategy from the chain.", className="sfa-flow-paper-position-meta")]
        else:
            card_children = [card for _, card in sorted(cards, key=lambda item: item[0], reverse=True)]
        return (label, options, contract_value, position_options, position_value,
                strategy_options, strategy_value, card_children,
                (mode != "replay" or index >= len(snapshots) - 1), next_style)

    @app.callback(
        Output("flow-paper-quote-preview", "children"), Output("flow-paper-buy", "disabled"),
        Output("flow-paper-buy", "children"),
        Output("flow-paper-close-preview", "children"), Output("flow-paper-close", "disabled"),
        Output("flow-paper-record-entry", "disabled"), Output("flow-paper-settle", "disabled"),
        Input("flow-paper-state", "data"), Input("flow-paper-contract", "value"),
        Input("flow-paper-position", "value"), Input("flow-paper-fee", "value"),
        Input("flow-paper-entry-premium", "value"), Input("flow-paper-mode", "value"),
        Input("flow-paper-quantity", "value"),
    )
    def preview_paper(state, key, position_id, fee, entry_premium, mode, quantity):
        qty = order_quantity(quantity)
        buy_label = f"Buy {qty or '–'} contract{'s' if qty != 1 else ''} at ask"
        ticker = (state or {}).get("ticker")
        data = flow_paper.load(ticker) if ticker else {"snapshots": [], "positions": []}
        snapshots = flow_paper.timeline(ticker, state.get("replay")) if ticker else []
        if not snapshots:
            return "Rescan to load contracts and quotes.", True, buy_label, "No open position yet.", True, True, True
        snap = snapshots[min(int(state.get("index", 0)), len(snapshots) - 1)]
        contract = flow_paper.quote(snap, key)
        ask = contract.get("ask") if contract else None
        charge = fee if isinstance(fee, (int, float)) and fee >= 0 else 0
        if not ask:
            buy_preview = "Observed ask missing. This contract cannot be paper bought."
        elif qty is None:
            buy_preview = "Enter a whole number of contracts between 1 and 100."
        else:
            buy_preview = order_summary(contract, qty, charge)
        p = next((row for row in data["positions"] if row["id"] == position_id), None)
        q = flow_paper.quote(snap, p["contract"]) if p else None
        bid = q.get("bid") if q else None
        closable = bool(p and p["status"] == "open" and snap["observed_at"] > p["opened_at"] and bid)
        if closable:
            held = p.get("quantity", 1)
            pnl = (bid - p["entry_ask"]) * p["multiplier"] * held - p["entry_fee"] - charge * held
            close_preview = (f"Sell {held} contract{'s' if held != 1 else ''} at observed bid {_money(bid)} × {p['multiplier']} · "
                             f"estimated realised P&L {_money(pnl)} including closing fees.")
        else:
            close_preview = "Select an open position. A later observation with a bid is required to close."
        historical = bool(mode == "replay" and contract and not ask and qty
                          and isinstance(entry_premium, (int, float)) and entry_premium > 0)
        return (buy_preview, not (ask and qty), buy_label, close_preview,
                not closable, not historical, not bool(p and p["status"] == "open"))

    @app.callback(
        Output("flow-paper-strategy-preview", "children"), Output("flow-paper-strategy-open", "disabled"),
        Output("flow-paper-strategy-close-preview", "children"), Output("flow-paper-strategy-close", "disabled"),
        Output("flow-paper-strategy-settle", "disabled"),
        Input("flow-paper-state", "data"), Input("flow-paper-strategy-selection", "data"),
        Input("flow-paper-strategy-position", "value"), Input("flow-paper-fee", "value"),
        Input("flow-paper-mode", "value"), Input("flow-paper-revision", "data"),
    )
    def preview_strategy(state, selection, strategy_id, fee, mode, _revision):
        ticker = (state or {}).get("ticker")
        data = flow_paper.load(ticker) if ticker else {"snapshots": [], "strategies": []}
        replay_id = (state or {}).get("replay")
        snapshots = flow_paper.timeline(ticker, replay_id) if ticker else []
        if not snapshots:
            return "Rescan to record option quotes first.", True, "No open strategy yet.", True, True
        snap = snapshots[min(int(state.get("index", 0)), len(snapshots) - 1)]
        charge = fee if isinstance(fee, (int, float)) and fee >= 0 else None
        problem = selection_problem(selection, mode, replay_id, ticker) if selection else None
        if selection and selection.get("ticker") == ticker and not problem:
            try:
                priced = flow_paper.quote_strategy(snap, selection.get("legs") or [], fee_per_contract=charge)
                leg_lines = [
                    html.Div(f"Priced at the observation of {display_date(snap['observed_at'], time=True)}"
                             + (" (historical end-of-day quotes)" if replay_id else "")),
                ] + [
                    html.Div(f"{'Buy' if leg['side'] == 'buy' else 'Sell'} {leg['qty']} "
                             f"{'Call' if leg['cp'] == 'C' else 'Put'} {leg['strike']:g} at observed "
                             f"{'ask' if leg['side'] == 'buy' else 'bid'} {_money(leg['entry_price'])} × {leg['multiplier']}")
                    for leg in priced["legs"]
                ]
                cash = priced["entry_cashflow"]
                entry_preview = html.Div([
                    html.Div(f"Expires {display_date(priced['expiry'])} · "
                             f"{'receive' if cash >= 0 else 'pay'} {_money(abs(cash))} including entry fees"),
                    *leg_lines,
                    html.Div("Review these recorded prices, then open the whole strategy as one paper trade.",
                             className="sfa-flow-paper-strategy-preview-note"),
                ])
                can_open = True
            except (ValueError, TypeError, KeyError) as exc:
                entry_preview, can_open = f"Cannot open this selection: {exc}", False
        elif selection and problem:
            entry_preview, can_open = problem, False
        else:
            entry_preview, can_open = "Build a strategy in the option chain and choose ‘Send to paper trading’. ", False
        position = next((p for p in data["strategies"] if p["id"] == strategy_id), None)
        closable = bool(position and position["status"] == "open" and snap["observed_at"] > position["opened_at"])
        mark = flow_paper.strategy_valuation(position, snap) if closable else None
        if mark is None:
            closable = False
            close_preview = "A later observation with quotes for every leg is needed to close this strategy."
        else:
            fee_total = charge * sum(leg["qty"] for leg in position["legs"]) if charge is not None else 0
            close_preview = f"Estimated realised P&L {_money(mark - fee_total)} including {_money(fee_total)} closing fees."
        return entry_preview, not can_open, close_preview, not closable, not bool(position and position["status"] == "open")
