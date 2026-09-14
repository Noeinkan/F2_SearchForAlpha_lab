"""
Public demo — the kill switch, the seals, the caps and the frozen snapshot.

The thing these guard: the demo is the one deployment of this repo a stranger
can reach, so every promise it makes has to hold at the server, not in the
page. "No broker" means the order path cannot be imported; "frozen data" means
the process cannot open a socket to a vendor; "capped" means an oversized
request is clamped or refused before it spends CPU; and "switched off" means
the dashboard is never imported at all.

The pure pieces (limiter, job gate, session store, snapshot reader) are tested
in-process. Anything that installs the demo's seams runs in a subprocess,
because the seams patch sockets and module globals for the whole interpreter
and would leak into every other test in the suite.
"""

from __future__ import annotations

import json
import os
import socket
import subprocess
import sys
import textwrap
from pathlib import Path

import pandas as pd
import pytest

import demo
from demo import sealing, snapshot
from demo.limits import JobGate, SlidingWindowLimiter
from demo.sessions import SessionScopedState, SessionStore, current_sid, fallback_session_id, valid_session_id
from lib.fetch_errors import DataFetchError

REPO_ROOT = Path(__file__).resolve().parents[2]


class FakeClock:
    def __init__(self) -> None:
        self.now = 1000.0

    def __call__(self) -> float:
        return self.now


# --- Kill switch --------------------------------------------------------------

@pytest.mark.parametrize("value, expected", [
    (None, False), ("", False), ("false", False), ("0", False), ("no", False),
    ("true", True), ("1", True), ("YES", True), (" on ", True),
])
def test_demo_mode_is_off_unless_explicitly_on(monkeypatch, value, expected):
    if value is None:
        monkeypatch.delenv("DEMO_MODE", raising=False)
    else:
        monkeypatch.setenv("DEMO_MODE", value)
    assert demo.enabled() is expected


def test_switched_off_app_404s_every_page_but_stays_healthy():
    from demo.server import create_off_app

    client = create_off_app().test_client()
    for path in ("/", "/ticker/TSLA", "/optimize/TSLA", "/_dash-layout"):
        assert client.get(path).status_code == 404
    health = client.get("/healthz")
    assert health.status_code == 200
    assert health.get_json() == {"status": "ok", "demo": False}


def test_switched_off_server_never_imports_the_dashboard():
    script = textwrap.dedent("""
        import sys
        from demo.server import create_off_app
        create_off_app().test_client().get('/ticker/TSLA')
        print(any(m.startswith('lib.dash') for m in sys.modules))
    """)
    env = {k: v for k, v in os.environ.items() if k != "DEMO_MODE"}
    out = subprocess.run([sys.executable, "-c", script], cwd=REPO_ROOT, env=env,
                         capture_output=True, text=True, timeout=120)
    assert out.returncode == 0, out.stderr
    assert out.stdout.strip() == "False"


# --- Seals --------------------------------------------------------------------

def test_broker_seal_refuses_the_order_path():
    sealing.install_broker_seal()
    try:
        for module in ("lib.live.broker", "lib.live.runner", "ib_async"):
            with pytest.raises(sealing.BrokerRefused):
                __import__(module)
    finally:
        sealing.remove_broker_seal()
        for name in [m for m in sys.modules if m.startswith("lib.live")]:
            del sys.modules[name]


def test_network_seal_refuses_outbound_but_not_loopback():
    real_yf = sys.modules.get("yfinance")
    listener = socket.socket()
    listener.bind(("127.0.0.1", 0))
    listener.listen(1)
    port = listener.getsockname()[1]
    sealing.install_network_seal()
    try:
        with pytest.raises(sealing.NetworkRefused):
            socket.create_connection(("query1.finance.yahoo.com", 443), timeout=2)
        with pytest.raises(sealing.NetworkRefused):
            socket.getaddrinfo("data.sec.gov", 443)
        with pytest.raises(OSError):  # NetworkRefused is a ConnectionRefusedError
            socket.socket().connect(("93.184.216.34", 80))
        import yfinance
        with pytest.raises(sealing.NetworkRefused):
            yfinance.Ticker("TSLA")
        local = socket.create_connection(("127.0.0.1", port), timeout=2)
        local.close()
    finally:
        sealing.remove_network_seal(real_yf)
        listener.close()


