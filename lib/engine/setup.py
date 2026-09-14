"""Resolve ``backtest()``'s arguments into an engine config and per-symbol contexts.

Split in two because a portfolio needs them split: the config is resolved once
for the basket, and each symbol is prepared on its own frame — its own ATR
stops, volatility, signal arrays and session marks — against that one config.
"""

from __future__ import annotations

import logging
from typing import Dict, List, Optional, Sequence

import numpy as np
import pandas as pd

from lib.engine.errors import ValidationError
from lib.engine.results import calculate_returns, create_result_dataframe, market_returns
from lib.engine.signal_inputs import raw_signals
from lib.engine.sizing import get_position_sizer
from lib.engine.state import Account, EngineConfig, SymbolContext
from lib.metrics.ledger import trades_to_frame
from lib.orders import ORDER_TYPES, TIME_IN_FORCE, fills_to_frame
from lib.panel import MARK_COLUMN, TRADABLE_COLUMN
from lib.sessions import resolve_session_starts

# The fallback warnings below have always been logged as 'lib.strategy', and
# callers filter on that name. Moving the code did not move the contract.
logger = logging.getLogger('lib.strategy')

# Column written by ATR_TradingStrategy holding the Chandelier long stop level.
ATR_STOP_COLUMN = 'ATR_Stop_Long'

STOP_MODES = ('percent', 'atr')
STRATEGY_MODES = ('trading', 'accumulation', 'rebalancing')
CONSECUTIVE_SIGNAL_MODES = ('scale_in', 'edge', 'cooldown', 'reset_cooldown')


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

    # Check for NaN in Close prices. A panel's holes are NaN by design and are
    # never traded, so only a NaN on a bar marked tradable is worth a warning.
    close = df['Close']
    if TRADABLE_COLUMN in df.columns:
        close = close[df[TRADABLE_COLUMN].astype(bool)]
    nan_count = close.isna().sum()
    if nan_count > 0:
        logger.warning(f"DataFrame contains {nan_count} NaN values in 'Close' column")


def resolve_config(
    *,
    strategy_mode: str,
    consecutive_signal_mode: str,
    cooldown_bars: int,
    delay: int,
    min_holding_period: int,
    position_scaling: float,
    position_size_pct: float,
    amount_per_buy: Optional[float],
    take_profit: float,
    trailing_stop_loss: float,
    commission_per_trade: float,
    slippage_pct: float,
    fx_fee_pct: float,
    allow_fractional: bool,
    order_type: str,
    limit_offset_pct: float,
    stop_offset_pct: float,
    time_in_force: str,
    order_expiry_bars: int,
    trailing_stop_orders: bool,
    use_brackets: bool,
    bracket_stop_pct: float,
    bracket_target_pct: float,
) -> EngineConfig:
    """Validate and normalise the run-wide knobs. Raises ``ValidationError``."""
    strategy_mode = _validate_choice(strategy_mode, STRATEGY_MODES, 'strategy_mode')
    consecutive_signal_mode = _validate_choice(
        consecutive_signal_mode, CONSECUTIVE_SIGNAL_MODES, 'consecutive_signal_mode'
    )
    cooldown_bars = max(0, int(cooldown_bars or 0))
    delay = max(0, int(delay or 0))
    min_holding_period = max(0, int(min_holding_period or 0))

    order_type = _validate_choice(order_type, ORDER_TYPES, 'order_type')
    time_in_force = _validate_choice(time_in_force, TIME_IN_FORCE, 'time_in_force')
    limit_offset_pct = max(0.0, float(limit_offset_pct or 0))
    stop_offset_pct = max(0.0, float(stop_offset_pct or 0))
    order_expiry_bars = max(0, int(order_expiry_bars or 0))
    trailing_stop_orders = bool(trailing_stop_orders)
    # Resolve the bracket legs before deciding whether brackets are on: a
    # bracket with no stop and no target is not a bracket, and leaving the
    # flag set would silently disable the exits it replaced.
    bracket_stop = max(0.0, float(bracket_stop_pct or 0)) or max(0.0, float(trailing_stop_loss or 0))
    bracket_target = max(0.0, float(bracket_target_pct or 0)) or max(0.0, float(take_profit or 0))
    use_brackets = bool(use_brackets) and (bracket_stop > 0 or bracket_target > 0)
    if strategy_mode == 'accumulation':
        # Accumulation never exits, so an exit book would only ever be
        # cancelled again on the next bar. Say so once rather than pretend.
        if trailing_stop_orders or use_brackets:
            logger.warning(
                "strategy_mode='accumulation' has no exits — ignoring "
                "trailing_stop_orders / use_brackets."
            )
        trailing_stop_orders = False
        use_brackets = False
    uses_orders = order_type != 'market' or trailing_stop_orders or use_brackets

    if allow_fractional:
        def round_units(value: float) -> float:
            """Fractional shares: keep the exact quantity, floor at zero."""
            return float(value) if value > 0 else 0.0
    else:
        def round_units(value: float) -> float:
            """Whole shares: truncate toward zero, as a broker lot would."""
            return float(int(value)) if value > 0 else 0.0

    return EngineConfig(
        delay=delay,
        strategy_mode=strategy_mode,
        consecutive_signal_mode=consecutive_signal_mode,
        cooldown_bars=cooldown_bars,
        min_holding_period=min_holding_period,
        position_scaling=position_scaling,
        position_size_pct=position_size_pct,
        amount_per_buy=amount_per_buy,
        take_profit=max(0.0, float(take_profit or 0)),
        fee_rate=max(0.0, float(commission_per_trade or 0)) + max(0.0, float(fx_fee_pct or 0)),
        slippage_pct=max(0.0, float(slippage_pct or 0)),
        order_type=order_type,
        limit_offset=limit_offset_pct,
        stop_offset=stop_offset_pct,
        time_in_force=time_in_force,
        order_expiry_bars=order_expiry_bars,
        trailing_stop_orders=trailing_stop_orders,
        use_brackets=use_brackets,
        bracket_stop=bracket_stop,
        bracket_target=bracket_target,
        uses_orders=uses_orders,
        round_units=round_units,
    )


