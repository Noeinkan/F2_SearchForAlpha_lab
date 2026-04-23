"""
Broker abstraction for the paper trading runner.

The Broker Protocol is the only seam between the runner and any execution
venue. IBBroker wraps ib_async for paper trading against an IB Gateway on the
loopback. MockBroker is a deterministic, in process broker used by tests; it
must be importable without ib_async installed, and it never opens a socket.

Important: ib_async is NOT imported at module load. Tests can import this file
freely without the dependency present at runtime.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any, Awaitable, Callable, Protocol, runtime_checkable


@dataclass(frozen=True)
class Bar:
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: float


@dataclass(frozen=True)
class Order:
    symbol: str
    side: str  # "BUY" or "SELL"
    quantity: float
    order_type: str = "MKT"
    limit_price: float | None = None


@dataclass(frozen=True)
class Fill:
    order: Order
    price: float
    quantity: float
    commission: float
    timestamp: datetime
    realised_pnl: float = 0.0


@dataclass(frozen=True)
class Position:
    symbol: str
    quantity: float
    avg_cost: float
    market_price: float

    @property
    def market_value(self) -> float:
        return self.quantity * self.market_price

    @property
    def unrealised_pnl(self) -> float:
        return (self.market_price - self.avg_cost) * self.quantity


@dataclass(frozen=True)
class AccountSnapshot:
    cash: float
    equity: float
    realised_pnl_today: float


BarHandler = Callable[[Bar], Awaitable[None]]


@runtime_checkable
class Broker(Protocol):
    """Minimal contract the runner needs from any execution venue."""

    async def connect(self) -> None: ...
    async def disconnect(self) -> None: ...
    async def is_connected(self) -> bool: ...
    async def get_server_time(self) -> datetime: ...
    async def get_positions(self) -> list[Position]: ...
    async def get_account(self) -> AccountSnapshot: ...
    async def submit_order(self, order: Order) -> Fill: ...
    async def cancel_all(self, symbol: str | None = None) -> None: ...
    async def subscribe_bars(self, symbol: str, on_bar: BarHandler) -> None: ...


# ---------------------------------------------------------------------------
# MockBroker: deterministic, in process, used exclusively in tests.
# ---------------------------------------------------------------------------


@dataclass
class MockBroker:
    """In process broker. Bars are pushed manually via push_bar() in tests.

    server_time tracks wall clock by default. Tests that need a frozen broker
    clock can set ``broker.frozen_server_time = some_datetime`` and that value
    will be returned instead. Bar timestamps do not influence server time.
    """

    starting_cash: float = 100_000.0
    commission_per_share: float = 0.0

    cash: float = field(init=False)
    positions: dict[str, Position] = field(init=False, default_factory=dict)
    fills: list[Fill] = field(init=False, default_factory=list)
    realised_pnl_today: float = field(init=False, default=0.0)
    last_price: dict[str, float] = field(init=False, default_factory=dict)
    frozen_server_time: datetime | None = field(init=False, default=None)
    _connected: bool = field(init=False, default=False)
    _bar_handlers: dict[str, list[BarHandler]] = field(init=False, default_factory=dict)

    def __post_init__(self) -> None:
        self.cash = float(self.starting_cash)

    async def connect(self) -> None:
        self._connected = True

    async def disconnect(self) -> None:
        self._connected = False

    async def is_connected(self) -> bool:
        return self._connected

    async def get_server_time(self) -> datetime:
        return self.frozen_server_time if self.frozen_server_time is not None else datetime.now(UTC)

    async def get_positions(self) -> list[Position]:
        out = []
        for sym, pos in self.positions.items():
            mkt = self.last_price.get(sym, pos.market_price)
            out.append(Position(symbol=sym, quantity=pos.quantity, avg_cost=pos.avg_cost, market_price=mkt))
        return out

    async def get_account(self) -> AccountSnapshot:
        equity = self.cash + sum(p.market_value for p in (await self.get_positions()))
        return AccountSnapshot(
            cash=self.cash,
            equity=equity,
            realised_pnl_today=self.realised_pnl_today,
        )

    async def submit_order(self, order: Order) -> Fill:
        if not self._connected:
            raise RuntimeError("MockBroker not connected")
        price = self.last_price.get(order.symbol)
        if price is None:
            raise RuntimeError(f"No market price for {order.symbol}; push a bar first")
        if order.order_type != "MKT":
            raise NotImplementedError("MockBroker only supports MKT orders")

        commission = float(order.quantity) * self.commission_per_share
        fill_qty = float(order.quantity)
        side = order.side.upper()
        existing = self.positions.get(order.symbol)

        if side == "BUY":
            cost = fill_qty * price + commission
            self.cash -= cost
            if existing:
                new_qty = existing.quantity + fill_qty
                new_avg = (existing.avg_cost * existing.quantity + price * fill_qty) / new_qty if new_qty else 0.0
                self.positions[order.symbol] = Position(order.symbol, new_qty, new_avg, price)
            else:
                self.positions[order.symbol] = Position(order.symbol, fill_qty, price, price)
            realised = 0.0
        elif side == "SELL":
            if not existing or existing.quantity < fill_qty:
                raise RuntimeError(f"Cannot sell {fill_qty} of {order.symbol}: insufficient position")
            proceeds = fill_qty * price - commission
            self.cash += proceeds
            realised = (price - existing.avg_cost) * fill_qty
            self.realised_pnl_today += realised
            new_qty = existing.quantity - fill_qty
            if new_qty == 0:
                del self.positions[order.symbol]
            else:
                self.positions[order.symbol] = Position(order.symbol, new_qty, existing.avg_cost, price)
        else:
            raise ValueError(f"Unknown order side {order.side!r}")

        fill = Fill(
            order=order,
            price=price,
            quantity=fill_qty,
            commission=commission,
            timestamp=self.frozen_server_time or datetime.now(UTC),
            realised_pnl=realised,
        )
        self.fills.append(fill)
        return fill

    async def cancel_all(self, symbol: str | None = None) -> None:
        # MockBroker has no resting orders; nothing to cancel.
        return

    async def subscribe_bars(self, symbol: str, on_bar: BarHandler) -> None:
        self._bar_handlers.setdefault(symbol, []).append(on_bar)

    async def push_bar(self, symbol: str, bar: Bar) -> None:
        """Simulate a market data tick. Updates last_price and dispatches to handlers.

        Does not touch server time; bar timestamps and broker server time are
        independent in the mock so the clock drift guard stays predictable.
        """
        self.last_price[symbol] = bar.close
        for handler in list(self._bar_handlers.get(symbol, [])):
            await handler(bar)


# ---------------------------------------------------------------------------
# IBBroker: real ib_async wrapper. Imports ib_async lazily.
# ---------------------------------------------------------------------------


class IBBroker:
    """Wraps ib_async for paper trading. Lazy imports keep tests free of ib_async."""

    def __init__(self, host: str = "127.0.0.1", port: int = 4002, client_id: int = 7) -> None:
        self.host = host
        self.port = port
        self.client_id = client_id
        self._ib: Any = None

    def _ensure_ib(self) -> Any:
        if self._ib is None:
            from ib_async import IB  # type: ignore

            self._ib = IB()
        return self._ib

    async def connect(self) -> None:
        ib = self._ensure_ib()
        await ib.connectAsync(self.host, self.port, clientId=self.client_id, readonly=False)

    async def disconnect(self) -> None:
        if self._ib is not None:
            self._ib.disconnect()

    async def is_connected(self) -> bool:
        return bool(self._ib and self._ib.isConnected())

    async def get_server_time(self) -> datetime:
        ib = self._ensure_ib()
        return await ib.reqCurrentTimeAsync()

    async def get_positions(self) -> list[Position]:
        ib = self._ensure_ib()
        out = []
        for p in ib.positions():
            out.append(
                Position(
                    symbol=p.contract.symbol,
                    quantity=float(p.position),
                    avg_cost=float(p.avgCost),
                    market_price=float(p.marketPrice or 0.0),
                )
            )
        return out

    async def get_account(self) -> AccountSnapshot:
        ib = self._ensure_ib()
        summary = {item.tag: item.value for item in ib.accountSummary()}
        return AccountSnapshot(
            cash=float(summary.get("TotalCashValue", 0.0)),
            equity=float(summary.get("NetLiquidation", 0.0)),
            realised_pnl_today=float(summary.get("RealizedPnL", 0.0)),
        )

    async def submit_order(self, order: Order) -> Fill:
        from ib_async import MarketOrder, Stock  # type: ignore

        ib = self._ensure_ib()
        contract = Stock(order.symbol, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)
        ib_order = MarketOrder(order.side.upper(), abs(float(order.quantity)))
        trade = ib.placeOrder(contract, ib_order)
        while not trade.isDone():
            await ib.waitOnUpdate(timeout=1)
        last_fill = trade.fills[-1] if trade.fills else None
        if last_fill is None:
            raise RuntimeError("Order placed but no fill received")
        return Fill(
            order=order,
            price=float(last_fill.execution.price),
            quantity=float(last_fill.execution.shares),
            commission=float(last_fill.commissionReport.commission or 0.0),
            timestamp=datetime.now(UTC),
            realised_pnl=float(last_fill.commissionReport.realizedPNL or 0.0),
        )

    async def cancel_all(self, symbol: str | None = None) -> None:
        ib = self._ensure_ib()
        for trade in ib.openTrades():
            if symbol and trade.contract.symbol != symbol:
                continue
            ib.cancelOrder(trade.order)

    async def subscribe_bars(self, symbol: str, on_bar: BarHandler) -> None:
        from ib_async import Stock  # type: ignore

        ib = self._ensure_ib()
        contract = Stock(symbol, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)
        bars = ib.reqRealTimeBars(contract, 5, "TRADES", False)

        def _on_update(updated_bars: Any, has_new_bar: bool) -> None:
            if not has_new_bar:
                return
            last = updated_bars[-1]
            bar = Bar(
                timestamp=last.time,
                open=float(last.open_),
                high=float(last.high),
                low=float(last.low),
                close=float(last.close),
                volume=float(last.volume),
            )
            ib.loop.create_task(on_bar(bar))

        bars.updateEvent += _on_update