# --- Snapshot -----------------------------------------------------------------

def test_snapshot_manifest_matches_the_bars_on_disk():
    manifest = snapshot.manifest()
    assert manifest["tickers"][0] == "TSLA"
    for symbol in manifest["tickers"]:
        bars = snapshot.load_bars(symbol, "1900-01-01", "2100-01-01", "1d")
        assert bars.index.max().date().isoformat() == manifest["snapshot"], symbol
        assert len(bars) == manifest["bars"][symbol]["daily"]


def test_snapshot_window_is_start_inclusive_end_exclusive():
    bars = snapshot.load_bars("TSLA", "2026-09-01", "2026-09-11", "1d")
    assert bars.index.min() >= pd.Timestamp("2026-09-01")
    assert bars.index.max() < pd.Timestamp("2026-09-11")


def test_a_ticker_outside_the_snapshot_fails_like_a_bad_ticker():
    with pytest.raises(DataFetchError):
        snapshot.load_bars("ZZZZ", "2020-01-01", "2026-01-01", "1d")
    # Short enough for the terminal header, which prints str(exc)[:40].
    with pytest.raises(DataFetchError) as info:
        snapshot.load_bars("GME", "2020-01-01", "2026-01-01", "1d")
    assert len(str(info.value)) <= 40


def test_fundamentals_are_frozen_at_the_snapshot_close():
    payload = snapshot.load_fundamentals("TSLA")
    assert payload["as_of"].startswith(snapshot.snapshot_date())
    last, _prev = snapshot.last_closes("TSLA")
    assert payload["last_price"] == pytest.approx(last, rel=1e-6)
    with pytest.raises(ValueError):
        snapshot.load_fundamentals("SPY")


def test_fixture_carries_no_credentials_or_addresses():
    for path in snapshot.FIXTURE_DIR.rglob("*.json"):
        text = path.read_text(encoding="utf-8")
        assert "@" not in text, path
        assert "api_key" not in text.lower(), path


# --- Limits -------------------------------------------------------------------

def test_sliding_window_blocks_the_n_plus_first_and_releases_after_the_window():
    clock = FakeClock()
    limiter = SlidingWindowLimiter(3, 60, clock=clock)
    assert [limiter.hit("1.2.3.4") for _ in range(3)] == [0, 0, 0]
    wait = limiter.hit("1.2.3.4")
    assert 0 < wait <= 60
    assert limiter.hit("5.6.7.8") == 0  # per key
    clock.now += 61
    assert limiter.hit("1.2.3.4") == 0


def test_job_gate_admits_up_to_the_cap_and_stops_runs_past_the_timeout():
    clock = FakeClock()
    gate = JobGate(2, 120, clock=clock)
    running = {"a": True, "b": True}
    cancelled = []
    for owner in ("a", "b"):
        assert gate.admit("combos", owner)
        gate.register("combos", owner, probe=lambda o=owner: running[o],
                      cancel=lambda reason, o=owner: cancelled.append((o, reason)))
    assert not gate.admit("combos", "c")
    running["a"] = False  # finished on its own
    assert gate.admit("combos", "c")
    clock.now += 121
    gate.sweep()
    assert cancelled == [("b", "timeout")]
    assert gate.running() == 0


def test_job_gate_drops_a_polled_run_whose_tab_went_away():
    clock = FakeClock()
    gate = JobGate(2, 600, stale_seconds=30, clock=clock)
    cancelled = []
    gate.register("combos", "a", probe=lambda: True, cancel=cancelled.append, polled=True)
    clock.now += 20
    gate.touch("combos", "a")
    clock.now += 20
    gate.sweep()
    assert cancelled == []
    clock.now += 31
    gate.sweep()
    assert cancelled == ["abandoned"]


