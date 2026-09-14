"""What the bar loop carries: shared configuration, one account, per-symbol state.

Roadmap 3.8.3 split the engine's single ``_EngineContext`` along the line a
portfolio needs drawn:

* :class:`EngineConfig` — the knobs of the run. One set for the whole basket
  ([docs/portfolio-semantics.md](../../docs/portfolio-semantics.md) §9: one
  config in v1).
* :class:`Account` — the **one** cash balance every symbol funds from (§1).
* :class:`SymbolContext` — everything that belongs to one symbol: its prices,
  its signals, its :class:`PositionState`, its order book, its ledgers and the
  output arrays its result frame is built from.

A single-symbol backtest is a basket of one: one :class:`SymbolContext` over one
:class:`Account`. There is no second code path.

Why cash moves only at settle points
------------------------------------
A fill never touches ``Account.cash`` directly. It *queues* a credit or a debit,
and :meth:`Account.settle` folds the queue in with :func:`math.fsum`, which is
exactly rounded and therefore gives the same bits whatever order the symbols
queued in. Plain ``cash += x`` in a loop over symbols would make the last few
bits of every balance depend on where a ticker sits in the list — small, but
precisely the dependence §4 rules out. For one symbol, whose one fill per bar is
one queued amount, ``fsum([cash, x])`` is ``cash + x`` bit for bit.

While a bar's credits are being decided, every read of cash sees
:attr:`Account.bar_cash` — the balance when the bar opened — so no symbol's
sizing can depend on whether another symbol's sell was processed before it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass, field
from typing import Any, Callable, List, Optional

import numpy as np
import pandas as pd

from lib.orders import Bar, Order, OrderBook

# Quantities below this are treated as flat (fractional-share rounding noise).
UNIT_EPS = 1e-9


@dataclass(frozen=True)
class EngineConfig:
    """The run's behaviour switches, resolved and validated, shared by every symbol."""
    delay: int
    strategy_mode: str
    consecutive_signal_mode: str
    cooldown_bars: int
    min_holding_period: int
    position_scaling: float
    position_size_pct: float
    amount_per_buy: Optional[float]
    take_profit: float
    fee_rate: float
    slippage_pct: float

    # Order model. ``order_type='market'`` with both order flags off means the
    # book is never touched and the engine behaves exactly as it did before
    # lib.orders existed — that equivalence is what test_strategy_snapshot pins.
    order_type: str
    limit_offset: float
    stop_offset: float
    time_in_force: str
    order_expiry_bars: int
    trailing_stop_orders: bool
    use_brackets: bool
    bracket_stop: float
    bracket_target: float
    uses_orders: bool

    round_units: Callable[[float], float]

    @property
    def exits_are_orders(self) -> bool:
        """True when the book, not ``check_exits``, owns the protective stop."""
        return self.trailing_stop_orders or self.use_brackets

    def cost_per_unit(self, price: float) -> float:
        """What one unit bought at *price* costs, slippage and fees included."""
        execution_price = price * (1 + self.slippage_pct)
        return execution_price * (1 + self.fee_rate)


@dataclass
class Account:
    """The single cash balance a basket trades against."""
    cash: float
    # Balance when the current bar opened. Every cash read made while the bar's
    # decisions are still being taken goes through this, never through ``cash``.
    bar_cash: float = 0.0
    _queued: List[float] = field(default_factory=list, repr=False)

    def __post_init__(self) -> None:
        self.bar_cash = self.cash

    def open_bar(self) -> None:
        self.bar_cash = self.cash

    def credit(self, amount: float) -> None:
        self._queued.append(amount)

    def debit(self, amount: float) -> None:
        self._queued.append(-amount)

    def settle(self) -> None:
        """Apply every queued amount at once, independent of queueing order."""
        if self._queued:
            self.cash = math.fsum([self.cash, *self._queued])
            self._queued.clear()


@dataclass
class PositionState:
    """One symbol's mutable position, carried across the bar loop.

    Holding this in one object rather than in a dozen loop-local names is what
    lets the exit / buy / sell steps live in their own functions: each reads the
    previous bar's values off the state, mutates them, and the loop snapshots
    the result into the output arrays. Cash is not here — it is the account's.
    """
    units: float = 0.0
    position_size: float = 0.0
    avg_entry: float = 0.0        # average execution price, fees excluded
    cost_basis: float = 0.0       # average execution price, fees included
    trailing_stop: float = np.inf
    buy_cooldown: int = 0
    sell_cooldown: int = 0
    buy_wait_reset: bool = False
    sell_wait_reset: bool = False


