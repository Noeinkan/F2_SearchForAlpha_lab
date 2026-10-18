"""WSGI entry point for the hosted workspace (alpha.noeinsolutions.com).

    SITE_LOGIN_EMAIL=... SITE_LOGIN_PASSWORD_HASH=... python -m hosted.server

The order matters: the login is read first, so a missing secret stops the
process before the dashboard is even imported (and the deploy's health check
fails instead of serving the workspace open); then the data volume is
prepared, since the dashboard reads config/ and state/ while it bootstraps.
"""

from __future__ import annotations

import logging
import os

from flask import Response, jsonify

logger = logging.getLogger("hosted.server")

ROBOTS = "User-agent: *\nDisallow: /\n"


def create_hosted_app(login=None):
    from hosted import persist
    from hosted.login import OwnerLogin

    login = login or OwnerLogin.from_env()
    persist.prepare(os.environ.get("SFA_DATA_DIR"), os.environ.get("SFA_DIST_CONFIG", "config.dist"))

    import lib.dash.integrated_dashboard as dashboard

    app = dashboard.create_app()
    login.install(app.server)

    @app.server.route("/healthz")
    def healthz():
        return jsonify(status="ok", ticker=dashboard.dashboard_state.ticker)

    @app.server.route("/robots.txt")
    def robots():
        return Response(ROBOTS, mimetype="text/plain")

    return app


def main() -> None:
    logging.basicConfig(level=os.environ.get("SFA_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.environ.get("SITE_HOST", "127.0.0.1")
    port = int(os.environ.get("SITE_PORT", "8050"))
    threads = int(os.environ.get("SITE_THREADS", "8"))

    app = create_hosted_app()

    from lib.dash.flow_refresh import start_flow_refresh

    start_flow_refresh()

    from waitress import serve

    logger.info("SearchForAlpha workspace on %s:%s, behind the owner login", host, port)
    serve(app.server, host=host, port=port, threads=threads, channel_timeout=300, connection_limit=100, ident="sfa")


if __name__ == "__main__":
    main()
