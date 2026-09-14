"""The bar loop: every symbol, one account, phase by phase.

Implements the per-bar sequence of
[docs/portfolio-semantics.md](../../docs/portfolio-semantics.md) §3. Each phase
runs across *every* symbol before the next one starts, so everything that
releases cash happens before anything that spends it:

1. **Expire and arm** each symbol's order book.
2. **Credits.** Each symbol resolves its bar exactly as the single-symbol
   engine always did — work the book, else check exits, else process signals —
   except that a buy is not filled on the spot. Sells fill; a buy comes back
   as a :class:`~lib.engine.state.PendingBuy`. Cash reads in this phase all see
   the balance the bar opened with, and credits settle together at the end.
3. **Debits.** Every pending buy gets its units from
   :func:`~lib.engine.allocation.water_fill` against the post-credit cash, then
   fills. A same-bar sale therefore funds a same-bar buy (T+0).
4. **Sync exit orders**, writing the levels the *next* bar is tested against.
5. **Snapshot** each symbol, then the account totals.

A symbol resolves in phase 2 or phase 3, never both, so the one-fill-per-symbol
per-bar rule is unchanged. With one symbol the phases collapse back into the
original cascade, which is why ``test_strategy_snapshot`` does not move.

A bar a symbol did not print (``tradable`` False, see :mod:`lib.panel`) is
**valued, not traded**: the symbol's holding clock and cooldowns tick, its
position is marked at the carried-forward price, and nothing else happens — no
exit, no signal, no order is offered the bar, and no exit level is re-synced.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import List, Optional, Sequence

import numpy as np

from lib.engine.allocation import water_fill
from lib.engine.resting import sync_exit_orders, work_resting_orders
from lib.engine.state import Account, EngineConfig, PendingBuy, SymbolContext
from lib.engine.steps import (
    arm_buy_cooldown,
    check_exits,
    fill_buy,
    finalise_trade,
    hold,
    process_signals,
)
from lib.orders import Bar


@dataclass(frozen=True, eq=False)
class AccountTape:
    """The account's bar-by-bar totals across the whole basket."""
    cash_value: np.ndarray
    stocks_value: np.ndarray
    portfolio_value: np.ndarray


def _start_bar(ctx: SymbolContext, bar: int) -> None:
    """Advance the holding clocks before anything trades on *bar*."""
    ctx.holding_period[bar] = ctx.holding_period[bar - 1] + 1 if ctx.state.units > 0 else 0
    # Bars held is a positional count; sessions crossed is the same hold
    # measured against the calendar. entry_bar is recoverable because
    # holding_period counts up one per bar from the fill.
    ctx.holding_sessions[bar] = (
        ctx.session_id[bar] - ctx.session_id[bar - ctx.holding_period[bar]]
    )


def _resolve_credits(
    ctx: SymbolContext, bar: int, prev_portfolio_value: float
) -> Optional[PendingBuy]:
    """Phases 1 and 2 for one symbol: the original cascade, minus the buy fill."""
    if ctx.cfg.uses_orders:
        bar_prices = Bar.from_arrays(
            bar, ctx.close_prices, ctx.open_prices, ctx.high_prices, ctx.low_prices,
            ctx.session_start, ctx.session_id,
        )
        ctx.book.expire(bar_prices)
        sold, pending = work_resting_orders(ctx, bar_prices)
        # Stop-limits touched but not filled become plain limits from the next
        # bar on. A pending buy is latched too, harmlessly: phase 3 removes it
        # from the book whether it fills or is starved.
        ctx.book.arm_triggered(bar_prices)
        if pending is not None:
            return pending
        if sold:
            hold(ctx, bar)
            return None

    if check_exits(ctx, bar):
        return None
    return process_signals(ctx, bar, prev_portfolio_value)


def _settle_buys(account: Account, pending: Sequence[PendingBuy], round_units) -> None:
    """Phase 3: share the post-credit cash out, then fill."""
    units = water_fill(
        account.cash, [(buy.qty, buy.cost_per_unit) for buy in pending], round_units
    )
    for buy, qty in zip(pending, units):
        ctx = buy.ctx
        order = buy.order
        if order is None:
            # A market buy on a signal. Starved means the existing
            # unaffordable-buy path: no fill, no cooldown, the ramp already moved.
            if qty <= 0:
                hold(ctx, buy.bar)
                continue
            fill_buy(ctx, buy.bar, qty, buy.price)
            arm_buy_cooldown(ctx)
            continue

        if qty <= 0:
            ctx.book.cancel(order, 'unaffordable')
            hold(ctx, buy.bar)
            continue
        ctx.book.fill(order, buy.bar_prices, qty, buy.price)
        fill_buy(
            ctx, buy.bar, qty, buy.price,
            order.order_type, order.reason, order.group, order.order_id,
        )
        hold(ctx, buy.bar)
    account.settle()


def _snapshot(ctx: SymbolContext, bar: int) -> None:
    state = ctx.state
    ctx.units[bar] = state.units
    ctx.trailing_stop[bar] = state.trailing_stop
    ctx.avg_entry_price[bar] = state.avg_entry
    ctx.avg_cost_basis[bar] = state.cost_basis
    ctx.stocks_value[bar] = state.units * ctx.mark_prices[bar]

    # Cooldowns are armed with cooldown_bars + 1 at fill time precisely
    # because this decrement also runs on the arming bar; the counter is
    # therefore non-zero on exactly the next `cooldown_bars` bars.
    if state.buy_cooldown > 0:
        state.buy_cooldown -= 1
    if state.sell_cooldown > 0:
        state.sell_cooldown -= 1


def run_bars(
    cfg: EngineConfig, account: Account, symbols: List[SymbolContext], num_rows: int
) -> AccountTape:
    """Run every bar for every symbol against one account.

    Mutates each context's state, arrays and ledgers in place, and closes out
    any position still open on the last bar at its mark (``exit_reason='open'``)
    so each ledger reconciles with the equity curve.
    """
    cash_value = np.full(num_rows, float(account.cash))
    stocks_value = np.zeros(num_rows)
    portfolio_value = np.full(num_rows, float(account.cash))

    # Bar 0 is the opening state, and bars before `delay` have no observable
    # signal yet, so the first tradable bar is max(1, delay).
    for i in range(max(1, cfg.delay), num_rows):
        # Sizing base (§2): total portfolio value at the previous bar, the same
        # number for every symbol whatever order they are visited in.
        prev_portfolio_value = portfolio_value[i - 1]
        account.open_bar()

        pending: List[PendingBuy] = []
        for ctx in symbols:
            _start_bar(ctx, i)
            if not ctx.tradable[i]:
                continue
            buy = _resolve_credits(ctx, i, prev_portfolio_value)
            if buy is not None:
                pending.append(buy)
        account.settle()

        if pending:
            _settle_buys(account, pending, cfg.round_units)

        for ctx in symbols:
            if cfg.uses_orders and ctx.tradable[i]:
                sync_exit_orders(ctx, i)
            _snapshot(ctx, i)

        cash_value[i] = account.cash
        stocks_value[i] = math.fsum(ctx.stocks_value[i] for ctx in symbols)
        portfolio_value[i] = account.cash + stocks_value[i]

    if num_rows > 0:
        for ctx in symbols:
            if ctx.open_trade is not None:
                ctx.trades.append(finalise_trade(ctx, ctx.open_trade, num_rows - 1, is_open=True))
                ctx.open_trade = None

    return AccountTape(
        cash_value=cash_value, stocks_value=stocks_value, portfolio_value=portfolio_value,
    )
