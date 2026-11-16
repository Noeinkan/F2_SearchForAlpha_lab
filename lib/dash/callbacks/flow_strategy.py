"""Flow strategy panel: one editor for chain and typed legs, one pricing path (lib.options.pricing)."""

from __future__ import annotations

import time
from datetime import date

import plotly.graph_objects as go
from dash import Input, Output, State, callback_context, html, no_update
from dash.exceptions import PreventUpdate

from lib.dash import flow_store
from lib.dash.callbacks.flow_history import _current_report
from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.flow_strategy import (
    GREEKS, add_chain_leg, analyze, apply_edit, blank_row, curve, days_between, paper_selection, preset_rows,
)
from lib.dash.routes import extract_path_ticker, is_flow_route


def _money(value: float | None) -> str:
    return "No fixed limit" if value is None else f"${value:,.2f}"


def _signed(value: float) -> str:
    return f"{value:+,.3f}"


def _report_spot(flow_data, ticker: str | None) -> float | None:
    report = _current_report(flow_data, ticker) if ticker else None
    try:
        spot = float((report or {}).get("spot") or 0)
    except (TypeError, ValueError):
        return None
    return round(spot, 2) if spot > 0 else None


def _figure(result: dict, theme: dict) -> go.Figure:
    legs, spot = result["legs"], result["spot"]
    break_evens = result["summary"]["break_evens"]
    xs, ys = curve(legs, spot, break_evens)
    fig = go.Figure()
    fig.add_trace(go.Scatter(x=xs, y=[max(y, 0) for y in ys], mode="lines", fill="tozeroy", hoverinfo="skip",
                             line={"width": 0}, fillcolor="rgba(38,194,129,0.18)", showlegend=False))
    fig.add_trace(go.Scatter(x=xs, y=[min(y, 0) for y in ys], mode="lines", fill="tozeroy", hoverinfo="skip",
                             line={"width": 0}, fillcolor="rgba(239,83,80,0.18)", showlegend=False))
    fig.add_trace(go.Scatter(x=xs, y=ys, mode="lines", name="P/L at expiry",
                             line={"color": theme["accent_blue"], "width": 3},
                             hovertemplate="Underlying $%{x:,.2f}<br>P/L $%{y:,.2f}<extra></extra>"))
    if break_evens:
        fig.add_trace(go.Scatter(x=break_evens, y=[0] * len(break_evens), mode="markers+text",
                                 marker={"color": theme["accent_green"], "size": 9},
                                 text=[f"BE ${x:,.2f}" for x in break_evens], textposition="bottom center",
                                 textfont={"color": theme["accent_green"]}, hoverinfo="skip", showlegend=False))
    for strike in sorted({leg.strike for leg in legs}):
        fig.add_vline(x=strike, line_color=theme["text_tertiary"], line_width=1, line_dash="dot")
    fig.add_hline(y=0, line_color=theme["text_tertiary"], line_width=1)
    fig.add_vline(x=spot, line_color=theme["accent_cyan"], line_dash="dash",
                  annotation_text=f"Now ${spot:,.2f}", annotation_font_color=theme["accent_cyan"])
    fig.update_layout(template="plotly_dark", paper_bgcolor=theme["bg_primary"], plot_bgcolor=theme["bg_primary"],
                      margin={"l": 60, "r": 20, "t": 30, "b": 45}, height=340, showlegend=False,
                      xaxis_title="Underlying price at expiry ($)", yaxis_title="Profit / loss ($)",
                      font={"color": theme["text_secondary"]})
    fig.update_xaxes(gridcolor=theme["chart_grid"])
    fig.update_yaxes(gridcolor=theme["chart_grid"], zeroline=False)
    return fig


