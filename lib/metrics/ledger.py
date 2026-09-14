"""The round-trip trade ledger: its vocabulary and its frame shape.

This module owns the ledger *names* so that :mod:`lib.metrics` can read a
ledger without importing :mod:`lib.strategy`, which imports metrics back.
``lib.strategy`` is the only writer; it imports from here and re-exports
``TRADE_COLUMNS`` / ``trades_to_frame`` for callers that predate the split.

The engine attaches the ledger to its result frame as
``result_df.attrs['trades']``. One row per round trip, in entry order.

Field semantics, fixed here once:

``entry_bar`` / ``exit_bar``
    Positional indices into the result frame.
``units``
    Total units bought across the round trip. Scale-ins collapse into one row,
    so this is not the size of any single fill.
``avg_entry_price``
    Fee-exclusive average execution price.
``avg_cost_basis``
    The same average with entry fees folded in.
``exit_reason``
    One of :data:`EXIT_REASONS`, naming the *decision* that ended the trade —
    not the mechanism that executed it. A sell signal worked as a limit order
    still reads ``'signal'``; ``entry_order_type`` / ``exit_order_type`` carry
    the mechanism. ``'bracket_stop'`` and ``'bracket_target'`` are the two legs
    of an OCO bracket, and they are distinct reasons because a bracket's stop
    is not the trailing stop and its target is not ``take_profit``: both are
    fixed at entry and neither moves. ``'open'`` marks the position still held
    on the final bar; it is marked to market at that bar's close so the ledger
    reconciles with the equity curve, and it is excluded from every realised
    statistic (win rate, profit factor, expectancy).
``entry_order_type`` / ``exit_order_type``
    The order type that actually executed each side — one of
    :data:`lib.orders.ORDER_TYPES`. ``'market'`` throughout is the engine's
    default and means every fill was taken at a bar's close. Scale-ins collapse
    into one row like everything else, so ``entry_order_type`` records the
    *first* entry fill's type and ``exit_order_type`` the *last* exit fill's.
``net_pnl``
    ``gross_pnl - fees``, where ``fees`` covers entry and exit commission,
    FX fee and slippage.
``holding_bars``
    ``exit_bar - entry_bar``: bars of tape, so it never counts the hours the
    market was shut. Five 1h bars is five hours of trading whether or not a
    weekend fell in the middle.
``holding_sessions``
    Session boundaries the round trip crossed, from :mod:`lib.sessions`. ``0``
    means the trade opened and closed inside one session; on a daily tape it
    equals ``holding_bars``. This is the field that says whether a position was
    held overnight — ``holding_bars`` cannot.
"""

from __future__ import annotations

from typing import Sequence, Union

import pandas as pd

# Reasons a round trip can end, as written to the trade ledger.
EXIT_REASONS = (
    'signal', 'trailing_stop', 'take_profit', 'bracket_stop', 'bracket_target', 'open',
)

# Column order of the trade ledger attached as ``result_df.attrs['trades']``.
# The two order-type columns are appended last so that older readers indexing
# by position keep working.
TRADE_COLUMNS = (
    'entry_bar', 'entry_date', 'exit_bar', 'exit_date', 'units',
    'avg_entry_price', 'avg_cost_basis', 'exit_price', 'exit_reason',
    'gross_pnl', 'net_pnl', 'fees', 'holding_bars', 'holding_sessions', 'is_open',
    'entry_order_type', 'exit_order_type',
)


def trades_to_frame(trades: Union[pd.DataFrame, Sequence[dict], None]) -> pd.DataFrame:
    """Build the trade-ledger DataFrame, with stable columns even when empty."""
    if isinstance(trades, pd.DataFrame):
        trades = trades.to_dict('records')
    if not trades:
        return pd.DataFrame(columns=list(TRADE_COLUMNS))
    return pd.DataFrame(list(trades), columns=list(TRADE_COLUMNS))
