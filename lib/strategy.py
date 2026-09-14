# Strategy module with backtesting engine
"""
Backtesting engine for trading strategies with comprehensive error handling,
logging, and optimized operations for performance.

This module is the public entry point; the engine's internals live in
:mod:`lib.engine`, and everything callers have always imported from here is
re-exported. :func:`backtest` runs one symbol; :func:`lib.portfolio.backtest_portfolio`
runs a basket through the same loop.

Execution model (read this before interpreting any result)
----------------------------------------------------------
* **Signal lag.** Bar ``i`` is executed against the signal observed on bar
  ``i - delay``. With the default ``delay=1`` a signal printed on bar ``t`` is
  filled at bar ``t+1``'s close, so the engine never trades on information it
  could not have had. ``delay=0`` fills on the signal bar itself and is
  look-ahead by construction — use it only for diagnostics.
* **Order types.** By default every order is a market order and fills at a
  bar's close, which is what every result before roadmap 3.7 assumed.
  ``order_type='limit' | 'stop' | 'stop_limit'`` instead *rests* the order in a
  book (:mod:`lib.orders`) and lets a later bar's High/Low decide whether it
  trades at all. A resting order is worked at the start of each bar, before
  that bar's own signals, because it was placed earlier; a fill consumes the
  bar the way a trailing-stop exit always has. Nothing is reserved when an
  order is placed — quantities are re-clamped to the cash and units available
  at fill time, which is the one place this model is kinder than a broker.
  ``time_in_force`` and ``order_expiry_bars`` decide how long it waits, counted
  from the first bar it could actually trade against.
* **Where a resting order rests.** ``limit_offset_pct`` puts a limit that far
  *away* from the signal bar's close (buys below, sells above); ``stop_offset_pct``
  puts a stop that far *beyond* it (buy stops above, sell stops below). Orders
  are sized against the level they will fill at, not against the close, so the
  notional that lands is the notional that was asked for. One working
  signal-driven order per side at a time: a new signal replaces the old order
  rather than stacking a second one against the same cash.
* **Exits as orders.** ``trailing_stop_orders=True`` expresses the trailing
  stop as a resting sell stop instead of the close-based check below — the
  level still ratchets every bar, but it is tested against ``Low`` and fills at
  the stop, which is stricter and usually worse. ``use_brackets=True`` attaches
  an OCO pair to every entry, fixed at the average entry price, and whichever
  leg trades cancels the other. A working bracket owns the exits: the built-in
  trailing stop is skipped, and so is ``take_profit`` when a target leg exists.
  Both flags change results and both are off by default.
* **Two orders touched on one bar.** OHLC cannot say which came first, so the
  book applies a stated, pessimistic rule: orders marketable at the open fill
  first, then stops before limits, then nearest the open. A bar that touches
  both legs of a bracket is therefore scored as the stop — ranking the
  profitable leg first would make every wide bracket look free.
* **Simultaneous buy and sell.** Buy wins. The branches are ordered
  ``if allow_buy: ... elif allow_sell: ...``, so a bar carrying both an accepted
  buy and an accepted sell is treated as a buy and the sell is dropped silently
  (it is *not* flagged in ``Sell_Trigger_Rejected``).
* **Exits versus ``min_holding_period``.** The trailing stop ignores
  ``min_holding_period`` — a risk exit that waits is not a risk exit. Take
  profit and discretionary sell signals both respect it.
* **Intrabar stop breaches.** By default the trailing stop is compared against
  ``Close`` only, so a bar that traded through the stop and recovered by the
  close is not treated as an exit. That is optimistic. Pass
  ``use_low_for_stops=True`` to test the breach against ``Low`` instead; the
  fill is then taken at ``min(stop_level, Close)``, which charges the stop level
  on an intrabar breach and the (worse) close on a gap-down.
  ``trailing_stop_orders=True`` is the newer and stricter answer to the same
  question: the stop becomes a resting order and fills at the stop level itself,
  or at the ``Open`` when the market gapped through it — never at a close that
  had recovered.
* **Sessions and overnight gaps.** The loop is positionally indexed, but it is
  no longer session-blind. ``lib.sessions`` infers where each trading session
  begins from the timestamps (every bar on a daily tape; the overnight step on
  an intraday one), and that mask is exposed as the ``Session_Start`` column.
  A caller holding a real exchange calendar can supply the column instead.
* **Gap fills.** On a session's first bar, a market that reopens at or below
  the trailing stop has *gapped through* it — the stop could not be worked
  while the exchange was shut, so it becomes a market order and fills at the
  **open**, not at the close and not at the stop level. This is what
  ``gap_fills=True`` (the default) does, and it applies in both stop modes;
  ``gap_fills=False`` restores the pre-3.9 close-only behaviour.
* **Holding period is session time.** ``Holding_Period`` and the ledger's
  ``holding_bars`` count *bars of tape*, so they never include the hours a
  market was shut — five 1h bars is five hours of trading even when a weekend
  falls in the middle. ``Holding_Sessions`` and the ledger's
  ``holding_sessions`` report how many session boundaries the trade crossed,
  which is the number that tells you whether it was held overnight.
  ``min_holding_period`` is counted in bars.
* **Cost basis versus entry price.** ``Avg_Entry_Price`` is the average
  execution price excluding fees; ``Avg_Cost_Basis`` is the same average with
  entry commission, FX fee and slippage folded in. ``take_profit`` triggers off
  ``Avg_Entry_Price``, so a 10% take profit fires on a 10% *price* move and the
  realised net return is slightly lower once round-trip fees are paid.
* **Many symbols, one account.** Each bar runs phase by phase across the basket
  — every symbol's sells, then every symbol's buys — so a same-bar sale funds a
  same-bar buy, and buys that outrun the cash share it by
  ``CASH_ALLOCATION_RULE`` (:mod:`lib.engine.allocation`). A bar a symbol did
  not print is valued at its carried-forward mark and never traded. With one
  symbol all of this reduces to the rules above, bar for bar.
  [docs/portfolio-semantics.md](../docs/portfolio-semantics.md) is the full model.
"""

