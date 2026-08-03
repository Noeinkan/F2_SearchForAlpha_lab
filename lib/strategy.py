# Strategy module with backtesting engine
"""
Backtesting engine for trading strategies with comprehensive error handling,
logging, and optimized operations for performance.

Execution model (read this before interpreting any result)
----------------------------------------------------------
* **Signal lag.** Bar ``i`` is executed against the signal observed on bar
  ``i - delay``. With the default ``delay=1`` a signal printed on bar ``t`` is
  filled at bar ``t+1``'s close, so the engine never trades on information it
  could not have had. ``delay=0`` fills on the signal bar itself and is
  look-ahead by construction — use it only for diagnostics.
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
* **Cost basis versus entry price.** ``Avg_Entry_Price`` is the average
  execution price excluding fees; ``Avg_Cost_Basis`` is the same average with
  entry commission, FX fee and slippage folded in. ``take_profit`` triggers off
  ``Avg_Entry_Price``, so a 10% take profit fires on a 10% *price* move and the
  realised net return is slightly lower once round-trip fees are paid.
"""

import logging
from dataclasses import dataclass, field
from typing import Any, Callable, Dict, List, Optional, Sequence, Union

import numpy as np
import pandas as pd

# Configure module logger
logger = logging.getLogger(__name__)


class BacktestError(Exception):
    """Custom exception for backtest-related errors."""
    pass


class ValidationError(Exception):
    """Custom exception for input validation errors."""
    pass


# Position sizers that need a third, per-bar argument (volatility or ATR).
_EXTRA_ARG_SIZERS = frozenset({"volatility_based", "atr_risk_based"})

# Column written by ATR_TradingStrategy holding the Chandelier long stop level.
ATR_STOP_COLUMN = 'ATR_Stop_Long'

STOP_MODES = ('percent', 'atr')
STRATEGY_MODES = ('trading', 'accumulation', 'rebalancing')
CONSECUTIVE_SIGNAL_MODES = ('scale_in', 'edge', 'cooldown', 'reset_cooldown')

# Reasons a round trip can end, as written to the trade ledger.
EXIT_REASONS = ('signal', 'trailing_stop', 'take_profit', 'open')

# Column order of the trade ledger attached as ``result_df.attrs['trades']``.
TRADE_COLUMNS = (
    'entry_bar', 'entry_date', 'exit_bar', 'exit_date', 'units',
    'avg_entry_price', 'avg_cost_basis', 'exit_price', 'exit_reason',
    'gross_pnl', 'net_pnl', 'fees', 'holding_bars', 'is_open',
)

# Quantities below this are treated as flat (fractional-share rounding noise).
_UNIT_EPS = 1e-9


def _numeric_column(df: pd.DataFrame, column: str) -> Optional[np.ndarray]:
    """Return *column* as a float array, or None when it is missing/all-NaN."""
    if column not in df.columns:
        return None
    values = pd.to_numeric(df[column], errors='coerce').to_numpy(dtype=float)
    if not np.isfinite(values).any():
        return None
    return values


def _validate_choice(value: str, allowed: Sequence[str], name: str) -> str:
    """Lowercase *value* and check it against *allowed*, mirroring STOP_MODES."""
    normalised = (value or allowed[0]).lower()
    if normalised not in allowed:
        raise ValidationError(
            f"Unknown {name}: '{value}'. Available: {', '.join(allowed)}"
        )
    return normalised


def _resolve_atr_stops(df: pd.DataFrame, stop_mode: str) -> Optional[np.ndarray]:
    """
    Resolve the per-bar ATR stop levels for ``stop_mode='atr'``.

    Returns None — meaning "use percentage stops" — when percent mode was asked
    for, or when the ATR column is absent. Bundles that don't include the ATR
    strategy simply won't have written ``ATR_Stop_Long``; that degrades to the
    percentage stop with a warning rather than raising, so an ATR run over a
    non-ATR bundle still produces a result.
    """
    mode = _validate_choice(stop_mode, STOP_MODES, 'stop_mode')
    if mode != 'atr':
        return None

    values = _numeric_column(df, ATR_STOP_COLUMN)
    if values is None:
        logger.warning(
            "stop_mode='atr' requested but '%s' is missing or empty — "
            "falling back to percentage trailing stops.", ATR_STOP_COLUMN
        )
    return values


def validate_backtest_inputs(
    df: pd.DataFrame,
    initial_capital: float,
    buy_indicators: List[str],
    sell_indicators: List[str]
) -> None:
    """
    Validate inputs to the backtest function.

    Args:
        df: DataFrame with price data and signals.
        initial_capital: Starting capital for backtest.
        buy_indicators: List of buy signal column names.
        sell_indicators: List of sell signal column names.

    Raises:
        ValidationError: If any inputs are invalid.
    """
    if df is None or df.empty:
        raise ValidationError("DataFrame is empty or None")

    if initial_capital <= 0:
        raise ValidationError(f"Initial capital must be positive, got {initial_capital}")

    required_columns = ['Close']
    missing_cols = [col for col in required_columns if col not in df.columns]
    if missing_cols:
        raise ValidationError(f"Missing required columns: {missing_cols}")

    # Check for buy/sell indicator columns
    missing_buy = [col for col in buy_indicators if col not in df.columns]
    if missing_buy:
        raise ValidationError(f"Missing buy indicator columns: {missing_buy}")

    # Sell indicators are optional (for accumulation/rebalancing modes)
    if sell_indicators:
        missing_sell = [col for col in sell_indicators if col not in df.columns]
        if missing_sell:
            raise ValidationError(f"Missing sell indicator columns: {missing_sell}")

    # Check for NaN in Close prices
    nan_count = df['Close'].isna().sum()
    if nan_count > 0:
        logger.warning(f"DataFrame contains {nan_count} NaN values in 'Close' column")


