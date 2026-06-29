"""
Professional Trading Dashboard entry point.

Phase 3 refactor: layout builders moved to `lib/dash.layout` package,
mirroring the `callbacks/` package. This file is now a thin entry point
that wires the layout together with callbacks and runs the Dash app.

Public API kept stable for backwards compatibility:
- `create_dashboard_layout(theme)` — composes the layout regions
- `run_dashboard(dev_mode)` — boots the server
- `find_available_port`, `_get_env_port` — port helpers
- `create_dash_app`, `plot_financial_chart_dash` — legacy API
"""

import json
import glob
import logging
import os
import socket
import subprocess
import threading
import time
import urllib.error
import urllib.request
import webbrowser

import dash
import dash_bootstrap_components as dbc
from flask import Response, request, send_file

from lib.dash.dash_config import (
    DEFAULT_THEME,
    START_PORT, MAX_PORT_TRIES,
    get_theme,
)
from lib.dash.styles import CUSTOM_CSS
from lib.dash.chart_builder import create_chart
from lib.dash.layout import create_dashboard_layout as _create_dashboard_layout
from lib.dash.layout.shell import wire_command_palette_is_open
from lib.dash.callbacks import register_callbacks
from lib.dash.bootstrap import try_bootstrap_default_session

# Re-export so callers like `from lib.dash.integrated_dashboard import
# create_dashboard_layout` keep working unchanged.
create_dashboard_layout = _create_dashboard_layout

logger = logging.getLogger(__name__)

_ASSETS_DIR = os.path.join(os.path.dirname(__file__), "assets")
_REPO_ROOT = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))

DEFAULT_FLOW_REPORT = os.path.join(os.getcwd(), "flow_report.html")

