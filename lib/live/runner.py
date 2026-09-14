"""
Async paper trading runner.

For each new bar from the broker, the runner:
    1. Appends the bar to a rolling in memory OHLCV buffer.
    2. Re runs add_indicators and generate_signals on the buffer.
    3. Reads the latest combined buy and sell signal columns; if a buy signal
       fires and we are flat, places an order; if a sell signal fires and we
       are long, closes the position. The order type is the strategy's
       (lib.live.execution): a market order is waited for, any other rests and
       is settled, expired or replaced on later bars (lib.live.working_orders).
    4. Persists every fill via lib.store.fills.
    5. Evaluates all guards; on first trigger it cancels open orders and
       stops the loop.

Independently of bars, a heartbeat runs every ``runner.heartbeat_seconds``:
    - it picks up a stop request from ``sfa kill`` (lib.live.stop_request) and
      stops cleanly, closing the position first when asked;
    - it checks the broker connection and, when it has dropped, reconnects with
      backoff and re-subscribes to bars (lib.live.connection) — this is how a
      runner survives the IB Gateway daily restart;
    - it evaluates the guards, so a broker that has stopped sending bars still
      trips broker_disconnected instead of leaving the runner silently idle.

Guard trips, refused orders and a crashed runner are also sent to the
``SFA_ALERT_WEBHOOK`` webhook when one is set (lib.live.alerts).

The runner is intentionally simple: one strategy per process, one ticker per
strategy, one working order per side. The dashboard, the optimisers, and the
backtest engine are unaffected by anything here.
"""

from __future__ import annotations

import asyncio
import hashlib
import json
import os
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime, timedelta
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
from lib.live import alerts, stop_request
from lib.live import guards as guard_module
from lib.live.broker import ORDER_REJECTED, AccountSnapshot, Bar, Broker, IBBroker, Order, Position
from lib.live.connection import ReconnectPolicy, RestartWindow
from lib.live.execution import DEFAULT_PRICE_TICK, LiveOrderModel, UnsupportedLiveParams
from lib.live.working_orders import WorkingOrders
from lib.signals.indicators import add_indicators, generate_signals
from lib.store import fills as fills_store
from lib.store import state as state_store

logger = structlog.get_logger(__name__)

DEFAULT_HEARTBEAT_SECONDS = 5.0
DEFAULT_FLATTEN_TIMEOUT_SECONDS = 30.0


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
    # Connection bookkeeping for the heartbeat.
    reconnecting: bool = False
    reconnect_attempt: int = 0
    next_reconnect_at: datetime | None = None
    disconnected_since: datetime | None = None
    # Last broker readings, used when the broker cannot answer mid-outage.
    last_account: AccountSnapshot | None = None
    last_positions: list[Position] = field(default_factory=list)
    stopping: bool = False
    stop_result: dict[str, Any] | None = None
    heartbeat_task: asyncio.Task | None = None


