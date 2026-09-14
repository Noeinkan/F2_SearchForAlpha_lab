"""
Orders, fills and the resting-order book.

Until this module existed the engine had no order abstraction at all: every
decision in :mod:`lib.strategy` turned straight into a fill at the bar's close,
and the only nod to intrabar reality was a bespoke branch that compared the
trailing stop against ``Low``. This module is that missing layer — a small,
pure, engine-agnostic description of *what was asked for* (:class:`Order`),
*what happened* (:class:`Fill`), and *which resting orders a bar touches*
(:class:`OrderBook`).

Nothing here mutates portfolio state, sizes a position or knows about cash.
:mod:`lib.strategy` owns all of that; the book only answers "given this bar's
open/high/low/close, which of these resting orders would have traded, at what
price, and in what order?".

Fill model
----------
The bar is the finest resolution we have, so every rule below is a stated
assumption about a path we cannot see, not a fact:

``market``
    Fills at the bar's ``Close``. This is what the engine did for everything
    before order types existed, and it is unchanged.

``limit``
    A buy limit at ``L`` fills when the bar trades at or below ``L``. If the bar
    *opens* at or below ``L`` the fill is at the **open** — you cannot be filled
    worse than the first price at which your resting order was marketable, and
    the price improvement is real. Otherwise the fill is at ``L`` exactly. Sell
    limits mirror this against ``High``.

``stop``
    A sell stop at ``S`` triggers when the bar trades at or below ``S`` and
    becomes a market order. Opening at or below ``S`` means the market gapped
    through it, so the fill is at the **open** — the first price anyone could
    trade. Otherwise the fill is at ``S``. Buy stops mirror this against
    ``High``. This is the generalisation of the old low-based trailing-stop
    check, which special-cased the session-open gap and otherwise charged the
    close.

``stop_limit``
    The stop arms exactly as above, then a limit at ``limit_price`` is worked
    for the rest of the bar. If the trigger price is already acceptable to the
    limit, that is the fill. If it is not — the classic "gapped past my limit"
    case — the order does *not* fill at a worse price; it stays resting as a
    plain limit (``triggered`` set) and can fill on this or any later bar if the
    range comes back to it. That is the whole point of a stop-limit, and the
    reason it can leave you in a position a plain stop would have exited.

Slippage and fees are the engine's business and are applied on top of these
prices, exactly as they are for market fills.

Priority when a bar touches more than one order
-----------------------------------------------
A bar can touch a bracket's stop *and* its target. Which one filled first is
unknowable from OHLC alone, so :meth:`OrderBook.candidates` sorts on a stated,
deterministic and deliberately pessimistic rule (see :data:`PRIORITY_RULE`):

1. **Orders marketable at the open fill first.** The open is the only price we
   know came first. Among these, ties break by rule 2 then 3.
2. **Adverse before favourable.** Stop-type orders rank ahead of limit-type
   ones. For a long position that means the bracket's stop is assumed to have
   filled before its target, so an ambiguous bar is scored as a loss. Ranking
   the profitable leg first would make every wide bracket look free.
3. **Nearest the open first**, then by submission order (``order_id``), so the
   sequence is stable across runs and platforms.

The engine applies candidates in that order and stops as soon as the position
can absorb no more; :meth:`OrderBook.fill` cancels the rest of a filled order's
OCO group, which is what makes a bracket a bracket.

Time in force
-------------
``gtc``
    Rests until it fills or is cancelled.
``day``
    Cancelled at the first bar of a new session. On a daily tape every bar
    starts a session, so ``day`` means "this bar only" — which is the honest
    reading, not a bug.
``ioc``
    Fills on the bar it is first worked, or is cancelled. Combined with the
    engine's signal lag this is "try once, at the next bar's range".

``expire_bars`` layers a hard age cap on top of any of them: an order older
than ``expire_bars`` bars is cancelled before the bar is worked. ``None`` or
``0`` disables it.
"""

from __future__ import annotations

import itertools
from dataclasses import dataclass, field
from typing import Iterable, Iterator, List, Optional, Sequence, Tuple

import numpy as np

# Order types the book understands, in the order they were added to the engine.
ORDER_TYPES = ('market', 'limit', 'stop', 'stop_limit')

# Types that rest in the book waiting for the market to come to them. A market
# order never rests: the engine fills it on the bar it is created.
RESTING_ORDER_TYPES = ('limit', 'stop', 'stop_limit')