import logging
from typing import Dict, List, Optional, Sequence, Union

import pandas as pd

from lib.engine.errors import BacktestError, ValidationError
from lib.engine.loop import run_bars
from lib.engine.results import calculate_returns, create_result_dataframe
from lib.engine.setup import (
    ATR_STOP_COLUMN,
    CONSECUTIVE_SIGNAL_MODES,
    STOP_MODES,
    STRATEGY_MODES,
    build_symbol,
    resolve_config,
    symbol_result_frame,
    validate_backtest_inputs,
)
from lib.engine.signal_inputs import calculate_signal_strengths
from lib.engine.sizing import (
    atr_risk_based,
    fixed_dollar_amount,
    get_position_sizer,
    kelly_criterion,
    percentage_of_portfolio,
    risk_based,
    volatility_based,
)
from lib.engine.state import Account

# The ledger's shape lives in lib.metrics.ledger so the metrics engine can read
# a ledger without importing this module. EXIT_REASONS and TRADE_COLUMNS are
# there too, for anyone who needs the vocabulary.
from lib.metrics.ledger import trades_to_frame

# ``ORDER_TYPES`` and ``TIME_IN_FORCE`` are re-exported from here, so a caller
# configuring the engine has one import for the whole execution vocabulary.
# lib.orders owns the definitions.
from lib.orders import ORDER_TYPES, TIME_IN_FORCE

# Configure module logger
logger = logging.getLogger(__name__)

__all__ = [
    'ATR_STOP_COLUMN', 'BacktestError', 'CONSECUTIVE_SIGNAL_MODES', 'ORDER_TYPES',
    'STOP_MODES', 'STRATEGY_MODES', 'TIME_IN_FORCE', 'ValidationError',
    'atr_risk_based', 'backtest', 'calculate_metrics', 'calculate_returns',
    'calculate_signal_strengths', 'create_result_dataframe', 'fixed_dollar_amount',
    'get_position_sizer', 'kelly_criterion', 'percentage_of_portfolio', 'risk_based',
    'run_backtest', 'validate_backtest_inputs', 'volatility_based',
]


