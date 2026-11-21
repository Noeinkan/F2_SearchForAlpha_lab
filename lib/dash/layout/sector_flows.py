"""Layout and weekly comparison table for the Sector Flows workspace."""

from datetime import timedelta

from dash import dcc, html


def create_sector_flows_layout():
    return html.Main([
        html.H1("Sector Flows"),
        html.P("Weekly estimated net flows for selected U.S. sector and industry ETFs."),
        dcc.Loading(html.Div(id="sector-flows-result", **{"aria-live": "polite"})),
        html.P([
            "Daily changes in shares outstanding are valued at that day's NAV and summed weekly. "
            "Percentages use assets at the start of each week. Each row represents one ETF. ",
            html.A(
                "State Street NAV history",
                href="https://www.ssga.com/us/en/individual/capabilities/equities/sector-investing/sector-and-industry-etfs",
                target="_blank",
                rel="noopener noreferrer",
            ),
        ], className="sfa-sector-flows-note"),
    ], id="sector-flows-page", className="sfa-sector-flows", hidden=True)


def _flow_cell(value, *, percent=False):
    if value is None:
        return html.Td("—", title="Data unavailable")
    text = f"{value:+.2%}" if percent else f"{value / 1_000_000:+,.1f}"
    direction = "inflow" if value > 0 else "outflow" if value < 0 else ""
    return html.Td(text, className=direction)


def render_sector_flows(friday, rows):
    if friday is None or all(row["latest"] is None and row["prior"] is None for row in rows):
        return html.P("NAV history is temporarily unavailable. Reopen the page to retry.")

    previous = friday - timedelta(days=7)
    body = []
    for row in sorted(rows, key=lambda row: row["latest"][1] if row["latest"] else float("-inf"), reverse=True):
        prior, latest = row["prior"], row["latest"]
        change = latest[0] - prior[0] if latest is not None and prior is not None else None
        body.append(html.Tr([
            html.Th(row["label"], scope="row"),
            html.Td(row["ticker"]),
            _flow_cell(prior[0] if prior else None),
            _flow_cell(latest[0] if latest else None),
            _flow_cell(change),
            _flow_cell(latest[1] if latest else None, percent=True),
        ]))

    columns = ["Sector / industry", "ETF", f"Week to {previous:%d %b}", f"Week to {friday:%d %b}",
               "Weekly change", "% of starting assets"]
    return html.Div(html.Table([
        html.Caption(f"Weeks ending {previous:%d %B %Y} and {friday:%d %B %Y}. Flows in USD millions."),
        html.Thead(html.Tr([html.Th(column, scope="col") for column in columns])),
        html.Tbody(body),
    ]), className="sfa-sector-flows-table")