SIDES = ('buy', 'sell')

TIME_IN_FORCE = ('gtc', 'day', 'ioc')

# Why an order exists. Mirrors (and extends) the ledger's exit vocabulary so a
# fill can be traced back to the decision that placed it.
ORDER_REASONS = (
    'signal',
    'trailing_stop',
    'take_profit',
    'bracket_stop',
    'bracket_target',
)

# One-line statement of the multi-touch rule, quoted by the UI and the docs so
# there is exactly one wording of it.
PRIORITY_RULE = (
    "open-marketable first, then stops before limits, then nearest the open — "
    "an ambiguous bar is scored against the position"
)

_ORDER_IDS = itertools.count(1)


class OrderError(ValueError):
    """An order was described in a way the book cannot work."""


def reset_order_ids() -> None:
    """Restart the order-id counter.

    Ids are only ever used to break ties deterministically *within* one book,
    so a global counter is harmless — but tests that assert on ids want a fixed
    starting point, and :class:`OrderBook` calls this when it is constructed
    with ``reset_ids=True``.
    """
    global _ORDER_IDS
    _ORDER_IDS = itertools.count(1)


@dataclass(frozen=True)
class Bar:
    """The four prices a bar can be filled against, plus where it sits.

    ``session_start`` matters because a gap through a resting order is only a
    gap when the market was shut; :mod:`lib.sessions` decides that, not this
    module. ``high`` and ``low`` fall back to the open/close range when a frame
    has no High/Low columns, which keeps a signals-only frame runnable instead
    of raising halfway through a backtest.
    """

    index: int
    open: float
    high: float
    low: float
    close: float
    session_start: bool = False
    session_id: int = 0

    @classmethod
    def from_arrays(
        cls,
        index: int,
        close: Sequence[float],
        open_: Optional[Sequence[float]] = None,
        high: Optional[Sequence[float]] = None,
        low: Optional[Sequence[float]] = None,
        session_start: Optional[Sequence[bool]] = None,
        session_id: Optional[Sequence[int]] = None,
    ) -> "Bar":
        """Build a bar from the engine's parallel price arrays."""
        close_price = float(close[index])
        open_price = float(open_[index]) if open_ is not None else close_price
        if not np.isfinite(open_price):
            open_price = close_price
        high_price = float(high[index]) if high is not None else max(open_price, close_price)
        low_price = float(low[index]) if low is not None else min(open_price, close_price)
        if not np.isfinite(high_price):
            high_price = max(open_price, close_price)
        if not np.isfinite(low_price):
            low_price = min(open_price, close_price)
        # A frame can carry a High below its Close (bad vendor data, or a
        # synthetic tape built by multiplying the close). Widen rather than
        # raise: an order the bar demonstrably reached should still fill.
        high_price = max(high_price, open_price, close_price)
        low_price = min(low_price, open_price, close_price)
        return cls(
            index=index,
            open=open_price,
            high=high_price,
            low=low_price,
            close=close_price,
            session_start=bool(session_start[index]) if session_start is not None else False,
            session_id=int(session_id[index]) if session_id is not None else 0,
        )


