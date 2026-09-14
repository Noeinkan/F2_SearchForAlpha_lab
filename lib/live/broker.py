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

import structlog

_logger = structlog.get_logger(__name__)

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
    order_type: str = "MKT"  # IB vocabulary: MKT, LMT, STP, STP LMT
    limit_price: float | None = None
    client_order_id: str | None = None
    stop_price: float | None = None
    time_in_force: str = "DAY"  # GTC or DAY


ORDER_WORKING = "working"
ORDER_FILLED = "filled"
ORDER_CANCELLED = "cancelled"
ORDER_REJECTED = "rejected"


@dataclass(frozen=True)
class OrderStatus:
    """Where a placed order stands. ``filled_quantity`` can be above zero on a
    working or cancelled order: that is a partial fill."""

    order_id: str
    status: str
    filled_quantity: float = 0.0
    avg_fill_price: float = 0.0
    commission: float = 0.0
    realised_pnl: float = 0.0
    message: str = ""

    @property
    def done(self) -> bool:
        return self.status != ORDER_WORKING


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

# IB order type -> lib.orders order type, for the mock's fill model.
_BOOK_ORDER_TYPES = {"LMT": "limit", "STP": "stop", "STP LMT": "stop_limit"}


def _ib_number(value: Any) -> float:
    """IB marks "no value" with the largest double (e.g. realised PnL on an
    opening fill); read that, and None, as 0."""
    try:
        number = float(value or 0.0)
    except (TypeError, ValueError):
        return 0.0
    return 0.0 if abs(number) > 1e300 else number


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
    # Resting orders: place returns at once with the broker's order id; the
    # runner polls the status and cancels when the order has run out of time.
    async def place_order(self, order: Order) -> str: ...
    async def order_status(self, order_id: str) -> OrderStatus: ...
    async def cancel_order(self, order_id: str) -> None: ...
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
    _books: dict[str, Any] = field(init=False, default_factory=dict)
    _resting: dict[str, tuple[Order, Any]] = field(init=False, default_factory=dict)
    _statuses: dict[str, OrderStatus] = field(init=False, default_factory=dict)
    _order_seq: int = field(init=False, default=0)
    _bar_seq: int = field(init=False, default=0)

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
            raise NotImplementedError("submit_order waits for a fill; rest other order types with place_order")
        return self._execute(order, price)

    async def place_order(self, order: Order) -> str:
        """Rest an order. A MKT order fills on the spot at the last price.

        Resting orders are worked against each later bar with the backtest's
        fill model (lib.orders.fill_price and the priority rule), so a paper run
        against this mock fills exactly where a backtest would.
        """
        if not self._connected:
            raise RuntimeError("MockBroker not connected")
        self._order_seq += 1
        order_id = f"mock-{self._order_seq}"
        if order.order_type == "MKT":
            fill = await self.submit_order(order)
            self._statuses[order_id] = OrderStatus(
                order_id, ORDER_FILLED, fill.quantity, fill.price, fill.commission, fill.realised_pnl
            )
            return order_id

        from lib.orders import Order as BookOrder
        from lib.orders import OrderBook, OrderError

        book_type = _BOOK_ORDER_TYPES.get(order.order_type)
        try:
            if book_type is None:
                raise OrderError(f"unsupported order type {order.order_type!r}")
            book_order = BookOrder(
                side=order.side.lower(),
                order_type=book_type,
                qty=float(order.quantity),
                limit_price=order.limit_price,
                stop_price=order.stop_price,
            )
        except OrderError as exc:
            self._statuses[order_id] = OrderStatus(order_id, ORDER_REJECTED, message=str(exc))
            return order_id
        self._books.setdefault(order.symbol, OrderBook()).submit(book_order)
        self._resting[order_id] = (order, book_order)
        self._statuses[order_id] = OrderStatus(order_id, ORDER_WORKING)
        return order_id

    async def order_status(self, order_id: str) -> OrderStatus:
        try:
            return self._statuses[order_id]
        except KeyError:
            raise RuntimeError(f"Unknown order id {order_id!r}") from None

    async def cancel_order(self, order_id: str) -> None:
        entry = self._resting.pop(order_id, None)
        if entry is None:
            return
        order, book_order = entry
        self._books[order.symbol].cancel(book_order)
        self._statuses[order_id] = OrderStatus(order_id, ORDER_CANCELLED)

    def _work_resting(self, symbol: str, bar: Bar) -> None:
        book = self._books.get(symbol)
        if book is None or book.is_empty:
            return
        from lib.orders import Bar as BookBar

        self._bar_seq += 1
        book_bar = BookBar(
            index=self._bar_seq,
            open=bar.open,
            high=max(bar.high, bar.open, bar.close),
            low=min(bar.low, bar.open, bar.close),
            close=bar.close,
        )
        ids = {id(book_order): oid for oid, (_, book_order) in self._resting.items()}
        for book_order, price in book.candidates(book_bar):
            if book_order not in book:
                continue
            order_id = ids[id(book_order)]
            order, _ = self._resting.pop(order_id)
            try:
                fill = self._execute(order, price)
            except RuntimeError as exc:  # e.g. a sell for more than is held
                book.cancel(book_order, "rejected")
                self._statuses[order_id] = OrderStatus(order_id, ORDER_REJECTED, message=str(exc))
                continue
            book.fill(book_order, book_bar, fill.quantity, price)
            self._statuses[order_id] = OrderStatus(
                order_id, ORDER_FILLED, fill.quantity, fill.price, fill.commission, fill.realised_pnl
            )
        book.arm_triggered(book_bar)

    def _execute(self, order: Order, price: float) -> Fill:
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
        for order_id, (order, _) in list(self._resting.items()):
            if symbol is None or order.symbol == symbol:
                await self.cancel_order(order_id)

    async def subscribe_bars(self, symbol: str, on_bar: BarHandler) -> None:
        # Idempotent, like IBBroker: the runner re-subscribes after a reconnect
        # and must not end up handling every bar twice.
        handlers = self._bar_handlers.setdefault(symbol, [])
        if on_bar not in handlers:
            handlers.append(on_bar)

    async def push_bar(self, symbol: str, bar: Bar) -> None:
        """Simulate a market data tick. Updates last_price and dispatches to handlers.

        Does not touch server time; bar timestamps and broker server time are
        independent in the mock so the clock drift guard stays predictable.

        Resting orders are worked against the bar *before* the handlers see it:
        an order placed while handling one bar first trades on the next, as in
        the backtest.
        """
        self._work_resting(symbol, bar)
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
        self._bar_queues: dict[str, Any] = {}
        self._bar_tasks: dict[str, Any] = {}
        self._bar_subs: dict[str, tuple[Any, Any]] = {}
        self._trades: dict[str, Any] = {}

    def _ensure_ib(self) -> Any:
        if self._ib is None:
            from ib_async import IB  # type: ignore

            self._ib = IB()
        return self._ib

    async def connect(self) -> None:
        """Connect, or reconnect after the Gateway dropped us. No-op when connected."""
        ib = self._ensure_ib()
        if ib.isConnected():
            return
        # ib_async resets its session state when the socket drops, so the same
        # IB object reconnects cleanly after a Gateway restart.
        await ib.connectAsync(self.host, self.port, clientId=self.client_id, readonly=False)

    async def disconnect(self) -> None:
        import asyncio as _asyncio

        current = _asyncio.current_task()
        for task in self._bar_tasks.values():
            # The runner can stop from inside a bar handler; cancelling that
            # task would abort the stop half-way.
            if task is not current:
                task.cancel()
        self._bar_tasks.clear()
        self._bar_subs.clear()
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
        if order.client_order_id:
            ib_order.orderRef = order.client_order_id
        trade = ib.placeOrder(contract, ib_order)
        while not trade.isDone():
            if not ib.isConnected():
                # Without this the loop polls a dead socket forever and the
                # runner never gets to its next bar or guard check.
                raise ConnectionError(
                    f"Disconnected from IB Gateway before {order.client_order_id or 'the order'} completed"
                )
            await ib.waitOnUpdate(timeout=1)
        last_fill = trade.fills[-1] if trade.fills else None
        if last_fill is None:
            raise RuntimeError("Order placed but no fill received")
        return Fill(
            order=order,
            price=float(last_fill.execution.price),
            quantity=float(last_fill.execution.shares),
            commission=_ib_number(last_fill.commissionReport.commission),
            timestamp=datetime.now(UTC),
            realised_pnl=_ib_number(last_fill.commissionReport.realizedPNL),
        )

    async def place_order(self, order: Order) -> str:
        from ib_async import LimitOrder, MarketOrder, Stock, StopLimitOrder, StopOrder  # type: ignore

        ib = self._ensure_ib()
        contract = Stock(order.symbol, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)
        action, qty = order.side.upper(), abs(float(order.quantity))
        kind, limit, stop = order.order_type, order.limit_price, order.stop_price
        ib_order: Any
        if kind == "MKT":
            ib_order = MarketOrder(action, qty)
        elif kind == "LMT" and limit is not None:
            ib_order = LimitOrder(action, qty, float(limit))
        elif kind == "STP" and stop is not None:
            ib_order = StopOrder(action, qty, float(stop))
        elif kind == "STP LMT" and limit is not None and stop is not None:
            ib_order = StopLimitOrder(action, qty, float(limit), float(stop))
        else:
            raise ValueError(f"Order type {kind!r} is unsupported or missing its price: {order}")
        ib_order.tif = order.time_in_force
        if order.client_order_id:
            ib_order.orderRef = order.client_order_id
        trade = ib.placeOrder(contract, ib_order)
        order_id = str(trade.order.orderId)
        self._trades[order_id] = trade
        return order_id

    def _find_trade(self, order_id: str) -> Any:
        ib = self._ensure_ib()
        # After a Gateway restart ib_async rebuilds its Trade objects from the
        # open and completed orders it fetches on connect; prefer those to the
        # object kept from before the drop.
        for trade in ib.trades():
            if str(trade.order.orderId) == order_id:
                self._trades[order_id] = trade
                return trade
        return self._trades.get(order_id)

    async def order_status(self, order_id: str) -> OrderStatus:
        trade = self._find_trade(order_id)
        if trade is None:
            raise RuntimeError(f"Unknown order id {order_id!r}")
        state = trade.orderStatus.status
        if state == "Filled":
            status = ORDER_FILLED
        elif state in ("Cancelled", "ApiCancelled"):
            status = ORDER_CANCELLED
        elif state == "Inactive":
            status = ORDER_REJECTED
        else:
            status = ORDER_WORKING
        reports = [f.commissionReport for f in trade.fills if f.commissionReport]
        message = " ".join(str(entry.message) for entry in trade.log if entry.message)
        return OrderStatus(
            order_id=order_id,
            status=status,
            filled_quantity=float(trade.orderStatus.filled or 0.0),
            avg_fill_price=float(trade.orderStatus.avgFillPrice or 0.0),
            commission=sum(_ib_number(r.commission) for r in reports),
            realised_pnl=sum(_ib_number(r.realizedPNL) for r in reports),
            message=message,
        )

    async def cancel_order(self, order_id: str) -> None:
        trade = self._find_trade(order_id)
        if trade is None or trade.isDone():
            return
        self._ensure_ib().cancelOrder(trade.order)

    async def cancel_all(self, symbol: str | None = None) -> None:
        ib = self._ensure_ib()
        for trade in ib.openTrades():
            if symbol and trade.contract.symbol != symbol:
                continue
            ib.cancelOrder(trade.order)

    async def subscribe_bars(self, symbol: str, on_bar: BarHandler) -> None:
        """Subscribe to 5-second bars. Calling it again replaces the old subscription.

        The runner calls it again after every reconnect: the Gateway forgets
        real-time bar subscriptions when it restarts, and ib_async does not
        renew them.
        """
        import asyncio as _asyncio
        from ib_async import Stock  # type: ignore

        ib = self._ensure_ib()
        self._drop_subscription(symbol)
        contract = Stock(symbol, "SMART", "USD")
        await ib.qualifyContractsAsync(contract)
        bars = ib.reqRealTimeBars(contract, 5, "TRADES", False)

        queue: _asyncio.Queue = _asyncio.Queue()
        self._bar_queues[symbol] = queue

        async def _consumer() -> None:
            while True:
                bar = await queue.get()
                try:
                    await on_bar(bar)
                except Exception as exc:
                    # One failed bar must not end the stream: an uncaught error
                    # here used to kill this task and the runner went deaf.
                    _logger.exception("broker.bar_handler_failed", symbol=symbol, error=str(exc))
                finally:
                    queue.task_done()

        loop = _asyncio.get_event_loop()
        task = loop.create_task(_consumer())
        self._bar_tasks[symbol] = task

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
            loop.call_soon_threadsafe(queue.put_nowait, bar)

        bars.updateEvent += _on_update
        self._bar_subs[symbol] = (bars, _on_update)

    def _drop_subscription(self, symbol: str) -> None:
        import asyncio as _asyncio

        task = self._bar_tasks.pop(symbol, None)
        if task is not None and task is not _asyncio.current_task():
            task.cancel()
        sub = self._bar_subs.pop(symbol, None)
        if sub is None:
            return
        bars, handler = sub
        try:
            bars.updateEvent -= handler
        except Exception:
            pass
        if self._ib is not None and self._ib.isConnected():
            try:
                self._ib.cancelRealTimeBars(bars)
            except Exception:
                pass  # the Gateway restarted and no longer knows this request