def build_symbol(
    symbol: str,
    df: pd.DataFrame,
    cfg: EngineConfig,
    account: Account,
    *,
    position_sizing_strategy: str,
    position_sizing_params: dict,
    buy_indicators: List[str],
    sell_indicators: List[str],
    use_signal_strength: bool,
    indicator_weights: Optional[Dict[str, float]],
    buy_threshold: float,
    sell_threshold: float,
    signal_logic: str,
    signal_window: int,
    trailing_stop_loss: float,
    stop_mode: str,
    volatility_window: int,
    allow_fractional: bool,
    use_low_for_stops: bool,
    gap_fills: bool,
) -> SymbolContext:
    """Prepare one symbol's arrays, callables and effective switches.

    Honours two optional columns a :mod:`lib.panel` frame carries: ``Tradable``
    (bars the symbol may trade; every bar when absent) and ``Mark`` (the
    valuation price; ``Close`` when absent). A plain single-symbol frame has
    neither, and runs exactly as it always has.
    """
    num_rows = len(df)
    signal_window = max(0, int(signal_window or 0))

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

    position_sizer = get_position_sizer(
        position_sizing_strategy, fractional=allow_fractional, **position_sizing_params
    )

    buy_signal_raw, sell_signal_raw = raw_signals(
        df, buy_indicators, sell_indicators,
        use_signal_strength=use_signal_strength,
        indicator_weights=indicator_weights,
        buy_threshold=buy_threshold,
        sell_threshold=sell_threshold,
        signal_logic=signal_logic,
        signal_window=signal_window,
    )

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

    close_prices = df['Close'].to_numpy(dtype=float)

    # High and Low are resolved unconditionally now that the order book can
    # need them; the legacy close-only stop check simply ignores them.
    low_prices = _numeric_column(df, 'Low')
    high_prices = _numeric_column(df, 'High')
    if use_low_for_stops and low_prices is None:
        logger.warning(
            "use_low_for_stops=True but 'Low' is missing or empty — "
            "falling back to close-only stop checks."
        )
        use_low_for_stops = False
    if cfg.uses_orders and (low_prices is None or high_prices is None):
        logger.warning(
            "Order types need 'High' and 'Low' to test intrabar touches; one "
            "is missing or empty, so every bar's range collapses to its "
            "open-to-close span and resting orders will fill less often."
        )

    # Session marks come from the timestamps unless the caller supplied a
    # Session_Start column. Without an Open column there is no gap price to
    # fill at, so gap handling turns itself off rather than inventing one.
    session_start = resolve_session_starts(df)
    session_id = np.cumsum(session_start) - 1 if num_rows else np.zeros(0, dtype=int)
    open_prices = None
    if gap_fills:
        open_prices = _numeric_column(df, 'Open')
        if open_prices is None:
            logger.warning(
                "gap_fills=True but 'Open' is missing or empty — overnight "
                "gaps through the trailing stop will fill at the close."
            )
            gap_fills = False

    if TRADABLE_COLUMN in df.columns:
        tradable = df[TRADABLE_COLUMN].to_numpy(dtype=bool)
        # The first bar back after a hole reopens this symbol the way a
        # session open reopens the market.
        after_hole = np.zeros(num_rows, dtype=bool)
        if num_rows > 1:
            after_hole[1:] = tradable[1:] & ~tradable[:-1]
        reopens = np.asarray(session_start, dtype=bool) | after_hole
    else:
        tradable = np.ones(num_rows, dtype=bool)
        reopens = session_start

    if MARK_COLUMN in df.columns:
        # NaN only before the symbol lists, when nothing can be held.
        mark_prices = pd.to_numeric(df[MARK_COLUMN], errors='coerce').fillna(0.0).to_numpy(dtype=float)
    else:
        mark_prices = close_prices

    return SymbolContext(
        symbol=symbol,
        cfg=cfg,
        account=account,
        frame=df,
        close_prices=close_prices,
        low_prices=low_prices,
        high_prices=high_prices,
        open_prices=open_prices,
        mark_prices=mark_prices,
        tradable=tradable,
        session_start=session_start,
        session_id=session_id,
        reopens=reopens,
        dates=df.index,
        buy_signal_raw=buy_signal_raw,
        sell_signal_raw=sell_signal_raw,
        use_low_for_stops=use_low_for_stops,
        gap_fills=gap_fills,
        effective_stop_mode=effective_stop_mode,
        position_sizing_strategy=position_sizing_strategy,
        size_position=size_position,
        long_stop_level=long_stop_level,
    )