def test_clamp_rewrites_oversized_and_missing_values_before_the_callback_sees_them():
    from demo.guards import DemoGuards
    from demo.settings import DemoSettings

    class _App:
        callback_map: dict = {}

    settings = DemoSettings(max_combos=150, max_signals_per_side=2)
    guards = DemoGuards(_App(), SessionStore(max_sessions=1, idle_seconds=60), settings)
    seen = {}

    def original(clicks, combos, signals, capital):
        seen.update(combos=combos, signals=signals, capital=capital)

    names = ["run-optimization-btn.n_clicks", "max-combos-input.value", "max-signals-slider.value", "initial-capital.value"]
    clamped = guards._clamping(original, names)
    clamped(1, 5000, 5, 10_000)
    assert seen == {"combos": 150, "signals": 2, "capital": 10_000}
    clamped(1, None, "abc", 10_000)
    assert seen["combos"] == 150 and seen["signals"] == 2
    clamped(1, 40, 1, 10_000)
    assert seen["combos"] == 40 and seen["signals"] == 1


def test_a_dropped_final_progress_reply_is_replayed_on_the_next_poll():
    """The renderer drops the reply to a poll still in flight when the next
    interval tick fires. If that reply was the one saying "completed", the page
    froze at "Testing 95/100" (seen on the live demo, 14 Sep 2026)."""
    from demo.guards import DemoGuards
    from demo.settings import DemoSettings

    class _App:
        callback_map: dict = {}

    store = SessionStore(max_sessions=5, idle_seconds=60)
    guards = DemoGuards(_App(), store, DemoSettings())
    sid = "visitor-" + "r" * 20
    state = store.get(sid)
    calls = []

    def original_tick(*_args, **_kwargs):
        calls.append(1)
        if state.optimization_state.get("running"):
            state.update_optimization_state(running=False, completed=True)
            return '{"response": "completed leaderboard"}'
        from dash.exceptions import PreventUpdate
        raise PreventUpdate  # what the real callback does once the run is over

    tick = guards._combos_tick(original_tick)
    token = current_sid.set(sid)
    try:
        state.update_optimization_state(running=True)
        assert tick() == '{"response": "completed leaderboard"}'  # this reply is lost in transit
        assert tick() == '{"response": "completed leaderboard"}'  # replayed, not a silent no-op
        assert len(calls) == 1
    finally:
        current_sid.reset(token)


def test_settings_read_every_limit_from_the_environment(monkeypatch):
    from demo.settings import DemoSettings

    monkeypatch.setenv("DEMO_MAX_COMBOS", "75")
    monkeypatch.setenv("DEMO_JOBS_PER_IP_PER_HOUR", "not-a-number")
    settings = DemoSettings.from_env()
    assert settings.max_combos == 75
    assert settings.jobs_per_ip_per_hour == DemoSettings().jobs_per_ip_per_hour


# --- Sessions -----------------------------------------------------------------

def test_each_visitor_gets_their_own_dashboard_state():
    store = SessionStore(max_sessions=10, idle_seconds=60)
    store.template.ticker = "TSLA"
    proxy = SessionScopedState(store)
    token = current_sid.set("visitor-a-" + "x" * 16)
    try:
        assert proxy.ticker == "TSLA"  # starts from the template
        proxy.ticker = "AAPL"
        proxy.update_optimization_state(running=True)
    finally:
        current_sid.reset(token)
    token = current_sid.set("visitor-b-" + "x" * 16)
    try:
        assert proxy.ticker == "TSLA"
        assert not proxy.optimization_state.get("running")
    finally:
        current_sid.reset(token)
    assert store.template.ticker == "TSLA"


def test_session_store_evicts_the_oldest_and_purges_the_idle():
    clock = FakeClock()
    store = SessionStore(max_sessions=2, idle_seconds=60, clock=clock)
    first = store.get("s1")
    store.get("s2")
    store.get("s3")
    assert len(store) == 2 and store.peek("s1") is None
    clock.now += 61
    store.purge()
    assert len(store) == 0
    assert store.get("s1") is not first