class PaperRunner:
    """Wires a Broker, a strategy bundle, and the guard set together."""

    def __init__(
        self,
        broker: Broker,
        options: RunnerOptions,
        *,
        alert_sink: alerts.AlertSink | None = None,
    ) -> None:
        self.broker = broker
        self.options = options
        self.state = _RunnerState()
        agent_cfg = get_agent_config()
        self._guards_config = (agent_cfg.get("guards") or {}) | {}
        ib_cfg = agent_cfg.get("ib") or {}
        runner_cfg = agent_cfg.get("runner") or {}
        self.heartbeat_seconds = float(runner_cfg.get("heartbeat_seconds", DEFAULT_HEARTBEAT_SECONDS))
        self.flatten_timeout_seconds = float(
            runner_cfg.get("flatten_timeout_seconds", DEFAULT_FLATTEN_TIMEOUT_SECONDS)
        )
        self.reconnect_policy = ReconnectPolicy.from_config(ib_cfg.get("reconnect"))
        self.restart_window = RestartWindow.from_config(ib_cfg.get("daily_restart"))
        self._alert_sink: alerts.AlertSink = alert_sink or alerts.notify
        # Raises UnsupportedLiveParams before anything connects (see lib.live.execution).
        self.order_model = LiveOrderModel.from_live_params(
            options.bundle.live_params,
            price_tick=float(runner_cfg.get("price_tick", DEFAULT_PRICE_TICK)),
        )
        self.orders = WorkingOrders(
            broker,
            self.order_model,
            strategy=options.name,
            symbol=options.bundle.ticker,
            db_path=options.db_path,
        )

    async def start(self) -> None:
        await self.broker.connect()
        self.state.last_connected_at = datetime.now(UTC)
        account = await self.broker.get_account()
        self.state.last_account = account
        self.state.starting_equity = account.equity or self.options.initial_capital
        await self.broker.subscribe_bars(self.options.bundle.ticker, self._on_bar)
        if self.heartbeat_seconds > 0:
            self.state.heartbeat_task = asyncio.create_task(self._heartbeat_loop())
        logger.info(
            "runner.start",
            strategy=self.options.name,
            ticker=self.options.bundle.ticker,
            starting_equity=self.state.starting_equity,
        )

    async def stop(
        self,
        *,
        flatten: bool = False,
        reason: str = "requested",
        alert: alerts.Alert | None = None,
        write_result: bool = False,
    ) -> dict[str, Any]:
        """Cancel open orders, optionally close the position, disconnect, and finish.

        Safe to call twice: a second call returns without touching the broker.
        Everything that must happen before the process exits — the alert, the
        result file for ``sfa kill`` — happens before ``stop_event`` is set,
        because setting it lets ``asyncio.run`` return and cancel what is left.
        """
        if self.state.stopping:
            return self.state.stop_result or {"strategy": self.options.name, "already_stopping": True}
        self.state.stopping = True
        ticker = self.options.bundle.ticker
        result: dict[str, Any] = {
            "strategy": self.options.name,
            "ticker": ticker,
            "reason": reason,
            "flatten": {"requested": flatten, "flattened": None, "orders": []},
        }
        try:
            # Settle the runner's own resting orders first, so a partial fill
            # is recorded and any shares it bought are there for flatten to close.
            settled = await self.orders.cancel_all(why="stopped")
            if settled:
                result["cancelled_orders"] = [s.as_dict() for s in settled]
        except Exception as exc:
            logger.error("runner.cancel_working_failed", strategy=self.options.name, error=str(exc))
        try:
            await self.broker.cancel_all(ticker)
        except Exception as exc:
            logger.error("runner.cancel_failed", strategy=self.options.name, error=str(exc))
            result["cancel_error"] = str(exc)
        if flatten:
            result["flatten"] = await self._flatten()
        try:
            await self.broker.disconnect()
        except Exception as exc:
            logger.error("runner.disconnect_failed", strategy=self.options.name, error=str(exc))
        if alert is not None:
            await self._alert(alert)
        self.state.stop_result = result
        if write_result:
            stop_request.write_stop_result(self.options.name, result)
        heartbeat = self.state.heartbeat_task
        if heartbeat is not None and heartbeat is not asyncio.current_task():
            heartbeat.cancel()
        self.state.stop_event.set()
        logger.info("runner.stop", strategy=self.options.name, reason=reason)
        return result

    async def wait_until_done(self) -> None:
        await self.state.stop_event.wait()

    # ------------------------------------------------------------------
    # Bars
    # ------------------------------------------------------------------

    async def _on_bar(self, bar: Bar) -> None:
        async with self.state.bar_lock:
            if self.state.triggered_guard is not None or self.state.stopping:
                return
            if self.state.bars and bar.timestamp <= self.state.bars[-1].timestamp:
                # A bar we already have, e.g. replayed around a reconnect.
                return
            self.state.bars.append(bar)
            if len(self.state.bars) > self.options.rolling_buffer_bars:
                self.state.bars = self.state.bars[-self.options.rolling_buffer_bars :]
            self.state.last_connected_at = datetime.now(UTC)
            # Resting orders have now had this bar's range: settle or expire them
            # before the signals decide anything.
            await self._settle_orders()

            df = self._buffer_to_df()
            if len(df) < 30:
                await self._evaluate_guards()
                return

            indicator_settings = params_to_indicator_settings(self.options.bundle.live_params)
            df_with_ind = add_indicators(df.copy(), indicator_settings)
            df_with_signals, _ = generate_signals(df_with_ind, indicator_settings)

            buy_now = self._latest_combined(df_with_signals, self.options.bundle.buy_signals)
            sell_now = self._latest_combined(df_with_signals, self.options.bundle.sell_signals)

            held = await self._held()

            if buy_now and not self.state.last_buy_emitted and held is None:
                # A new buy signal replaces a buy still working, as in the
                # backtest; if that order traded while being cancelled we now
                # hold shares, and a second entry would double the position.
                if await self._replace_working("BUY"):
                    await self._submit(side="BUY", quantity=self.options.quantity_per_signal, bar=bar)
            if sell_now and not self.state.last_sell_emitted and held is not None and held.quantity > 0:
                if await self._replace_working("SELL"):
                    held = await self._held()  # a partial fill of the old sell shrank it
                    if held is not None and held.quantity > 0:
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

        # A resting order is capped at the price it rests at, like the backtest sizes it.
        reference = self.order_model.prices(side, bar.close)["reference"] or bar.close
        notional = quantity * reference
        if notional > max_notional:
            logger.warning(
                "runner.pretrade_reject",
                reason="notional_exceeded",
                notional=notional,
                limit=max_notional,
                strategy=self.options.name,
            )
            return

        try:
            if self.order_model.rests:
                await self.orders.place(side=side, quantity=quantity, close=bar.close, client_order_id=coid)
            else:
                await self._place(side=side, quantity=quantity, coid=coid)
        except Exception as exc:
            logger.error(
                "runner.submit_failed",
                strategy=self.options.name,
                side=side,
                qty=quantity,
                coid=coid,
                error=str(exc),
            )
            await self._alert(
                alerts.Alert(
                    event=alerts.ORDER_FAILED,
                    strategy=self.options.name,
                    ticker=self.options.bundle.ticker,
                    summary=f"{side} {quantity:g} {self.order_model.order_type} order failed: {exc}",
                    details={"side": side, "quantity": quantity, "client_order_id": coid},
                )
            )

    async def _held(self) -> Position | None:
        positions = await self.broker.get_positions()
        return next((p for p in positions if p.symbol == self.options.bundle.ticker), None)

    async def _replace_working(self, side: str) -> bool:
        """Cancel the order still working on ``side``. True when a new one may be placed."""
        if self.orders.get(side) is None:
            return True
        settled = await self.orders.cancel(side, why="replaced")
        if settled is None:
            return False  # cancel not confirmed yet: never stack a second order on it
        return side == "SELL" or settled.status.filled_quantity == 0

    async def _settle_orders(self) -> None:
        for settled in await self.orders.on_bar():
            if settled.outcome != "rejected" and settled.status.status != ORDER_REJECTED:
                continue
            order = settled.working.order
            await self._alert(
                alerts.Alert(
                    event=alerts.ORDER_FAILED,
                    strategy=self.options.name,
                    ticker=self.options.bundle.ticker,
                    summary=(
                        f"{order.side} {order.quantity:g} {order.order_type} rejected by the broker"
                        + (f": {settled.status.message}" if settled.status.message else "")
                    ),
                    details=settled.as_dict(),
                )
            )

    async def _place(self, *, side: str, quantity: float, coid: str) -> None:
        """Record the intent, send the order, record the fill. Raises on broker failure."""
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

    async def _flatten(self) -> dict[str, Any]:
        """Close this strategy's position in its ticker with a market order.

        Only the runner's own ticker is touched; anything else in the account is
        not this strategy's to close. The order-size caps do not apply: they
        stop oversized entries, and must never stop an exit.
        """
        ticker = self.options.bundle.ticker
        outcome: dict[str, Any] = {"requested": True, "flattened": False, "orders": []}
        try:
            positions = await self.broker.get_positions()
        except Exception as exc:
            outcome["error"] = f"could not read positions: {exc}"
            return outcome
        held = [p for p in positions if p.symbol == ticker and p.quantity != 0]
        for pos in held:
            side = "SELL" if pos.quantity > 0 else "BUY"
            quantity = abs(float(pos.quantity))
            coid = hashlib.sha1(
                f"{self.options.name}|flatten|{datetime.now(UTC).isoformat()}|{side}|{quantity}".encode()
            ).hexdigest()[:16]
            order_row: dict[str, Any] = {"side": side, "quantity": quantity, "client_order_id": coid}
            outcome["orders"].append(order_row)
            try:
                await asyncio.wait_for(
                    self._place(side=side, quantity=quantity, coid=coid),
                    timeout=self.flatten_timeout_seconds,
                )
                order_row["status"] = "filled"
            except TimeoutError:
                order_row["status"] = "unconfirmed"
                outcome["error"] = (
                    f"no fill confirmed within {self.flatten_timeout_seconds:g}s; the order may "
                    "still be working at the broker, check TWS or the Gateway"
                )
            except Exception as exc:
                order_row["status"] = "failed"
                outcome["error"] = str(exc)
        outcome["flattened"] = all(row.get("status") == "filled" for row in outcome["orders"])
        logger.info("runner.flatten", strategy=self.options.name, **outcome)
        return outcome

    # ------------------------------------------------------------------
    # Heartbeat: stop requests, connection, guards
    # ------------------------------------------------------------------

    async def _heartbeat_loop(self) -> None:
        while not self.state.stop_event.is_set():
            try:
                await self.heartbeat()
            except Exception as exc:
                logger.exception("runner.heartbeat_failed", strategy=self.options.name, error=str(exc))
            try:
                await asyncio.wait_for(self.state.stop_event.wait(), timeout=self.heartbeat_seconds)
            except TimeoutError:
                pass

    async def heartbeat(self, now: datetime | None = None) -> None:
        """One heartbeat tick. Public so tests can drive it without waiting."""
        if self.state.stopping:
            return
        request = stop_request.read_stop_request(self.options.name)
        if request is not None:
            stop_request.clear_stop_request(self.options.name)
            await self.stop(flatten=bool(request.get("flatten")), reason="kill", write_result=True)
            return
        await self._check_connection(now or datetime.now(UTC))
        if self.state.triggered_guard is None and not self.state.stopping:
            await self._evaluate_guards()

    async def _check_connection(self, now: datetime) -> None:
        try:
            connected = await self.broker.is_connected()
        except Exception:
            connected = False

        if connected and not self.state.reconnecting:
            self.state.last_connected_at = now
            return

        # From here on we are recovering: the socket is down, or it is back but
        # the bar subscription it carried has not been renewed yet.
        if not self.state.reconnecting:
            self.state.reconnecting = True
            self.state.reconnect_attempt = 0
            self.state.next_reconnect_at = now
            self.state.disconnected_since = now
            logger.warning(
                "runner.disconnected",
                strategy=self.options.name,
                outage_expected=self._outage_expected(now),
            )
        if connected:
            self.state.last_connected_at = now
        if self.state.next_reconnect_at is not None and now < self.state.next_reconnect_at:
            return

        if not connected:
            try:
                await self.broker.connect()
                connected = await self.broker.is_connected()
                error = "" if connected else "broker reports not connected"
            except Exception as exc:
                error = str(exc)
            if not connected:
                self._schedule_reconnect(now, error)
                return

        self.state.last_connected_at = now
        try:
            await self.broker.subscribe_bars(self.options.bundle.ticker, self._on_bar)
        except Exception as exc:
            self._schedule_reconnect(now, f"re-subscribe failed: {exc}")
            return
        down_for = (now - self.state.disconnected_since).total_seconds() if self.state.disconnected_since else 0.0
        self.state.reconnecting = False
        self.state.reconnect_attempt = 0
        self.state.next_reconnect_at = None
        self.state.disconnected_since = None
        logger.info("runner.reconnected", strategy=self.options.name, down_seconds=round(down_for, 1))

    def _schedule_reconnect(self, now: datetime, error: str) -> None:
        delay = self.reconnect_policy.delay(self.state.reconnect_attempt)
        self.state.reconnect_attempt += 1
        self.state.next_reconnect_at = now + timedelta(seconds=delay)
        logger.warning(
            "runner.reconnect_failed",
            strategy=self.options.name,
            attempt=self.state.reconnect_attempt,
            retry_in_seconds=delay,
            error=error,
        )

    def _outage_expected(self, moment: datetime) -> bool:
        return self.restart_window is not None and self.restart_window.contains(moment)

    async def _evaluate_guards(self) -> None:
        if self.state.triggered_guard is not None or self.state.stopping:
            return
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
                "connected": not self.state.reconnecting,
                "working_orders": self.orders.snapshot(),
            },
            guard_state=guard_state,
            db_path=self.options.db_path,
        )
        triggered = guard_module.first_trigger(results)
        if triggered and self.state.triggered_guard is None:
            self.state.triggered_guard = triggered
            logger.warning(
                "runner.guard_triggered",
                strategy=self.options.name,
                guard=triggered.name,
                reason=triggered.reason,
            )
            await self.stop(
                reason=f"guard:{triggered.name}",
                alert=alerts.Alert(
                    event=alerts.GUARD_TRIGGERED,
                    strategy=self.options.name,
                    ticker=self.options.bundle.ticker,
                    summary=f"{triggered.name}: {triggered.reason}. Open orders cancelled, runner stopped.",
                    details={
                        "guard": triggered.name,
                        "reason": triggered.reason,
                        "equity": snapshot.account.equity,
                        "positions": [
                            {"symbol": p.symbol, "quantity": p.quantity} for p in snapshot.positions
                        ],
                    },
                ),
            )

    async def _snapshot(self) -> guard_module.RunnerSnapshot:
        try:
            account = await self.broker.get_account()
            positions = await self.broker.get_positions()
            self.state.last_account = account
            self.state.last_positions = positions
        except Exception:
            # Mid-outage the broker may not answer; the disconnect guard still
            # has to run, so fall back to the last readings.
            if self.state.last_account is None:
                raise
            account, positions = self.state.last_account, self.state.last_positions
        local_now = datetime.now(UTC)
        try:
            server_time = await self.broker.get_server_time()
        except Exception:
            server_time = local_now
        return guard_module.RunnerSnapshot(
            starting_equity=self.state.starting_equity,
            account=account,
            positions=positions,
            last_connected_at=self.state.last_connected_at,
            server_time=server_time,
            local_now=local_now,
            outage_expected=self._outage_expected(local_now),
        )

    async def _alert(self, alert: alerts.Alert) -> None:
        try:
            await self._alert_sink(alert)
        except Exception as exc:
            logger.warning("alert.sink_failed", alert_event=alert.event, error=str(exc))

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
    try:
        runner = PaperRunner(broker=broker, options=options)
    except UnsupportedLiveParams as exc:
        typer.echo(json.dumps(
            CliError(
                "unsupported_live_params",
                f"{exc}. Remove these keys from live_params of {name!r} in config/strategy_config.yaml, "
                "or set them to values the runner reproduces, before paper trading it.",
            ).as_dict()
            | {"keys": exc.problems}
        ))
        raise typer.Exit(code=2) from exc
    except ValueError as exc:
        typer.echo(json.dumps(CliError("invalid_live_params", f"{name!r}: {exc}").as_dict()))
        raise typer.Exit(code=2) from exc

    state_store.write_pid(name)
    stop_request.clear_stop_request(name)  # a request left by an earlier run is not for this one
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
                lambda: asyncio.create_task(runner.stop(reason="sigterm")),
            )
        except (NotImplementedError, OSError):
            pass  # Windows does not support add_signal_handler; sfa kill uses a stop request
        try:
            await runner.start()
            await runner.wait_until_done()
        except Exception as exc:
            await runner._alert(
                alerts.Alert(
                    event=alerts.RUNNER_CRASHED,
                    strategy=name,
                    ticker=bundle.ticker,
                    summary=f"{type(exc).__name__}: {exc}",
                )
            )
            raise
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


