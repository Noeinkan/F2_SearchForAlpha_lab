"""One symbol's resting-order book, worked once per bar, and its protective exits."""

from __future__ import annotations

from typing import Optional, Tuple

import numpy as np

from lib.engine.state import UNIT_EPS, PendingBuy, SymbolContext
from lib.engine.steps import affordable_units, close_position, fill_sell
from lib.orders import Bar, Order, bracket_orders


def work_resting_orders(
    ctx: SymbolContext, bar: Bar
) -> Tuple[bool, Optional[PendingBuy]]:
    """Walk what *bar* touches, in the book's priority order.

    Returns ``(sold, pending)``: ``sold`` is True when a sell filled, and
    ``pending`` is the buy the walk stopped at, waiting for the loop to hand it
    its share of the cash. At most one of the two is set, because a fill — or a
    buy that will fill — consumes the bar for this symbol.

    Resting orders are worked *before* the bar's signals, because they were
    placed on an earlier bar: a stop left working overnight does not wait for
    today's indicator to be recomputed. At most one order trades per bar per
    symbol, so ``Units_to_buy`` / ``Units_to_sell`` stay one number each.

    A buy is tested here against the cash the bar *opened* with. One that could
    not buy a single unit with it is cancelled as ``'unaffordable'`` and the walk
    moves on, exactly as it always has; one that could becomes the pending buy,
    and the quantity it finally gets is decided after every symbol's sells for
    the bar have settled. So a same-bar sale elsewhere in the basket can top up
    a buy that was already fundable, but cannot rescue one that was not.

    Quantities are re-clamped at fill time, not at submission: a buy sized
    against last week's cash may no longer be affordable, and an exit sized
    against a position that has since been trimmed must not sell units that are
    gone. Nothing is reserved when an order is placed, which is the one place
    this model is more optimistic than a real broker's.
    """
    if ctx.book.is_empty:
        return False, None

    cfg, state = ctx.cfg, ctx.state
    filled = False
    index = bar.index
    for order, price in ctx.book.candidates(bar):
        if order not in ctx.book:
            continue  # an OCO sibling filled earlier on this same bar
        if not np.isfinite(price) or price <= 0:
            continue

        if order.side == 'buy':
            if filled:
                continue  # one fill per bar; the rest keep resting
            requested = order.qty if order.qty is not None else 0.0
            affordable = affordable_units(ctx, price, ctx.account.bar_cash)
            qty = cfg.round_units(min(requested, affordable) if affordable > 0 else 0.0)
            if qty <= 0:
                ctx.book.cancel(order, 'unaffordable')
                continue
            # Stopping here is what the old walk did in effect: once a buy
            # filled, every later candidate was skipped.
            return False, PendingBuy(
                ctx=ctx, bar=index, qty=requested, price=price,
                order=order, bar_prices=bar,
            )

        available = state.units
        if available <= UNIT_EPS:
            ctx.book.cancel(order, 'flat')
            continue
        if filled:
            continue
        qty = available if order.qty is None else min(float(order.qty), available)
        qty = cfg.round_units(qty)
        if qty <= 0:
            ctx.book.cancel(order, 'flat')
            continue
        ctx.book.fill(order, bar, qty, price)
        if qty >= available - UNIT_EPS:
            close_position(
                ctx, index, price, order.reason,
                order.order_type, order.group, order.order_id,
            )
        else:
            fill_sell(
                ctx, index, qty, price,
                order.order_type, order.reason, order.group, order.order_id,
            )
        filled = True

    return filled, None


def attach_bracket(ctx: SymbolContext, bar: int) -> None:
    """Hang an OCO stop / target pair off the average entry of the open position.

    Both legs are fixed at the entry price and neither moves — that is what
    separates a bracket from the trailing stop, and why its exits get their own
    reasons in the ledger. ``qty=None`` means "whatever is held when this
    fills", so a scale-in that grows the position does not leave part of it
    unprotected.
    """
    cfg, state = ctx.cfg, ctx.state
    entry = state.avg_entry
    if entry <= 0:
        return

    ctx.bracket_seq += 1
    group = f"bracket-{ctx.bracket_seq}"
    session = int(ctx.session_id[bar])

    # Exit orders are always GTC, whatever ``time_in_force`` says. That knob is
    # about how patient an *entry* is; expiring a protective stop overnight
    # would leave the position naked on the bar after every expiry, because
    # sync_exit_orders can only re-post it once the bar has been worked.
    stop_price = entry * (1 - cfg.bracket_stop) if cfg.bracket_stop > 0 else None
    if stop_price is not None and cfg.trailing_stop_orders and np.isfinite(state.trailing_stop):
        # Composing the two features: the protective leg starts at whichever of
        # the bracket stop and the trailing stop is already tighter, and the
        # trail keeps ratcheting it from there.
        stop_price = max(stop_price, state.trailing_stop)
    target_price = entry * (1 + cfg.bracket_target) if cfg.bracket_target > 0 else None

    if stop_price is not None and target_price is not None:
        for leg in bracket_orders(
            'sell', stop_price, target_price, group, bar, session, tif='gtc'
        ):
            ctx.book.submit(leg)
        return

    if stop_price is not None:
        ctx.book.submit(Order(
            side='sell', order_type='stop', stop_price=stop_price, tif='gtc',
            reason='bracket_stop', group=group, created_bar=bar, created_session=session,
        ))
    elif target_price is not None:
        ctx.book.submit(Order(
            side='sell', order_type='limit', limit_price=target_price, tif='gtc',
            reason='bracket_target', group=group, created_bar=bar, created_session=session,
        ))


def sync_exit_orders(ctx: SymbolContext, bar: int) -> None:
    """Keep the working exit orders in step with the position, once per bar.

    Called after the bar has been resolved, so the levels it writes are the ones
    the *next* bar will be tested against — which is exactly the timing the
    close-based trailing stop always had.
    """
    cfg, state = ctx.cfg, ctx.state
    flat = state.units <= UNIT_EPS or cfg.strategy_mode == 'accumulation'
    if flat:
        for reason in ('trailing_stop', 'bracket_stop', 'bracket_target'):
            ctx.book.cancel_where(side='sell', reason=reason, why='flat')
        return

    if cfg.use_brackets:
        stop_leg = ctx.book.open_orders(side='sell', reason='bracket_stop')
        target_leg = ctx.book.open_orders(side='sell', reason='bracket_target')
        if not stop_leg and not target_leg:
            attach_bracket(ctx, bar)
        elif stop_leg and cfg.trailing_stop_orders and np.isfinite(state.trailing_stop):
            order = stop_leg[0]
            ctx.book.reprice(order, stop_price=max(float(order.stop_price), state.trailing_stop))
        return

    if cfg.trailing_stop_orders:
        level = state.trailing_stop
        if not np.isfinite(level):
            return
        existing = ctx.book.open_orders(side='sell', reason='trailing_stop')
        if existing:
            order = existing[0]
            # A trailing stop only ever ratchets up; repricing it down would
            # undo the whole point of the trail.
            ctx.book.reprice(order, stop_price=max(float(order.stop_price), level))
        else:
            # GTC for the same reason the bracket's legs are: a stop that
            # expires is not a stop.
            ctx.book.submit(Order(
                side='sell', order_type='stop', stop_price=level, tif='gtc',
                reason='trailing_stop', created_bar=bar,
                created_session=int(ctx.session_id[bar]),
            ))