@dataclass
class OpenTrade:
    """Accumulator for the round trip currently in progress."""
    entry_bar: int
    units_bought: float = 0.0
    units_sold: float = 0.0
    gross_cost: float = 0.0       # notional paid, fees excluded
    gross_proceeds: float = 0.0   # notional received, fees excluded
    entry_fees: float = 0.0
    exit_fees: float = 0.0
    exit_reason: str = 'signal'
    # Mechanism, as opposed to cause. Set on the first entry fill and the last
    # exit fill; 'market' throughout is the engine's default.
    entry_order_type: str = 'market'
    exit_order_type: str = 'market'


def _zeros(n: int, dtype: Any = float) -> np.ndarray:
    return np.zeros(n, dtype=dtype)


@dataclass
class SymbolContext:
    """One symbol's inputs, state, book, ledgers and output arrays."""
    symbol: str
    cfg: EngineConfig
    account: Account
    frame: pd.DataFrame           # the input frame plus Volatility; the result is built on it

    # Price / signal inputs
    close_prices: np.ndarray
    low_prices: Optional[np.ndarray]
    high_prices: Optional[np.ndarray]
    open_prices: Optional[np.ndarray]
    # Valuation price: ``Close`` on a plain frame, the forward-filled ``Mark``
    # on a panel frame (NaN before listing read as 0 — nothing is held then).
    mark_prices: np.ndarray
    # False on a bar the symbol did not print: valued, never traded (§6).
    tradable: np.ndarray
    session_start: np.ndarray
    session_id: np.ndarray
    # First bar the symbol could trade after the market *or the symbol* was shut:
    # a session start, or the bar after a hole. A stop the symbol reopened
    # through fills at the open either way.
    reopens: np.ndarray
    dates: Any
    buy_signal_raw: np.ndarray
    sell_signal_raw: np.ndarray

    # Per-symbol effective switches — downgraded when a column is missing.
    use_low_for_stops: bool
    gap_fills: bool
    effective_stop_mode: str
    position_sizing_strategy: str

    # Callables that read this symbol's own columns (ATR, volatility).
    size_position: Callable[[float, float, int], float]
    long_stop_level: Callable[[int, float], float]

    state: PositionState = field(default_factory=PositionState)

    # Output arrays, allocated in __post_init__.
    units_to_buy: np.ndarray = field(init=False)
    units_to_sell: np.ndarray = field(init=False)
    buy_signal_counter: np.ndarray = field(init=False)
    sell_signal_counter: np.ndarray = field(init=False)
    buy_triggered: np.ndarray = field(init=False)
    buy_rejected: np.ndarray = field(init=False)
    sell_triggered: np.ndarray = field(init=False)
    sell_rejected: np.ndarray = field(init=False)
    holding_period: np.ndarray = field(init=False)
    holding_sessions: np.ndarray = field(init=False)
    units: np.ndarray = field(init=False)
    trailing_stop: np.ndarray = field(init=False)
    avg_entry_price: np.ndarray = field(init=False)
    avg_cost_basis: np.ndarray = field(init=False)
    stocks_value: np.ndarray = field(init=False)

    # Trade ledger
    trades: List[dict] = field(default_factory=list)
    open_trade: Optional[OpenTrade] = None

    # Order layer. ``book`` is always constructed but stays empty unless
    # something can rest in it; ``cfg.uses_orders`` is the cheap guard the bar
    # loop checks so the default path pays nothing for it.
    book: OrderBook = field(default_factory=OrderBook)
    fill_rows: List[dict] = field(default_factory=list)
    bracket_seq: int = 0

    def __post_init__(self) -> None:
        n = len(self.close_prices)
        self.units_to_buy = _zeros(n)
        self.units_to_sell = _zeros(n)
        self.buy_signal_counter = _zeros(n, int)
        self.sell_signal_counter = _zeros(n, int)
        self.buy_triggered = _zeros(n, bool)
        self.buy_rejected = _zeros(n, bool)
        self.sell_triggered = _zeros(n, bool)
        self.sell_rejected = _zeros(n, bool)
        self.holding_period = _zeros(n, int)
        self.holding_sessions = _zeros(n, int)
        self.units = _zeros(n)
        self.trailing_stop = np.full(n, np.inf)
        self.avg_entry_price = _zeros(n)
        self.avg_cost_basis = _zeros(n)
        self.stocks_value = _zeros(n)


@dataclass
class PendingBuy:
    """A buy decided in the credit phase and waiting for its share of the cash.

    ``qty`` is what the symbol asked for, before any cash clamp; the allocation
    rule decides how much of it lands. ``order`` is the resting order being
    filled, or ``None`` for a market buy on a signal.
    """
    ctx: SymbolContext
    bar: int
    qty: float
    price: float
    order: Optional[Order] = None
    bar_prices: Optional[Bar] = None

    @property
    def cost_per_unit(self) -> float:
        return self.ctx.cfg.cost_per_unit(self.price)
