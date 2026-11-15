"""Compact paper and historical replay controls for the Flow Scanner."""

from dash import dcc, html


def panel(theme: dict) -> html.Details:
    control = {"minWidth": "150px", "maxWidth": "270px", "fontSize": "12px"}
    button = {"padding": "6px 10px", "cursor": "pointer"}
    return html.Details([
        html.Summary("Options paper trading & historical replay"),
        html.P("One long call or put per position. Buys use the observed ask; closes and open P&L use the observed bid. Missing quotes block execution.",
               style={"fontSize": "12px", "color": theme["text_secondary"]}),
        html.Div([
            dcc.RadioItems(id="flow-paper-mode", options=[{"label": "Paper", "value": "paper"}, {"label": "Replay", "value": "replay"}],
                           value="paper", inline=True),
            html.Span(id="flow-paper-observation", style={"fontSize": "12px"}),
            html.Button("Next observation", id="flow-paper-next", n_clicks=0, style=button),
            dcc.Upload(id="flow-paper-import", children=html.Button("Import snapshots JSON", style=button),
                       accept=".json,application/json", multiple=False),
        ], style={"display": "flex", "gap": "12px", "alignItems": "center", "flexWrap": "wrap"}),
        html.P('Import a JSON snapshot or {"snapshots": [ ... ]}. Each observation needs ticker, observed_at, underlying, and contracts with expiry, cp (C/P), strike, bid, ask, volume, and open_interest. Use null for missing quotes.',
               style={"fontSize": "11px", "color": theme["text_secondary"], "margin": "6px 0"}),
        html.Div([
            html.Label("Contract"), dcc.Dropdown(id="flow-paper-contract", style=control),
            html.Label("Fee per side ($)"), dcc.Input(id="flow-paper-fee", type="number", min=0, value=0, step=0.01, style={"width": "85px"}),
            html.Button("Buy 1", id="flow-paper-buy", n_clicks=0, style=button),
            html.Label("Known entry premium ($)"), dcc.Input(id="flow-paper-entry-premium", type="number", min=0, step=0.01, style={"width": "90px"}),
            html.Button("Record historical entry", id="flow-paper-record-entry", n_clicks=0, style=button),
            html.Label("Open position"), dcc.Dropdown(id="flow-paper-position", style=control),
            html.Button("Close at bid", id="flow-paper-close", n_clicks=0, style=button),
        ], style={"display": "flex", "gap": "8px", "alignItems": "center", "flexWrap": "wrap", "marginTop": "12px"}),
        html.Div([
            html.Label("Expiry settlement ($)"), dcc.Input(id="flow-paper-settlement", type="number", min=0, step=0.01, style={"width": "110px"}),
            html.Label("Verified source (manual)"), dcc.Input(id="flow-paper-source", type="text", placeholder="Exchange / source URL", style={"minWidth": "180px"}),
            html.Label("Observed at (UTC)"), dcc.Input(id="flow-paper-verified-at", type="text", placeholder="YYYY-MM-DDTHH:MM:SSZ", style={"minWidth": "190px"}),
            html.Button("Settle at expiry", id="flow-paper-settle", n_clicks=0, style=button),
        ], style={"display": "flex", "gap": "8px", "alignItems": "center", "flexWrap": "wrap", "marginTop": "10px"}),
        html.Div(id="flow-paper-message", style={"fontSize": "12px", "marginTop": "8px"}),
        html.Div(id="flow-paper-positions", style={"fontSize": "12px", "marginTop": "8px"}),
    ], className="sfa-flow-paper", style={"padding": "12px", "borderBottom": f'1px solid {theme["border_primary"]}',
                                       "color": theme["text_primary"], "backgroundColor": theme["bg_secondary"]})