def _summary(result: dict) -> html.Div:
    summary, cash = result["summary"], result["net_premium"]
    entry = f"Pay ${cash:,.2f}" if cash > 0 else f"Receive ${-cash:,.2f}" if cash < 0 else "$0.00"
    best, worst = summary["max_profit"], summary["max_loss"]
    rows = [("At the start", entry),
            ("Break-even prices", " · ".join(f"${x:,.2f}" for x in summary["break_evens"]) or "None"),
            ("Best at expiry", _money(best)),
            ("Most you could lose", _money(None if worst is None else abs(min(worst, 0))))]
    if best is not None and worst is not None and best > 0 and worst < 0:
        rows.append(("Best gain ÷ most you could lose", f"{best / -worst:.2f}"))
    return html.Div([html.Div([html.Span(label), html.Strong(value)]) for label, value in rows],
                    className="sfa-flow-strategy-metrics")


def _greeks(result: dict) -> html.Div:
    totals = result["totals"]
    head = ("Strategy: " + " · ".join(f"{name.title()} {_signed(value)}" for name, value in totals.items())
            if totals else "Strategy Greeks need every leg to have an IV and time left to expiry.")
    body = []
    for p in result["priced"]:
        leg, greeks = p["leg"], p["greeks"]
        scale = leg.multiplier * leg.quantity
        iv = "—" if p["iv"] is None else f"{p['iv'] * 100:.1f}%" + ("*" if p["solved"] else "")
        cells = ["—" if not greeks or greeks[name] is None else _signed(greeks[name] * scale) for name in GREEKS]
        body.append(html.Tr([html.Td(f"{leg.quantity:+d} {leg.kind} {leg.strike:g}"), html.Td(iv),
                             html.Td("—" if not greeks else f"${greeks['value']:.2f}"),
                             *[html.Td(cell) for cell in cells]]))
    return html.Div([
        html.Div("Greeks per position (× contracts × multiplier)", className="sfa-flow-strategy-greeks-title"),
        html.Div(head, className="sfa-flow-strategy-greeks-total"),
        html.Table([html.Thead(html.Tr([html.Th(x) for x in ("Leg", "IV", "Model value", "Delta", "Gamma",
                                                             "Theta/day", "Vega/1%", "Rho/1%")])),
                    html.Tbody(body)], className="sfa-flow-strategy-greeks-table"),
    ])


