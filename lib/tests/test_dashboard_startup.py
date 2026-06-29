"""Tests for dashboard startup, dev server helpers, and main entry defaults."""

from __future__ import annotations

import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest.mock import MagicMock, patch

import dash

from lib.dash.integrated_dashboard import (
    _collect_asset_files,
    _configure_dev_server,
    _get_env_port,
    _wait_for_server_ready,
    run_dashboard,
)


class _OkHandler(BaseHTTPRequestHandler):
    def do_GET(self):  # noqa: N802
        self.send_response(200)
        self.end_headers()

    def log_message(self, *_args, **_kwargs):
        return


def test_dash_dev_defaults_to_enabled(monkeypatch):
    monkeypatch.delenv("DASH_DEV", raising=False)
    import importlib
    import main as main_module

    importlib.reload(main_module)
    with patch("lib.dash.integrated_dashboard.run_dashboard") as mock_run:
        main_module.main()
    mock_run.assert_called_once_with(dev_mode=True)


def test_dash_dev_respects_explicit_zero(monkeypatch):
    monkeypatch.setenv("DASH_DEV", "0")
    import importlib
    import main as main_module

    importlib.reload(main_module)
    with patch("lib.dash.integrated_dashboard.run_dashboard") as mock_run:
        main_module.main()
    mock_run.assert_called_once_with(dev_mode=False)


def test_get_env_port_uses_start_port_default(monkeypatch):
    monkeypatch.delenv("DASH_PORT", raising=False)
    assert _get_env_port(8050) == 8050


def test_collect_asset_files_includes_dashboard_css():
    paths = _collect_asset_files()
    assert any(path.endswith("dashboard.css") for path in paths)


def test_configure_dev_server_sets_no_store_on_assets():
    app = dash.Dash(__name__)

    @app.server.route("/assets/dashboard.css")
    def _css():
        return "body{}"

    extra_files = _configure_dev_server(app, dev_mode=True)
    assert extra_files
    assert any(path.endswith("dashboard.css") for path in extra_files)

    client = app.server.test_client()
    resp = client.get("/assets/dashboard.css")
    assert resp.headers.get("Cache-Control") == "no-store"


def test_configure_dev_server_skips_hooks_in_production():
    app = dash.Dash(__name__)

    @app.server.route("/assets/dashboard.css")
    def _css():
        return "body{}"

    assert _configure_dev_server(app, dev_mode=False) is None
    client = app.server.test_client()
    resp = client.get("/assets/dashboard.css")
    assert resp.headers.get("Cache-Control") is None


def test_wait_for_server_ready_returns_true_when_port_responds():
    server = HTTPServer(("127.0.0.1", 0), _OkHandler)
    port = server.server_address[1]
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        assert _wait_for_server_ready("127.0.0.1", port, timeout=5.0) is True
    finally:
        server.shutdown()
        thread.join(timeout=2)


def test_wait_for_server_ready_times_out_on_closed_port():
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        port = sock.getsockname()[1]
    assert _wait_for_server_ready("127.0.0.1", port, timeout=0.5) is False


@patch("lib.dash.integrated_dashboard.try_bootstrap_default_session", return_value=None)
@patch("lib.dash.ticker_search.ensure_ticker_options_loaded")
@patch("lib.dash.integrated_dashboard.register_callbacks")
@patch("lib.dash.integrated_dashboard.wire_command_palette_is_open")
@patch("lib.dash.integrated_dashboard._configure_dev_server", return_value=None)
@patch("lib.dash.integrated_dashboard._kill_stale_port_listener")
@patch("lib.dash.integrated_dashboard._schedule_browser_open")
@patch("lib.dash.integrated_dashboard.dash.Dash")
def test_run_dashboard_defers_ticker_index(
    mock_dash_cls,
    _mock_browser,
    _mock_kill_port,
    _mock_configure,
    _mock_wire,
    _mock_register,
    mock_ensure_tickers,
    _mock_bootstrap,
):
    mock_app = MagicMock()
    mock_dash_cls.return_value = mock_app
    mock_app.run = MagicMock()

    run_dashboard(dev_mode=False)

    mock_ensure_tickers.assert_not_called()
    _mock_bootstrap.assert_called_once()
