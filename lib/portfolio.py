"""Backtest a basket of symbols against one cash account (roadmap 3.8.3 / 3.8.4).

:func:`backtest_portfolio` takes a :class:`lib.panel.Panel` — many symbols on one
index, holes labelled — and runs it through the same bar loop as
:func:`lib.strategy.backtest`, with one :class:`~lib.engine.state.SymbolContext`
per member instead of one in total. Everything that makes a basket different
from N separate runs is decided in
[docs/portfolio-semantics.md](../docs/portfolio-semantics.md) and implemented in
:mod:`lib.engine`:

* **one cash account**, sized off **total** portfolio value from the previous bar;
* **phase-major bars** — every symbol's sells settle before any symbol buys, so
  a same-bar sale funds a same-bar buy;
* **equal-share water-fill** (``CASH_ALLOCATION_RULE``) when buys outrun cash;
* a symbol with no bar is **valued, not traded**.

Nothing about the result depends on the order of :attr:`Panel.symbols`: cash is
settled with exactly-rounded sums and the allocation rule is symmetric, so
reversing the ticker list reproduces every unit, every round trip and every
balance to the last bit. (Fill ``order_id`` values are submission counters and
do renumber; they only ever break ties inside one symbol's book.)

**The result shape is provisional.** :class:`PortfolioResult` exists so the
engine can be exercised and tested now; the multi-symbol ledger, the
``Buy_Unfunded`` column (3.8.5), the external contract (3.8.6) and the
portfolio-level metrics (3.8.7) will settle what callers finally read. Nothing
outside ``lib/tests`` should depend on it yet.
"""

from __future__ import annotations

import inspect
from dataclasses import dataclass, field
from typing import Any, Dict, List, Mapping, Union

import numpy as np
import pandas as pd

from lib.engine.errors import BacktestError, ValidationError
from lib.engine.loop import run_bars
from lib.engine.results import calculate_returns, market_returns
from lib.engine.setup import (
    build_symbol,
    resolve_config,
    symbol_result_frame,
    validate_backtest_inputs,
)
from lib.engine.state import Account
from lib.metrics.ledger import TRADE_COLUMNS
from lib.orders import FILL_COLUMNS
from lib.panel import MARK_COLUMN, TRADABLE_COLUMN, Panel, align_panel
from lib.sessions import SESSION_START_COLUMN
from lib.strategy import backtest

# Arguments resolved once for the basket, and those resolved per symbol. Their
# defaults are read off backtest()'s signature, so the two entry points cannot
# drift apart on what an omitted option means.
_CONFIG_OPTIONS = tuple(inspect.signature(resolve_config).parameters)
_SYMBOL_OPTIONS = (
    'use_signal_strength', 'indicator_weights', 'buy_threshold', 'sell_threshold',
    'signal_logic', 'signal_window', 'trailing_stop_loss', 'stop_mode',
    'volatility_window', 'allow_fractional', 'use_low_for_stops', 'gap_fills',
)
_DEFAULTS = {
    name: param.default
    for name, param in inspect.signature(backtest).parameters.items()
    if param.default is not inspect.Parameter.empty
}