def test_session_ids_are_validated_and_cookieless_clients_stay_stable():
    assert not valid_session_id("../../etc")
    assert not valid_session_id("short")
    assert fallback_session_id("1.2.3.4", "UA") == fallback_session_id("1.2.3.4", "UA")
    assert fallback_session_id("1.2.3.4", "UA") != fallback_session_id("1.2.3.5", "UA")


# --- The running demo, end to end ---------------------------------------------

_PROBE = textwrap.dedent(r"""
    import json, logging, sys, warnings
    warnings.simplefilter('ignore')
    logging.disable(logging.CRITICAL)
    from demo.server import create_demo_app
    from demo import sessions
    app = create_demo_app()
    results = {}

    # Default UI values, read off the layout the way the browser starts.
    defaults = {}
    def walk(node):
        node_id = getattr(node, 'id', None)
        if isinstance(node_id, str):
            for prop in node._prop_names:
                defaults[f'{node_id}.{prop}'] = getattr(node, prop, None)
        children = getattr(node, 'children', None)
        if isinstance(children, (list, tuple)):
            for child in children:
                walk(child)
        elif hasattr(children, 'to_plotly_json'):
            walk(children)
    walk(app.layout)

    def key_for(output, required_input):
        for key, entry in app.callback_map.items():
            names = [f"{d['id']}.{d['property']}" for d in entry['inputs'] if isinstance(d['id'], str)]
            if output in key and required_input in names:
                return key
        raise KeyError(output)

    def outputs_of(key):
        if not key.startswith('..'):
            dep_id, prop = key.rsplit('.', 1)
            return {'id': dep_id, 'property': prop}
        parts = key[2:-2].split('...')
        return [dict(zip(('id', 'property'), p.rsplit('.', 1))) for p in parts]

    def call(client, output, required_input, overrides, ip='203.0.113.7'):
        key = key_for(output, required_input)
        entry = app.callback_map[key]
        values = {**defaults, **overrides}
        deps = lambda ds: [{'id': d['id'], 'property': d['property'], 'value': values.get(f"{d['id']}.{d['property']}")}
                           for d in ds if isinstance(d['id'], str)]
        body = {'output': key, 'outputs': outputs_of(key), 'inputs': deps(entry['inputs']),
                'state': deps(entry['state']), 'changedPropIds': [required_input]}
        r = client.post('/_dash-update-component', json=body, headers={'X-Real-IP': ip})
        return r.status_code, r.get_data(as_text=True)

    import re
    def visitor(address):
        # The access gate is on (console mailer): bounce, ask for a code, type it.
        c = app.server.test_client()
        bounced = c.get('/ticker/TSLA')
        results.setdefault('signed_out_redirect', bounced.status_code == 302 and bounced.headers['Location'].startswith('/access'))
        results.setdefault('signed_out_no_session', sessions.COOKIE_NAME not in (bounced.headers.get('Set-Cookie') or ''))
        c.post('/access', data={'email': address, 'next': '/ticker/TSLA'})
        code = ''.join(re.search(r'code is (\d{3}) (\d{3})', app.demo_access.mailer.outbox[-1].text).groups())
        c.post('/access/code', data={'email': address, 'code': code})
        return c, c.get('/ticker/TSLA')

    a, page = visitor('visitor-a@example.com')
    html = page.get_data(as_text=True)
    results['page_status'] = page.status_code
    results['banner'] = 'PUBLIC DEMO' in html and '11 Sep 2026' in html
    results['signed_in_line'] = 'Signed in as <b>visitor-a@example.com</b>' in html
    results['cookie'] = sessions.COOKIE_NAME in (page.headers.get('Set-Cookie') or '')
    results['layout_bytes'] = len(a.get('/_dash-layout').get_data())
    status, body = call(a, 'data-display-store.data', 'open-data-button.n_clicks', {'open-data-button.n_clicks': 1})
    results['data_table_filled_on_open'] = status == 200 and 'range_start' in body

    backtest = {'run-backtest-btn.n_clicks': 1,
                'buy-signals.value': ['BB_Breakout_Buy'], 'sell-signals.value': ['BB_Breakout_Sell'],
                'test-window-start.date': '2016-01-01', 'test-window-end.date': '2026-09-11'}
    status, body = call(a, 'backtest-results.children', 'run-backtest-btn.n_clicks', backtest)
    results['backtest_status'] = status
    results['backtest_has_metrics'] = 'TOTAL RETURN' in body.upper() and 'SHARPE' in body.upper()
    results['backtest_error'] = None if results['backtest_has_metrics'] else body[:400]

    # Rate limit: DEMO_ACTIONS_PER_IP_PER_MINUTE=2 in this subprocess.
    call(a, 'backtest-results.children', 'run-backtest-btn.n_clicks', backtest)
    status, body = call(a, 'backtest-results.children', 'run-backtest-btn.n_clicks', backtest)
    results['rate_limited_wall'] = 'demo-wall-body' in body and 'next one is available' in body

    # Size cap: ask for 1000 combinations and 5 signals a side.
    combos = {'run-optimization-btn.n_clicks': 1, 'max-combos-input.value': 1000,
              'max-signals-slider.value': 5, 'test-window-start.date': '2016-01-01',
              'test-window-end.date': '2026-09-11'}
    status, body = call(a, 'optimization-state.data', 'run-optimization-btn.n_clicks', combos, ip='198.51.100.1')
    sid_a = a.get_cookie(sessions.COOKIE_NAME).value
    opt = app.demo_store.get(sid_a).optimization_state
    results['combos_started'] = bool(opt.get('running'))
    results['combos_total'] = opt.get('total_combinations')
    results['combos_signals_per_side'] = max((max(len(b), len(s)) for b, s in opt.get('combinations', [])), default=0)

    # Concurrency: DEMO_MAX_CONCURRENT_JOBS=1, so a second visitor is walled.
    b, _ = visitor('visitor-b@example.com')
    status, body = call(b, 'optimization-state.data', 'run-optimization-btn.n_clicks', combos, ip='198.51.100.2')
    results['second_run_walled'] = 'demo-wall-body' in body and 'already going' in body
    sid_b = b.get_cookie(sessions.COOKIE_NAME).value
    results['second_state_untouched'] = not app.demo_store.get(sid_b).optimization_state.get('running')
    results['visitor_b_ticker'] = app.demo_store.get(sid_b).ticker

    # One-at-a-time jobs: visitor B can neither stop nor read visitor A's grid search.
    from lib.dash.callbacks import optimizer_grid
    optimizer_grid._grid_job.update(running=True, result=None, error=None)
    app.demo_guards._last_owner['grid'] = sid_a
    status, body = call(b, 'grid-interval.disabled', 'run-grid-btn.n_clicks', {'run-grid-btn.n_clicks': 1}, ip='198.51.100.3')
    results['grid_other_owner_walled'] = 'demo-wall-body' in body and "Another visitor" in body
    results['grid_not_cancelled'] = not optimizer_grid._grid_cancel.is_set()
    status, body = call(b, 'grid-results-store.data', 'grid-interval.n_intervals', {'grid-interval.n_intervals': 3}, ip='198.51.100.3')
    results['grid_poll_by_other_status'] = status
    optimizer_grid._grid_job.update(running=False)

    # Flow Scanner is off.
    status, body = call(a, 'flow-content.children', 'flow-rescan-button.n_clicks',
                        {'flow-rescan-button.n_clicks': 1, 'app-url.pathname': '/flow/TSLA'})
    results['flow_off'] = 'live options chain' in body

    # Usage recorded against each signed-in email.
    usage = {}
    for row in app.demo_access.store.visitor_rows():
        usage[row['email']] = {k: row[k] for k in ('visits', 'backtests', 'optimizer_runs', 'limits_hit')}
    results['usage'] = usage
    results['admin_off_without_token'] = app.server.test_client().get('/admin').status_code

    # Seals, from inside the running demo process.
    try:
        import lib.live.runner
        results['broker_import'] = 'allowed'
    except ImportError as exc:
        results['broker_import'] = type(exc).__name__
    try:
        import yfinance
        yfinance.download('TSLA')
        results['yfinance'] = 'allowed'
    except ConnectionError as exc:
        results['yfinance'] = type(exc).__name__
    from scripts.flow_runner import run_flow_scan
    results['flow_subprocess'] = run_flow_scan(['TSLA'], 'x.html')[0]
    from lib.data_processing import fetch_data
    results['fetch_rows'] = len(fetch_data('AAPL', '2020-01-01', '2026-09-12'))
    print('PROBE=' + json.dumps(results))
""")


