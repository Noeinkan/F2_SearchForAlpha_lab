"""The per-bar steps one symbol takes: exits, signal gating, sizing and fills.

Every function here acts on one :class:`~lib.engine.state.SymbolContext`. None
of them loops over symbols and none of them decides *when* it runs relative to
another symbol — that is :mod:`lib.engine.loop`'s job, and the reason a buy
decided here comes back as a :class:`~lib.engine.state.PendingBuy` instead of
spending cash on the spot.

Cash is queued on the account (``credit`` / ``debit``), never written; reads
made while a bar is being decided go through ``account.bar_cash``. See
:mod:`lib.engine.state` for why.
"""

from __future__ import annotations

from typing import Optional

import numpy as np

from lib.engine.state import UNIT_EPS, EngineConfig, OpenTrade, PendingBuy, SymbolContext
from lib.orders import Order

# --------------------------------------------------------------------------- #
# Trade ledger
# --------------------------------------------------------------------------- #

def record_entry(
    ctx: SymbolContext, bar: int, qty: float, value: float, fee: float,
    order_type: str = 'market',
) -> None:
    """Fold a fill into the open round trip, opening one if the book was flat."""
    if ctx.open_trade is None:
        ctx.open_trade = OpenTrade(entry_bar=bar, entry_order_type=order_type)
    trade = ctx.open_trade
    trade.units_bought += qty
    trade.gross_cost += value
    trade.entry_fees += fee


def record_exit(
    ctx: SymbolContext, bar: int, qty: float, value: float, fee: float, reason: str,
    order_type: str = 'market',
) -> None:
    """Fold a sell into the open round trip, closing it once the book is flat."""
    trade = ctx.open_trade
    if trade is None:
        return
    trade.units_sold += qty
    trade.gross_proceeds += value
    trade.exit_fees += fee
    trade.exit_reason = reason
    trade.exit_order_type = order_type
    if trade.units_sold >= trade.units_bought - UNIT_EPS:
        ctx.trades.append(finalise_trade(ctx, trade, bar, is_open=False))
        ctx.open_trade = None


def finalise_trade(
    ctx: SymbolContext, trade: OpenTrade, exit_bar: int, is_open: bool
) -> dict:
    """Turn an accumulated round trip into a ledger row.

    An ``is_open`` trade is the position still held on the final bar; it is
    marked to market at that bar's mark (its close, on a plain frame) so the
    ledger reconciles with the equity curve. Its ``exit_reason`` is ``'open'``
    and the realised-performance metrics (win rate, profit factor) exclude it.

    ``avg_entry_price`` is fee-exclusive; ``avg_cost_basis`` is the same average
    with entry fees folded in.
    """
    units = trade.units_bought
    gross_proceeds = trade.gross_proceeds
    if is_open:
        remaining = max(units - trade.units_sold, 0.0)
        gross_proceeds += remaining * ctx.mark_prices[exit_bar]

    avg_entry = trade.gross_cost / units if units > 0 else 0.0
    avg_cost_basis = (trade.gross_cost + trade.entry_fees) / units if units > 0 else 0.0
    exit_price = gross_proceeds / units if units > 0 else 0.0
    gross_pnl = gross_proceeds - trade.gross_cost
    fees = trade.entry_fees + trade.exit_fees

    return {
        'entry_bar': int(trade.entry_bar),
        'entry_date': ctx.dates[trade.entry_bar],
        'exit_bar': int(exit_bar),
        'exit_date': ctx.dates[exit_bar],
        'units': float(units),
        'avg_entry_price': float(avg_entry),
        'avg_cost_basis': float(avg_cost_basis),
        'exit_price': float(exit_price),
        'exit_reason': 'open' if is_open else trade.exit_reason,
        'gross_pnl': float(gross_pnl),
        'net_pnl': float(gross_pnl - fees),
        'fees': float(fees),
        'holding_bars': int(exit_bar - trade.entry_bar),
        'holding_sessions': int(
            ctx.session_id[exit_bar] - ctx.session_id[trade.entry_bar]
        ),
        'is_open': bool(is_open),
        'entry_order_type': trade.entry_order_type,
        # A position marked to market on the final bar was not executed at all,
        # so calling its exit a market order would be a small lie. Say so.
        'exit_order_type': 'none' if is_open else trade.exit_order_type,
    }


