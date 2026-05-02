"""
Async paper trading runner.

For each new bar from the broker, the runner:
    1. Appends the bar to a rolling in memory OHLCV buffer.
    2. Re runs add_indicators and generate_signals on the buffer.
    3. Reads the latest combined buy and sell signal columns; if a buy signal
       fires and we are flat, places a market order; if a sell signal fires
       and we are long, closes the position.
    4. Persists every fill via lib.store.fills.
    5. Evaluates all guards; on first trigger it cancels open orders and
       stops the loop.

The runner is intentionally simple: one strategy per process, one ticker per
strategy, market orders only. The dashboard, the optimisers, and the
backtest engine are unaffected by anything here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import logging
import os
import signal
import sys
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import structlog
import typer

from lib.agent_strategy import (
    AgentStrategyBundle,
    StrategyNotFoundError,
    load_bundle,
    params_to_indicator_settings,
)
from lib.cli.contracts import CliError
from lib.config_loader import get_agent_config
from lib.live import guards as guard_module
from lib.live.broker import Bar, Broker, IBBroker, Order
from lib.signals.indicators import add_indicators, generate_signals
from lib.store import fills as fills_store
from lib.store import state as state_store

logger = structlog.get_logger(__name__)


@dataclass
class RunnerOptions:
    name: str
    bundle: AgentStrategyBundle
    initial_capital: float = 100_000.0
    quantity_per_signal: int = 10
    rolling_buffer_bars: int = 250
    db_path: Path | None = None


@dataclass
class _RunnerState:
    bars: list[Bar] = field(default_factory=list)
    last_connected_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    starting_equity: float = 0.0
    last_buy_emitted: bool = False
    last_sell_emitted: bool = False
    triggered_guard: guard_module.GuardResult | None = None
    stop_event: asyncio.Event = field(default_factory=asyncio.Event)
    bar_lock: asyncio.Lock = field(default_factory=asyncio.Lock)
    inflight: set[str] = field(default_factory=set)


class PaperRunner:
    """Wires a Broker, a strategy bundle, and the guard set together."""

    def __init__(self, broker: Broker, options: RunnerOptions) -> None:
        self.broker = broker
        self.options = options
        self.state = _RunnerState()
        self._guards_config = (get_agent_config().get("guards") or {}) | {}

    async def start(self) -> None:
        await self.broker.connect()
        self.state.last_connected_at = datetime.now(UTC)
        account = await self.broker.get_account()
        self.state.starting_equity = account.equity or self.options.initial_capital
        await self.broker.subscribe_bars(self.options.bundle.ticker, self._on_bar)
        logger.info(
            "runner.start",
            strategy=self.options.name,
            ticker=self.options.bundle.ticker,
            starting_equity=self.state.starting_equity,
        )

    async def stop(self) -> None:
        await self.broker.cancel_all(self.options.bundle.ticker)
        await self.broker.disconnect()
        self.state.stop_event.set()
        logger.info("runner.stop", strategy=self.options.name)

    async def wait_until_done(self) -> None:
        await self.state.stop_event.wait()

    async def _on_bar(self, bar: Bar) -> None:
        async with self.state.bar_lock:
            if self.state.triggered_guard is not None:
                return
            self.state.bars.append(bar)
            if len(self.state.bars) > self.options.rolling_buffer_bars:
                self.state.bars = self.state.bars[-self.options.rolling_buffer_bars :]
            self.state.last_connected_at = datetime.now(UTC)

            df = self._buffer_to_df()
            if len(df) < 30:
                await self._evaluate_guards()
                return

            indicator_settings = params_to_indicator_settings(self.options.bundle.live_params)
            df_with_ind = add_indicators(df.copy(), indicator_settings)
            df_with_signals, _ = generate_signals(df_with_ind, indicator_settings)

            buy_now = self._latest_combined(df_with_signals, self.options.bundle.buy_signals)
            sell_now = self._latest_combined(df_with_signals, self.options.bundle.sell_signals)

            positions = await self.broker.get_positions()
            held = next((p for p in positions if p.symbol == self.options.bundle.ticker), None)

            if buy_now and not self.state.last_buy_emitted and held is None:
                await self._submit(side="BUY", quantity=self.options.quantity_per_signal, bar=bar)
            if sell_now and not self.state.last_sell_emitted and held is not None and held.quantity > 0:
                await self._submit(side="SELL", quantity=float(held.quantity), bar=bar)

            self.state.last_buy_emitted = bool(buy_now)
            self.state.last_sell_emitted = bool(sell_now)

            await self._evaluate_guards()

    async def _submit(self, *, side: str, quantity: float, bar: Bar) -> None:
        coid = hashlib.sha1(
            f"{self.options.name}|{bar.timestamp.isoformat()}|{side}|{quantity}".encode()
        ).hexdigest()[:16]

        if coid in self.state.inflight:
            logger.warning(
                "runner.submit_skipped_inflight",
                coid=coid,
                strategy=self.options.name,
            )
            return

        max_qty = float(self._guards_config.get("max_order_quantity", float("inf")))
        max_notional = float(self._guards_config.get("max_order_notional", float("inf")))

        if quantity > max_qty:
            logger.warning(
                "runner.pretrade_reject",
                reason="quantity_exceeded",
                qty=quantity,
                limit=max_qty,
                strategy=self.options.name,
            )
            return

        notional = quantity * bar.close
        if notional > max_notional:
            logger.warning(
                "runner.pretrade_reject",
                reason="notional_exceeded",
                notional=notional,
                limit=max_notional,
                strategy=self.options.name,
            )
            return

        fills_store.record_intent(
            self.options.name,
            self.options.bundle.ticker,
            side,
            quantity,
            coid,
            db_path=self.options.db_path,
        )
        self.state.inflight.add(coid)
        try:
            order = Order(
                symbol=self.options.bundle.ticker,
                side=side,
                quantity=quantity,
                client_order_id=coid,
            )
            fill = await self.broker.submit_order(order)
            fills_store.mark_filled(coid, fill, db_path=self.options.db_path)
            logger.info(
                "runner.fill",
                strategy=self.options.name,
                side=side,
                qty=quantity,
                price=fill.price,
                realised_pnl=fill.realised_pnl,
                coid=coid,
            )
        finally:
            self.state.inflight.discard(coid)

    async def _evaluate_guards(self) -> None:
        snapshot = await self._snapshot()
        results = guard_module.evaluate(snapshot, self._guards_config)
        guard_state = [r.as_dict() for r in results]
        state_store.upsert_state(
            strategy_name=self.options.name,
            starting_equity=self.state.starting_equity,
            snapshot={
                "ticker": self.options.bundle.ticker,
                "cash": snapshot.account.cash,
                "equity": snapshot.account.equity,
                "realised_pnl_today": snapshot.account.realised_pnl_today,
                "positions": [
                    {"symbol": p.symbol, "quantity": p.quantity, "market_value": p.market_value}
                    for p in snapshot.positions
                ],
            },
            guard_state=guard_state,
            db_path=self.options.db_path,
        )
        triggered = guard_module.first_trigger(results)
        if triggered:
            self.state.triggered_guard = triggered
            logger.warning(
                "runner.guard_triggered",
                strategy=self.options.name,
                guard=triggered.name,
                reason=triggered.reason,
            )
            await self.stop()

    async def _snapshot(self) -> guard_module.RunnerSnapshot:
        account = await self.broker.get_account()
        positions = await self.broker.get_positions()
        try:
            server_time = await self.broker.get_server_time()
        except Exception:
            server_time = datetime.now(UTC)
        return guard_module.RunnerSnapshot(
            starting_equity=self.state.starting_equity,
            account=account,
            positions=positions,
            last_connected_at=self.state.last_connected_at,
            server_time=server_time,
            local_now=datetime.now(UTC),
        )

    def _buffer_to_df(self) -> pd.DataFrame:
        if not self.state.bars:
            return pd.DataFrame(columns=["Open", "High", "Low", "Close", "Volume"])
        rows = [
            {
                "Open": b.open,
                "High": b.high,
                "Low": b.low,
                "Close": b.close,
                "Volume": b.volume,
            }
            for b in self.state.bars
        ]
        idx = [b.timestamp for b in self.state.bars]
        return pd.DataFrame(rows, index=pd.Index(idx))

    @staticmethod
    def _latest_combined(df: pd.DataFrame, columns: list[str]) -> bool:
        if df.empty or not columns:
            return False
        present = [c for c in columns if c in df.columns]
        if not present:
            return False
        last = df[present].iloc[-1]
        return bool(last.fillna(0).gt(0).any())


# ---------------------------------------------------------------------------
# CLI helpers wired to sfa run / sfa status / sfa kill
# ---------------------------------------------------------------------------


def run_paper_cli(*, name: str, json_output: bool) -> None:
    try:
        bundle = load_bundle(name)
    except StrategyNotFoundError:
        typer.echo(json.dumps(CliError("unknown_strategy", f"No agent strategy named {name!r}.").as_dict()))
        raise typer.Exit(code=2)

    cfg = get_agent_config().get("ib") or {}
    broker = IBBroker(
        host=str(cfg.get("host", "127.0.0.1")),
        port=int(cfg.get("port", 4002)),
        client_id=int(cfg.get("client_id", 7)),
    )
    options = RunnerOptions(name=name, bundle=bundle)
    runner = PaperRunner(broker=broker, options=options)

    state_store.write_pid(name)
    payload = {
        "started": True,
        "strategy": name,
        "ticker": bundle.ticker,
        "broker": {"host": cfg.get("host", "127.0.0.1"), "port": int(cfg.get("port", 4002))},
        "pid": os.getpid(),
    }
    typer.echo(json.dumps(payload, default=str) if json_output else f"Started paper runner for {name} (pid {os.getpid()})")

    async def _run() -> None:
        loop = asyncio.get_running_loop()
        try:
            loop.add_signal_handler(
                signal.SIGTERM,
                lambda: asyncio.create_task(runner.stop()),
            )
        except (NotImplementedError, OSError):
            pass  # Windows does not support add_signal_handler
        try:
            await runner.start()
            await runner.wait_until_done()
        finally:
            state_store.remove_pid(name)

    try:
        asyncio.run(_run())
    except (KeyboardInterrupt, asyncio.CancelledError):
        state_store.remove_pid(name)


def status_cli(*, name: str | None, json_output: bool) -> None:
    rows = state_store.read_state(strategy_name=name)
    payload = {"running": rows}
    if json_output:
        typer.echo(json.dumps(payload, indent=2, default=str))
        return
    if not rows:
        typer.echo("No running strategies.")
        return
    for r in rows:
        guards = ", ".join(g["name"] for g in r["guard_state"] if g["triggered"]) or "ok"
        typer.echo(
            f"{r['strategy_name']}  pid={r['pid']}  equity={r['snapshot'].get('equity'):.2f}  guards={guards}"
        )


def kill_cli(*, name: str, flatten: bool, json_output: bool) -> None:
    pid = state_store.read_pid(name)
    if pid is None:
        typer.echo(json.dumps(CliError("not_running", f"No running PID for {name!r}.").as_dict()))
        raise typer.Exit(code=2)

    if flatten:
        typer.echo(
            json.dumps({
                "killed": False,
                "strategy": name,
                "reason": "flatten_not_supported_in_kill",
                "details": (
                    "--flatten is not handled in this build to keep kill side effect free. "
                    "Stop the runner first; close positions via sfa run with a SELL signal "
                    "or manually in TWS."
                ),
            })
        )
        raise typer.Exit(code=3)

    try:
        os.kill(pid, signal.SIGTERM)
    except (ProcessLookupError, PermissionError) as exc:
        typer.echo(json.dumps(CliError("kill_failed", str(exc)).as_dict()))
        raise typer.Exit(code=3) from exc

    state_store.remove_pid(name)
    state_store.clear_state(name)
    payload = {"killed": True, "strategy": name, "pid": pid}
    typer.echo(json.dumps(payload) if json_output else f"Killed {name} (pid {pid}).")