def symbol_result_frame(
    ctx: SymbolContext,
    cash_value: np.ndarray,
    portfolio_value: np.ndarray,
) -> pd.DataFrame:
    """One symbol's result frame, against the account's cash and total value.

    For a single-symbol run that is the whole account. In a basket every
    symbol's frame carries the same ``Cash_Value`` and ``Portfolio_Value`` —
    the one account — while ``Stocks_Value``, ``Units`` and the ledgers are the
    symbol's own.
    """
    returns = market_returns(ctx.mark_prices)
    strategy_returns, cumulative_returns, cumulative_market_returns = calculate_returns(
        portfolio_value, returns
    )
    result_df = create_result_dataframe(
        ctx.frame, ctx.units, ctx.units_to_buy, ctx.units_to_sell, cash_value,
        ctx.stocks_value, portfolio_value,
        ctx.buy_signal_raw, ctx.sell_signal_raw,
        returns, strategy_returns, cumulative_returns, cumulative_market_returns,
        ctx.holding_period, ctx.trailing_stop,
        ctx.buy_triggered, ctx.buy_rejected, ctx.sell_triggered, ctx.sell_rejected,
        avg_entry_price=ctx.avg_entry_price, avg_cost_basis=ctx.avg_cost_basis,
        session_start=ctx.session_start, holding_sessions=ctx.holding_sessions
    )
    cfg = ctx.cfg
    # Record what was actually applied, not what was asked for — either may
    # have been downgraded to the percentage fallback.
    result_df.attrs['stop_mode'] = ctx.effective_stop_mode
    result_df.attrs['position_sizing_strategy'] = ctx.position_sizing_strategy
    result_df.attrs['trades'] = trades_to_frame(ctx.trades)
    result_df.attrs['fills'] = fills_to_frame(ctx.fill_rows)
    # What the order layer actually did, after accumulation mode or an empty
    # bracket turned any of it back off.
    result_df.attrs['order_type'] = cfg.order_type
    result_df.attrs['time_in_force'] = cfg.time_in_force
    result_df.attrs['trailing_stop_orders'] = cfg.trailing_stop_orders
    result_df.attrs['use_brackets'] = cfg.use_brackets
    return result_df
