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
        html.Summary("Paper options & replay", className="sfa-flow-paper-summary",
                     **{"data-explain-head": ""}),  # ✦ smart help, 95-explain.js
        html.Div([
            html.Div([
                html.Strong("Practise options without placing a real order"),
                html.P("Try one option here, or send a strategy from the option chain. Paper entries use recorded asks for buys and bids for sells."),
            ], className="sfa-flow-paper-intro"),
            dcc.RadioItems(
                id="flow-paper-mode",
                options=[{"label": "Paper trading", "value": "paper"}, {"label": "Historical replay", "value": "replay"}],
                value="paper", inline=True, className="sfa-flow-paper-mode",
            ),
            html.Div([
                html.Label("Replay source", htmlFor="flow-paper-replay-source"),
                dcc.Dropdown(id="flow-paper-replay-source", className="sfa-flow-paper-dropdown",
                             options=[{"label": "Recorded scans", "value": "recorded"}],
                             value="recorded", clearable=False, searchable=False),
                html.Small("Recorded scans replays this page's own snapshots. A historical replay is created "
                           "when you send a strategy built on a historical option chain to paper trading."),
            ], id="flow-paper-replay-source-wrap", className="sfa-flow-paper-field sfa-flow-paper-replay-source",
                style={"display": "none"}),
            html.Div([
                html.Div(id="flow-paper-observation", className="sfa-flow-paper-observation"),
                html.Button("Next observation →", id="flow-paper-next", n_clicks=0, className="sfa-flow-paper-button secondary"),
            ], className="sfa-flow-paper-timeline"),
            html.Div(id="flow-paper-replay-ledger", className="sfa-flow-paper-replay-ledger"),
            dcc.Store(id="flow-paper-replay-built"),
            html.Div([
                html.Section([
                    html.Div([html.H4("Buy an option"), html.Span("PAPER ORDER", className="sfa-flow-ticket-badge")],
                             className="sfa-flow-ticket-head"),
                    html.Label("Option contract", htmlFor="flow-paper-contract"),
                    dcc.Dropdown(id="flow-paper-contract", className="sfa-flow-paper-dropdown", placeholder="Choose a call or put"),
                    html.Div([
                        html.Div([html.Label("Contracts", htmlFor="flow-paper-quantity"),
                                  dcc.Input(id="flow-paper-quantity", type="number", min=1, max=100, step=1, value=1,
                                            inputMode="numeric")], className="sfa-flow-paper-field"),
                        html.Div([html.Label("Fee / contract / side", htmlFor="flow-paper-fee"),
                                  dcc.Input(id="flow-paper-fee", type="number", min=0, value=0.54, step=0.01)],
                                 className="sfa-flow-paper-field"),
                    ], className="sfa-flow-ticket-inputs"),
                    html.Div(id="flow-paper-quote-preview", className="sfa-flow-paper-preview sfa-flow-ticket-breakdown"),
                    html.Div([
                        html.Small("Robinhood UK stock options: $0.50 contract fee + $0.04 regulatory/OCC fee per side. "
                                   "Other sell-side or FX charges may apply."),
                    ], className="sfa-flow-ticket-note"),
                    html.Button("Buy 1 contract at ask", id="flow-paper-buy", n_clicks=0,
                                className="sfa-flow-paper-button primary sfa-flow-ticket-submit"),
                ], className="sfa-flow-paper-card sfa-flow-order-ticket"),
                html.Section([
                    html.H4("2 · Track or close"),
                    html.Label("Open position", htmlFor="flow-paper-position"),
                    dcc.Dropdown(id="flow-paper-position", className="sfa-flow-paper-dropdown", placeholder="Choose an open position"),
                    html.Div(id="flow-paper-close-preview", className="sfa-flow-paper-preview"),
                    html.Button("Close at observed bid", id="flow-paper-close", n_clicks=0, className="sfa-flow-paper-button secondary"),
                ], className="sfa-flow-paper-card"),
            ], className="sfa-flow-paper-grid"),
            html.Section([
                html.H4("Strategy from the option chain"),
                html.Div(id="flow-paper-strategy-preview", className="sfa-flow-paper-preview"),
                html.Button("Open this strategy in paper", id="flow-paper-strategy-open", n_clicks=0,
                            disabled=True, className="sfa-flow-paper-button primary"),
                html.Div([
                    html.Label("Open paper strategy", htmlFor="flow-paper-strategy-position"),
                    dcc.Dropdown(id="flow-paper-strategy-position", className="sfa-flow-paper-dropdown",
                                 placeholder="Choose a strategy to track or close"),
                    html.Div(id="flow-paper-strategy-close-preview", className="sfa-flow-paper-preview"),
                    html.Button("Close strategy at observed quotes", id="flow-paper-strategy-close", n_clicks=0,
                                disabled=True, className="sfa-flow-paper-button secondary"),
                ], className="sfa-flow-paper-strategy-track"),
            ], className="sfa-flow-paper-card sfa-flow-paper-strategy-card"),
            html.Div(id="flow-paper-message", role="status", className="sfa-flow-paper-message"),
            html.Div(id="flow-paper-positions", className="sfa-flow-paper-positions"),
            dcc.Store(id="flow-paper-strategy-selection"),
            dcc.Store(id="flow-paper-delete-target"),
            dcc.ConfirmDialog(id="flow-paper-delete-dialog"),
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
                    html.Button("Settle selected strategy", id="flow-paper-strategy-settle", n_clicks=0,
                                disabled=True, className="sfa-flow-paper-button secondary"),
                ], className="sfa-flow-paper-tools-row"),
            ], className="sfa-flow-paper-advanced", open=False),
        ], className="sfa-flow-paper-body"),
    ], className="sfa-flow-paper", open=True, **{"data-explain-panel": "Paper options & replay"})
