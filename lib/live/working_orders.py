"""
The paper runner's resting orders, from placement to the end of their life.

A market order is sent and waited for (``Broker.submit_order``). A limit, stop
or stop-limit order may wait in the market for many bars, so it cannot hold up
the bar loop: it is placed (``Broker.place_order``), remembered here, and looked
at again on every bar the runner receives. Each order ends in exactly one way,
and that ending is written to ``sfa_fills``:

    filled            the broker filled it
    partially_filled  some shares traded, then it was cancelled or rejected
    cancelled         nothing traded; ``why`` says who ended it:
                        ioc       one bar of range went by (time_in_force: ioc)
                        expired   order_expiry_bars went by
                        replaced  a new signal on the same side took its place
                        stopped   the runner stopped
    rejected          the broker refused it

At most one order per side works at a time, as in the backtest, where a new
signal cancels the working order on its side (``submit_signal_order``).
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import structlog

from lib.live.broker import (
    ORDER_CANCELLED,
    ORDER_FILLED,
    ORDER_REJECTED,
    Broker,
    Order,
    OrderStatus,
)
from lib.live.execution import LiveOrderModel
from lib.store import fills as fills_store

logger = structlog.get_logger(__name__)


@dataclass
class WorkingOrder:
    client_order_id: str
    broker_order_id: str
    order: Order
    bars_seen: int = 0

    @property
    def side(self) -> str:
        return self.order.side

    def as_dict(self) -> dict[str, Any]:
        return {
            "side": self.order.side,
            "quantity": self.order.quantity,
            "order_type": self.order.order_type,
            "limit_price": self.order.limit_price,
            "stop_price": self.order.stop_price,
            "time_in_force": self.order.time_in_force,
            "bars_seen": self.bars_seen,
            "client_order_id": self.client_order_id,
            "broker_order_id": self.broker_order_id,
        }


@dataclass(frozen=True)
class Settled:
    """How one working order ended."""

    working: WorkingOrder
    status: OrderStatus
    outcome: str  # filled | partially_filled | cancelled | rejected
    why: str

    def as_dict(self) -> dict[str, Any]:
        return self.working.as_dict() | {
            "outcome": self.outcome,
            "why": self.why,
            "filled_quantity": self.status.filled_quantity,
            "avg_fill_price": self.status.avg_fill_price,
        }


class WorkingOrders:
    def __init__(
        self,
        broker: Broker,
        model: LiveOrderModel,
        *,
        strategy: str,
        symbol: str,
        db_path: Path | None = None,
        cancel_confirm_seconds: float = 5.0,
    ) -> None:
        self.broker = broker
        self.model = model
        self.strategy = strategy
        self.symbol = symbol
        self.db_path = db_path
        self.cancel_confirm_seconds = cancel_confirm_seconds
        self._by_side: dict[str, WorkingOrder] = {}

    def get(self, side: str) -> WorkingOrder | None:
        return self._by_side.get(side.upper())

    def snapshot(self) -> list[dict[str, Any]]:
        return [w.as_dict() for w in self._by_side.values()]

    def __len__(self) -> int:
        return len(self._by_side)

    async def place(self, *, side: str, quantity: float, close: float, client_order_id: str) -> WorkingOrder:
        """Record the intent, rest the order at the broker, remember it. Raises on broker failure."""
        side = side.upper()
        existing = self._by_side.get(side)
        if existing is not None and existing.client_order_id == client_order_id:
            return existing  # the same bar's order, offered twice
        order = self.model.broker_order(
            symbol=self.symbol, side=side, quantity=quantity, close=close, client_order_id=client_order_id
        )
        fills_store.record_intent(
            self.strategy, self.symbol, side, quantity, client_order_id,
            db_path=self.db_path, order_type=self.model.order_type,
        )
        broker_order_id = await self.broker.place_order(order)
        fills_store.mark_working(client_order_id, broker_order_id, db_path=self.db_path)
        working = WorkingOrder(client_order_id, broker_order_id, order)
        self._by_side[side] = working
        logger.info("runner.order_working", strategy=self.strategy, **working.as_dict())
        return working

    async def on_bar(self) -> list[Settled]:
        """Count one bar against every working order; settle the finished, cancel the expired."""
        settled: list[Settled] = []
        cancel_after = self.model.cancel_after_bars
        for side, working in list(self._by_side.items()):
            working.bars_seen += 1
            try:
                status = await self.broker.order_status(working.broker_order_id)
            except Exception as exc:
                logger.warning("runner.order_status_failed", strategy=self.strategy, side=side, error=str(exc))
                continue
            if status.done:
                settled.append(self._settle(working, status, why=status.status))
            elif cancel_after is not None and working.bars_seen >= cancel_after:
                # ioc allows one bar, which no expiry can undercut.
                why = "ioc" if self.model.time_in_force == "ioc" else "expired"
                result = await self.cancel(side, why=why)
                if result is not None:
                    settled.append(result)
        return settled

    async def cancel(self, side: str, *, why: str) -> Settled | None:
        """Cancel the working order on ``side`` and settle it.

        Returns None when there is none, or when the broker has not confirmed the
        cancel in time; the order then stays tracked and settles on a later bar.
        """
        working = self._by_side.get(side.upper())
        if working is None:
            return None
        try:
            await self.broker.cancel_order(working.broker_order_id)
        except Exception as exc:
            logger.warning("runner.cancel_order_failed", strategy=self.strategy, side=side, error=str(exc))
        status = await self._await_done(working.broker_order_id)
        if status is None or not status.done:
            logger.warning(
                "runner.cancel_unconfirmed", strategy=self.strategy, side=side, why=why,
                broker_order_id=working.broker_order_id,
            )
            return None
        return self._settle(working, status, why=why if status.status == ORDER_CANCELLED else status.status)

    async def cancel_all(self, *, why: str) -> list[Settled]:
        settled = []
        for side in list(self._by_side):
            result = await self.cancel(side, why=why)
            if result is not None:
                settled.append(result)
        return settled

    async def _await_done(self, broker_order_id: str) -> OrderStatus | None:
        loop = asyncio.get_running_loop()
        deadline = loop.time() + self.cancel_confirm_seconds
        status: OrderStatus | None = None
        while True:
            try:
                status = await self.broker.order_status(broker_order_id)
            except Exception:
                status = None
            if (status is not None and status.done) or loop.time() >= deadline:
                return status
            await asyncio.sleep(0.1)

    def _settle(self, working: WorkingOrder, status: OrderStatus, *, why: str) -> Settled:
        self._by_side.pop(working.side, None)
        traded = status.filled_quantity
        if status.status == ORDER_FILLED:
            outcome = "filled"
        elif traded > 0:
            outcome = "partially_filled"
        elif status.status == ORDER_REJECTED:
            outcome = "rejected"
        else:
            outcome = "cancelled"
        fills_store.mark_closed(
            working.client_order_id,
            status=outcome,
            quantity=traded if traded > 0 else None,
            price=status.avg_fill_price,
            commission=status.commission,
            realised_pnl=status.realised_pnl if traded > 0 else None,
            db_path=self.db_path,
        )
        result = Settled(working, status, outcome, why)
        logger.info("runner.order_settled", strategy=self.strategy, **result.as_dict())
        return result