@pytest.fixture(scope="module")
def probe(tmp_path_factory):
    env = {
        **os.environ,
        "DEMO_MODE": "true",
        "DEMO_ACTIONS_PER_IP_PER_MINUTE": "2",
        "DEMO_MAX_CONCURRENT_JOBS": "1",
        "DEMO_MAX_COMBOS": "40",
        "DEMO_MAX_SIGNALS_PER_SIDE": "2",
        "DEMO_ACCESS_GATE": "true",
        "DEMO_MAIL_BACKEND": "console",
        "DEMO_ACCESS_DB": str(tmp_path_factory.mktemp("demo-access") / "access.sqlite3"),
        "DEMO_ADMIN_TOKEN": "",
    }
    out = subprocess.run([sys.executable, "-c", _PROBE], cwd=REPO_ROOT, env=env,
                         capture_output=True, text=True, timeout=600)
    line = next((l for l in out.stdout.splitlines() if l.startswith("PROBE=")), None)
    assert line, f"probe failed:\n{out.stdout[-2000:]}\n{out.stderr[-4000:]}"
    return json.loads(line[len("PROBE="):])


def test_demo_page_serves_the_banner_and_a_session_cookie(probe):
    assert probe["page_status"] == 200
    assert probe["banner"] and probe["cookie"]