def backtest(
    df: pd.DataFrame,
    initial_capital: float,
    position_sizing_strategy: str,
    position_sizing_params: dict,
    buy_indicators: List[str],
    sell_indicators: List[str],
    use_signal_strength: bool = False,
    indicator_weights: Optional[Dict[str, float]] = None,
    buy_threshold: float = 0.5,
    sell_threshold: float = 0.5,
    delay: int = 1,
    min_holding_period: int = 0,
    position_scaling: float = 0.25,
    trailing_stop_loss: float = 0.05,
    stop_mode: str = 'percent',
    volatility_window: int = 20,
    strategy_mode: str = 'trading',
    amount_per_buy: Optional[float] = None,
    position_size_pct: float = 100,
    take_profit: float = 0.0,
    signal_logic: str = 'or',
    signal_window: int = 0,
    consecutive_signal_mode: str = 'scale_in',
    cooldown_bars: int = 0,
    commission_per_trade: float = 0.0,
    slippage_pct: float = 0.0005,
    fx_fee_pct: float = 0.0015,
    use_low_for_stops: bool = False,
    gap_fills: bool = True,
    allow_fractional: bool = False,
    order_type: str = 'market',
    limit_offset_pct: float = 0.002,
    stop_offset_pct: float = 0.002,
    time_in_force: str = 'gtc',
    order_expiry_bars: int = 0,
    trailing_stop_orders: bool = False,
    use_brackets: bool = False,
    bracket_stop_pct: float = 0.0,
    bracket_target_pct: float = 0.0
) -> pd.DataFrame:
    """
    Run a backtest on the provided DataFrame.

    The module docstring documents the execution model this function implements:
    signal lag, buy-wins tie-breaking, which exits respect ``min_holding_period``,
    the close-only stop check, and the cost-basis/entry-price split.

    Args:
        df: DataFrame with OHLCV data and signal columns.
        initial_capital: Starting capital for the backtest.
        position_sizing_strategy: Strategy for determining position sizes.
        position_sizing_params: Parameters for the position sizing strategy.
        buy_indicators: List of column names containing buy signals.
        sell_indicators: List of column names containing sell signals.
        use_signal_strength: Whether to use weighted signal strength.
        indicator_weights: Weights for each indicator when using signal strength.
        buy_threshold: Threshold for buy signal strength to trigger a buy.
        sell_threshold: Threshold for sell signal strength to trigger a sell.
        delay: Bars of lag between a signal printing and its fill. ``delay=1``
            (the default) fills bar ``t``'s signal at bar ``t+1``'s close;
            ``delay=0`` fills on the signal bar itself and is look-ahead.
        min_holding_period: Minimum number of periods to hold a position.
        position_scaling: Factor for scaling position size on repeated signals.
        trailing_stop_loss: Trailing stop loss percentage (used by stop_mode='percent',
            and as the per-bar fallback when an ATR stop level is unusable).
        stop_mode: 'percent' for a fixed percentage trail, or 'atr' to drive the trail
            from the ``ATR_Stop_Long`` column written by ATR_TradingStrategy. Falls
            back to 'percent' with a warning when that column is unavailable.
        volatility_window: Window for volatility calculation.
        strategy_mode: 'trading' (buy/sell cycles), 'accumulation' (DCA), or 'rebalancing' (partial).
        amount_per_buy: Fixed dollar amount per buy signal (for accumulation mode).
        position_size_pct: Percentage of portfolio per trade (for rebalancing mode).
        take_profit: Take profit percentage (0 disables), measured against the
            fee-exclusive average entry price.
        signal_logic: 'or' (any signal triggers) or 'and' (all signals must agree).
        signal_window: Window size (candles) for AND confirmation across signals.
        consecutive_signal_mode: How to handle repeated triggers ('scale_in', 'edge', 'cooldown', 'reset_cooldown').
        cooldown_bars: Bars to wait between same-direction triggers (used by cooldown
            modes). ``cooldown_bars=N`` blocks exactly the N bars following a fill.
        commission_per_trade: Commission fee as % of trade notional (0.001 = 0.1%).
        slippage_pct: Slippage as % of price (0.0005 = 5 bps).
        fx_fee_pct: FX fee as % of notional (Trading 212 UK default 0.15%).
        use_low_for_stops: Test trailing-stop breaches against ``Low`` rather than
            ``Close``. Requires a ``Low`` column; falls back to ``Close`` with a
            warning when absent.
        gap_fills: On the first bar of a session, fill a breached trailing stop
            at the ``Open`` rather than the ``Close`` — the market gapped
            through the stop while it could not be worked. Requires an ``Open``
            column; silently inactive without one. Session boundaries come from
            ``lib.sessions``, or from a ``Session_Start`` column on ``df``.
        allow_fractional: Permit fractional share quantities (Trading 212 supports
            them). Default False keeps whole-share truncation.
        order_type: How an accepted signal is worked — ``'market'`` (the
            default: fill at the bar's close, the only behaviour the engine had
            before order types existed), ``'limit'``, ``'stop'`` or
            ``'stop_limit'``. Anything but ``'market'`` rests the order in the
            book and fills it against a later bar's range, or never. Fill rules
            and the multi-touch priority rule live in :mod:`lib.orders`.
        limit_offset_pct: How far *away* from the signal bar's close a limit
            rests, as a fraction (0.002 = 20 bps). Buys rest below, sells above.
            Also the slippage cap between a stop-limit's stop and its limit.
        stop_offset_pct: How far *beyond* the signal bar's close a stop rests,
            as a fraction. Buy stops rest above (breakout confirmation), sell
            stops below.
        time_in_force: ``'gtc'`` (rest until filled or cancelled), ``'day'``
            (cancelled at the next session boundary) or ``'ioc'`` (one bar of
            range, then cancelled). Applies to signal-driven orders only —
            protective exits are always GTC, because a stop that expires
            overnight is not a stop.
        order_expiry_bars: Hard age cap in bars on any resting order, applied on
            top of ``time_in_force``. 0 disables it.
        trailing_stop_orders: Express the trailing stop as a resting stop order
            instead of the built-in close-based check. The level still ratchets
            every bar, but it is now tested against the bar's ``Low`` and fills
            at the stop (or at the ``Open`` on a gap), which is stricter and
            usually worse than the default. **This changes results.**
        use_brackets: On every entry, attach an OCO pair — a protective stop and
            a profit target, both fixed at the average entry price — and let
            whichever trades first cancel the other. While a bracket is working
            it owns the exits: the built-in trailing stop is skipped, and so is
            ``take_profit`` when a target leg exists. **This changes results.**
        bracket_stop_pct: Bracket stop distance below entry, as a fraction.
            Defaults to ``trailing_stop_loss`` when left at 0.
        bracket_target_pct: Bracket target distance above entry, as a fraction.
            Defaults to ``take_profit`` when left at 0. A bracket with neither
            leg is not a bracket, and ``use_brackets`` turns itself off.

    Returns:
        DataFrame with backtest results including portfolio values and metrics,
        plus ``Session_Start`` and ``Holding_Sessions``.
        ``result_df.attrs['trades']`` holds the round-trip trade ledger and
        ``attrs['fills']`` the execution-level fill ledger (one row per fill,
        market orders included);
        ``attrs['stop_mode']``, ``attrs['order_type']`` and
        ``attrs['position_sizing_strategy']`` record what was actually applied
        after any fallback.

    Raises:
        ValidationError: If inputs are invalid.
        BacktestError: If an error occurs during backtesting.
    """
    try:
        # Validate inputs
        validate_backtest_inputs(df, initial_capital, buy_indicators, sell_indicators)
        logger.info(f"Starting backtest with {len(df)} rows, initial capital: ${initial_capital:,.2f}")

        cfg = resolve_config(
            strategy_mode=strategy_mode,
            consecutive_signal_mode=consecutive_signal_mode,
            cooldown_bars=cooldown_bars,
            delay=delay,
            min_holding_period=min_holding_period,
            position_scaling=position_scaling,
            position_size_pct=position_size_pct,
            amount_per_buy=amount_per_buy,
            take_profit=take_profit,
            trailing_stop_loss=trailing_stop_loss,
            commission_per_trade=commission_per_trade,
            slippage_pct=slippage_pct,
            fx_fee_pct=fx_fee_pct,
            allow_fractional=allow_fractional,
            order_type=order_type,
            limit_offset_pct=limit_offset_pct,
            stop_offset_pct=stop_offset_pct,
            time_in_force=time_in_force,
            order_expiry_bars=order_expiry_bars,
            trailing_stop_orders=trailing_stop_orders,
            use_brackets=use_brackets,
            bracket_stop_pct=bracket_stop_pct,
            bracket_target_pct=bracket_target_pct,
        )
        account = Account(cash=float(initial_capital))
        # A single-symbol run is a basket of one: the same loop, one context.
        ctx = build_symbol(
            '', df, cfg, account,
            position_sizing_strategy=position_sizing_strategy,
            position_sizing_params=position_sizing_params,
            buy_indicators=buy_indicators,
            sell_indicators=sell_indicators,
            use_signal_strength=use_signal_strength,
            indicator_weights=indicator_weights,
            buy_threshold=buy_threshold,
            sell_threshold=sell_threshold,
            signal_logic=signal_logic,
            signal_window=signal_window,
            trailing_stop_loss=trailing_stop_loss,
            stop_mode=stop_mode,
            volatility_window=volatility_window,
            allow_fractional=allow_fractional,
            use_low_for_stops=use_low_for_stops,
            gap_fills=gap_fills,
        )

        tape = run_bars(cfg, account, [ctx], len(df))
        result_df = symbol_result_frame(ctx, tape.cash_value, tape.portfolio_value)

        portfolio_value = tape.portfolio_value
        final_return = (portfolio_value[-1] / initial_capital - 1) * 100
        logger.info(f"Backtest complete. Final portfolio: ${portfolio_value[-1]:,.2f} ({final_return:+.2f}%)")

        return result_df

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error during backtest: {str(e)}")
        raise BacktestError(f"Backtest failed: {str(e)}") from e


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def calculate_metrics(
    df: pd.DataFrame,
    trades: Union[pd.DataFrame, Sequence[dict], None] = None,
    periods_per_year: int = 252,
    risk_free_rate: Optional[float] = None
) -> Dict[str, float]:
    """
    Summarise a backtest result frame and its trade ledger as a metric dict.

    Thin adapter over :func:`lib.metrics.compute_metrics`, kept because callers
    and tests have always reached for it here. New code should use the metrics
    engine directly and hold a :class:`~lib.metrics.BacktestMetrics` rather than
    a loose dict.

    Args:
        df: A DataFrame returned by :func:`backtest`.
        trades: The round-trip ledger. Defaults to ``df.attrs['trades']``. Rows
            with ``exit_reason == 'open'`` are excluded from the realised trade
            statistics (win rate, profit factor, average win/loss) and counted
            separately as ``open_trades``.
        periods_per_year: Bars per year, for annualising Sharpe/Sortino and for
            the CAGR horizon (252 daily, 52 weekly, 12 monthly, ...). See
            ``lib.timeframes.periods_per_year`` for the per-interval values.
        risk_free_rate: Annual risk-free rate used as the excess-return hurdle.
            Defaults to the configured convention (see
            ``lib.metrics.core.resolve_risk_free_rate``).

    Returns:
        Dict of metrics. Counts are ints, everything else is a float; undefined
        quantities are reported as 0.0 rather than NaN. ``num_trades`` counts
        **closed round trips**, not fills — ``num_fills`` carries that.
    """
    from lib.metrics import compute_metrics

    m = compute_metrics(
        df,
        trades=trades_to_frame(trades) if trades is not None else None,
        periods_per_year=periods_per_year,
        risk_free_rate=risk_free_rate,
        context='lib.strategy.calculate_metrics',
    )
    return m.as_dict()