_FLOW_STUB_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Flow Scanner</title>
<style>body{background:#0d1117;color:#c9d1d9;font-family:system-ui;padding:24px;}</style>
</head><body><h1>No flow report yet</h1>
<p>Click <strong>RESCAN NOW</strong> on the Flow Scanner page, or run:</p>
<pre>python scripts/flow_scanner.py AAPL</pre>
</body></html>"""


def find_available_port(start_port: int = START_PORT, max_tries: int = MAX_PORT_TRIES) -> int:
    """Find an available port."""
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    raise RuntimeError("No available ports found")


def _get_env_port(default_port: int) -> int:
    """Read DASH_PORT from env with safe integer fallback."""
    raw_port = os.getenv("DASH_PORT", str(default_port)).strip()
    try:
        return int(raw_port)
    except (TypeError, ValueError):
        logger.warning("Invalid DASH_PORT=%r; falling back to %d", raw_port, default_port)
        return default_port


def _kill_stale_port_listener(port: int) -> None:
    """Best-effort: stop any process currently listening on `port`.

    Mirrors scripts/run_dashboard_latest.ps1 so that bare `python main.py`
    picks up the same UX without going through the PowerShell launcher.
    Silently no-ops when the port is free or the PID can't be identified.
    """
    # Quick check: if we can bind, nothing to do.
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as probe:
        if probe.connect_ex(("127.0.0.1", port)) != 0:
            return

    pid: int | None = None
    try:
        if os.name == "nt":
            # netstat is bundled with Windows; parse -ano for LISTENING rows.
            import subprocess
            out = subprocess.run(
                ["netstat", "-ano", "-p", "TCP"],
                capture_output=True, text=True, timeout=5,
            ).stdout
            for line in out.splitlines():
                parts = line.split()
                # Format: Proto  LocalAddress  ForeignAddress  State  PID
                if len(parts) >= 5 and parts[-1].isdigit():
                    local = parts[1]
                    if local.endswith(f":{port}") and parts[3].upper() == "LISTENING":
                        pid = int(parts[-1])
                        break
        else:
            # lsof exists on macOS and most Linux dev boxes.
            import subprocess
            out = subprocess.run(
                ["lsof", "-ti", f"tcp:{port}", "-sTCP:LISTEN"],
                capture_output=True, text=True, timeout=5,
            ).stdout.strip()
            if out:
                pid = int(out.splitlines()[0].strip())
    except (OSError, ValueError, subprocess.TimeoutExpired):
        pid = None

    if not pid or pid == os.getpid():
        return

    try:
        if os.name == "nt":
            import subprocess
            subprocess.run(
                ["taskkill", "/F", "/PID", str(pid)],
                capture_output=True, text=True, timeout=5,
            )
        else:
            import signal as _sig
            os.kill(pid, _sig.SIGTERM)
    except (OSError, subprocess.TimeoutExpired):
        pass


def _collect_asset_files() -> list[str]:
    """Return tracked static asset paths for Werkzeug dev reloader."""
    pattern = os.path.join(_ASSETS_DIR, "**", "*")
    return [path for path in glob.glob(pattern, recursive=True) if os.path.isfile(path)]


def _wait_for_server_ready(host: str, port: int, timeout: float = 15.0) -> bool:
    """Poll until the dashboard responds on HTTP or timeout."""
    deadline = time.monotonic() + timeout
    url = f"http://{host}:{port}/"
    while time.monotonic() < deadline:
        try:
            with urllib.request.urlopen(url, timeout=1) as resp:
                if resp.status < 500:
                    return True
        except (urllib.error.URLError, TimeoutError, OSError, ValueError):
            pass
        time.sleep(0.2)
    return False


def _schedule_browser_open(host: str, port: int) -> None:
    """Open the browser once the server accepts HTTP connections."""
    def _open_when_ready() -> None:
        if _wait_for_server_ready(host, port):
            webbrowser.open_new(f"http://{host}:{port}/")

    threading.Thread(target=_open_when_ready, daemon=True).start()


def _configure_dev_server(app: dash.Dash, dev_mode: bool) -> list[str] | None:
    """Register dev-only server hooks and return asset paths for the reloader."""
    if dev_mode:
        @app.server.after_request
        def _dev_no_cache_assets(response):  # noqa: F841
            if request.path.startswith("/assets/"):
                response.headers["Cache-Control"] = "no-store"
            return response
        return _collect_asset_files()
    return None


def run_dashboard(dev_mode: bool = False) -> None:
    """Run the professional trading dashboard."""
    theme = get_theme(DEFAULT_THEME)

    logger.info("Bootstrapping default market session (%s)...", "TSLA")
    bootstrap = try_bootstrap_default_session()

    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        suppress_callback_exceptions=True,
        meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}]
    )

    app.index_string = f'''
    <!DOCTYPE html>
    <html>
        <head>
            {{%metas%}}
            <title>SearchForAlpha - Trading Dashboard</title>
            {{%favicon%}}
            {{%css%}}
            <style>{CUSTOM_CSS}</style>
        </head>
        <body>
            {{%app_entry%}}
            <footer>
                {{%config%}}
                {{%scripts%}}
                {{%renderer%}}
            </footer>
        </body>
    </html>
    '''

    app.layout = create_dashboard_layout(theme, bootstrap=bootstrap)

    # Register all callbacks
    register_callbacks(app)

    # Phase 5 — bind the modal `is_open` prop to the open store.
    # Kept out of the layout module so the layout builder remains pure.
    wire_command_palette_is_open(app)

    @app.server.route("/flow_report.html")
    def serve_flow_report():
        if os.path.exists(DEFAULT_FLOW_REPORT):
            resp = send_file(DEFAULT_FLOW_REPORT, mimetype="text/html")
            resp.headers["Cache-Control"] = "no-store"
            return resp
        return Response(_FLOW_STUB_HTML, mimetype="text/html")

    def _serve_dash_shell():
        html = app.index()
        path = request.path or '/'
        query = request.query_string.decode('utf-8')
        search = f'?{query}' if query else ''
        boot = json.dumps({'pathname': path, 'search': search})
        script = f'<script>window.__SFA_BOOT_URL__={boot};</script>'
        if isinstance(html, str):
            html = html.replace('</head>', f'{script}</head>', 1)
        return html

    _shell_routes = (
        "/fundamentals",
        "/fundamentals/",
        "/fundamentals/<ticker>",
        "/flow",
        "/flow/",
        "/flow/<ticker>",
        "/ticker/<ticker>",
    )
    for idx, route in enumerate(_shell_routes):
        endpoint = f"sfa_shell_{idx}"
        app.server.add_url_rule(route, endpoint=endpoint, view_func=_serve_dash_shell)

    # In dev mode the reloader spawns two processes; keep a fixed port to
    # avoid the second process auto-selecting the next free port.
    host = "127.0.0.1" if dev_mode else os.getenv("DASH_HOST", "127.0.0.1").strip()
    port = _get_env_port(START_PORT)
    _kill_stale_port_listener(port)
    _schedule_browser_open(host, port)
    extra_files = _configure_dev_server(app, dev_mode)
    # Reloader is opt-in via DASH_RELOAD=1. Werkzeug's reloader on Windows
    # spawns a child process that can silently exit the parent; defaulting
    # it off keeps `python main.py` reliable. Debug error pages still honour
    # dev_mode.
    use_reloader = os.getenv("DASH_RELOAD", "0") == "1"
    logger.info("Starting dashboard on %s:%s", host, port)
    app.run(
        debug=dev_mode,
        use_reloader=use_reloader,
        host=host,
        port=port,
        extra_files=extra_files if use_reloader else None,
    )


# =============================================================================
# LEGACY SUPPORT
# =============================================================================

def create_dash_app(df, ticker: str, backtest_results: dict) -> dash.Dash:
    """Legacy function for backwards compatibility."""
    from dash import dcc, html

    theme = get_theme()
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

    config = {
        'selected_plots': ['candlestick', 'volume', 'rsi'],
        'show_candlesticks': True,
        'show_bollinger': True,
        'show_sma': True,
        'show_ema': False,
        'show_buy_sell_signals': True,
        'show_legend': True,
        'selected_signals': ['buy', 'sell'],
        'title': f'{ticker} Analysis',
    }

    fig = create_chart(df, config, theme)

    app.layout = html.Div([
        dcc.Graph(figure=fig, style={'height': '90vh'}),
    ], style={'backgroundColor': theme['bg_primary'], 'height': '100vh'})

    return app


def plot_financial_chart_dash(df, ticker: str, backtest_results: dict) -> None:
    """Legacy function for backwards compatibility."""
    app = create_dash_app(df, ticker, backtest_results)
    port = find_available_port()
    _schedule_browser_open("127.0.0.1", port)
    app.run(debug=False, use_reloader=False, port=port)


if __name__ == '__main__':
    run_dashboard(dev_mode=os.getenv("DASH_DEV", "1") == "1")