def log_fill(
    ctx: SymbolContext, bar: int, side: str, qty: float, price: float,
    order_type: str, reason: str, group: Optional[str] = None, order_id: int = 0,
) -> None:
    """Append one row to the fill ledger.

    Every execution goes through here, market orders included, so
    ``attrs['fills']`` is a complete account of what traded even on a run that
    never places a resting order. ``price`` is the market price *before*
    slippage and fees — the trade ledger's ``fees`` column is the difference.
    """
    ctx.fill_rows.append({
        'order_id': int(order_id),
        'bar': int(bar),
        'date': ctx.dates[bar],
        'side': side,
        'qty': float(qty),
        'price': float(price),
        'order_type': order_type,
        'reason': reason,
        'group': group,
    })


# --------------------------------------------------------------------------- #
# Holding, exits and fills
# --------------------------------------------------------------------------- #

def hold(ctx: SymbolContext, bar: int) -> None:
    """No fill this bar: carry the position and ratchet the trailing stop.

    The stop only ever moves up. Every no-fill path routes through here so a
    rejected, undersized or unaffordable order cannot leave the stop stale.
    """
    state = ctx.state
    if ctx.cfg.strategy_mode == 'accumulation' or state.units <= 0:
        state.trailing_stop = np.inf
    else:
        state.trailing_stop = max(
            state.trailing_stop, ctx.long_stop_level(bar, ctx.close_prices[bar])
        )


def close_position(
    ctx: SymbolContext, bar: int, price: float, reason: str,
    order_type: str = 'market', group: Optional[str] = None, order_id: int = 0,
) -> None:
    """Liquidate the whole position at *price* (pre-slippage) and log the exit."""
    state = ctx.state
    qty = state.units
    ctx.units_to_sell[bar] += qty
    execution_price = price * (1 - ctx.cfg.slippage_pct)
    value = qty * execution_price
    fee = value * ctx.cfg.fee_rate

    state.units = 0.0
    ctx.account.credit(value - fee)
    state.position_size = 0.0
    state.trailing_stop = np.inf
    state.avg_entry = 0.0
    state.cost_basis = 0.0

    record_exit(ctx, bar, qty, value, fee, reason, order_type)
    log_fill(ctx, bar, 'sell', qty, price, order_type, reason, group, order_id)


def check_exits(ctx: SymbolContext, bar: int) -> bool:
    """Apply trailing stop and take profit. Returns True if the bar was consumed.

    Ordering is deliberate: the stop is tested first and ignores
    ``min_holding_period``; take profit is tested second and respects it. Both
    are disabled entirely in accumulation mode (long-term hold).

    Either branch can be handed to the order book instead. When the trailing
    stop is expressed as a resting stop order (``trailing_stop_orders``) or a
    bracket is working, the stop branch here is skipped — the book already
    tested it against the bar's range, and testing it twice would double-exit.
    A bracket with a live profit target likewise owns the take-profit branch.
    """
    cfg, state = ctx.cfg, ctx.state
    if cfg.strategy_mode == 'accumulation' or state.units <= 0:
        return False

    close_price = ctx.close_prices[bar]
    stop_level = np.inf if cfg.exits_are_orders else state.trailing_stop

    if np.isfinite(stop_level):
        # An overnight gap is not an intrabar move. The stop could not be
        # worked while the exchange was shut — or while this symbol was halted —
        # so a reopen at or below it fills at the open, the first price anyone
        # could actually trade, however the bar goes on to close.
        if ctx.gap_fills and ctx.reopens[bar] and ctx.open_prices is not None:
            open_price = ctx.open_prices[bar]
            if np.isfinite(open_price) and open_price <= stop_level:
                close_position(ctx, bar, open_price, 'trailing_stop')
                return True
        if ctx.use_low_for_stops:
            # Intrabar breach: a resting stop order would have filled at the stop,
            # unless the bar closed below it (gap), where the close is the worse
            # and more honest assumption.
            if ctx.low_prices[bar] <= stop_level:
                close_position(ctx, bar, min(stop_level, close_price), 'trailing_stop')
                return True
        elif close_price <= stop_level:
            close_position(ctx, bar, close_price, 'trailing_stop')
            return True

    if (
        cfg.take_profit > 0
        and not (cfg.use_brackets and cfg.bracket_target > 0)
        and state.avg_entry > 0
        and close_price >= state.avg_entry * (1 + cfg.take_profit)
        and ctx.holding_period[bar] >= cfg.min_holding_period
    ):
        close_position(ctx, bar, close_price, 'take_profit')
        return True

    return False


