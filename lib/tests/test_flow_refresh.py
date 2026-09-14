"""Per-ticker flow report store and the scheduled refresh on top of it."""

from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timedelta
from pathlib import Path

import pytest

from _dash_post import callback_key, post_callback
from lib.dash import flow_refresh, flow_store
from lib.dash.flow_store import ScanOutcome
from scripts.flow_scanner import ET


@pytest.fixture(autouse=True)
def isolated_store(tmp_path, monkeypatch):
    monkeypatch.setattr(flow_store, "FLOW_DIR", tmp_path / "flow")
    monkeypatch.setattr(flow_refresh, "_last_attempt", {})
    return tmp_path / "flow"


def _runner(report: dict | None = None, *, rc: int = 0, generated_at: str = "2026-09-14T10:00:00", calls=None):
    def run(tickers, output_path, *, json_path=None, quiet=True, **_kwargs):
        if calls is not None:
            calls.append(list(tickers))
        if rc == 0:
            body = {"ticker": tickers[0], "error": None} if report is None else report
            Path(json_path).write_text(json.dumps({"generated_at": generated_at, "reports": [body]}), encoding="utf-8")
            Path(output_path).write_text("<html></html>", encoding="utf-8")
        return rc, "scanner said no"

    return run


RATE_LIMITED = {"ticker": "AAPL", "error": "Too Many Requests", "error_kind": "rate_limited"}


# --- store -----------------------------------------------------------------------------


def test_a_good_scan_is_promoted(isolated_store):
    outcome = flow_store.scan_into_store("aapl", runner=_runner())
    assert outcome.promoted and outcome.error_kind is None
    assert flow_store.load_report("AAPL")["generated_at"] == "2026-09-14T10:00:00"
    assert flow_store.html_path("AAPL").is_file()
    assert list((isolated_store / ".partial").iterdir()) == []


def test_a_failed_scan_is_kept_when_there_is_nothing_to_lose():
    outcome = flow_store.scan_into_store("AAPL", runner=_runner(RATE_LIMITED))
    assert outcome.promoted
    assert outcome.error_kind == "rate_limited"
    assert flow_store.load_report("AAPL")["reports"][0]["error_kind"] == "rate_limited"


def test_a_failed_scan_never_replaces_a_good_report():
    flow_store.scan_into_store("AAPL", runner=_runner(generated_at="2026-09-14T10:00:00"))
    outcome = flow_store.scan_into_store("AAPL", runner=_runner(RATE_LIMITED, generated_at="2026-09-14T10:15:00"))
    assert not outcome.promoted
    assert outcome.error_kind == "rate_limited"
    assert outcome.payload["generated_at"] == "2026-09-14T10:00:00"
    assert flow_store.load_report("AAPL")["reports"][0]["error"] is None


def test_a_crashed_scanner_keeps_the_stored_report():
    flow_store.scan_into_store("AAPL", runner=_runner())
    outcome = flow_store.scan_into_store("AAPL", runner=_runner(rc=1))
    assert outcome.error_kind == "scan_failed"
    assert "scanner said no" in outcome.message
    assert outcome.payload is not None


def test_symbols_round_trip_through_file_names(isolated_store):
    flow_store.scan_into_store("^SPX", runner=_runner())
    flow_store.scan_into_store("BRK-B", runner=_runner())
    assert sorted(flow_store.stored_tickers()) == ["BRK-B", "^SPX"]
    assert flow_store.json_path("../../etc/passwd").parent == isolated_store


def test_a_busy_ticker_is_skipped_without_blocking():
    lock = flow_store._lock_for("AAPL")
    with lock:
        assert flow_store.scan_into_store("AAPL", blocking=False, runner=_runner()) is None


# --- when a report is due -----------------------------------------------------------------

MON_1000 = datetime(2026, 9, 14, 10, 0, tzinfo=ET)
INTERVAL = timedelta(minutes=15)


def test_latest_close():
    assert flow_refresh.latest_close(MON_1000) == datetime(2026, 9, 11, 16, 0, tzinfo=ET)
    assert flow_refresh.latest_close(MON_1000.replace(hour=16, minute=30)) == datetime(2026, 9, 14, 16, 0, tzinfo=ET)
    assert flow_refresh.latest_close(datetime(2026, 9, 13, 12, 0, tzinfo=ET)) == datetime(2026, 9, 11, 16, 0, tzinfo=ET)


