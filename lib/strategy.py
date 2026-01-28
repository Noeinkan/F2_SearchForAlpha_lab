# Strategy module with backtesting engine
"""
Backtesting engine for trading strategies with comprehensive error handling,
logging, and optimized operations for performance.
"""

import logging
import numpy as np
import pandas as pd
from typing import List, Callable, Dict, Optional

# Configure module logger
logger = logging.getLogger(__name__)


class BacktestError(Exception):
    """Custom exception for backtest-related errors."""
    pass


class ValidationError(Exception):
    """Custom exception for input validation errors."""
    pass


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
    volatility_window: int = 20,
    strategy_mode: str = 'trading',
    amount_per_buy: float = None,
    position_size_pct: float = 100,
    take_profit: float = 0.0,
    signal_logic: str = 'or',
    signal_window: int = 0,
    consecutive_signal_mode: str = 'scale_in',
    cooldown_bars: int = 0,
    commission_per_trade: float = 0.0,
    slippage_pct: float = 0.0005,
    fx_fee_pct: float = 0.0015
) -> pd.DataFrame:
    """
    Run a backtest on the provided DataFrame.

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
        delay: Number of periods to delay signal execution.
        min_holding_period: Minimum number of periods to hold a position.
        position_scaling: Factor for scaling position size on repeated signals.
        trailing_stop_loss: Trailing stop loss percentage.
        volatility_window: Window for volatility calculation.
        strategy_mode: 'trading' (buy/sell cycles), 'accumulation' (DCA), or 'rebalancing' (partial).
        amount_per_buy: Fixed dollar amount per buy signal (for accumulation mode).
        position_size_pct: Percentage of portfolio per trade (for rebalancing mode).
        take_profit: Take profit percentage (0 disables).
        signal_logic: 'or' (any signal triggers) or 'and' (all signals must agree).
        signal_window: Window size (candles) for AND confirmation across signals.
        consecutive_signal_mode: How to handle repeated triggers ('scale_in', 'edge', 'cooldown', 'reset_cooldown').
        cooldown_bars: Bars to wait between same-direction triggers (used by cooldown modes).
        commission_per_trade: Commission fee as % of trade notional (0.001 = 0.1%).
        slippage_pct: Slippage as % of price (0.0005 = 5 bps).
        fx_fee_pct: FX fee as % of notional (Trading 212 UK default 0.15%).

    Returns:
        DataFrame with backtest results including portfolio values and metrics.

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
        consecutive_signal_mode = (consecutive_signal_mode or 'scale_in').lower()
        cooldown_bars = max(0, int(cooldown_bars or 0))
    
        # Initialize arrays
        units = np.zeros(num_rows)
        cash_value = np.full(num_rows, initial_capital)
        stocks_value = np.zeros(num_rows)
        portfolio_value = np.full(num_rows, initial_capital)
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

        # Get position sizer function
        position_sizer = get_position_sizer(position_sizing_strategy, **position_sizing_params)

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

        # Calculate volatility
        df = df.copy()
        df['Volatility'] = df['Close'].pct_change().rolling(window=volatility_window).std()

        close_prices = df['Close'].values
        returns = np.zeros(num_rows)
        returns[1:] = np.diff(close_prices) / close_prices[:-1]

        position_size = 0
        buy_cooldown = 0
        sell_cooldown = 0
        buy_wait_reset = False
        sell_wait_reset = False

        take_profit = max(0.0, float(take_profit or 0))
        fee_rate = max(0.0, float(commission_per_trade or 0)) + max(0.0, float(fx_fee_pct or 0))
        slippage_pct = max(0.0, float(slippage_pct or 0))

        for i in range(1 + delay, num_rows):
            close_price = close_prices[i]
            prev_portfolio_value = portfolio_value[i-1]
            prev_cash_value = cash_value[i-1]
            prev_units = units[i-1]
            avg_entry_price[i] = avg_entry_price[i-1]

            # Update holding period
            if prev_units > 0:
                holding_period[i] = holding_period[i-1] + 1
            else:
                holding_period[i] = 0

            # Check for trailing stop loss (disabled for accumulation mode - long term hold)
            if strategy_mode != 'accumulation' and prev_units > 0 and close_price <= trailing_stop[i-1]:
                units_to_sell[i] = prev_units
                execution_price = close_price * (1 - slippage_pct)
                value_to_sell = units_to_sell[i] * execution_price
                total_sell_fee = value_to_sell * fee_rate
                units[i] = 0
                cash_value[i] = prev_cash_value + value_to_sell - total_sell_fee
                position_size = 0
                trailing_stop[i] = np.inf
                avg_entry_price[i] = 0
            elif strategy_mode != 'accumulation' and take_profit > 0 and prev_units > 0 and \
                 avg_entry_price[i-1] > 0 and close_price >= avg_entry_price[i-1] * (1 + take_profit) and \
                 holding_period[i] >= min_holding_period:
                units_to_sell[i] = prev_units
                execution_price = close_price * (1 - slippage_pct)
                value_to_sell = units_to_sell[i] * execution_price
                total_sell_fee = value_to_sell * fee_rate
                units[i] = 0
                cash_value[i] = prev_cash_value + value_to_sell - total_sell_fee
                position_size = 0
                trailing_stop[i] = np.inf
                avg_entry_price[i] = 0
            else:
                current_buy_signal = bool(buy_signal_raw[i])
                current_sell_signal = bool(sell_signal_raw[i])
                prev_buy_signal = bool(buy_signal_raw[i - 1]) if i > 0 else False
                prev_sell_signal = bool(sell_signal_raw[i - 1]) if i > 0 else False

                if consecutive_signal_mode == 'reset_cooldown' and not current_buy_signal:
                    buy_wait_reset = False
                if consecutive_signal_mode == 'reset_cooldown' and not current_sell_signal:
                    sell_wait_reset = False

                if consecutive_signal_mode == 'edge':
                    allow_buy = current_buy_signal and not prev_buy_signal
                    allow_sell = current_sell_signal and not prev_sell_signal
                elif consecutive_signal_mode == 'cooldown':
                    allow_buy = current_buy_signal and buy_cooldown == 0
                    allow_sell = current_sell_signal and sell_cooldown == 0
                elif consecutive_signal_mode == 'reset_cooldown':
                    allow_buy = current_buy_signal and buy_cooldown == 0 and not buy_wait_reset
                    allow_sell = current_sell_signal and sell_cooldown == 0 and not sell_wait_reset
                else:
                    allow_buy = current_buy_signal
                    allow_sell = current_sell_signal

                if current_buy_signal and not allow_buy:
                    buy_rejected[i] = True
                if current_sell_signal and not allow_sell:
                    sell_rejected[i] = True

                # Buy signal
                if allow_buy:
                    buy_triggered[i] = True
                    buy_signal_counter[i] = buy_signal_counter[i-1] + 1

                    # Calculate units to buy based on strategy mode
                    if strategy_mode == 'accumulation':
                        # Fixed dollar amount per buy (DCA style)
                        buy_amount = amount_per_buy if amount_per_buy else 1000
                        if prev_cash_value >= buy_amount:
                            units_to_buy[i] = int(buy_amount // close_price)
                        else:
                            units_to_buy[i] = int(prev_cash_value // close_price)
                    elif strategy_mode == 'rebalancing':
                        # Percentage of available cash
                        pct = (position_size_pct or 100) / 100.0
                        buy_amount = prev_cash_value * pct
                        units_to_buy[i] = int(buy_amount // close_price)
                    else:
                        # Trading mode - original logic
                        position_size = min(position_size + position_scaling, 1)
                        if position_sizing_strategy == "volatility_based":
                            units_to_buy[i] = position_sizer(prev_portfolio_value, close_price, df['Volatility'].iloc[i])
                        else:
                            units_to_buy[i] = position_sizer(prev_portfolio_value, close_price)
                        units_to_buy[i] = int(units_to_buy[i] * position_size)

                    if units_to_buy[i] > 0:
                        execution_price = close_price * (1 + slippage_pct)
                        total_cost_per_unit = execution_price * (1 + fee_rate)
                        max_units_affordable = int(prev_cash_value // total_cost_per_unit) if total_cost_per_unit > 0 else 0
                        if max_units_affordable <= 0:
                            units_to_buy[i] = 0
                        elif units_to_buy[i] > max_units_affordable:
                            units_to_buy[i] = max_units_affordable

                    if units_to_buy[i] > 0:
                        execution_price = close_price * (1 + slippage_pct)
                        value_to_buy = units_to_buy[i] * execution_price
                        total_buy_fee = value_to_buy * fee_rate
                        total_buy_cost = value_to_buy + total_buy_fee
                        units[i] = prev_units + units_to_buy[i]
                        cash_value[i] = prev_cash_value - total_buy_cost
                        if units[i] > 0:
                            avg_entry_price[i] = (
                                (avg_entry_price[i-1] * prev_units) + total_buy_cost
                            ) / units[i]
                        if strategy_mode != 'accumulation':
                            trailing_stop[i] = close_price * (1 - trailing_stop_loss)
                        else:
                            trailing_stop[i] = np.inf  # No trailing stop for accumulation
                        if consecutive_signal_mode in ('cooldown', 'reset_cooldown') and cooldown_bars > 0:
                            buy_cooldown = cooldown_bars
                        if consecutive_signal_mode == 'reset_cooldown':
                            buy_wait_reset = True
                    else:
                        units[i] = prev_units
                        cash_value[i] = prev_cash_value
                        trailing_stop[i] = trailing_stop[i-1] if prev_units > 0 else np.inf

                # Sell signal (skipped entirely for accumulation mode)
                elif strategy_mode != 'accumulation' and allow_sell:
                    sell_triggered[i] = True
                    if holding_period[i] >= min_holding_period:
                        sell_signal_counter[i] = sell_signal_counter[i-1] + 1

                        if strategy_mode == 'rebalancing':
                            # Sell a percentage of current position
                            pct = (position_size_pct or 100) / 100.0
                            units_to_sell[i] = int(prev_units * pct)
                        else:
                            # Trading mode - original logic
                            position_size = max(position_size - position_scaling, 0)
                            if position_sizing_strategy == "volatility_based":
                                units_to_sell[i] = position_sizer(prev_portfolio_value, close_price, df['Volatility'].iloc[i])
                            else:
                                units_to_sell[i] = position_sizer(prev_portfolio_value, close_price)
                            units_to_sell[i] = min(int(units_to_sell[i] * (1 - position_size)), prev_units)

                        if units_to_sell[i] > 0:
                            execution_price = close_price * (1 - slippage_pct)
                            value_to_sell = units_to_sell[i] * execution_price
                            total_sell_fee = value_to_sell * fee_rate
                            units[i] = prev_units - units_to_sell[i]
                            cash_value[i] = prev_cash_value + value_to_sell - total_sell_fee
                            if units[i] == 0:
                                trailing_stop[i] = np.inf
                                avg_entry_price[i] = 0
                            else:
                                trailing_stop[i] = max(trailing_stop[i-1], close_price * (1 - trailing_stop_loss))
                            if consecutive_signal_mode in ('cooldown', 'reset_cooldown') and cooldown_bars > 0:
                                sell_cooldown = cooldown_bars
                            if consecutive_signal_mode == 'reset_cooldown':
                                sell_wait_reset = True
                        else:
                            units[i] = prev_units
                            cash_value[i] = prev_cash_value
                            trailing_stop[i] = max(trailing_stop[i-1], close_price * (1 - trailing_stop_loss)) if prev_units > 0 else np.inf
                    else:
                        units[i] = prev_units
                        cash_value[i] = prev_cash_value
                        trailing_stop[i] = max(trailing_stop[i-1], close_price * (1 - trailing_stop_loss)) if prev_units > 0 else np.inf
                else:
                    units[i] = prev_units
                    cash_value[i] = prev_cash_value
                    if strategy_mode == 'accumulation':
                        trailing_stop[i] = np.inf
                    else:
                        trailing_stop[i] = max(trailing_stop[i-1], close_price * (1 - trailing_stop_loss)) if prev_units > 0 else np.inf

            stocks_value[i] = units[i] * close_price
            portfolio_value[i] = cash_value[i] + stocks_value[i]

            if buy_cooldown > 0:
                buy_cooldown -= 1
            if sell_cooldown > 0:
                sell_cooldown -= 1

        # Calculate returns and create result DataFrame
        strategy_returns, cumulative_returns, cumulative_market_returns = calculate_returns(portfolio_value, returns)
        
        result_df = create_result_dataframe(
            df, units, units_to_buy, units_to_sell, cash_value, stocks_value, portfolio_value,
            buy_signal_strength > buy_threshold, sell_signal_strength > sell_threshold,
            returns, strategy_returns, cumulative_returns, cumulative_market_returns,
            holding_period, trailing_stop, buy_triggered, buy_rejected, sell_triggered, sell_rejected
        )

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
    """Calculate strategy and market returns."""
    strategy_returns = np.zeros_like(returns)
    strategy_returns[1:] = (portfolio_value[1:] - portfolio_value[:-1]) / portfolio_value[:-1]
    cumulative_returns = np.cumprod(1 + strategy_returns)
    cumulative_market_returns = np.cumprod(1 + returns)
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
    sell_rejected: np.ndarray
) -> pd.DataFrame:
    df = df.copy()
    df['Units'] = units
    df['Units_to_buy'] = units_to_buy
    df['Units_to_sell'] = units_to_sell
    df['Cash_Value'] = cash_value
    df['Stocks_Value'] = stocks_value
    df['Portfolio_Value'] = portfolio_value
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
    return df

def get_position_sizer(strategy: str, **kwargs) -> Callable:
    """
    Get the position sizing function for the specified strategy.
    
    Args:
        strategy: Name of the position sizing strategy.
        **kwargs: Additional parameters for the strategy.
        
    Returns:
        Callable position sizing function.
        
    Raises:
        ValueError: If strategy is not recognized.
    """
    strategies = {
        "percentage_of_portfolio": lambda pv, cp: percentage_of_portfolio(
            pv, cp, kwargs.get('percent', 0.01)
        ),
        "fixed_dollar_amount": lambda pv, cp: fixed_dollar_amount(
            cp, kwargs.get('amount', 1000)
        ),
        "volatility_based": lambda pv, cp, vol: volatility_based(
            pv, cp, vol, kwargs.get('target_volatility', 0.01)
        ),
        "kelly_criterion": lambda pv, cp: kelly_criterion(
            kwargs['win_rate'], kwargs['win_loss_ratio'], pv, cp
        ),
        "risk_based": lambda pv, cp: risk_based(
            pv, cp, kwargs['stop_loss_percent'], kwargs.get('risk_percent', 0.01)
        )
    }
    
    if strategy not in strategies:
        available = ", ".join(strategies.keys())
        raise ValueError(f"Unknown position sizing strategy: '{strategy}'. Available: {available}")
    
    return strategies[strategy]


def percentage_of_portfolio(portfolio_value: float, close_price: float, percent: float = 0.02) -> int:
    """Calculate position size as percentage of portfolio."""
    if close_price <= 0:
        return 0
    return int((portfolio_value * percent) // close_price)

def fixed_dollar_amount(close_price: float, amount: float = 500) -> int:
    """Calculate position size based on fixed dollar amount."""
    if close_price <= 0:
        return 0
    return int(amount // close_price)


def volatility_based(
    portfolio_value: float,
    close_price: float,
    volatility: float,
    target_volatility: float = 0.01
) -> int:
    """Calculate position size based on asset volatility."""
    if close_price <= 0 or volatility <= 0:
        return 0
    position_size = (target_volatility / volatility) * portfolio_value
    return int(position_size // close_price)


def kelly_criterion(
    win_rate: float,
    win_loss_ratio: float,
    portfolio_value: float,
    close_price: float
) -> int:
    """Calculate position size using Kelly Criterion."""
    if close_price <= 0 or win_loss_ratio <= 0:
        return 0
    kelly_percentage = win_rate - ((1 - win_rate) / win_loss_ratio)
    kelly_percentage = max(0, min(kelly_percentage, 1))
    position_size = kelly_percentage * portfolio_value
    return int(position_size // close_price)


def risk_based(
    portfolio_value: float,
    close_price: float,
    stop_loss_percent: float,
    risk_percent: float = 0.01
) -> int:
    """Calculate position size based on fixed risk per trade."""
    if close_price <= 0 or stop_loss_percent <= 0:
        return 0
    risk_amount = portfolio_value * risk_percent
    stop_loss_amount = close_price * stop_loss_percent
    position_size = risk_amount / stop_loss_amount
    return int(position_size)


def calculate_max_drawdown(df: pd.DataFrame) -> float:
    """Calculate the maximum drawdown from cumulative returns."""
    if 'Cumulative_Returns' not in df.columns:
        logger.warning("Cumulative_Returns column not found")
        return 0.0
    cumulative_returns = df['Cumulative_Returns']
    peak = cumulative_returns.expanding(min_periods=1).max()
    drawdown = (cumulative_returns / peak) - 1
    return drawdown.min()


def run_backtest(
    df: pd.DataFrame,
    initial_capital: float,
    buy_indicators: List[str],
    sell_indicators: List[str],
    strategy_mode: str = 'trading',
    amount_per_buy: float = None,
    position_size_pct: float = 100,
    kelly_win_rate: float = 0.5,
    kelly_win_loss_ratio: float = 1.5,
    min_holding_period: int = 5,
    trailing_stop_loss: float = 0.05,
    position_scaling: float = 0.25,
    take_profit: float = 0.0,
    signal_logic: str = 'or',
    signal_window: int = 0,
    consecutive_signal_mode: str = 'scale_in',
    cooldown_bars: int = 0,
    commission_per_trade: float = 0.0,
    slippage_pct: float = 0.0005,
    fx_fee_pct: float = 0.0015
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
        position_scaling: Position scaling factor on repeated buys.
        take_profit: Take profit percentage (0 disables).
        signal_logic: 'or' (any signal triggers) or 'and' (all signals must agree).
        signal_window: Window size (candles) for AND confirmation across signals.
        consecutive_signal_mode: How to handle repeated triggers ('scale_in', 'edge', 'cooldown', 'reset_cooldown').
        cooldown_bars: Bars to wait between same-direction triggers.
        commission_per_trade: Commission fee as % of trade notional (0.001 = 0.1%).
        slippage_pct: Slippage as % of price (0.0005 = 5 bps).
        fx_fee_pct: FX fee as % of notional (Trading 212 UK default 0.15%).

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
        fx_fee_pct=fx_fee_pct
    )