def affordable_units(ctx: SymbolContext, price: float, cash: float) -> float:
    """Units *price* can be bought at with *cash*, fees included."""
    total_cost_per_unit = ctx.cfg.cost_per_unit(price)
    if total_cost_per_unit <= 0:
        return 0.0
    return ctx.cfg.round_units(cash / total_cost_per_unit)


def size_buy(
    ctx: SymbolContext, bar: int, prev_portfolio_value: float, price: float,
) -> float:
    """Units to buy at *price*, before the affordability clamp.

    *price* is the price the order expects to trade at: a market order's bar
    close, or a resting order's own limit / stop level. Sizing off the level a
    limit order will actually fill at is the only way the requested notional
    matches the notional that lands.

    Mutates ``state.position_size`` in trading mode — the scale-in ramp advances
    when the signal is *accepted*, not when it fills, which is what makes a
    rejected or unaffordable buy still consume a rung of the ramp.
    """
    cfg, state = ctx.cfg, ctx.state
    if cfg.strategy_mode == 'accumulation':
        # Fixed dollar amount per buy (DCA style), capped by the cash the bar
        # opened with.
        buy_amount = cfg.amount_per_buy if cfg.amount_per_buy else 1000.0
        buy_amount = min(float(buy_amount), ctx.account.bar_cash)
        return cfg.round_units(buy_amount / price)
    if cfg.strategy_mode == 'rebalancing':
        # Target weight: trade ``pct`` of *portfolio value*, so repeated buys stay
        # equal-weight instead of decaying against a shrinking cash balance. The
        # affordability clamp caps an over-weight request at available cash.
        pct = (cfg.position_size_pct or 100) / 100.0
        return cfg.round_units((prev_portfolio_value * pct) / price)
    state.position_size = min(state.position_size + cfg.position_scaling, 1)
    raw = ctx.size_position(prev_portfolio_value, price, bar)
    return cfg.round_units(raw * state.position_size)


def size_sell(
    ctx: SymbolContext, bar: int, prev_portfolio_value: float, price: float,
) -> float:
    """Units to sell at *price*, clamped to the position actually held."""
    cfg, state = ctx.cfg, ctx.state
    prev_units = state.units
    if cfg.strategy_mode == 'rebalancing':
        # Mirror of the buy side: shed ``pct`` of portfolio value, capped at what
        # is actually held so a large target weight liquidates rather than errors.
        pct = (cfg.position_size_pct or 100) / 100.0
        return min(cfg.round_units((prev_portfolio_value * pct) / price), prev_units)
    state.position_size = max(state.position_size - cfg.position_scaling, 0)
    raw = ctx.size_position(prev_portfolio_value, price, bar)
    return min(cfg.round_units(raw * (1 - state.position_size)), prev_units)


