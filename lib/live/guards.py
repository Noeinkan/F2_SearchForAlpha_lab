"""
Guards for the paper trading runner.

A Guard takes a RunnerSnapshot and returns a GuardResult. The runner trips on
the first triggered guard and immediately stops itself, cancelling open
orders. Each guard's threshold is configurable via config/agent.yaml.

Implemented guards:
    1. daily_loss          : realised PnL today below -max_daily_loss_pct
    2. position_size       : any position market value above max_position_pct
    3. broker_disconnected : seconds since last successful heartbeat exceed
                             max_disconnect_seconds
    4. clock_drift         : abs(local now - broker server time) exceeds
                             max_clock_drift_seconds
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Callable

from lib.live.broker import AccountSnapshot, Position


DEFAULTS = {
    "max_daily_loss_pct": 0.02,
    "max_position_pct": 0.25,
    "max_disconnect_seconds": 60,
    "max_clock_drift_seconds": 5,
}


@dataclass(frozen=True)
class GuardResult:
    triggered: bool
    name: str
    reason: str = ""

    def as_dict(self) -> dict[str, Any]:
        return {"triggered": self.triggered, "name": self.name, "reason": self.reason}


@dataclass(frozen=True)
class RunnerSnapshot:
    starting_equity: float
    account: AccountSnapshot
    positions: list[Position]
    last_connected_at: datetime
    server_time: datetime
    local_now: datetime


def daily_loss_guard(snapshot: RunnerSnapshot, config: dict[str, Any]) -> GuardResult:
    limit = float(config.get("max_daily_loss_pct", DEFAULTS["max_daily_loss_pct"]))
    if snapshot.starting_equity <= 0:
        return GuardResult(False, "daily_loss")
    pnl_pct = snapshot.account.realised_pnl_today / snapshot.starting_equity
    if pnl_pct <= -limit:
        return GuardResult(
            True,
            "daily_loss",
            f"Realised PnL {pnl_pct:.4f} below limit -{limit:.4f}",
        )
    return GuardResult(False, "daily_loss")


def position_size_guard(snapshot: RunnerSnapshot, config: dict[str, Any]) -> GuardResult:
    limit = float(config.get("max_position_pct", DEFAULTS["max_position_pct"]))
    if snapshot.account.equity <= 0:
        return GuardResult(False, "position_size")
    for pos in snapshot.positions:
        share = abs(pos.market_value) / snapshot.account.equity
        if share > limit:
            return GuardResult(
                True,
                "position_size",
                f"{pos.symbol} share {share:.4f} above limit {limit:.4f}",
            )
    return GuardResult(False, "position_size")


def broker_disconnected_guard(snapshot: RunnerSnapshot, config: dict[str, Any]) -> GuardResult:
    limit = float(config.get("max_disconnect_seconds", DEFAULTS["max_disconnect_seconds"]))
    elapsed = (snapshot.local_now - snapshot.last_connected_at).total_seconds()
    if elapsed > limit:
        return GuardResult(
            True,
            "broker_disconnected",
            f"No connection for {elapsed:.1f}s (limit {limit:.0f}s)",
        )
    return GuardResult(False, "broker_disconnected")


def clock_drift_guard(snapshot: RunnerSnapshot, config: dict[str, Any]) -> GuardResult:
    limit = float(config.get("max_clock_drift_seconds", DEFAULTS["max_clock_drift_seconds"]))
    drift = abs((snapshot.local_now - snapshot.server_time).total_seconds())
    if drift > limit:
        return GuardResult(
            True,
            "clock_drift",
            f"Drift {drift:.2f}s above limit {limit:.0f}s",
        )
    return GuardResult(False, "clock_drift")


ALL_GUARDS: list[Callable[[RunnerSnapshot, dict[str, Any]], GuardResult]] = [
    daily_loss_guard,
    position_size_guard,
    broker_disconnected_guard,
    clock_drift_guard,
]


def evaluate(snapshot: RunnerSnapshot, config: dict[str, Any]) -> list[GuardResult]:
    """Run every guard and return all results (triggered + not triggered)."""
    return [guard(snapshot, config) for guard in ALL_GUARDS]


def first_trigger(results: list[GuardResult]) -> GuardResult | None:
    for r in results:
        if r.triggered:
            return r
    return None