# --------------------------------------------------------------------------- #
# Engine state
# --------------------------------------------------------------------------- #

@dataclass
class _PositionState:
    """Mutable per-bar state carried across the simulation loop.

    Holding this in one object rather than in a dozen loop-local names is what
    lets the exit / buy / sell steps live in their own functions: each reads the
    previous bar's values off the state, mutates them, and the loop body
    snapshots the result into the output arrays.
    """
    units: float = 0.0
    cash: float = 0.0
    position_size: float = 0.0
    avg_entry: float = 0.0        # average execution price, fees excluded
    cost_basis: float = 0.0       # average execution price, fees included
    trailing_stop: float = np.inf
    buy_cooldown: int = 0
    sell_cooldown: int = 0
    buy_wait_reset: bool = False
    sell_wait_reset: bool = False


@dataclass
class _OpenTrade:
    """Accumulator for the round trip currently in progress."""
    entry_bar: int
    units_bought: float = 0.0
    units_sold: float = 0.0
    gross_cost: float = 0.0       # notional paid, fees excluded
    gross_proceeds: float = 0.0   # notional received, fees excluded
    entry_fees: float = 0.0
    exit_fees: float = 0.0
    exit_reason: str = 'signal'


@dataclass
class _EngineContext:
    """Per-run configuration plus the output arrays being filled in."""
    # Price / signal inputs
    close_prices: np.ndarray
    low_prices: Optional[np.ndarray]
    dates: Any
    buy_signal_raw: np.ndarray
    sell_signal_raw: np.ndarray

    # Behaviour switches
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
    use_low_for_stops: bool

    # Callables
    size_position: Callable[[float, float, int], float]
    long_stop_level: Callable[[int, float], float]
    round_units: Callable[[float], float]

    # Output arrays
    units_to_buy: np.ndarray
    units_to_sell: np.ndarray
    buy_signal_counter: np.ndarray
    sell_signal_counter: np.ndarray
    buy_triggered: np.ndarray
    buy_rejected: np.ndarray
    sell_triggered: np.ndarray
    sell_rejected: np.ndarray
    holding_period: np.ndarray

    # Trade ledger
    trades: List[dict] = field(default_factory=list)
    open_trade: Optional[_OpenTrade] = None


# --------------------------------------------------------------------------- #
# Trade ledger
# --------------------------------------------------------------------------- #

def _record_entry(ctx: _EngineContext, bar: int, qty: float, value: float, fee: float) -> None:
    """Fold a fill into the open round trip, opening one if the book was flat."""
    if ctx.open_trade is None:
        ctx.open_trade = _OpenTrade(entry_bar=bar)
    trade = ctx.open_trade
    trade.units_bought += qty
    trade.gross_cost += value
    trade.entry_fees += fee


def _record_exit(
    ctx: _EngineContext, bar: int, qty: float, value: float, fee: float, reason: str
) -> None:
    """Fold a sell into the open round trip, closing it once the book is flat."""
    trade = ctx.open_trade
    if trade is None:
        return
    trade.units_sold += qty
    trade.gross_proceeds += value
    trade.exit_fees += fee
    trade.exit_reason = reason
    if trade.units_sold >= trade.units_bought - _UNIT_EPS:
        ctx.trades.append(_finalise_trade(ctx, trade, bar, is_open=False))
        ctx.open_trade = None


def _finalise_trade(
    ctx: _EngineContext, trade: _OpenTrade, exit_bar: int, is_open: bool
) -> dict:
    """Turn an accumulated round trip into a ledger row.

    An ``is_open`` trade is the position still held on the final bar; it is
    marked to market at that bar's close so the ledger reconciles with the
    equity curve. Its ``exit_reason`` is ``'open'`` and the realised-performance
    metrics (win rate, profit factor) exclude it.

    ``avg_entry_price`` is fee-exclusive; ``avg_cost_basis`` is the same average
    with entry fees folded in.
    """
    units = trade.units_bought
    gross_proceeds = trade.gross_proceeds
    if is_open:
        remaining = max(units - trade.units_sold, 0.0)
        gross_proceeds += remaining * ctx.close_prices[exit_bar]

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
        'is_open': bool(is_open),
    }


def trades_to_frame(trades: Union[pd.DataFrame, Sequence[dict], None]) -> pd.DataFrame:
    """Build the trade-ledger DataFrame, with stable columns even when empty."""
    if isinstance(trades, pd.DataFrame):
        trades = trades.to_dict('records')
    if not trades:
        return pd.DataFrame(columns=list(TRADE_COLUMNS))
    return pd.DataFrame(list(trades), columns=list(TRADE_COLUMNS))


# --------------------------------------------------------------------------- #
# Per-bar steps
# --------------------------------------------------------------------------- #

def _hold(ctx: _EngineContext, state: _PositionState, bar: int) -> None:
    """No fill this bar: carry the position and ratchet the trailing stop.

    The stop only ever moves up. Every no-fill path routes through here so a
    rejected, undersized or unaffordable order cannot leave the stop stale.
    """
    if ctx.strategy_mode == 'accumulation' or state.units <= 0:
        state.trailing_stop = np.inf
    else:
        state.trailing_stop = max(
            state.trailing_stop, ctx.long_stop_level(bar, ctx.close_prices[bar])
        )


def _close_position(
    ctx: _EngineContext, state: _PositionState, bar: int, price: float, reason: str
) -> None:
    """Liquidate the whole position at *price* (pre-slippage) and log the exit."""
    qty = state.units
    ctx.units_to_sell[bar] = qty
    execution_price = price * (1 - ctx.slippage_pct)
    value = qty * execution_price
    fee = value * ctx.fee_rate

    state.units = 0.0
    state.cash += value - fee
    state.position_size = 0.0
    state.trailing_stop = np.inf
    state.avg_entry = 0.0
    state.cost_basis = 0.0

    _record_exit(ctx, bar, qty, value, fee, reason)