# eq=False: DataFrames do not answer ==. Compare the parts you mean.
@dataclass(frozen=True, eq=False)
class PortfolioResult:
    """What a basket backtest produced. Provisional — see the module docstring.

    Attributes:
        symbols: The basket, in panel order.
        portfolio: One row per panel bar — ``Cash_Value``, ``Stocks_Value``,
            ``Portfolio_Value``, ``Strategy_Returns``, ``Cumulative_Returns``,
            ``Session_Start``, and ``Returns`` / ``Cumulative_Market_Returns``
            for the equal-weight buy-and-hold benchmark of the same basket
            (§7). ``attrs['trades']`` is :attr:`trades`, so
            :func:`lib.metrics.compute_metrics` reads the frame as it reads a
            single-symbol result.
        frames: Each symbol's result frame, shaped like :func:`lib.strategy.backtest`'s.
            ``Units``, ``Stocks_Value``, the trigger flags and the ledgers are
            the symbol's own; ``Cash_Value``, ``Portfolio_Value`` and
            ``Strategy_Returns`` are the shared account's.
        trades: Every symbol's round trips, with a leading ``symbol`` column,
            ordered by entry bar then symbol.
        fills: Every symbol's executions, with a leading ``symbol`` column,
            ordered by bar then symbol.
    """
    symbols: tuple
    portfolio: pd.DataFrame = field(repr=False)
    frames: Dict[str, pd.DataFrame] = field(repr=False)
    trades: pd.DataFrame = field(repr=False)
    fills: pd.DataFrame = field(repr=False)

    def frame(self, symbol: str) -> pd.DataFrame:
        try:
            return self.frames[symbol]
        except KeyError:
            raise KeyError(
                f"{symbol!r} is not in this basket ({', '.join(self.symbols)})"
            ) from None


def _resolve_options(options: Mapping[str, Any]) -> Dict[str, Any]:
    unknown = sorted(set(options) - set(_DEFAULTS))
    if unknown:
        raise ValidationError(
            f"Unknown backtest option(s): {', '.join(unknown)}. "
            "backtest_portfolio accepts the same keyword options as backtest()."
        )
    return {**_DEFAULTS, **options}


def equal_weight_benchmark(panel: Panel) -> np.ndarray:
    """Per-bar returns of equal-weight buy-and-hold over *panel* (§7).

    The capital is split equally across the basket. Each sleeve buys its symbol
    at the close of that symbol's first tradable bar, holds it marked at
    ``Mark`` for the rest of the panel, and is never rebalanced; until then it
    sits in cash. No costs are charged, as for the single-symbol ``Returns``
    column this replaces. A one-symbol panel therefore reproduces that symbol's
    own buy-and-hold return.
    """
    num_rows = len(panel)
    weight = 1.0 / len(panel.symbols)
    sleeves = []
    # Sorted, so the summation — and its last bit — ignores the panel's order.
    for symbol in sorted(panel.symbols):
        frame = panel.frame(symbol)
        tradable = frame[TRADABLE_COLUMN].to_numpy(dtype=bool)
        close = frame['Close'].to_numpy(dtype=float)
        sleeve = np.full(num_rows, weight)
        usable = np.flatnonzero(tradable & (close > 0))
        if usable.size:
            first = int(usable[0])
            marks = frame[MARK_COLUMN].to_numpy(dtype=float)
            sleeve[first:] = weight * marks[first:] / close[first]
        sleeves.append(sleeve)
    value = np.sum(np.vstack(sleeves), axis=0)
    return market_returns(value)


def _combined_ledger(
    frames: Mapping[str, pd.DataFrame], key: str, columns, sort_by: List[str]
) -> pd.DataFrame:
    parts = []
    for symbol, frame in frames.items():
        ledger = frame.attrs[key]
        if len(ledger):
            ledger = ledger.copy()
            ledger.insert(0, 'symbol', symbol)
            parts.append(ledger)
    if not parts:
        return pd.DataFrame(columns=['symbol', *columns])
    combined = pd.concat(parts, ignore_index=True)
    return combined.sort_values(sort_by, kind='mergesort').reset_index(drop=True)