def run_backtest(
    df: pd.DataFrame,
    initial_capital: float,
    buy_indicators: List[str],
    sell_indicators: List[str],
    strategy_mode: str = 'trading',
    amount_per_buy: Optional[float] = None,
    position_size_pct: float = 100,
    kelly_win_rate: float = 0.5,
    kelly_win_loss_ratio: float = 1.5,
    min_holding_period: int = 5,
    trailing_stop_loss: float = 0.05,
    stop_mode: str = 'percent',
    position_scaling: float = 0.25,
    take_profit: float = 0.0,
    signal_logic: str = 'or',
    signal_window: int = 0,
    consecutive_signal_mode: str = 'scale_in',
    cooldown_bars: int = 0,
    commission_per_trade: float = 0.0,
    slippage_pct: float = 0.0005,
    fx_fee_pct: float = 0.0015,
    use_low_for_stops: bool = False,
    gap_fills: bool = True,
    allow_fractional: bool = False,
    order_type: str = 'market',
    limit_offset_pct: float = 0.002,
    stop_offset_pct: float = 0.002,
    time_in_force: str = 'gtc',
    order_expiry_bars: int = 0,
    trailing_stop_orders: bool = False,
    use_brackets: bool = False,
    bracket_stop_pct: float = 0.0,
    bracket_target_pct: float = 0.0
) -> pd.DataFrame:
    """
    Convenience function to run a backtest with default Kelly Criterion sizing.

    Args:
        df: DataFrame with price data and signals.
        initial_capital: Starting capital.
        buy_indicators: List of buy signal columns.
        sell_indicators: List of sell signal columns.
        strategy_mode: 'trading' (buy/sell cycles), 'accumulation' (DCA), or 'rebalancing' (partial positions).
        amount_per_buy: Fixed dollar amount per buy signal (for accumulation mode).
        position_size_pct: Percentage of portfolio per trade (for rebalancing mode).
        kelly_win_rate: Expected win rate for Kelly sizing (0-1).
        kelly_win_loss_ratio: Expected win/loss ratio for Kelly sizing.
        min_holding_period: Minimum bars to hold before selling.
        trailing_stop_loss: Trailing stop loss percentage.
        stop_mode: 'percent' (fixed trail) or 'atr' (volatility-scaled Chandelier stop).
        position_scaling: Position scaling factor on repeated buys.
        take_profit: Take profit percentage (0 disables).
        signal_logic: 'or' (any signal triggers) or 'and' (all signals must agree).
        signal_window: Window size (candles) for AND confirmation across signals.
        consecutive_signal_mode: How to handle repeated triggers ('scale_in', 'edge', 'cooldown', 'reset_cooldown').
        cooldown_bars: Bars to wait between same-direction triggers.
        commission_per_trade: Commission fee as % of trade notional (0.001 = 0.1%).
        slippage_pct: Slippage as % of price (0.0005 = 5 bps).
        fx_fee_pct: FX fee as % of notional (Trading 212 UK default 0.15%).
        use_low_for_stops: Check trailing-stop breaches against ``Low`` instead of ``Close``.
        gap_fills: Fill a stop the market reopened through at the session's
            ``Open`` rather than its ``Close``.
        allow_fractional: Permit fractional share quantities.

    Returns:
        DataFrame with backtest results.
    """
    kelly_win_rate = 0.5 if kelly_win_rate is None else float(kelly_win_rate)
    kelly_win_loss_ratio = 1.5 if kelly_win_loss_ratio is None else float(kelly_win_loss_ratio)
    kelly_win_rate = min(1.0, max(0.0, kelly_win_rate))
    kelly_win_loss_ratio = max(0.01, kelly_win_loss_ratio)
    position_sizing_params = {
        "win_rate": kelly_win_rate,
        "win_loss_ratio": kelly_win_loss_ratio
    }

    return backtest(
        df=df,
        initial_capital=initial_capital,
        position_sizing_strategy="kelly_criterion",
        position_sizing_params=position_sizing_params,
        buy_indicators=buy_indicators,
        sell_indicators=sell_indicators,
        use_signal_strength=False,  # Set to False by default
        buy_threshold=0.6,
        sell_threshold=0.6,
        min_holding_period=min_holding_period,
        position_scaling=position_scaling,
        trailing_stop_loss=trailing_stop_loss,
        stop_mode=stop_mode,
        volatility_window=20,
        strategy_mode=strategy_mode,
        amount_per_buy=amount_per_buy,
        position_size_pct=position_size_pct,
        take_profit=take_profit,
        signal_logic=signal_logic,
        signal_window=signal_window,
        consecutive_signal_mode=consecutive_signal_mode,
        cooldown_bars=cooldown_bars,
        commission_per_trade=commission_per_trade,
        slippage_pct=slippage_pct,
        fx_fee_pct=fx_fee_pct,
        use_low_for_stops=use_low_for_stops,
        gap_fills=gap_fills,
        allow_fractional=allow_fractional,
        order_type=order_type,
        limit_offset_pct=limit_offset_pct,
        stop_offset_pct=stop_offset_pct,
        time_in_force=time_in_force,
        order_expiry_bars=order_expiry_bars,
        trailing_stop_orders=trailing_stop_orders,
        use_brackets=use_brackets,
        bracket_stop_pct=bracket_stop_pct,
        bracket_target_pct=bracket_target_pct
    )