def test_the_real_demo_is_behind_the_email_gate(probe):
    assert probe["signed_out_redirect"]
    assert probe["signed_out_no_session"]  # no dashboard state is minted for a refused browser
    assert probe["signed_in_line"]
    assert probe["admin_off_without_token"] == 404


def test_usage_is_recorded_against_the_signed_in_email(probe):
    a = probe["usage"]["visitor-a@example.com"]
    assert a["visits"] >= 1
    assert a["backtests"] >= 1
    assert a["optimizer_runs"] == 1
    assert a["limits_hit"] >= 1  # the per-minute backtest limit
    assert probe["usage"]["visitor-b@example.com"]["optimizer_runs"] == 0


def test_page_ships_without_the_data_table_payload_until_it_is_opened(probe):
    # The workspace embeds ~10 MB of table JSON and the browser POSTs it back.
    assert probe["layout_bytes"] < 2_000_000
    assert probe["data_table_filled_on_open"]


def test_a_backtest_runs_end_to_end_on_the_frozen_snapshot(probe):
    assert probe["backtest_status"] == 200
    assert probe["backtest_has_metrics"], probe["backtest_error"]
    assert probe["fetch_rows"] > 1000


def test_per_ip_rate_limit_returns_a_wall_not_an_error(probe):
    assert probe["rate_limited_wall"]


def test_oversized_optimiser_requests_are_clamped_server_side(probe):
    assert probe["combos_started"]
    assert 0 < probe["combos_total"] <= 40
    assert probe["combos_signals_per_side"] <= 2


def test_concurrent_run_cap_walls_the_next_visitor_and_leaves_state_alone(probe):
    assert probe["second_run_walled"]
    assert probe["second_state_untouched"]
    assert probe["visitor_b_ticker"] == "TSLA"


def test_a_shared_job_can_only_be_stopped_or_read_by_its_owner(probe):
    assert probe["grid_other_owner_walled"]
    assert probe["grid_not_cancelled"]
    assert probe["grid_poll_by_other_status"] == 204


def test_order_path_and_vendors_are_refused_inside_the_demo(probe):
    assert probe["broker_import"] == "BrokerRefused"
    assert probe["yfinance"] == "NetworkRefused"
    assert probe["flow_subprocess"] != 0
    assert probe["flow_off"]