def _process_matches(pid: int, name: str) -> str:
    """``"runner"`` if ``pid`` is alive with this strategy on its command line,
    ``"gone"`` if no such process, ``"other"`` if alive but not provably ours."""
    import psutil

    try:
        cmdline = " ".join(psutil.Process(pid).cmdline())
    except psutil.NoSuchProcess:
        return "gone"
    except (psutil.AccessDenied, psutil.ZombieProcess):
        return "other"
    return "runner" if name in cmdline else "other"


def _terminate(pid: int) -> None:
    import psutil

    psutil.Process(pid).terminate()


def kill_cli(
    *,
    name: str,
    flatten: bool,
    json_output: bool,
    wait_seconds: float = 60.0,
    poll_seconds: float = 0.5,
    sleep: Callable[[float], None] = time.sleep,
    clock: Callable[[], float] = time.monotonic,
) -> None:
    """Ask the runner to stop through a stop request; terminate it only if it does not answer.

    Exit codes: 0 stopped (and flattened, if asked); 2 not running;
    3 could not stop it, or stopped but the position was not confirmed closed.
    """
    pid = state_store.read_pid(name)
    if pid is None:
        typer.echo(json.dumps(CliError("not_running", f"No running PID for {name!r}.").as_dict()))
        raise typer.Exit(code=2)

    stop_request.request_stop(name, flatten=flatten)
    runner_cfg = get_agent_config().get("runner") or {}
    heartbeat = float(runner_cfg.get("heartbeat_seconds", DEFAULT_HEARTBEAT_SECONDS))
    # A live runner consumes the request within one heartbeat. If it is still
    # there after a few, nobody is reading it: do not wait the full minute.
    unanswered_after = max(3 * heartbeat + 2.0, 5.0)
    started = clock()
    deadline = started + wait_seconds
    result: dict[str, Any] | None = None
    while clock() < deadline:
        result = stop_request.pop_stop_result(name)
        if result is not None:
            break
        if stop_request.stop_request_pending(name) and clock() - started > unanswered_after:
            break
        sleep(poll_seconds)

    payload: dict[str, Any] = {"strategy": name, "pid": pid}
    if result is not None:
        payload |= {"killed": True, "graceful": True, "flatten": result.get("flatten")}
    else:
        stop_request.clear_stop_request(name)
        match = _process_matches(pid, name)
        if match == "gone":
            state_store.remove_pid(name)
            state_store.clear_state(name)
            typer.echo(
                json.dumps(
                    CliError(
                        "not_running",
                        f"PID {pid} for {name!r} is no longer running; removed the stale PID file.",
                    ).as_dict()
                )
            )
            raise typer.Exit(code=2)
        if match == "other":
            # Never terminate a process we cannot tie to this strategy: the PID
            # may have been reused by something unrelated.
            typer.echo(
                json.dumps(
                    CliError(
                        "pid_mismatch",
                        f"PID {pid} is running, but not as the {name!r} runner, and it did not answer "
                        f"the stop request. Nothing was terminated; check {state_store.PID_DIR / (name + '.pid')}.",
                    ).as_dict()
                )
            )
            raise typer.Exit(code=3)
        try:
            _terminate(pid)
        except Exception as exc:
            typer.echo(json.dumps(CliError("kill_failed", str(exc)).as_dict()))
            raise typer.Exit(code=3) from exc
        payload |= {
            "killed": True,
            "graceful": False,
            "details": (
                "The runner did not answer the stop request and was terminated: open orders "
                "were not cancelled by the runner."
            ),
            "flatten": {
                "requested": flatten,
                "flattened": False if flatten else None,
                "orders": [],
                **({"error": "runner did not answer; the position was not closed"} if flatten else {}),
            },
        }

    state_store.remove_pid(name)
    state_store.clear_state(name)
    flatten_info = payload.get("flatten") or {}
    unconfirmed = flatten and flatten_info.get("flattened") is not True

    if json_output:
        typer.echo(json.dumps(payload, default=str))
    else:
        how = "cleanly" if payload["graceful"] else "by force (it did not answer)"
        line = f"Stopped {name} (pid {pid}) {how}."
        if flatten:
            orders = flatten_info.get("orders") or []
            if not unconfirmed:
                line += f" Position closed ({len(orders)} order{'s' if len(orders) != 1 else ''})." if orders else " No position to close."
            else:
                line += f" Position NOT confirmed closed: {flatten_info.get('error', 'unknown reason')}."
        typer.echo(line)
    if unconfirmed:
        raise typer.Exit(code=3)
