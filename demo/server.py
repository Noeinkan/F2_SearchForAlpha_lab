"""WSGI entry point for the public demo.

    DEMO_MODE=true python -m demo.server        # http://127.0.0.1:8050/ticker/TSLA

With ``DEMO_MODE`` unset or false this serves a 404 for every page (and a
health check that says the demo is off) and never imports the dashboard: the
switch takes the demo down without falling back to the live, unguarded
workspace on a public address.

With it on, the order matters and ``create_demo_app`` is the one place it is
written down: seal the process first, import the dashboard, swap its seams for
the snapshot, give every visitor their own state, build the app with the
template session pinned, then wrap its callbacks and add the demo chrome.
The access gate (``demo.access``) goes in front of everything else: its
before-request check is registered first, so no page or callback runs for a
browser without a verified email and a live trial.
"""

from __future__ import annotations

import logging
import os
import threading
import time

from flask import Flask, Response, g, jsonify, request

import demo
from demo.settings import DemoSettings

logger = logging.getLogger("demo.server")

ROBOTS = "User-agent: *\nDisallow: /_dash-\nDisallow: /_reload-hash\nDisallow: /access\nDisallow: /admin\n"
PURGE_EVERY_SECONDS = 3600


def create_off_app() -> Flask:
    server = Flask("sfa-demo-off")

    @server.route("/healthz")
    def healthz():
        return jsonify(status="ok", demo=False)

    @server.route("/", defaults={"path": ""})
    @server.route("/<path:path>")
    def switched_off(path: str):  # noqa: ARG001
        return Response(
            "The SearchForAlpha Lab public demo is switched off.\n",
            status=404,
            mimetype="text/plain",
        )

    return server


def _install_request_hooks(server: Flask, store) -> None:
    from demo import sessions
    from demo.guards import client_ip

    exempt = ("/_dash-", "/assets/", "/_favicon", "/healthz", "/robots.txt", "/access", "/admin")

    @server.before_request
    def bind_session():
        sid = request.cookies.get(sessions.COOKIE_NAME)
        g.demo_new_sid = None
        if not sessions.valid_session_id(sid):
            if request.method == "GET" and not request.path.startswith(exempt):
                sid = g.demo_new_sid = sessions.new_session_id()
            else:
                sid = sessions.fallback_session_id(client_ip(), request.headers.get("User-Agent", ""))
        g.demo_sid_token = sessions.current_sid.set(sid)

    @server.after_request
    def issue_cookie(response):
        new_sid = g.get("demo_new_sid")
        if new_sid:
            response.set_cookie(
                sessions.COOKIE_NAME,
                new_sid,
                httponly=True,
                samesite="Lax",
                secure=request.headers.get("X-Forwarded-Proto") == "https",
                path="/",
            )
        return response

    @server.teardown_request
    def unbind_session(_exc):
        token = g.pop("demo_sid_token", None)
        if token is not None:
            try:
                sessions.current_sid.reset(token)
            except ValueError:
                sessions.current_sid.set(None)


def create_demo_app(settings: DemoSettings | None = None, access_settings=None, mailer=None):
    """Build the guarded demo app.

    Raises if the snapshot cannot bootstrap, or if the access gate is on but
    cannot send a sign-in email (a gate nobody can pass is an outage).
    """
    settings = settings or DemoSettings.from_env()

    from demo.access import AccessSettings, build_access

    access_settings = access_settings or AccessSettings.from_env()
    problems = access_settings.problems()
    if problems:
        raise RuntimeError("the demo access gate is misconfigured: " + "; ".join(problems))

    from demo import sealing

    sealing.install_broker_seal()
    sealing.install_network_seal()
    if access_settings.enabled and access_settings.mail_backend == "smtp":
        sealing.allow_outbound(access_settings.smtp_host, access_settings.smtp_port)

    import lib.dash.integrated_dashboard as dashboard

    from demo import banner, patches, snapshot
    from demo.guards import DemoGuards, client_ip, wall_response
    from demo.sessions import SessionStore

    patches.install(settings)
    store = SessionStore(max_sessions=settings.max_sessions, idle_seconds=settings.session_idle_minutes * 60)
    patches.install_session_state(store)

    with store.pinned(store.template):
        app = dashboard.create_app()
    if store.template.df is None:
        raise RuntimeError("the default session did not bootstrap from the snapshot; refusing to serve an empty demo")

    app.title = "SearchForAlpha Lab — public demo"
    app.layout = banner.decorate_layout(app.layout, settings)
    app.index_string = banner.inject_index(app.index_string, settings)
    banner.register_wall_close(app)
    patches.register_lazy_data_display(app)

    access = admin = None
    if access_settings.enabled:
        access, admin = build_access(access_settings, wall=wall_response, client_ip=client_ip, mailer=mailer)
        # Before _install_request_hooks: Flask runs before-request hooks in
        # registration order, and a refused browser must not be handed a
        # dashboard session first.
        access.install(app.server)
        # Installed either way: with no token its routes answer 404, instead of
        # /admin falling through to the Dash catch-all.
        admin.install(app.server)
        if not access_settings.admin_enabled:
            logger.warning("DEMO_ADMIN_TOKEN is unset or shorter than 24 characters: /admin answers 404")
    else:
        logger.warning("DEMO_ACCESS_GATE is off: the demo is open to anyone and usage is not recorded")

    guards = DemoGuards(app, store, settings, access=access)
    guards.install()
    _install_request_hooks(app.server, store)

    @app.server.route("/healthz")
    def healthz():
        return jsonify(
            status="ok",
            demo=True,
            access_gate=access is not None,
            snapshot=snapshot.snapshot_date(),
            tickers=len(snapshot.tickers()),
            sessions=len(store),
            jobs=guards.gate.running(),
        )

    @app.server.route("/robots.txt")
    def robots():
        return Response(ROBOTS, mimetype="text/plain")

    def housekeeping() -> None:
        last_purge = 0.0
        while True:
            time.sleep(5)
            try:
                guards.gate.sweep()
                store.purge()
                guards.prune()
                if access is not None and time.monotonic() - last_purge > PURGE_EVERY_SECONDS:
                    last_purge = time.monotonic()
                    removed = access.purge()
                    if removed:
                        logger.info("demo access: deleted %d visitors past the retention period", removed)
            except Exception:  # noqa: BLE001 - the sweeper must outlive a bad tick
                logger.exception("demo housekeeping failed")

    threading.Thread(target=housekeeping, name="demo-housekeeping", daemon=True).start()
    app.demo_store = store
    app.demo_guards = guards
    app.demo_settings = settings
    app.demo_access = access
    logger.info(
        "SearchForAlpha demo ready: snapshot %s, limits %s, access %s",
        snapshot.snapshot_date(),
        settings.as_manifest_limits(),
        access_settings.as_manifest_limits() if access is not None else "open",
    )
    return app


def main() -> None:
    logging.basicConfig(level=os.environ.get("SFA_LOG_LEVEL", "INFO"), format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    host = os.environ.get("DEMO_HOST", "127.0.0.1")
    port = int(os.environ.get("DEMO_PORT", "8050"))
    threads = int(os.environ.get("DEMO_THREADS", "8"))

    if demo.enabled():
        server = create_demo_app().server
    else:
        logger.warning("DEMO_MODE is off: serving 404 for every page")
        server = create_off_app()

    from waitress import serve

    serve(server, host=host, port=port, threads=threads, channel_timeout=180, connection_limit=300, ident="sfa-demo")


if __name__ == "__main__":
    main()
