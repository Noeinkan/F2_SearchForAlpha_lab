"""Layout of the Flow strategy panel: legs table, expiry payoff and Greeks (callbacks/flow_strategy.py)."""

from __future__ import annotations

from dash import dash_table, dcc, html

from lib.dash.flow_strategy import PRESETS


def _field(label: str, ident: str, value, step) -> html.Div:
    return html.Div([html.Label(label, htmlFor=ident),
                     dcc.Input(id=ident, type="number", value=value, step=step, debounce=True)],
                    className="sfa-flow-strategy-field")


def panel(theme: dict) -> html.Details:
    return html.Details([
        html.Summary("Strategy · payoff & Greeks", className="sfa-flow-strategy-panel-summary",
                     **{"data-explain-head": ""}),  # ✦ smart help, 95-explain.js
        html.Div([
            html.P("Click a bid or ask in the option chain and choose “Add to strategy”, or start from a "
                   "template. Edit any cell to try a what-if: quantity + buys and − sells, premium is per "
                   "share. European Black–Scholes estimates, before fees; US equity options can be "
                   "exercised early, especially around dividends.", className="sfa-flow-strategy-intro"),
            html.Div([
                _field("Spot ($)", "flow-strategy-spot", None, 0.01),
                _field("Days to expiry", "flow-strategy-days", 30, 1),
                _field("Risk-free rate (%)", "flow-strategy-rate", 5, 0.1),
                _field("Dividend yield (%)", "flow-strategy-yield", 0, 0.1),
                html.Div([html.Label("Start from a template", htmlFor="flow-strategy-preset"),
                          dcc.Dropdown(id="flow-strategy-preset", placeholder="Choose…", clearable=False,
                                       searchable=False, className="sfa-flow-paper-dropdown",
                                       options=[{"label": a, "value": b} for a, b in PRESETS])],
                         className="sfa-flow-strategy-field sfa-flow-strategy-field-wide"),
            ], className="sfa-flow-strategy-controls"),
            dash_table.DataTable(
                id="flow-strategy-legs", data=[], editable=True, row_deletable=True,
                columns=[{"name": "Qty (+ buy / − sell)", "id": "quantity", "type": "numeric"},
                         {"name": "Call / put", "id": "kind", "presentation": "dropdown"},
                         {"name": "Strike ($)", "id": "strike", "type": "numeric"},
                         {"name": "Premium ($/share)", "id": "premium", "type": "numeric"},
                         {"name": "IV (%)", "id": "iv", "type": "numeric"}],
                dropdown={"kind": {"options": [{"label": "call", "value": "call"},
                                               {"label": "put", "value": "put"}], "clearable": False}},
                style_table={"overflowX": "auto"},
                style_cell={"backgroundColor": theme["bg_tertiary"], "color": theme["text_primary"],
                            "border": f"1px solid {theme['border_primary']}", "textAlign": "left",
                            "minWidth": "90px", "fontSize": "12px"},
                style_header={"backgroundColor": theme["table_header_bg"], "fontWeight": "bold"},
                css=[{"selector": ".Select-value-label", "rule": f"color: {theme['text_primary']} !important"}],
            ),
            html.Div([
                html.Button("Add leg", id="flow-strategy-add-leg", n_clicks=0,
                            className="sfa-flow-paper-button secondary"),
                html.Button("Clear", id="flow-strategy-clear", n_clicks=0,
                            className="sfa-flow-paper-button secondary"),
            ], className="sfa-flow-strategy-actions"),
            html.Div(id="flow-strategy-message", role="status", className="sfa-flow-strategy-message"),
            html.Div([
                dcc.Graph(id="flow-strategy-chart", config={"displayModeBar": False},
                          className="sfa-flow-strategy-chart", style={"display": "none"}),
                html.Div([html.Div(id="flow-strategy-summary"), html.Div(id="flow-strategy-greeks")],
                         className="sfa-flow-strategy-results"),
            ], className="sfa-flow-strategy-output"),
            html.Div(id="flow-strategy-notes", className="sfa-flow-strategy-notes"),
            html.Button("Send to paper trading →", id="flow-strategy-paper", n_clicks=0, disabled=True,
                        className="sfa-flow-paper-button primary",
                        title="Only legs taken from the option chain can be paper traded"),
            # Written by assets/52-flow-strategy.js when "Add to strategy" is clicked in the chain.
            dcc.Store(id="flow-strategy-add"),
            dcc.Store(id="flow-strategy-context", data={}),
        ], className="sfa-flow-strategy-body"),
    ], id="flow-strategy-panel", className="sfa-flow-strategy-panel", open=False,
        **{"data-explain-panel": "Strategy payoff & Greeks"})
