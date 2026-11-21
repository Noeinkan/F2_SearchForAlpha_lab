"""Load Sector Flows only when its workspace is open."""

from datetime import datetime
from zoneinfo import ZoneInfo

from dash import Input, Output, html, no_update

from lib.dash.layout.sector_flows import render_sector_flows
from lib.dash.routes import is_sector_flows_route
from lib.sector_flows import compare_weeks, load_sector_histories


def register_sector_flows_callbacks(app):
    @app.callback(Output("sector-flows-page", "hidden"), Input("app-url", "pathname"))
    def show_sector_flows(pathname):
        return not is_sector_flows_route(pathname)

    @app.callback(Output("sector-flows-result", "children"), Input("app-url", "pathname"))
    def update_sector_flows(pathname):
        if not is_sector_flows_route(pathname):
            return no_update
        if app.server.config.get("SFA_AUTH_MODE") == "demo":
            return html.P("Live ETF flows are available in the full workspace.")
        today = datetime.now(ZoneInfo("America/New_York")).date()
        return render_sector_flows(*compare_weeks(load_sector_histories(), today))