def _check_exits(ctx: _EngineContext, state: _PositionState, bar: int) -> bool:
    """Apply trailing stop and take profit. Returns True if the bar was consumed.

    Ordering is deliberate: the stop is tested first and ignores
    ``min_holding_period``; take profit is tested second and respects it. Both
    are disabled entirely in accumulation mode (long-term hold).
    """
    if ctx.strategy_mode == 'accumulation' or state.units <= 0:
        return False

    close_price = ctx.close_prices[bar]
    stop_level = state.trailing_stop

    if np.isfinite(stop_level):
        if ctx.use_low_for_stops:
            # Intrabar breach: a resting stop order would have filled at the stop,
            # unless the bar closed below it (gap), where the close is the worse
            # and more honest assumption.
            if ctx.low_prices[bar] <= stop_level:
                _close_position(ctx, state, bar, min(stop_level, close_price), 'trailing_stop')
                return True
        elif close_price <= stop_level:
            _close_position(ctx, state, bar, close_price, 'trailing_stop')
            return True

    if (
        ctx.take_profit > 0
        and state.avg_entry > 0
        and close_price >= state.avg_entry * (1 + ctx.take_profit)
        and ctx.holding_period[bar] >= ctx.min_holding_period
    ):
        _close_position(ctx, state, bar, close_price, 'take_profit')
        return True

    return False


def _execute_buy(
    ctx: _EngineContext, state: _PositionState, bar: int, prev_portfolio_value: float
) -> None:
    """Size, clamp to affordable cash, and fill a buy at *bar*'s close."""
    ctx.buy_triggered[bar] = True
    ctx.buy_signal_counter[bar] = ctx.buy_signal_counter[bar - 1] + 1

    close_price = ctx.close_prices[bar]
    prev_units = state.units

    if not np.isfinite(close_price) or close_price <= 0:
        _hold(ctx, state, bar)
        return

    if ctx.strategy_mode == 'accumulation':
        # Fixed dollar amount per buy (DCA style), capped by cash on hand.
        buy_amount = ctx.amount_per_buy if ctx.amount_per_buy else 1000.0
        buy_amount = min(float(buy_amount), state.cash)
        qty = ctx.round_units(buy_amount / close_price)
    elif ctx.strategy_mode == 'rebalancing':
        pct = (ctx.position_size_pct or 100) / 100.0
        qty = ctx.round_units((state.cash * pct) / close_price)
    else:
        state.position_size = min(state.position_size + ctx.position_scaling, 1)
        raw = ctx.size_position(prev_portfolio_value, close_price, bar)
        qty = ctx.round_units(raw * state.position_size)

    if qty > 0:
        execution_price = close_price * (1 + ctx.slippage_pct)
        total_cost_per_unit = execution_price * (1 + ctx.fee_rate)
        affordable = (
            ctx.round_units(state.cash / total_cost_per_unit)
            if total_cost_per_unit > 0 else 0.0
        )
        qty = 0.0 if affordable <= 0 else min(qty, affordable)

    if qty <= 0:
        _hold(ctx, state, bar)
        return

    ctx.units_to_buy[bar] = qty
    execution_price = close_price * (1 + ctx.slippage_pct)
    value = qty * execution_price
    fee = value * ctx.fee_rate

    state.units = prev_units + qty
    state.cash -= value + fee
    state.avg_entry = ((state.avg_entry * prev_units) + value) / state.units
    state.cost_basis = ((state.cost_basis * prev_units) + value + fee) / state.units

    if ctx.strategy_mode == 'accumulation':
        state.trailing_stop = np.inf  # No trailing stop for accumulation
    else:
        level = ctx.long_stop_level(bar, close_price)
        # Scaling into an existing position must never loosen a stop that has
        # already ratcheted up; only a fresh entry sets the level outright.
        state.trailing_stop = max(state.trailing_stop, level) if prev_units > 0 else level

    if ctx.consecutive_signal_mode in ('cooldown', 'reset_cooldown') and ctx.cooldown_bars > 0:
        state.buy_cooldown = ctx.cooldown_bars + 1
    if ctx.consecutive_signal_mode == 'reset_cooldown':
        state.buy_wait_reset = True

    _record_entry(ctx, bar, qty, value, fee)


def _execute_sell(
    ctx: _EngineContext, state: _PositionState, bar: int, prev_portfolio_value: float
) -> None:
    """Size and fill a discretionary (signal-driven) sell at *bar*'s close."""
    ctx.sell_triggered[bar] = True

    if ctx.holding_period[bar] < ctx.min_holding_period:
        _hold(ctx, state, bar)
        return

    ctx.sell_signal_counter[bar] = ctx.sell_signal_counter[bar - 1] + 1
    close_price = ctx.close_prices[bar]
    prev_units = state.units

    if ctx.strategy_mode == 'rebalancing':
        pct = (ctx.position_size_pct or 100) / 100.0
        qty = ctx.round_units(prev_units * pct)
    else:
        state.position_size = max(state.position_size - ctx.position_scaling, 0)
        raw = ctx.size_position(prev_portfolio_value, close_price, bar)
        qty = min(ctx.round_units(raw * (1 - state.position_size)), prev_units)

    if qty <= 0:
        _hold(ctx, state, bar)
        return

    ctx.units_to_sell[bar] = qty
    execution_price = close_price * (1 - ctx.slippage_pct)
    value = qty * execution_price
    fee = value * ctx.fee_rate

    state.units = prev_units - qty
    state.cash += value - fee

    if state.units <= _UNIT_EPS:
        state.units = 0.0
        state.trailing_stop = np.inf
        state.avg_entry = 0.0
        state.cost_basis = 0.0
    else:
        state.trailing_stop = max(
            state.trailing_stop, ctx.long_stop_level(bar, close_price)
        )

    if ctx.consecutive_signal_mode in ('cooldown', 'reset_cooldown') and ctx.cooldown_bars > 0:
        state.sell_cooldown = ctx.cooldown_bars + 1
    if ctx.consecutive_signal_mode == 'reset_cooldown':
        state.sell_wait_reset = True

    _record_exit(ctx, bar, qty, value, fee, 'signal')