def register_flow_strategy_callbacks(app) -> None:
    @app.callback(
        Output("flow-strategy-legs", "data"), Output("flow-strategy-spot", "value"),
        Output("flow-strategy-days", "value"), Output("flow-strategy-context", "data"),
        Output("flow-strategy-message", "children"), Output("flow-strategy-preset", "value"),
        Input("flow-strategy-add", "data"), Input("flow-strategy-preset", "value"),
        Input("flow-strategy-add-leg", "n_clicks"), Input("flow-strategy-clear", "n_clicks"),
        Input("flow-strategy-legs", "data_timestamp"),
        Input("app-url", "pathname"), Input("flow-data-store", "data"),
        State("flow-strategy-legs", "data"), State("flow-strategy-legs", "data_previous"),
        State("flow-strategy-context", "data"), State("flow-strategy-spot", "value"),
        State("flow-strategy-days", "value"), State("flow-strategy-rate", "value"),
        State("flow-strategy-yield", "value"),
    )
    def edit_strategy(added, preset, _add_leg, _clear, _edited, pathname, flow_data,
                      rows, previous, context, spot, days, rate, yield_pct):
        if not is_flow_route(pathname):
            raise PreventUpdate
        trigger = callback_context.triggered_id
        ticker = flow_store.normalize_ticker(extract_path_ticker(pathname))
        context = context or {}
        rows = rows or []
        keep = (no_update,) * 6
        if trigger == "flow-strategy-add":
            if not added or added.get("ticker") != ticker:
                raise PreventUpdate
            try:
                rows, context, fresh = add_chain_leg(rows, context, added)
            except ValueError as exc:
                return no_update, no_update, no_update, no_update, str(exc), no_update
            as_of = date.fromisoformat(context["trade_date"]) if context["trade_date"] else date.today()
            name = f"{rows[-1]['kind'].title()} ${rows[-1]['strike']:,.2f}"
            message = (f"{name} added" + (" as a new strategy" if fresh and len(rows) == 1 else "")
                       + ". Make the quantity negative to sell it.")
            return (rows, context.get("spot") or spot, days_between(context["expiry"], as_of), context,
                    message, no_update)
        if trigger == "flow-strategy-preset":
            if not preset:
                raise PreventUpdate
            try:
                new_rows = preset_rows(preset, spot=float(spot), days=float(days or 0),
                                       rate_pct=float(rate or 0), yield_pct=float(yield_pct or 0))
            except (TypeError, ValueError):
                return no_update, no_update, no_update, no_update, "Enter a positive spot first.", None
            return (new_rows, no_update, no_update, {"ticker": ticker},
                    "Template legs are priced at the model value with a 20% IV. Edit any cell.", None)
        if trigger == "flow-strategy-add-leg":
            return rows + [blank_row(spot)], no_update, no_update, no_update, "", no_update
        if trigger == "flow-strategy-clear":
            return [], _report_spot(flow_data, ticker) or spot, 30, {"ticker": ticker}, "", None
        if trigger == "flow-strategy-legs":
            return apply_edit(rows, previous), no_update, no_update, no_update, "", no_update
        # Page load, a ticker change or a rescan: follow the Flow ticker's spot.
        if context.get("ticker") and context.get("ticker") != ticker:
            return [], _report_spot(flow_data, ticker), 30, {"ticker": ticker}, "", None
        if any(row.get("key") for row in rows):
            return keep  # chain legs keep the spot of the quotes they were priced from
        fresh_spot = _report_spot(flow_data, ticker)
        if fresh_spot is None or fresh_spot == spot:
            raise PreventUpdate
        return no_update, fresh_spot, no_update, {**context, "ticker": ticker}, no_update, no_update

    @app.callback(
        Output("flow-strategy-chart", "figure"), Output("flow-strategy-chart", "style"),
        Output("flow-strategy-summary", "children"), Output("flow-strategy-greeks", "children"),
        Output("flow-strategy-notes", "children"), Output("flow-strategy-paper", "disabled"),
        Input("flow-strategy-legs", "data"), Input("flow-strategy-spot", "value"),
        Input("flow-strategy-days", "value"), Input("flow-strategy-rate", "value"),
        Input("flow-strategy-yield", "value"), Input("theme-store", "data"),
        State("flow-strategy-context", "data"),
    )
    def price_strategy(rows, spot, days, rate, yield_pct, theme_name, context):
        try:
            paper_selection(rows, context, 0)
            tradable = True
        except ValueError:
            tradable = False
        try:
            result = analyze(rows, spot=spot, days=days, rate_pct=rate, yield_pct=yield_pct)
        except ValueError as exc:
            return go.Figure(), {"display": "none"}, html.Div(str(exc), className="sfa-flow-strategy-empty"), \
                None, None, True
        theme = get_theme(theme_name or DEFAULT_THEME)
        notes = [html.Div(note) for note in result["notes"]]
        return _figure(result, theme), {}, _summary(result), _greeks(result), notes, not tradable

    @app.callback(
        Output("flow-paper-strategy-selection", "data", allow_duplicate=True),
        Output("flow-strategy-message", "children", allow_duplicate=True),
        Input("flow-strategy-paper", "n_clicks"),
        State("flow-strategy-legs", "data"), State("flow-strategy-context", "data"),
        prevent_initial_call=True,
    )
    def send_to_paper(clicks, rows, context):
        if not clicks:
            raise PreventUpdate
        try:
            selection = paper_selection(rows, context, int(time.time() * 1000))
        except ValueError as exc:
            return no_update, str(exc)
        if selection["source"] == "historical":
            return selection, "Loading daily quotes from that date through expiry for Historical replay…"
        return selection, "Strategy sent to paper trading. Review the recorded prices before opening it."
