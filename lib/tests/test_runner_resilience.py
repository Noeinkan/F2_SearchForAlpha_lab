"""
PaperRunner resilience: the heartbeat, reconnect across an IB Gateway restart,
guard-trip alerts, and sfa kill's stop request with --flatten.

MockBroker + isolated SQLite + a temporary PID directory. No ib_async, no
network: alerts go to a recording sink.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
from datetime import UTC, datetime, timedelta
from unittest.mock import AsyncMock

import pytest
import typer

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.agent_strategy import load_bundle
from lib.live import alerts, stop_request
from lib.live import runner as runner_module
from lib.live.broker import Bar, MockBroker, Order
from lib.live.connection import RestartWindow
from lib.live.runner import PaperRunner, RunnerOptions, kill_cli
from lib.store import fills as fills_store
from lib.store import state as state_store
from lib.store import trials as trials_store

BUNDLE = "mean_reversion_rsi_bb"


@pytest.fixture
def isolated(tmp_path, monkeypatch):
    db_path = tmp_path / "resilience.db"
    monkeypatch.setattr(trials_store, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(state_store, "PID_DIR", tmp_path / "running")
    monkeypatch.delenv(alerts.ALERT_WEBHOOK_ENV, raising=False)
    return db_path


class _Sink:
    def __init__(self) -> None:
        self.alerts: list[alerts.Alert] = []

    async def __call__(self, alert: alerts.Alert) -> bool:
        self.alerts.append(alert)
        return True


def _bar(i: int, price: float = 100.0) -> Bar:
    return Bar(
        timestamp=datetime(2024, 1, 1, tzinfo=UTC) + timedelta(days=i),
        open=price,
        high=price * 1.01,
        low=price * 0.99,
        close=price,
        volume=1_000_000,
    )


async def _started_runner(db_path, name: str = "resilience") -> tuple[PaperRunner, MockBroker, _Sink]:
    bundle = load_bundle(BUNDLE)
    broker = MockBroker(starting_cash=100_000)
    sink = _Sink()
    runner = PaperRunner(broker, RunnerOptions(name=name, bundle=bundle, db_path=db_path), alert_sink=sink)
    runner.heartbeat_seconds = 0  # tests drive heartbeat() by hand
    runner.restart_window = None  # never depend on the wall clock vs config/agent.yaml
    await runner.start()
    return runner, broker, sink


def _gateway_goes_down(broker: MockBroker, monkeypatch) -> AsyncMock:
    """Drop the connection, forget the bar subscriptions, refuse reconnects."""
    broker._connected = False
    broker._bar_handlers.clear()
    refused = AsyncMock(side_effect=ConnectionRefusedError("Gateway restarting"))
    monkeypatch.setattr(broker, "connect", refused)
    return refused


def _gateway_comes_back(broker: MockBroker, monkeypatch) -> None:
    monkeypatch.setattr(broker, "connect", AsyncMock(side_effect=lambda: setattr(broker, "_connected", True)))


# ---------------------------------------------------------------------------
# 8.13 heartbeat and reconnect
# ---------------------------------------------------------------------------


async def test_disconnect_guard_trips_with_no_bars_arriving(isolated, monkeypatch):
    runner, broker, sink = await _started_runner(isolated)
    _gateway_goes_down(broker, monkeypatch)
    runner.state.last_connected_at = datetime.now(UTC) - timedelta(seconds=120)

    await runner.heartbeat()

    assert runner.state.triggered_guard is not None
    assert runner.state.triggered_guard.name == "broker_disconnected"
    assert runner.state.stop_event.is_set()
    assert [a.event for a in sink.alerts] == [alerts.GUARD_TRIGGERED]
    assert "broker_disconnected" in sink.alerts[0].summary


async def test_gateway_restart_window_holds_the_guard_then_runner_resumes(isolated, monkeypatch):
    runner, broker, sink = await _started_runner(isolated)
    ticker = runner.options.bundle.ticker
    now = datetime.now(UTC)
    runner.restart_window = RestartWindow(start=(now - timedelta(minutes=2)).time(), minutes=15, tz=UTC)

    _gateway_goes_down(broker, monkeypatch)
    runner.state.last_connected_at = now - timedelta(seconds=300)
    await runner.heartbeat(now=now)

    assert runner.state.triggered_guard is None
    assert runner.state.reconnecting
    row = state_store.read_state("resilience", db_path=isolated)[0]
    disconnect = next(g for g in row["guard_state"] if g["name"] == "broker_disconnected")
    assert not disconnect["triggered"] and "restart window" in disconnect["reason"]
    assert row["snapshot"]["connected"] is False

    _gateway_comes_back(broker, monkeypatch)
    await runner.heartbeat(now=now + timedelta(minutes=3))

    assert not runner.state.reconnecting
    assert broker._bar_handlers[ticker] == [runner._on_bar], "bars must be re-subscribed exactly once"
    await broker.push_bar(ticker, _bar(1))
    assert len(runner.state.bars) == 1
    assert sink.alerts == []


async def test_reconnect_attempts_back_off(isolated, monkeypatch):
    runner, broker, _ = await _started_runner(isolated)
    runner._guards_config["max_disconnect_seconds"] = 10_000
    refused = _gateway_goes_down(broker, monkeypatch)
    t0 = datetime.now(UTC)

    for offset in (0, 1, 2, 5, 6):  # delays 2s then 4s: attempts at 0, 2 and 6
        await runner.heartbeat(now=t0 + timedelta(seconds=offset))

    assert refused.await_count == 3
    assert runner.state.reconnect_attempt == 3
    assert runner.state.next_reconnect_at == t0 + timedelta(seconds=6 + 8)


async def test_a_replayed_bar_is_not_processed_twice(isolated):
    runner, broker, _ = await _started_runner(isolated)
    ticker = runner.options.bundle.ticker
    await broker.push_bar(ticker, _bar(1))
    await broker.push_bar(ticker, _bar(1))
    await broker.push_bar(ticker, _bar(0))
    assert len(runner.state.bars) == 1


async def test_refused_order_alerts_and_the_runner_keeps_going(isolated, monkeypatch):
    runner, broker, sink = await _started_runner(isolated)
    monkeypatch.setattr(broker, "submit_order", AsyncMock(side_effect=RuntimeError("rejected: no permissions")))

    await runner._submit(side="BUY", quantity=10.0, bar=_bar(1))

    assert [a.event for a in sink.alerts] == [alerts.ORDER_FAILED]
    assert "no permissions" in sink.alerts[0].summary
    assert runner.state.inflight == set()
    assert not runner.state.stop_event.is_set()


async def test_stop_is_idempotent(isolated, monkeypatch):
    runner, broker, _ = await _started_runner(isolated)
    cancel = AsyncMock()
    monkeypatch.setattr(broker, "cancel_all", cancel)
    await runner.stop()
    await runner.stop()
    assert cancel.await_count == 1


# ---------------------------------------------------------------------------
# sfa kill --flatten: the runner side
# ---------------------------------------------------------------------------


async def test_stop_request_with_flatten_closes_the_position(isolated):
    runner, broker, _ = await _started_runner(isolated, name="flat")
    ticker = runner.options.bundle.ticker
    runner._guards_config["max_order_quantity"] = 5  # caps limit entries, never the exit
    await broker.push_bar(ticker, _bar(1, price=100.0))
    await broker.submit_order(Order(symbol=ticker, side="BUY", quantity=10))

    stop_request.request_stop("flat", flatten=True)
    await runner.heartbeat()

    assert runner.state.stop_event.is_set()
    assert await broker.get_positions() == []
    assert not stop_request.stop_request_pending("flat")
    result = stop_request.pop_stop_result("flat")
    assert result["reason"] == "kill"
    assert result["flatten"]["flattened"] is True
    assert [(o["side"], o["quantity"], o["status"]) for o in result["flatten"]["orders"]] == [("SELL", 10.0, "filled")]
    rows = fills_store.list_fills(strategy_name="flat", db_path=isolated)
    assert [(r["side"], r["status"]) for r in rows] == [("SELL", "filled")]


async def test_stop_request_flatten_with_no_position(isolated):
    runner, _, _ = await _started_runner(isolated, name="flat_empty")
    stop_request.request_stop("flat_empty", flatten=True)
    await runner.heartbeat()
    result = stop_request.pop_stop_result("flat_empty")
    assert result["flatten"] == {"requested": True, "flattened": True, "orders": []}


async def test_flatten_that_never_fills_is_reported_unconfirmed(isolated, monkeypatch):
    runner, broker, _ = await _started_runner(isolated, name="flat_slow")
    ticker = runner.options.bundle.ticker
    await broker.push_bar(ticker, _bar(1))
    await broker.submit_order(Order(symbol=ticker, side="BUY", quantity=10))

    async def _never_fills(order):
        await asyncio.sleep(10)

    monkeypatch.setattr(broker, "submit_order", _never_fills)
    runner.flatten_timeout_seconds = 0.05
    result = await runner.stop(flatten=True)
    assert result["flatten"]["flattened"] is False
    assert result["flatten"]["orders"][0]["status"] == "unconfirmed"
    assert "TWS" in result["flatten"]["error"]


async def test_heartbeat_loop_answers_a_stop_request(isolated):
    bundle = load_bundle(BUNDLE)
    runner = PaperRunner(
        MockBroker(), RunnerOptions(name="looped", bundle=bundle, db_path=isolated), alert_sink=_Sink()
    )
    runner.heartbeat_seconds = 0.02
    runner.restart_window = None
    await runner.start()
    stop_request.request_stop("looped", flatten=False)
    await asyncio.wait_for(runner.wait_until_done(), timeout=5)
    assert stop_request.pop_stop_result("looped")["reason"] == "kill"
    await asyncio.sleep(0)
    assert runner.state.heartbeat_task.done()


# ---------------------------------------------------------------------------
# sfa kill: the CLI side
# ---------------------------------------------------------------------------


class _FakeClock:
    def __init__(self) -> None:
        self.now = 0.0
        self.on_sleep = None

    def clock(self) -> float:
        return self.now

    def sleep(self, seconds: float) -> None:
        self.now += seconds
        if self.on_sleep:
            self.on_sleep()


def _json_out(capsys) -> dict:
    return json.loads(capsys.readouterr().out.strip().splitlines()[-1])


def test_kill_waits_for_the_runner_to_answer(isolated, capsys, monkeypatch):
    state_store.write_pid("k1")
    fake = _FakeClock()

    def _runner_answers():
        if stop_request.stop_request_pending("k1"):
            assert stop_request.read_stop_request("k1") == {"flatten": True}
            stop_request.clear_stop_request("k1")
            stop_request.write_stop_result(
                "k1", {"flatten": {"requested": True, "flattened": True, "orders": [{"side": "SELL"}]}}
            )

    fake.on_sleep = _runner_answers
    terminate = []
    monkeypatch.setattr(runner_module, "_terminate", terminate.append)

    kill_cli(name="k1", flatten=True, json_output=True, sleep=fake.sleep, clock=fake.clock)

    payload = _json_out(capsys)
    assert payload["killed"] is True and payload["graceful"] is True
    assert payload["flatten"]["flattened"] is True
    assert terminate == []
    assert state_store.read_pid("k1") is None


def test_kill_terminates_an_unresponsive_runner_and_says_flatten_did_not_happen(isolated, capsys, monkeypatch):
    state_store.write_pid("k2")
    fake = _FakeClock()
    terminate = []
    monkeypatch.setattr(runner_module, "_process_matches", lambda pid, name: "runner")
    monkeypatch.setattr(runner_module, "_terminate", terminate.append)

    with pytest.raises(typer.Exit) as exit_info:
        kill_cli(name="k2", flatten=True, json_output=True, sleep=fake.sleep, clock=fake.clock)

    assert exit_info.value.exit_code == 3
    payload = _json_out(capsys)
    assert payload["graceful"] is False
    assert payload["flatten"]["flattened"] is False
    assert terminate == [os.getpid()]
    assert fake.now < 60, "an unanswered request must not wait out the full timeout"
    assert not stop_request.stop_request_pending("k2")


def test_kill_cleans_up_a_stale_pid(isolated, capsys, monkeypatch):
    state_store.write_pid("k3")
    fake = _FakeClock()
    monkeypatch.setattr(runner_module, "_process_matches", lambda pid, name: "gone")

    with pytest.raises(typer.Exit) as exit_info:
        kill_cli(name="k3", flatten=False, json_output=True, sleep=fake.sleep, clock=fake.clock)

    assert exit_info.value.exit_code == 2
    assert _json_out(capsys)["error"] == "not_running"
    assert state_store.read_pid("k3") is None


def test_kill_never_terminates_a_process_it_cannot_identify(isolated, capsys, monkeypatch):
    state_store.write_pid("k4")
    fake = _FakeClock()
    terminate = []
    monkeypatch.setattr(runner_module, "_process_matches", lambda pid, name: "other")
    monkeypatch.setattr(runner_module, "_terminate", terminate.append)

    with pytest.raises(typer.Exit) as exit_info:
        kill_cli(name="k4", flatten=False, json_output=True, sleep=fake.sleep, clock=fake.clock)

    assert exit_info.value.exit_code == 3
    assert _json_out(capsys)["error"] == "pid_mismatch"
    assert terminate == []
    assert state_store.read_pid("k4") is not None