def _process_signals(
    ctx: _EngineContext, state: _PositionState, bar: int, prev_portfolio_value: float
) -> None:
    """Gate the lagged signals through the consecutive-signal policy and route.

    The signal read for bar ``i`` is the one printed on bar ``i - delay``; edge
    detection compares that bar against ``i - delay - 1``. When both a buy and a
    sell survive gating the buy wins (see the module docstring).
    """
    signal_bar = bar - ctx.delay
    prev_signal_bar = signal_bar - 1

    current_buy = bool(ctx.buy_signal_raw[signal_bar])
    current_sell = bool(ctx.sell_signal_raw[signal_bar])
    prev_buy = bool(ctx.buy_signal_raw[prev_signal_bar]) if prev_signal_bar >= 0 else False
    prev_sell = bool(ctx.sell_signal_raw[prev_signal_bar]) if prev_signal_bar >= 0 else False

    mode = ctx.consecutive_signal_mode
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
        _execute_buy(ctx, state, bar, prev_portfolio_value)
    elif ctx.strategy_mode != 'accumulation' and allow_sell:
        _execute_sell(ctx, state, bar, prev_portfolio_value)
    else:
        _hold(ctx, state, bar)


# --------------------------------------------------------------------------- #
# Public entry point
# --------------------------------------------------------------------------- #

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
    allow_fractional: bool = False
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
        allow_fractional: Permit fractional share quantities (Trading 212 supports
            them). Default False keeps whole-share truncation.

    Returns:
        DataFrame with backtest results including portfolio values and metrics.
        ``result_df.attrs['trades']`` holds the round-trip trade ledger;
        ``attrs['stop_mode']`` and ``attrs['position_sizing_strategy']`` record
        what was actually applied after any fallback.

    Raises:
        ValidationError: If inputs are invalid.
        BacktestError: If an error occurs during backtesting.
    """
    try:
        # Validate inputs
        validate_backtest_inputs(df, initial_capital, buy_indicators, sell_indicators)
        logger.info(f"Starting backtest with {len(df)} rows, initial capital: ${initial_capital:,.2f}")

        num_rows = len(df)
        signal_window = max(0, int(signal_window or 0))
        strategy_mode = _validate_choice(strategy_mode, STRATEGY_MODES, 'strategy_mode')
        consecutive_signal_mode = _validate_choice(
            consecutive_signal_mode, CONSECUTIVE_SIGNAL_MODES, 'consecutive_signal_mode'
        )
        cooldown_bars = max(0, int(cooldown_bars or 0))
        delay = max(0, int(delay or 0))
        min_holding_period = max(0, int(min_holding_period or 0))

        # Initialize arrays
        units = np.zeros(num_rows)
        cash_value = np.full(num_rows, float(initial_capital))
        stocks_value = np.zeros(num_rows)
        portfolio_value = np.full(num_rows, float(initial_capital))
        units_to_buy = np.zeros(num_rows)
        units_to_sell = np.zeros(num_rows)
        buy_signal_counter = np.zeros(num_rows, dtype=int)
        sell_signal_counter = np.zeros(num_rows, dtype=int)
        buy_triggered = np.zeros(num_rows, dtype=bool)
        buy_rejected = np.zeros(num_rows, dtype=bool)
        sell_triggered = np.zeros(num_rows, dtype=bool)
        sell_rejected = np.zeros(num_rows, dtype=bool)
        holding_period = np.zeros(num_rows, dtype=int)
        trailing_stop = np.full(num_rows, np.inf)
        avg_entry_price = np.zeros(num_rows)
        avg_cost_basis = np.zeros(num_rows)

        # Resolve the stop source before sizing — an ATR sizer that cannot find
        # its column has to be sized off whatever stop will actually be applied.
        atr_stop_values = _resolve_atr_stops(df, stop_mode)
        effective_stop_mode = 'atr' if atr_stop_values is not None else 'percent'

        position_sizing_params = dict(position_sizing_params or {})
        if position_sizing_strategy == "atr_risk_based" and _numeric_column(df, 'ATR') is None:
            logger.warning(
                "position_sizing_strategy='atr_risk_based' requested but 'ATR' is "
                "missing or empty — falling back to percentage risk_based sizing."
            )
            position_sizing_strategy = "risk_based"
            position_sizing_params = {
                "stop_loss_percent": max(float(trailing_stop_loss or 0), 0.01),
                "risk_percent": position_sizing_params.get("risk_percent", 0.01),
            }

        # Get position sizer function
        position_sizer = get_position_sizer(
            position_sizing_strategy, fractional=allow_fractional, **position_sizing_params
        )

        if use_signal_strength:
            buy_signal_strength, sell_signal_strength = calculate_signal_strengths(
                df, buy_indicators, sell_indicators, indicator_weights
            )
        else:
            buy_signal_strength = _combine_signals(df, buy_indicators, signal_logic, signal_window)
            if sell_indicators:
                sell_signal_strength = _combine_signals(df, sell_indicators, signal_logic, signal_window)
            else:
                sell_signal_strength = np.zeros(num_rows)

        if use_signal_strength:
            buy_signal_raw = buy_signal_strength > buy_threshold
            sell_signal_raw = sell_signal_strength > sell_threshold
        else:
            buy_signal_raw = buy_signal_strength > 0
            sell_signal_raw = sell_signal_strength > 0
        buy_signal_raw = np.asarray(buy_signal_raw, dtype=bool)
        sell_signal_raw = np.asarray(sell_signal_raw, dtype=bool)

        # Calculate volatility
        df = df.copy()
        df['Volatility'] = df['Close'].pct_change().rolling(window=volatility_window).std()

        # Per-bar third argument for the sizers that need one.
        if position_sizing_strategy == "volatility_based":
            sizer_extra = df['Volatility'].to_numpy(dtype=float)
        elif position_sizing_strategy == "atr_risk_based":
            sizer_extra = pd.to_numeric(df['ATR'], errors='coerce').to_numpy(dtype=float)
        else:
            sizer_extra = None

        def size_position(pv, price, bar: int) -> float:
            """Call the configured sizer, passing its per-bar argument if it takes one."""
            if sizer_extra is not None:
                return position_sizer(pv, price, sizer_extra[bar])
            return position_sizer(pv, price)

        def long_stop_level(bar: int, price) -> float:
            """Trailing stop level for a long held at *bar*.

            In ATR mode the level is the Chandelier stop the ATR strategy wrote.
            That stop is anchored to a rolling high, so after a sharp drop it can
            sit at or above the current close — using it there would fire on the
            very next bar regardless of the trade, so those bars fall back to the
            percentage stop.
            """
            if atr_stop_values is not None:
                level = atr_stop_values[bar]
                if np.isfinite(level) and 0 < level < price:
                    return level
            return price * (1 - trailing_stop_loss)

        if allow_fractional:
            def round_units(value: float) -> float:
                """Fractional shares: keep the exact quantity, floor at zero."""
                return float(value) if value > 0 else 0.0
        else:
            def round_units(value: float) -> float:
                """Whole shares: truncate toward zero, as a broker lot would."""
                return float(int(value)) if value > 0 else 0.0

        close_prices = df['Close'].to_numpy(dtype=float)

        low_prices = None
        if use_low_for_stops:
            low_prices = _numeric_column(df, 'Low')
            if low_prices is None:
                logger.warning(
                    "use_low_for_stops=True but 'Low' is missing or empty — "
                    "falling back to close-only stop checks."
                )
                use_low_for_stops = False

        # Market returns, guarded against a zero/NaN previous close.
        returns = np.zeros(num_rows)
        if num_rows > 1:
            prev_close = close_prices[:-1]
            positive = prev_close > 0
            with np.errstate(divide='ignore', invalid='ignore'):
                step = np.where(
                    positive,
                    np.diff(close_prices) / np.where(positive, prev_close, 1.0),
                    0.0,
                )
            returns[1:] = np.nan_to_num(step, nan=0.0, posinf=0.0, neginf=0.0)

        take_profit = max(0.0, float(take_profit or 0))
        fee_rate = max(0.0, float(commission_per_trade or 0)) + max(0.0, float(fx_fee_pct or 0))
        slippage_pct = max(0.0, float(slippage_pct or 0))

        ctx = _EngineContext(
            close_prices=close_prices,
            low_prices=low_prices,
            dates=df.index,
            buy_signal_raw=buy_signal_raw,
            sell_signal_raw=sell_signal_raw,
            delay=delay,
            strategy_mode=strategy_mode,
            consecutive_signal_mode=consecutive_signal_mode,
            cooldown_bars=cooldown_bars,
            min_holding_period=min_holding_period,
            position_scaling=position_scaling,
            position_size_pct=position_size_pct,
            amount_per_buy=amount_per_buy,
            take_profit=take_profit,
            fee_rate=fee_rate,
            slippage_pct=slippage_pct,
            use_low_for_stops=use_low_for_stops,
            size_position=size_position,
            long_stop_level=long_stop_level,
            round_units=round_units,
            units_to_buy=units_to_buy,
            units_to_sell=units_to_sell,
            buy_signal_counter=buy_signal_counter,
            sell_signal_counter=sell_signal_counter,
            buy_triggered=buy_triggered,
            buy_rejected=buy_rejected,
            sell_triggered=sell_triggered,
            sell_rejected=sell_rejected,
            holding_period=holding_period,
        )

        state = _PositionState(cash=float(initial_capital))

        # Bar 0 is the opening state, and bars before `delay` have no observable
        # signal yet, so the first tradable bar is max(1, delay).
        for i in range(max(1, delay), num_rows):
            close_price = close_prices[i]
            prev_portfolio_value = portfolio_value[i - 1]

            holding_period[i] = holding_period[i - 1] + 1 if state.units > 0 else 0

            if not _check_exits(ctx, state, i):
                _process_signals(ctx, state, i, prev_portfolio_value)

            units[i] = state.units
            cash_value[i] = state.cash
            trailing_stop[i] = state.trailing_stop
            avg_entry_price[i] = state.avg_entry
            avg_cost_basis[i] = state.cost_basis
            stocks_value[i] = state.units * close_price
            portfolio_value[i] = state.cash + stocks_value[i]

            # Cooldowns are armed with cooldown_bars + 1 at fill time precisely
            # because this decrement also runs on the arming bar; the counter is
            # therefore non-zero on exactly the next `cooldown_bars` bars.
            if state.buy_cooldown > 0:
                state.buy_cooldown -= 1
            if state.sell_cooldown > 0:
                state.sell_cooldown -= 1

        # A position still open on the last bar is marked to market so the ledger
        # reconciles with the equity curve; it carries exit_reason='open'.
        if ctx.open_trade is not None and num_rows > 0:
            ctx.trades.append(_finalise_trade(ctx, ctx.open_trade, num_rows - 1, is_open=True))
            ctx.open_trade = None

        # Calculate returns and create result DataFrame
        strategy_returns, cumulative_returns, cumulative_market_returns = calculate_returns(portfolio_value, returns)

        result_df = create_result_dataframe(
            df, units, units_to_buy, units_to_sell, cash_value, stocks_value, portfolio_value,
            buy_signal_raw, sell_signal_raw,
            returns, strategy_returns, cumulative_returns, cumulative_market_returns,
            holding_period, trailing_stop, buy_triggered, buy_rejected, sell_triggered, sell_rejected,
            avg_entry_price=avg_entry_price, avg_cost_basis=avg_cost_basis
        )
        # Record what was actually applied, not what was asked for — either may
        # have been downgraded to the percentage fallback above.
        result_df.attrs['stop_mode'] = effective_stop_mode
        result_df.attrs['position_sizing_strategy'] = position_sizing_strategy
        result_df.attrs['trades'] = trades_to_frame(ctx.trades)

        final_return = (portfolio_value[-1] / initial_capital - 1) * 100
        logger.info(f"Backtest complete. Final portfolio: ${portfolio_value[-1]:,.2f} ({final_return:+.2f}%)")

        return result_df

    except ValidationError:
        raise
    except Exception as e:
        logger.error(f"Error during backtest: {str(e)}")
        raise BacktestError(f"Backtest failed: {str(e)}") from e


def calculate_signal_strengths(
    df: pd.DataFrame,
    buy_indicators: List[str],
    sell_indicators: List[str],
    indicator_weights: Optional[Dict[str, float]] = None
) -> tuple:
    """
    Calculate weighted signal strengths for buy and sell indicators (vectorized).

    Args:
        df: DataFrame with signal columns.
        buy_indicators: List of buy indicator column names.
        sell_indicators: List of sell indicator column names.
        indicator_weights: Optional weights for each indicator.

    Returns:
        Tuple of (buy_signal_strength, sell_signal_strength) numpy arrays.
    """
    if indicator_weights is not None:
        buy_weights = np.array([indicator_weights.get(ind, 1.0) for ind in buy_indicators])
        sell_weights = np.array([indicator_weights.get(ind, 1.0) for ind in sell_indicators])

        buy_signal_strength = (df[buy_indicators].values * buy_weights).sum(axis=1)
        sell_signal_strength = (df[sell_indicators].values * sell_weights).sum(axis=1)
    else:
        buy_signal_strength = df[buy_indicators].sum(axis=1).values
        sell_signal_strength = df[sell_indicators].sum(axis=1).values

    return buy_signal_strength, sell_signal_strength


def _combine_signals(
    df: pd.DataFrame,
    columns: List[str],
    logic: str,
    window: int
) -> np.ndarray:
    """
    Combine multiple signal columns into a single 0/1 array.

    Args:
        df: DataFrame with signal columns.
        columns: Signal column names to combine.
        logic: 'or' (any signal) or 'and' (all signals).
        window: Rolling window for confirmation (0 disables).
    """
    if not columns:
        return np.zeros(len(df), dtype=int)

    valid_cols = [col for col in columns if col in df.columns]
    if not valid_cols:
        return np.zeros(len(df), dtype=int)

    signals = df[valid_cols].fillna(0)
    window = max(0, int(window or 0))
    logic = (logic or 'or').lower()

    if logic == 'and' and window > 0:
        windowed = signals.rolling(window=window + 1, min_periods=1).max()
        combined = (windowed > 0).all(axis=1)
    elif logic == 'and':
        combined = signals.gt(0).all(axis=1)
    else:
        combined = signals.gt(0).any(axis=1)

    return combined.astype(int).values


def calculate_returns(portfolio_value: np.ndarray, returns: np.ndarray) -> tuple:
    """Calculate strategy and market returns.

    A portfolio that reaches zero would divide by zero on the next bar; those
    bars are reported as a flat 0% rather than inf/NaN, which pins the cumulative
    curve at zero instead of poisoning the whole series.
    """
    pv = np.asarray(portfolio_value, dtype=float)
    market = np.asarray(returns, dtype=float)
    strategy_returns = np.zeros_like(market, dtype=float)

    if pv.size > 1:
        prev = pv[:-1]
        positive = prev > 0
        with np.errstate(divide='ignore', invalid='ignore'):
            step = np.where(positive, (pv[1:] - prev) / np.where(positive, prev, 1.0), 0.0)
        strategy_returns[1:] = np.nan_to_num(step, nan=0.0, posinf=0.0, neginf=0.0)

    cumulative_returns = np.cumprod(1 + strategy_returns)
    cumulative_market_returns = np.cumprod(1 + market)
    return strategy_returns, cumulative_returns, cumulative_market_returns


def create_result_dataframe(
    df: pd.DataFrame,
    units: np.ndarray,
    units_to_buy: np.ndarray,
    units_to_sell: np.ndarray,
    cash_value: np.ndarray,
    stocks_value: np.ndarray,
    portfolio_value: np.ndarray,
    buy_position: np.ndarray,
    sell_position: np.ndarray,
    returns: np.ndarray,
    strategy_returns: np.ndarray,
    cumulative_returns: np.ndarray,
    cumulative_market_returns: np.ndarray,
    holding_period: np.ndarray,
    trailing_stop: np.ndarray,
    buy_triggered: np.ndarray,
    buy_rejected: np.ndarray,
    sell_triggered: np.ndarray,
    sell_rejected: np.ndarray,
    avg_entry_price: Optional[np.ndarray] = None,
    avg_cost_basis: Optional[np.ndarray] = None
) -> pd.DataFrame:
    df = df.copy()
    df['Units'] = units
    df['Units_to_buy'] = units_to_buy
    df['Units_to_sell'] = units_to_sell
    df['Cash_Value'] = cash_value
    df['Stocks_Value'] = stocks_value
    df['Portfolio_Value'] = portfolio_value
    # These mirror the boolean arrays the simulation actually consumed, so a bar
    # flagged here is a bar the engine saw a signal on — before the `delay` lag
    # is applied at execution time.
    df['Buy_Position'] = buy_position
    df['Sell_Position'] = sell_position
    df['Returns'] = returns
    df['Strategy_Returns'] = strategy_returns
    df['Cumulative_Returns'] = cumulative_returns
    df['Cumulative_Market_Returns'] = cumulative_market_returns
    df['Holding_Period'] = holding_period
    df['Trailing_Stop'] = trailing_stop
    df['Buy_Trigger_Accepted'] = buy_triggered
    df['Buy_Trigger_Rejected'] = buy_rejected
    df['Sell_Trigger_Accepted'] = sell_triggered
    df['Sell_Trigger_Rejected'] = sell_rejected
    if avg_entry_price is not None:
        df['Avg_Entry_Price'] = avg_entry_price
    if avg_cost_basis is not None:
        df['Avg_Cost_Basis'] = avg_cost_basis
    return df


def get_position_sizer(strategy: str, fractional: bool = False, **kwargs) -> Callable:
    """
    Get the position sizing function for the specified strategy.

    Args:
        strategy: Name of the position sizing strategy.
        fractional: Return the exact (unrounded) quantity instead of whole
            shares. The engine sets this from ``backtest(allow_fractional=...)``;
            the truncation otherwise happens inside the sizer, where the engine
            cannot undo it.
        **kwargs: Additional parameters for the strategy.

    Returns:
        Callable position sizing function.

    Raises:
        ValueError: If strategy is not recognized.
    """
    strategies = {
        "percentage_of_portfolio": lambda pv, cp: _size_percentage_of_portfolio(
            pv, cp, kwargs.get('percent', 0.01)
        ),
        "fixed_dollar_amount": lambda pv, cp: _size_fixed_dollar_amount(
            cp, kwargs.get('amount', 1000)
        ),
        "volatility_based": lambda pv, cp, vol: _size_volatility_based(
            pv, cp, vol, kwargs.get('target_volatility', 0.01)
        ),
        "kelly_criterion": lambda pv, cp: _size_kelly_criterion(
            kwargs['win_rate'], kwargs['win_loss_ratio'], pv, cp
        ),
        "risk_based": lambda pv, cp: _size_risk_based(
            pv, cp, kwargs['stop_loss_percent'], kwargs.get('risk_percent', 0.01)
        ),
        "atr_risk_based": lambda pv, cp, atr: _size_atr_risk_based(
            pv, cp, atr, kwargs.get('atr_multiplier', 1.5), kwargs.get('risk_percent', 0.01)
        )
    }

    if strategy not in strategies:
        available = ", ".join(strategies.keys())
        raise ValueError(f"Unknown position sizing strategy: '{strategy}'. Available: {available}")

    sizer = strategies[strategy]
    if fractional:
        return sizer
    return lambda *args: int(sizer(*args))


# The `_size_*` helpers return the exact, unrounded quantity. The public
# functions below wrap them with the whole-share truncation callers expect.

def _size_percentage_of_portfolio(portfolio_value: float, close_price: float, percent: float) -> float:
    if close_price <= 0:
        return 0.0
    return (portfolio_value * percent) / close_price


def _size_fixed_dollar_amount(close_price: float, amount: float) -> float:
    if close_price <= 0:
        return 0.0
    return amount / close_price


def _size_volatility_based(
    portfolio_value: float, close_price: float, volatility: float, target_volatility: float
) -> float:
    if close_price <= 0 or volatility <= 0:
        return 0.0
    return ((target_volatility / volatility) * portfolio_value) / close_price


def _size_kelly_criterion(
    win_rate: float, win_loss_ratio: float, portfolio_value: float, close_price: float
) -> float:
    if close_price <= 0 or win_loss_ratio <= 0:
        return 0.0
    kelly_percentage = win_rate - ((1 - win_rate) / win_loss_ratio)
    kelly_percentage = max(0, min(kelly_percentage, 1))
    return (kelly_percentage * portfolio_value) / close_price


def _size_risk_based(
    portfolio_value: float, close_price: float, stop_loss_percent: float, risk_percent: float
) -> float:
    if close_price <= 0 or stop_loss_percent <= 0:
        return 0.0
    return (portfolio_value * risk_percent) / (close_price * stop_loss_percent)


def _size_atr_risk_based(
    portfolio_value: float, close_price: float, atr: float,
    atr_multiplier: float, risk_percent: float
) -> float:
    if close_price <= 0 or not np.isfinite(atr) or atr <= 0 or atr_multiplier <= 0:
        return 0.0
    return (portfolio_value * risk_percent) / (atr * atr_multiplier)


def percentage_of_portfolio(portfolio_value: float, close_price: float, percent: float = 0.02) -> int:
    """Calculate position size as percentage of portfolio."""
    return int(_size_percentage_of_portfolio(portfolio_value, close_price, percent))

def fixed_dollar_amount(close_price: float, amount: float = 500) -> int:
    """Calculate position size based on fixed dollar amount."""
    return int(_size_fixed_dollar_amount(close_price, amount))


def volatility_based(
    portfolio_value: float,
    close_price: float,
    volatility: float,
    target_volatility: float = 0.01
) -> int:
    """Calculate position size based on asset volatility."""
    return int(_size_volatility_based(portfolio_value, close_price, volatility, target_volatility))


def kelly_criterion(
    win_rate: float,
    win_loss_ratio: float,
    portfolio_value: float,
    close_price: float
) -> int:
    """Calculate position size using Kelly Criterion."""
    return int(_size_kelly_criterion(win_rate, win_loss_ratio, portfolio_value, close_price))


def risk_based(
    portfolio_value: float,
    close_price: float,
    stop_loss_percent: float,
    risk_percent: float = 0.01
) -> int:
    """Calculate position size based on fixed risk per trade."""
    return int(_size_risk_based(portfolio_value, close_price, stop_loss_percent, risk_percent))


def atr_risk_based(
    portfolio_value: float,
    close_price: float,
    atr: float,
    atr_multiplier: float = 1.5,
    risk_percent: float = 0.01
) -> int:
    """
    Size a position so that ``atr_multiplier`` ATRs of adverse move costs
    ``risk_percent`` of the portfolio.

    This is ``risk_based`` with the fixed stop percentage replaced by the
    instrument's own volatility, so a low-vol utility gets a larger position
    than a high-beta name for the same dollar risk. ``atr_multiplier`` defaults
    to 1.5 to match ``ATR_TradingStrategy``'s stop multiplier, so sizing and
    ``stop_mode='atr'`` agree on the same risk unit.

    Returns 0 for a non-finite or non-positive ATR (warmup bars) — a position
    whose risk cannot be measured is not taken.
    """
    return int(_size_atr_risk_based(portfolio_value, close_price, atr, atr_multiplier, risk_percent))


def calculate_max_drawdown(df: pd.DataFrame) -> float:
    """Calculate the maximum drawdown from cumulative returns."""
    if 'Cumulative_Returns' not in df.columns:
        logger.warning("Cumulative_Returns column not found")
        return 0.0
    cumulative_returns = df['Cumulative_Returns']
    if len(cumulative_returns) == 0:
        return 0.0
    peak = cumulative_returns.expanding(min_periods=1).max()
    with np.errstate(divide='ignore', invalid='ignore'):
        drawdown = (cumulative_returns / peak.replace(0, np.nan)) - 1
    return float(drawdown.fillna(0.0).min())


# --------------------------------------------------------------------------- #
# Metrics
# --------------------------------------------------------------------------- #

def calculate_metrics(
    df: pd.DataFrame,
    trades: Union[pd.DataFrame, Sequence[dict], None] = None,
    periods_per_year: int = 252,
    risk_free_rate: float = 0.0
) -> Dict[str, float]:
    """
    Summarise a backtest result frame and its trade ledger as a metric dict.

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

    Returns:
        Dict of metrics. Counts are ints, everything else is a float; undefined
        quantities are reported as 0.0 rather than NaN, except ``profit_factor``
        which is ``inf`` when there are wins and no losses.
    """
    metrics: Dict[str, float] = {
        'total_return': 0.0, 'cagr': 0.0, 'sharpe': 0.0, 'sortino': 0.0,
        'max_drawdown': 0.0, 'exposure': 0.0, 'num_trades': 0, 'open_trades': 0,
        'win_rate': 0.0, 'profit_factor': 0.0, 'avg_win': 0.0, 'avg_loss': 0.0,
        'expectancy': 0.0, 'avg_holding_bars': 0.0, 'total_fees': 0.0,
    }
    if df is None or len(df) == 0:
        return metrics

    ppy = max(1, int(periods_per_year or 252))

    # --- equity curve -----------------------------------------------------
    if 'Portfolio_Value' in df.columns:
        pv = pd.to_numeric(df['Portfolio_Value'], errors='coerce').to_numpy(dtype=float)
        start, end = pv[0], pv[-1]
        if start > 0:
            growth = end / start
            metrics['total_return'] = float(growth - 1.0)
            years = max(len(pv) - 1, 1) / ppy
            metrics['cagr'] = float(growth ** (1.0 / years) - 1.0) if growth > 0 else -1.0

    if 'Strategy_Returns' in df.columns:
        r = pd.to_numeric(df['Strategy_Returns'], errors='coerce').to_numpy(dtype=float)
        r = np.nan_to_num(r, nan=0.0, posinf=0.0, neginf=0.0)
        excess = r - (risk_free_rate / ppy)
        std = float(excess.std(ddof=1)) if excess.size > 1 else 0.0
        if std > 0:
            metrics['sharpe'] = float(np.sqrt(ppy) * excess.mean() / std)
        downside = excess[excess < 0]
        downside_std = float(downside.std(ddof=1)) if downside.size > 1 else 0.0
        if downside_std > 0:
            metrics['sortino'] = float(np.sqrt(ppy) * excess.mean() / downside_std)

    metrics['max_drawdown'] = float(calculate_max_drawdown(df))

    if 'Units' in df.columns:
        held = pd.to_numeric(df['Units'], errors='coerce').fillna(0) > 0
        metrics['exposure'] = float(held.mean())

    # --- trade ledger -----------------------------------------------------
    if trades is None:
        trades = df.attrs.get('trades')
    ledger = trades_to_frame(trades)
    if ledger.empty:
        return metrics

    metrics['open_trades'] = int((ledger['exit_reason'] == 'open').sum())
    metrics['total_fees'] = float(ledger['fees'].sum())

    closed = ledger[ledger['exit_reason'] != 'open']
    metrics['num_trades'] = int(len(closed))
    if closed.empty:
        return metrics

    pnl = closed['net_pnl'].to_numpy(dtype=float)
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    metrics['win_rate'] = float(len(wins) / len(pnl))
    metrics['avg_win'] = float(wins.mean()) if wins.size else 0.0
    metrics['avg_loss'] = float(losses.mean()) if losses.size else 0.0
    metrics['expectancy'] = float(pnl.mean())
    metrics['avg_holding_bars'] = float(closed['holding_bars'].mean())

    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    if gross_loss > 0:
        metrics['profit_factor'] = gross_profit / gross_loss
    else:
        metrics['profit_factor'] = float('inf') if gross_profit > 0 else 0.0

    return metrics


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
    allow_fractional: bool = False
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
        allow_fractional=allow_fractional
    )