def test_never_scanned_is_due():
    assert flow_refresh.is_due(None, MON_1000, INTERVAL)


def test_in_session_due_after_the_interval():
    assert flow_refresh.is_due(MON_1000 - timedelta(minutes=20), MON_1000, INTERVAL)
    assert not flow_refresh.is_due(MON_1000 - timedelta(minutes=5), MON_1000, INTERVAL)


def test_one_snapshot_after_the_close_then_quiet():
    after_close = MON_1000.replace(hour=16, minute=10)
    assert flow_refresh.is_due(MON_1000.replace(hour=15, minute=55), after_close, INTERVAL)
    assert not flow_refresh.is_due(MON_1000.replace(hour=16, minute=5), MON_1000.replace(hour=22), INTERVAL)


def test_quiet_over_the_weekend():
    friday_after_close = datetime(2026, 9, 11, 16, 5, tzinfo=ET)
    assert not flow_refresh.is_due(friday_after_close, datetime(2026, 9, 13, 12, 0, tzinfo=ET), INTERVAL)


def test_a_timestamp_in_another_zone_compares_correctly():
    # stored_at() returns the machine's local zone; 14:00 UTC is 10:00 ET.
    from datetime import timezone

    assert not flow_refresh.is_due(datetime(2026, 9, 14, 13, 55, tzinfo=timezone.utc), MON_1000, INTERVAL)


# --- which tickers, and a round ------------------------------------------------------------


def test_refresh_list_is_watchlist_first_then_stored(tmp_path):
    watchlist = tmp_path / "watchlist.txt"
    watchlist.write_text("# comment\nspy\nAAPL\n", encoding="utf-8")
    flow_store.scan_into_store("NVDA", runner=_runner())
    flow_store.scan_into_store("AAPL", runner=_runner())
    # Stored tickers come oldest first; pin the mtimes so the order is not a race.
    os.utime(flow_store.json_path("NVDA"), (1_000_000, 1_000_000))
    os.utime(flow_store.json_path("AAPL"), (2_000_000, 2_000_000))
    assert flow_refresh.refresh_tickers(watchlist) == ["SPY", "AAPL", "NVDA"]
    assert flow_refresh.refresh_tickers(watchlist, limit=2) == ["SPY", "AAPL"]
    assert flow_refresh.refresh_tickers(tmp_path / "missing.txt") == ["NVDA", "AAPL"]


def _fake_scan(outcomes: dict[str, ScanOutcome | None], calls: list[str]):
    def scan(ticker, *, blocking=True):
        calls.append(ticker)
        return outcomes.get(ticker, ScanOutcome(ticker, True, None, "", {}))

    return scan


def test_a_round_stops_at_the_first_rate_limit():
    calls: list[str] = []
    outcomes = {"AAPL": ScanOutcome("AAPL", False, "rate_limited", "Too Many Requests", {})}
    round_ = flow_refresh.refresh_once(MON_1000, tickers=["SPY", "AAPL", "NVDA"], scan=_fake_scan(outcomes, calls))
    assert calls == ["SPY", "AAPL"]
    assert round_.refreshed == ["SPY"]
    assert round_.kept_previous == ["AAPL"]
    assert round_.stopped_on_rate_limit


def test_a_failed_attempt_waits_for_the_interval():
    calls: list[str] = []
    outcomes = {"AAPL": ScanOutcome("AAPL", False, "error", "boom", {})}
    scan = _fake_scan(outcomes, calls)
    flow_refresh.refresh_once(MON_1000, tickers=["AAPL"], scan=scan)
    flow_refresh.refresh_once(MON_1000 + timedelta(minutes=1), tickers=["AAPL"], scan=scan)
    flow_refresh.refresh_once(MON_1000 + timedelta(minutes=16), tickers=["AAPL"], scan=scan)
    assert calls == ["AAPL", "AAPL"]


def test_a_busy_ticker_is_reported_and_a_stop_ends_the_round():
    calls: list[str] = []
    round_ = flow_refresh.refresh_once(MON_1000, tickers=["AAPL"], scan=_fake_scan({"AAPL": None}, calls))
    assert round_.busy == ["AAPL"]

    stop = threading.Event()
    stop.set()
    assert flow_refresh.refresh_once(MON_1000, tickers=["SPY"], scan=_fake_scan({}, calls), stop=stop).refreshed == []