@dataclass
class Order:
    """An instruction to trade, resting until the market reaches it.

    ``qty`` is a share count fixed at submission. It is *not* re-sized when the
    order finally fills: the engine clamps it to the cash or the units actually
    available at fill time, which is the same clamp a market order gets. A
    ``qty`` of ``None`` means "whatever the position holds when this fills" and
    is what exit brackets and trailing stops use.
    """

    side: str
    order_type: str = 'market'
    qty: Optional[float] = None
    limit_price: Optional[float] = None
    stop_price: Optional[float] = None
    tif: str = 'gtc'
    expire_bars: Optional[int] = None
    reason: str = 'signal'
    group: Optional[str] = None
    created_bar: int = 0
    created_session: int = 0
    # Set once a stop-limit's stop has been hit; from then on it is a plain
    # limit and must not re-arm off a later bar's range.
    triggered: bool = False
    # How many bars the order has been offered to, and the session it was first
    # offered in. Both are the book's bookkeeping, not the caller's: an order is
    # placed *after* its bar has closed, so the first bar it can trade against
    # is the next one, and every time-in-force rule counts from there.
    bars_worked: int = 0
    first_session: Optional[int] = None
    order_id: int = field(default_factory=lambda: next(_ORDER_IDS))

    def __post_init__(self) -> None:
        if self.side not in SIDES:
            raise OrderError(f"Unknown order side: {self.side!r}. Available: {', '.join(SIDES)}")
        if self.order_type not in ORDER_TYPES:
            raise OrderError(
                f"Unknown order type: {self.order_type!r}. Available: {', '.join(ORDER_TYPES)}"
            )
        if self.tif not in TIME_IN_FORCE:
            raise OrderError(
                f"Unknown time in force: {self.tif!r}. Available: {', '.join(TIME_IN_FORCE)}"
            )
        if self.order_type in ('limit', 'stop_limit') and self.limit_price is None:
            raise OrderError(f"{self.order_type} order needs a limit_price")
        if self.order_type in ('stop', 'stop_limit') and self.stop_price is None:
            raise OrderError(f"{self.order_type} order needs a stop_price")
        if self.qty is not None and self.qty <= 0:
            raise OrderError(f"Order qty must be positive or None, got {self.qty!r}")

    @property
    def rests(self) -> bool:
        """True when the order waits in the book rather than filling on sight."""
        return self.order_type in RESTING_ORDER_TYPES

    @property
    def is_stop(self) -> bool:
        """True for the types that rank ahead of limits in the priority rule."""
        return self.order_type in ('stop', 'stop_limit') and not self.triggered

    def trigger_price(self) -> Optional[float]:
        """The price the market must reach for this order to become live."""
        if self.order_type == 'limit' or (self.order_type == 'stop_limit' and self.triggered):
            return self.limit_price
        if self.order_type in ('stop', 'stop_limit'):
            return self.stop_price
        return None

    def describe(self) -> str:
        """Human-readable one-liner, used by the sandbox and the ledger notes."""
        parts = [self.side.upper(), self.order_type.replace('_', '-')]
        if self.order_type == 'stop_limit':
            parts.append(f"{self.stop_price:,.2f} → {self.limit_price:,.2f}")
        elif self.stop_price is not None:
            parts.append(f"{self.stop_price:,.2f}")
        elif self.limit_price is not None:
            parts.append(f"{self.limit_price:,.2f}")
        if self.tif != 'gtc':
            parts.append(self.tif.upper())
        return ' '.join(parts)


@dataclass(frozen=True)
class Fill:
    """One execution: the order, the bar, and the price before costs.

    ``price`` is pre-slippage and pre-fee — the price the *market* printed. The
    engine applies slippage and commission on top, so a fill ledger read
    alongside the trade ledger reconciles: ``fees`` in the trade ledger is the
    difference.
    """

    order_id: int
    bar: int
    side: str
    qty: float
    price: float
    order_type: str
    reason: str
    group: Optional[str] = None

    def as_row(self, date=None) -> dict:
        """Flatten to a ledger row, optionally stamped with the bar's date."""
        return {
            'order_id': int(self.order_id),
            'bar': int(self.bar),
            'date': date,
            'side': self.side,
            'qty': float(self.qty),
            'price': float(self.price),
            'order_type': self.order_type,
            'reason': self.reason,
            'group': self.group,
        }


# Column order of the fill ledger attached as ``result_df.attrs['fills']``.
FILL_COLUMNS = (
    'order_id', 'bar', 'date', 'side', 'qty', 'price', 'order_type', 'reason', 'group',
)


def fills_to_frame(fills):
    """Build the fill-ledger DataFrame, with stable columns even when empty."""
    import pandas as pd

    if isinstance(fills, pd.DataFrame):
        fills = fills.to_dict('records')
    if not fills:
        return pd.DataFrame(columns=list(FILL_COLUMNS))
    return pd.DataFrame(list(fills), columns=list(FILL_COLUMNS))


def fill_price(order: Order, bar: Bar) -> Optional[float]:
    """The price *order* would trade at on *bar*, or None if the bar misses it.

    Implements the fill model in the module docstring. Pure: it neither mutates
    the order nor knows whether the fill is affordable.
    """
    if order.order_type == 'market':
        return bar.close

    if order.order_type == 'limit' or (order.order_type == 'stop_limit' and order.triggered):
        return _limit_fill(order.side, float(order.limit_price), bar)

    if order.order_type == 'stop':
        return _stop_fill(order.side, float(order.stop_price), bar)

    if order.order_type == 'stop_limit':
        trigger = _stop_fill(order.side, float(order.stop_price), bar)
        if trigger is None:
            return None
        limit = float(order.limit_price)
        # Triggered at a price the limit accepts: that is the fill.
        if (order.side == 'buy' and trigger <= limit) or (order.side == 'sell' and trigger >= limit):
            return trigger
        # Triggered through the limit. The order is now a plain limit for the
        # remainder of this bar; it fills only if the range came back to it.
        return _limit_fill(order.side, limit, bar)

    return None


