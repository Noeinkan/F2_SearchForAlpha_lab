"""Paper options controls and European date labels for the Flow Scanner."""

from __future__ import annotations

from dash import dcc, html

from lib.dash.flow_dates import display_date


def contract_label(contract: dict) -> str:
    side = "Call" if contract["cp"] == "C" else "Put"
    return f"{side} {contract['strike']:g} · expires {display_date(contract['expiry'])}"


def panel(theme: dict) -> html.Details:
    _ = theme
    return html.Details([
        html.Summary("Paper options & replay", className="sfa-flow-paper-summary"),
        html.Div([
            html.Div([
                html.Strong("Practise one option at a time"),
                html.P("A paper buy uses the recorded ask. A close uses a later recorded bid. No real order is sent."),
            ], className="sfa-flow-paper-intro"),
            dcc.RadioItems(
                id="flow-paper-mode",
                options=[{"label": "Paper trading", "value": "paper"}, {"label": "Historical replay", "value": "replay"}],
                value="paper", inline=True, className="sfa-flow-paper-mode",
            ),
            html.Div([
                html.Div(id="flow-paper-observation", className="sfa-flow-paper-observation"),
                html.Button("Next observation →", id="flow-paper-next", n_clicks=0, className="sfa-flow-paper-button secondary"),
            ], className="sfa-flow-paper-timeline"),
            html.Div([
                html.Section([
                    html.H4("1 · Open a position"),
                    html.Label("Option contract", htmlFor="flow-paper-contract"),
                    dcc.Dropdown(id="flow-paper-contract", className="sfa-flow-paper-dropdown", placeholder="Choose a call or put"),
                    html.Div(id="flow-paper-quote-preview", className="sfa-flow-paper-preview"),
                    html.Div([
                        html.Label("Fee per transaction ($)", htmlFor="flow-paper-fee"),
                        dcc.Input(id="flow-paper-fee", type="number", min=0, value=0, step=0.01),
                    ], className="sfa-flow-paper-field"),
                    html.Button("Buy 1 contract at ask", id="flow-paper-buy", n_clicks=0, className="sfa-flow-paper-button primary"),
                ], className="sfa-flow-paper-card"),
                html.Section([
                    html.H4("2 · Track or close"),
                    html.Label("Open position", htmlFor="flow-paper-position"),
                    dcc.Dropdown(id="flow-paper-position", className="sfa-flow-paper-dropdown", placeholder="Choose an open position"),
                    html.Div(id="flow-paper-close-preview", className="sfa-flow-paper-preview"),
                    html.Button("Close at observed bid", id="flow-paper-close", n_clicks=0, className="sfa-flow-paper-button secondary"),
                ], className="sfa-flow-paper-card"),
            ], className="sfa-flow-paper-grid"),
            html.Div(id="flow-paper-message", role="status", className="sfa-flow-paper-message"),
            html.Div(id="flow-paper-positions", className="sfa-flow-paper-positions"),
            html.Details([
                html.Summary("Historical data & expiry settlement"),
                html.P("Import recorded observations to replay them in order. Missing quotes stay missing; a historical entry premium can be recorded only when no ask exists."),
                dcc.Upload(id="flow-paper-import", children=html.Button("Import snapshots JSON", className="sfa-flow-paper-button secondary"),
                           accept=".json,application/json", multiple=False),
                html.P('JSON needs ticker, observed_at, underlying, and contracts with expiry, cp (C/P), strike, bid, ask, volume, and open_interest. Use null for missing quotes. Dates in imported data use ISO 8601.'),
                html.Div([
                    html.Label("Known entry premium ($)", htmlFor="flow-paper-entry-premium"),
                    dcc.Input(id="flow-paper-entry-premium", type="number", min=0, step=0.01),
                    html.Button("Record historical entry", id="flow-paper-record-entry", n_clicks=0, className="sfa-flow-paper-button secondary"),
                ], className="sfa-flow-paper-tools-row"),
                html.Div([
                    html.Div([html.Label("Settlement price ($)", htmlFor="flow-paper-settlement"),
                              dcc.Input(id="flow-paper-settlement", type="number", min=0, step=0.01)], className="sfa-flow-paper-field"),
                    html.Div([html.Label("Verified source", htmlFor="flow-paper-source"),
                              dcc.Input(id="flow-paper-source", type="text", placeholder="Exchange or source URL")], className="sfa-flow-paper-field"),
                    html.Div([html.Label("Settlement date", htmlFor="flow-paper-verified-at"),
                              dcc.DatePickerSingle(id="flow-paper-verified-at", display_format="DD/MM/YYYY", placeholder="DD/MM/YYYY")], className="sfa-flow-paper-field"),
                    html.Div([html.Label("Time (UTC)", htmlFor="flow-paper-verified-time"),
                              dcc.Input(id="flow-paper-verified-time", type="text", value="21:00", placeholder="HH:MM")], className="sfa-flow-paper-field"),
                    html.Button("Calculate expiry P&L", id="flow-paper-settle", n_clicks=0, className="sfa-flow-paper-button secondary"),
                ], className="sfa-flow-paper-tools-row"),
            ], className="sfa-flow-paper-advanced", open=False),
        ], className="sfa-flow-paper-body"),
    ], className="sfa-flow-paper", open=True)