def test_refresh_is_off_at_zero_minutes():
    assert flow_refresh.start_flow_refresh(0) is None


# --- the flow page reading the store ---------------------------------------------------------


@pytest.fixture
def flow_app():
    import dash
    from dash import html

    from lib.dash.callbacks.flow import register_flow_callbacks

    app = dash.Dash(__name__, suppress_callback_exceptions=True)
    app.layout = html.Div()
    register_flow_callbacks(app)
    return app


def _open_flow(app, pathname, ticker="TSLA"):
    key = callback_key(app, "flow-content.children", "flow-rescan-button.n_clicks")
    return post_callback(app, key, "app-url.pathname", {
        "app-url.pathname": pathname,
        "flow-rescan-button.n_clicks": 0,
        "ticker-dropdown.value": ticker,
    })


def test_the_page_shows_the_report_of_the_ticker_in_the_url(flow_app):
    flow_store.scan_into_store("AAPL", runner=_runner())
    flow_store.scan_into_store("NVDA", runner=_runner({"ticker": "NVDA", "error": "unrelated"}))

    status, body = _open_flow(flow_app, "/flow/AAPL")
    assert status == 200
    response = body["response"]
    assert response["flow-status"]["children"].startswith("Report from")
    assert response["flow-data-store"]["data"]["reports"][0]["ticker"] == "AAPL"
    assert "unrelated" not in json.dumps(response["flow-content"])


def test_a_ticker_without_a_report_says_so_by_name(flow_app):
    status, body = _open_flow(flow_app, "/flow/MSFT")
    assert status == 200
    assert body["response"]["flow-status"]["children"] == "No report for MSFT yet. Click RESCAN NOW."
    assert body["response"]["flow-data-store"]["data"] is None


def test_rescan_throttled_keeps_the_last_good_report_on_screen(flow_app, monkeypatch):
    flow_store.scan_into_store("AAPL", runner=_runner(generated_at="2026-09-14T10:00:00"))
    monkeypatch.setattr(flow_store, "run_flow_scan", _runner(RATE_LIMITED, generated_at="2026-09-14T10:15:00"))

    key = callback_key(flow_app, "flow-content.children", "flow-rescan-button.n_clicks")
    status, body = post_callback(flow_app, key, "flow-rescan-button.n_clicks", {
        "app-url.pathname": "/flow/AAPL",
        "flow-rescan-button.n_clicks": 1,
    })
    assert status == 200
    response = body["response"]
    assert response["flow-status"]["children"].startswith("RATE LIMITED — kept the report from")
    assert response["flow-data-store"]["data"]["generated_at"] == "2026-09-14T10:00:00"


def test_the_poll_signals_only_a_newer_report(flow_app):
    flow_store.scan_into_store("AAPL", runner=_runner(generated_at="2026-09-14T10:15:00"))
    key = callback_key(flow_app, "flow-refresh-signal.data")
    values = {"app-url.pathname": "/flow/AAPL", "flow-refresh-interval.n_intervals": 3}

    status, body = post_callback(flow_app, key, "flow-refresh-interval.n_intervals", {
        **values, "flow-data-store.data": {"generated_at": "2026-09-14T10:00:00"},
    })
    assert status == 200
    assert body["response"]["flow-refresh-signal"]["data"] == {"ticker": "AAPL", "generated_at": "2026-09-14T10:15:00"}

    status, _ = post_callback(flow_app, key, "flow-refresh-interval.n_intervals", {
        **values, "flow-data-store.data": {"generated_at": "2026-09-14T10:15:00"},
    })
    assert status == 204


def test_route_points_the_new_tab_link_at_the_ticker(flow_app):
    key = callback_key(flow_app, "flow-open-tab-link.href")
    status, body = post_callback(flow_app, key, "app-url.pathname", {"app-url.pathname": "/flow/^SPX"})
    assert status == 200
    assert body["response"]["flow-open-tab-link"]["href"] == "/flow_report.html?ticker=%5ESPX"
    status, body = post_callback(flow_app, key, "app-url.pathname", {"app-url.pathname": "/ticker/AAPL"})
    assert body["response"]["flow-refresh-interval"]["disabled"] is True