def _limit_fill(side: str, limit: float, bar: Bar) -> Optional[float]:
    """Buy at or below *limit*, sell at or above it; the open can improve it."""
    if side == 'buy':
        if bar.open <= limit:
            return bar.open
        return limit if bar.low <= limit else None
    if bar.open >= limit:
        return bar.open
    return limit if bar.high >= limit else None


def _stop_fill(side: str, stop: float, bar: Bar) -> Optional[float]:
    """Trigger through *stop* and become a market order; a gap fills at the open."""
    if side == 'sell':
        if bar.open <= stop:
            return bar.open
        return stop if bar.low <= stop else None
    if bar.open >= stop:
        return bar.open
    return stop if bar.high >= stop else None


def _priority_key(order: Order, price: float, bar: Bar) -> tuple:
    """Sort key implementing :data:`PRIORITY_RULE`. Lower sorts first."""
    at_open = 0 if price == bar.open else 1
    adverse = 0 if order.is_stop else 1
    distance = abs(price - bar.open)
    return (at_open, adverse, distance, order.order_id)


class OrderBook:
    """The resting orders of one backtest, and which of them a bar touches.

    The book is deliberately small: submit, cancel, age out, ask for candidates,
    record a fill. It holds no position, no cash and no prices. The engine calls
    :meth:`expire` once per bar *before* working it, then walks
    :meth:`candidates` and calls :meth:`fill` for the ones it accepts.
    """

    def __init__(self, reset_ids: bool = False) -> None:
        if reset_ids:
            reset_order_ids()
        self._orders: List[Order] = []
        self.fills: List[Fill] = []
        self.cancelled: List[Tuple[Order, str]] = []

    # -- inspection --------------------------------------------------------- #

    def __len__(self) -> int:
        return len(self._orders)

    def __iter__(self) -> Iterator[Order]:
        return iter(tuple(self._orders))

    def __contains__(self, order: object) -> bool:
        # Identity, not equality: two legs of a bracket can compare equal on
        # every field the dataclass generates while being different orders.
        return any(o is order for o in self._orders)

    def __bool__(self) -> bool:
        # Explicit, because __len__ alone would make an empty book falsy in a
        # way that reads as "no book" at the call sites in lib.strategy.
        return True

    @property
    def is_empty(self) -> bool:
        return not self._orders

    def open_orders(
        self, side: Optional[str] = None, reason: Optional[str] = None
    ) -> Tuple[Order, ...]:
        """Resting orders, optionally filtered by side and/or reason."""
        return tuple(
            o for o in self._orders
            if (side is None or o.side == side) and (reason is None or o.reason == reason)
        )

    # -- lifecycle ---------------------------------------------------------- #

    def submit(self, order: Order) -> Order:
        """Rest *order* in the book. Market orders are rejected — they never rest."""
        if not order.rests:
            raise OrderError(
                "Market orders do not rest; fill them directly rather than submitting."
            )
        self._orders.append(order)
        return order

    def cancel(self, order: Order, why: str = 'cancelled') -> None:
        """Remove one order, recording why for the audit trail."""
        try:
            self._orders.remove(order)
        except ValueError:
            return
        self.cancelled.append((order, why))

    def cancel_group(self, group: Optional[str], keep: Optional[Order] = None) -> None:
        """Cancel every order in an OCO *group*, optionally sparing one."""
        if group is None:
            return
        for order in tuple(self._orders):
            if order.group == group and order is not keep:
                self.cancel(order, 'oco')

    def cancel_where(
        self, side: Optional[str] = None, reason: Optional[str] = None, why: str = 'cancelled'
    ) -> int:
        """Cancel every resting order matching *side* / *reason*. Returns the count."""
        doomed = self.open_orders(side=side, reason=reason)
        for order in doomed:
            self.cancel(order, why)
        return len(doomed)

    def cancel_all(self, why: str = 'flat') -> int:
        """Cancel everything — what a full liquidation does to working exits."""
        count = len(self._orders)
        for order in tuple(self._orders):
            self.cancel(order, why)
        return count

    def expire(self, bar: Bar) -> int:
        """Age resting orders into *bar*, cancelling the ones that have run out.

        Call this once per bar *before* :meth:`candidates`. Time in force counts
        from the first bar an order can actually trade against, which is the bar
        *after* the one that placed it — an order submitted on the close of bar
        ``t`` was not in the market while bar ``t`` was trading. Every order
        therefore gets at least one full bar of range before any TIF can kill
        it, whatever its type:

        * ``ioc`` is cancelled at the end of that one bar;
        * ``day`` survives while the session it was first worked in continues,
          so on a daily tape it behaves exactly like ``ioc``;
        * ``expire_bars`` caps the count of bars worked, on top of either.

        Returns how many orders were cancelled.
        """
        killed = 0
        for order in tuple(self._orders):
            if bar.index <= order.created_bar:
                continue  # placed on this bar; it is worked from the next one
            if order.bars_worked == 0:
                order.bars_worked = 1
                order.first_session = bar.session_id
                continue
            order.bars_worked += 1
            if order.tif == 'ioc':
                self.cancel(order, 'ioc')
                killed += 1
                continue
            if order.tif == 'day' and bar.session_id != order.first_session:
                self.cancel(order, 'day')
                killed += 1
                continue
            if order.expire_bars and order.bars_worked > int(order.expire_bars):
                self.cancel(order, 'expired')
                killed += 1
        return killed

    # -- working a bar ------------------------------------------------------ #

    def candidates(self, bar: Bar) -> List[Tuple[Order, float]]:
        """Every resting order *bar* touches, ordered by :data:`PRIORITY_RULE`."""
        touched: List[Tuple[Order, float]] = []
        for order in self._orders:
            price = fill_price(order, bar)
            if price is not None and np.isfinite(price):
                touched.append((order, float(price)))
        touched.sort(key=lambda pair: _priority_key(pair[0], pair[1], bar))
        return touched

    def arm_triggered(self, bar: Bar) -> None:
        """Latch stop-limits whose stop was hit but whose limit was not reached.

        Called after the bar's fills are applied, so an order that filled never
        gets latched. From the next bar on the order is a plain limit — a
        stop-limit does not re-arm.
        """
        for order in self._orders:
            if order.order_type == 'stop_limit' and not order.triggered:
                if _stop_fill(order.side, float(order.stop_price), bar) is not None:
                    order.triggered = True

    def fill(self, order: Order, bar: Bar, qty: float, price: float) -> Fill:
        """Record a fill, remove the order, and cancel its OCO siblings."""
        record = Fill(
            order_id=order.order_id,
            bar=bar.index,
            side=order.side,
            qty=float(qty),
            price=float(price),
            order_type=order.order_type,
            reason=order.reason,
            group=order.group,
        )
        self.fills.append(record)
        self.cancel_group(order.group, keep=order)
        self.cancel(order, 'filled')
        return record

    def reprice(
        self,
        order: Order,
        stop_price: Optional[float] = None,
        limit_price: Optional[float] = None,
    ) -> None:
        """Move a resting order's levels — what ratcheting a trailing stop is."""
        if stop_price is not None:
            order.stop_price = float(stop_price)
        if limit_price is not None:
            order.limit_price = float(limit_price)


def bracket_orders(
    side: str,
    stop_price: float,
    target_price: float,
    group: str,
    created_bar: int,
    created_session: int = 0,
    qty: Optional[float] = None,
    tif: str = 'gtc',
) -> Tuple[Order, Order]:
    """The two legs of a bracket: a protective stop and a profit target.

    They share an OCO ``group``, so :meth:`OrderBook.fill` cancels the survivor
    the moment either one trades. *side* is the side of the **exit** — ``'sell'``
    brackets a long.
    """
    protective = Order(
        side=side, order_type='stop', qty=qty, stop_price=float(stop_price),
        tif=tif, reason='bracket_stop', group=group,
        created_bar=created_bar, created_session=created_session,
    )
    target = Order(
        side=side, order_type='limit', qty=qty, limit_price=float(target_price),
        tif=tif, reason='bracket_target', group=group,
        created_bar=created_bar, created_session=created_session,
    )
    return protective, target


def summarise(orders: Iterable[Order]) -> str:
    """Compact description of a book, for logs and the sandbox's notes column."""
    described = [o.describe() for o in orders]
    return ' · '.join(described) if described else 'no resting orders'