def fill_buy(
    ctx: SymbolContext, bar: int, qty: float, price: float,
    order_type: str = 'market', reason: str = 'signal', group: Optional[str] = None,
    order_id: int = 0,
) -> None:
    """Apply a buy of *qty* at *price* (pre-slippage) to the position and ledgers."""
    cfg, state = ctx.cfg, ctx.state
    prev_units = state.units
    ctx.units_to_buy[bar] += qty
    execution_price = price * (1 + cfg.slippage_pct)
    value = qty * execution_price
    fee = value * cfg.fee_rate

    state.units = prev_units + qty
    ctx.account.debit(value + fee)
    state.avg_entry = ((state.avg_entry * prev_units) + value) / state.units
    state.cost_basis = ((state.cost_basis * prev_units) + value + fee) / state.units

    if cfg.strategy_mode == 'accumulation':
        state.trailing_stop = np.inf  # No trailing stop for accumulation
    else:
        level = ctx.long_stop_level(bar, price)
        # Scaling into an existing position must never loosen a stop that has
        # already ratcheted up; only a fresh entry sets the level outright.
        state.trailing_stop = max(state.trailing_stop, level) if prev_units > 0 else level

    record_entry(ctx, bar, qty, value, fee, order_type)
    log_fill(ctx, bar, 'buy', qty, price, order_type, reason, group, order_id)


def fill_sell(
    ctx: SymbolContext, bar: int, qty: float, price: float,
    order_type: str = 'market', reason: str = 'signal', group: Optional[str] = None,
    order_id: int = 0,
) -> None:
    """Apply a partial sell of *qty* at *price* (pre-slippage). Not a liquidation.

    A sell that happens to take the last unit resets the entry bookkeeping but
    deliberately leaves ``position_size`` where the scale-out ramp put it —
    that is the discretionary path, and it differs from :func:`close_position`,
    which is a risk exit and zeroes the ramp.
    """
    cfg, state = ctx.cfg, ctx.state
    prev_units = state.units
    ctx.units_to_sell[bar] += qty
    execution_price = price * (1 - cfg.slippage_pct)
    value = qty * execution_price
    fee = value * cfg.fee_rate

    state.units = prev_units - qty
    ctx.account.credit(value - fee)

    if state.units <= UNIT_EPS:
        state.units = 0.0
        state.trailing_stop = np.inf
        state.avg_entry = 0.0
        state.cost_basis = 0.0
    else:
        state.trailing_stop = max(
            state.trailing_stop, ctx.long_stop_level(bar, price)
        )

    record_exit(ctx, bar, qty, value, fee, reason, order_type)
    log_fill(ctx, bar, 'sell', qty, price, order_type, reason, group, order_id)


# --------------------------------------------------------------------------- #
# Signals
# --------------------------------------------------------------------------- #

def arm_buy_cooldown(ctx: SymbolContext) -> None:
    """Start the post-buy cooldown. Armed when the order is *placed*, not filled."""
    cfg, state = ctx.cfg, ctx.state
    if cfg.consecutive_signal_mode in ('cooldown', 'reset_cooldown') and cfg.cooldown_bars > 0:
        state.buy_cooldown = cfg.cooldown_bars + 1
    if cfg.consecutive_signal_mode == 'reset_cooldown':
        state.buy_wait_reset = True


def arm_sell_cooldown(ctx: SymbolContext) -> None:
    """Start the post-sell cooldown. Armed when the order is *placed*, not filled."""
    cfg, state = ctx.cfg, ctx.state
    if cfg.consecutive_signal_mode in ('cooldown', 'reset_cooldown') and cfg.cooldown_bars > 0:
        state.sell_cooldown = cfg.cooldown_bars + 1
    if cfg.consecutive_signal_mode == 'reset_cooldown':
        state.sell_wait_reset = True


