"""
Each of the four guards must trigger when expected and stay quiet otherwise.
Tests build RunnerSnapshot directly so they do not depend on the runner loop.
"""

from __future__ import annotations

import os
import sys
from datetime import UTC, datetime, timedelta

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.live.broker import AccountSnapshot, Position
from lib.live import guards as guard_module


def _snapshot(
    *,
    starting_equity: float = 100_000.0,
    cash: float = 90_000.0,
    equity: float = 100_000.0,
    realised_pnl_today: float = 0.0,
    positions: list[Position] | None = None,
    last_connected_at: datetime | None = None,
    server_time: datetime | None = None,
    local_now: datetime | None = None,
) -> guard_module.RunnerSnapshot:
    now = datetime.now(UTC)
    return guard_module.RunnerSnapshot(
        starting_equity=starting_equity,
        account=AccountSnapshot(cash=cash, equity=equity, realised_pnl_today=realised_pnl_today),
        positions=positions or [],
        last_connected_at=last_connected_at or now,
        server_time=server_time or now,
        local_now=local_now or now,
    )


CONFIG = {
    "max_daily_loss_pct": 0.02,
    "max_position_pct": 0.25,
    "max_disconnect_seconds": 60,
    "max_clock_drift_seconds": 5,
}


def test_daily_loss_guard_triggers_below_limit():
    snap = _snapshot(realised_pnl_today=-2_500)  # -2.5% on 100k starting
    result = guard_module.daily_loss_guard(snap, CONFIG)
    assert result.triggered
    assert "below limit" in result.reason


def test_daily_loss_guard_quiet_within_limit():
    snap = _snapshot(realised_pnl_today=-1_000)  # -1%
    result = guard_module.daily_loss_guard(snap, CONFIG)
    assert not result.triggered


def test_position_size_guard_triggers_above_limit():
    pos = Position(symbol="SPY", quantity=300, avg_cost=100, market_price=100)
    snap = _snapshot(equity=100_000, positions=[pos])  # 30% > 25%
    result = guard_module.position_size_guard(snap, CONFIG)
    assert result.triggered
    assert "SPY" in result.reason


def test_position_size_guard_quiet_below_limit():
    pos = Position(symbol="SPY", quantity=200, avg_cost=100, market_price=100)
    snap = _snapshot(equity=100_000, positions=[pos])  # 20%
    result = guard_module.position_size_guard(snap, CONFIG)
    assert not result.triggered


def test_disconnect_guard_triggers_after_threshold():
    now = datetime.now(UTC)
    snap = _snapshot(last_connected_at=now - timedelta(seconds=120), local_now=now)
    result = guard_module.broker_disconnected_guard(snap, CONFIG)
    assert result.triggered
    assert "No connection" in result.reason


def test_disconnect_guard_quiet_within_threshold():
    now = datetime.now(UTC)
    snap = _snapshot(last_connected_at=now - timedelta(seconds=10), local_now=now)
    result = guard_module.broker_disconnected_guard(snap, CONFIG)
    assert not result.triggered


def test_clock_drift_guard_triggers_when_drift_too_high():
    now = datetime.now(UTC)
    snap = _snapshot(local_now=now, server_time=now - timedelta(seconds=15))
    result = guard_module.clock_drift_guard(snap, CONFIG)
    assert result.triggered
    assert "Drift" in result.reason


def test_clock_drift_guard_quiet_within_limit():
    now = datetime.now(UTC)
    snap = _snapshot(local_now=now, server_time=now - timedelta(seconds=2))
    result = guard_module.clock_drift_guard(snap, CONFIG)
    assert not result.triggered


def test_evaluate_returns_one_result_per_guard():
    snap = _snapshot()
    results = guard_module.evaluate(snap, CONFIG)
    assert len(results) == len(guard_module.ALL_GUARDS)
    assert all(isinstance(r, guard_module.GuardResult) for r in results)


def test_first_trigger_returns_first_failed():
    snap = _snapshot(
        realised_pnl_today=-3_000,
        positions=[Position("SPY", 400, 100, 100)],
        equity=100_000,
    )
    results = guard_module.evaluate(snap, CONFIG)
    triggered = guard_module.first_trigger(results)
    assert triggered is not None
    assert triggered.triggered


def test_first_trigger_returns_none_when_clean():
    snap = _snapshot()
    results = guard_module.evaluate(snap, CONFIG)
    assert guard_module.first_trigger(results) is None