def backtest_portfolio(
    panel: Union[Panel, Mapping[str, pd.DataFrame]],
    initial_capital: float,
    position_sizing_strategy: str,
    position_sizing_params: dict,
    buy_indicators: List[str],
    sell_indicators: List[str],
    **options: Any,
) -> PortfolioResult:
    """Backtest every symbol in *panel* against one shared cash account.

    Args:
        panel: A :class:`~lib.panel.Panel`, or ``{symbol: frame}`` which is
            aligned with :func:`~lib.panel.align_panel` defaults. Every member
            must already carry the ``buy_indicators`` / ``sell_indicators``
            columns — enrich each symbol on its own tape before aligning.
        initial_capital: Starting cash for the whole basket.
        position_sizing_strategy, position_sizing_params: As for
            :func:`lib.strategy.backtest`, applied per symbol against the
            **total** portfolio value.
        buy_indicators, sell_indicators: Signal columns, the same names for
            every symbol (one strategy config for the basket, §9).
        **options: Any keyword option :func:`lib.strategy.backtest` accepts,
            with the same defaults — except ``position_size_pct``, which
            defaults to the equal weight ``100 / len(symbols)`` (§2). It is a
            per-symbol target weight of total portfolio value and an explicit
            value is **not** normalised: five symbols each asking for 100%
            compete for the cash under ``CASH_ALLOCATION_RULE`` rather than
            being rescaled to 20%.

    Returns:
        A :class:`PortfolioResult`.

    Raises:
        ValidationError: On an invalid option, capital, panel or member frame.
        BacktestError: If the run fails part-way.
    """
    try:
        opts = _resolve_options(options)
        if not isinstance(panel, Panel):
            if not isinstance(panel, Mapping):
                raise ValidationError(
                    f"panel must be a Panel or a mapping of frames, got {type(panel).__name__}"
                )
            panel = align_panel(panel)
        if 'position_size_pct' not in options:
            opts['position_size_pct'] = 100 / len(panel.symbols)

        for symbol in panel.symbols:
            try:
                validate_backtest_inputs(
                    panel.frame(symbol), initial_capital, buy_indicators, sell_indicators
                )
            except ValidationError as exc:
                raise ValidationError(f"{symbol}: {exc}") from None

        cfg = resolve_config(**{name: opts[name] for name in _CONFIG_OPTIONS})
        account = Account(cash=float(initial_capital))
        contexts = [
            build_symbol(
                symbol, panel.frame(symbol), cfg, account,
                position_sizing_strategy=position_sizing_strategy,
                position_sizing_params=position_sizing_params,
                buy_indicators=buy_indicators,
                sell_indicators=sell_indicators,
                **{name: opts[name] for name in _SYMBOL_OPTIONS},
            )
            for symbol in panel.symbols
        ]

        tape = run_bars(cfg, account, contexts, len(panel))

        frames = {
            ctx.symbol: symbol_result_frame(ctx, tape.cash_value, tape.portfolio_value)
            for ctx in contexts
        }
        trades = _combined_ledger(frames, 'trades', TRADE_COLUMNS, ['entry_bar', 'symbol'])
        fills = _combined_ledger(frames, 'fills', FILL_COLUMNS, ['bar', 'symbol'])

        benchmark = equal_weight_benchmark(panel)
        strategy_returns, cumulative_returns, cumulative_market_returns = calculate_returns(
            tape.portfolio_value, benchmark
        )
        portfolio = pd.DataFrame(
            {
                'Cash_Value': tape.cash_value,
                'Stocks_Value': tape.stocks_value,
                'Portfolio_Value': tape.portfolio_value,
                'Returns': benchmark,
                'Strategy_Returns': strategy_returns,
                'Cumulative_Returns': cumulative_returns,
                'Cumulative_Market_Returns': cumulative_market_returns,
                SESSION_START_COLUMN: panel.session_start,
            },
            index=panel.index,
        )
        portfolio.attrs['trades'] = trades
        portfolio.attrs['fills'] = fills
        portfolio.attrs['symbols'] = tuple(panel.symbols)
        portfolio.attrs['order_type'] = cfg.order_type
        portfolio.attrs['time_in_force'] = cfg.time_in_force
        portfolio.attrs['trailing_stop_orders'] = cfg.trailing_stop_orders
        portfolio.attrs['use_brackets'] = cfg.use_brackets

        return PortfolioResult(
            symbols=tuple(panel.symbols),
            portfolio=portfolio,
            frames=frames,
            trades=trades,
            fills=fills,
        )
    except ValidationError:
        raise
    except Exception as exc:
        raise BacktestError(f"Portfolio backtest failed: {exc}") from exc


__all__ = ['PortfolioResult', 'backtest_portfolio', 'equal_weight_benchmark']