def signal_order_prices(cfg: EngineConfig, side: str, close_price: float) -> dict:
    """Where a signal-driven resting order rests, relative to the signal's close.

    Both offsets are fractions of the reference close and both are *patient* in
    the direction that makes the order type mean something:

    * a **limit** buy rests ``limit_offset`` below the close and a limit sell
      the same distance above it — you are asking for a better price than the
      market is offering, and accepting that it may never come;
    * a **stop** buy rests ``stop_offset`` above the close and a stop sell the
      same distance below — you are asking for confirmation that the move
      continued, and paying for it in entry price;
    * a **stop-limit** combines them: the stop is placed as above, and the limit
      sits ``limit_offset`` beyond it as a cap on how much slippage you will
      accept once it triggers.

    Returns the keys ``limit_price``, ``stop_price`` and ``reference`` — the
    last being the price to size the order against (always the worst of the
    levels involved, so the notional cannot come in above what was asked for).
    """
    limit_off = cfg.limit_offset
    stop_off = cfg.stop_offset
    kind = cfg.order_type

    if kind == 'limit':
        price = close_price * (1 - limit_off) if side == 'buy' else close_price * (1 + limit_off)
        return {'limit_price': price, 'stop_price': None, 'reference': price}

    if kind == 'stop':
        price = close_price * (1 + stop_off) if side == 'buy' else close_price * (1 - stop_off)
        return {'limit_price': None, 'stop_price': price, 'reference': price}

    if kind == 'stop_limit':
        if side == 'buy':
            stop_price = close_price * (1 + stop_off)
            limit_price = stop_price * (1 + limit_off)
        else:
            stop_price = close_price * (1 - stop_off)
            limit_price = stop_price * (1 - limit_off)
        return {
            'limit_price': limit_price,
            'stop_price': stop_price,
            # Size against the limit: it is the worst price this order can get.
            'reference': limit_price,
        }

    return {'limit_price': None, 'stop_price': None, 'reference': close_price}


def submit_signal_order(
    ctx: SymbolContext, bar: int, side: str, qty: float, prices: dict,
) -> None:
    """Rest a signal-driven order, replacing any working order on the same side.

    One working entry (or discretionary exit) per side at a time. Without that
    rule a run of buy signals would stack orders that were each sized against
    cash the others also intend to spend, and a quiet week would end with the
    book holding six overlapping entries.
    """
    cfg = ctx.cfg
    ctx.book.cancel_where(side=side, reason='signal', why='replaced')
    ctx.book.submit(Order(
        side=side,
        order_type=cfg.order_type,
        qty=qty,
        limit_price=prices['limit_price'],
        stop_price=prices['stop_price'],
        tif=cfg.time_in_force,
        expire_bars=cfg.order_expiry_bars or None,
        reason='signal',
        created_bar=bar,
        created_session=int(ctx.session_id[bar]),
    ))


def execute_buy(
    ctx: SymbolContext, bar: int, prev_portfolio_value: float
) -> Optional[PendingBuy]:
    """Turn an accepted buy signal into a pending market buy, or a resting order.

    A market buy is sized here against the bar's close but not filled: it comes
    back as a :class:`PendingBuy`, and the loop clamps it to cash once every
    symbol's sells for the bar are in. With one symbol that clamp is exactly the
    affordability check this function used to apply itself.

    Any other order type sizes against the level the order will rest at, clamps
    to the cash the bar opened with, and submits it to the book; the bar itself
    sees no fill.
    """
    ctx.buy_triggered[bar] = True
    ctx.buy_signal_counter[bar] = ctx.buy_signal_counter[bar - 1] + 1

    close_price = ctx.close_prices[bar]
    if not np.isfinite(close_price) or close_price <= 0:
        hold(ctx, bar)
        return None

    prices = signal_order_prices(ctx.cfg, 'buy', close_price)
    reference = prices['reference']
    qty = size_buy(ctx, bar, prev_portfolio_value, reference)

    if ctx.cfg.order_type == 'market':
        if qty <= 0:
            hold(ctx, bar)
            return None
        return PendingBuy(ctx=ctx, bar=bar, qty=qty, price=close_price)

    if qty > 0:
        affordable = affordable_units(ctx, reference, ctx.account.bar_cash)
        qty = 0.0 if affordable <= 0 else min(qty, affordable)

    if qty <= 0:
        hold(ctx, bar)
        return None

    submit_signal_order(ctx, bar, 'buy', qty, prices)
    arm_buy_cooldown(ctx)
    # The signal was consumed but nothing traded, so the stop still has to
    # ratchet on this bar like any other no-fill bar.
    hold(ctx, bar)
    return None


def execute_sell(ctx: SymbolContext, bar: int, prev_portfolio_value: float) -> None:
    """Turn an accepted sell signal into a fill at the close, or a resting order."""
    ctx.sell_triggered[bar] = True

    if ctx.holding_period[bar] < ctx.cfg.min_holding_period:
        hold(ctx, bar)
        return

    ctx.sell_signal_counter[bar] = ctx.sell_signal_counter[bar - 1] + 1
    close_price = ctx.close_prices[bar]

    if not np.isfinite(close_price) or close_price <= 0:
        hold(ctx, bar)
        return

    prices = signal_order_prices(ctx.cfg, 'sell', close_price)
    qty = size_sell(ctx, bar, prev_portfolio_value, prices['reference'])

    if qty <= 0:
        hold(ctx, bar)
        return

    if ctx.cfg.order_type == 'market':
        fill_sell(ctx, bar, qty, close_price)
        arm_sell_cooldown(ctx)
        return

    submit_signal_order(ctx, bar, 'sell', qty, prices)
    arm_sell_cooldown(ctx)
    hold(ctx, bar)


def process_signals(
    ctx: SymbolContext, bar: int, prev_portfolio_value: float
) -> Optional[PendingBuy]:
    """Gate the lagged signals through the consecutive-signal policy and route.

    The signal read for bar ``i`` is the one printed on bar ``i - delay``; edge
    detection compares that bar against ``i - delay - 1``. When both a buy and a
    sell survive gating the buy wins (see :mod:`lib.strategy`'s docstring).
    """
    cfg, state = ctx.cfg, ctx.state
    signal_bar = bar - cfg.delay
    prev_signal_bar = signal_bar - 1

    current_buy = bool(ctx.buy_signal_raw[signal_bar])
    current_sell = bool(ctx.sell_signal_raw[signal_bar])
    prev_buy = bool(ctx.buy_signal_raw[prev_signal_bar]) if prev_signal_bar >= 0 else False
    prev_sell = bool(ctx.sell_signal_raw[prev_signal_bar]) if prev_signal_bar >= 0 else False

    mode = cfg.consecutive_signal_mode
    if mode == 'reset_cooldown':
        if not current_buy:
            state.buy_wait_reset = False
        if not current_sell:
            state.sell_wait_reset = False

    if mode == 'edge':
        allow_buy = current_buy and not prev_buy
        allow_sell = current_sell and not prev_sell
    elif mode == 'cooldown':
        allow_buy = current_buy and state.buy_cooldown == 0
        allow_sell = current_sell and state.sell_cooldown == 0
    elif mode == 'reset_cooldown':
        allow_buy = current_buy and state.buy_cooldown == 0 and not state.buy_wait_reset
        allow_sell = current_sell and state.sell_cooldown == 0 and not state.sell_wait_reset
    else:
        allow_buy = current_buy
        allow_sell = current_sell

    if current_buy and not allow_buy:
        ctx.buy_rejected[bar] = True
    if current_sell and not allow_sell:
        ctx.sell_rejected[bar] = True

    if allow_buy:
        return execute_buy(ctx, bar, prev_portfolio_value)
    if cfg.strategy_mode != 'accumulation' and allow_sell:
        execute_sell(ctx, bar, prev_portfolio_value)
    else:
        hold(ctx, bar)
    return None
