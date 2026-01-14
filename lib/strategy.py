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
    volatility_window: int = 20
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
    
        # Initialize arrays
        units = np.zeros(num_rows)
        cash_value = np.full(num_rows, initial_capital)
        stocks_value = np.zeros(num_rows)
        portfolio_value = np.full(num_rows, initial_capital)
        units_to_buy = np.zeros(num_rows)
        units_to_sell = np.zeros(num_rows)
        buy_signal_counter = np.zeros(num_rows, dtype=int)
        sell_signal_counter = np.zeros(num_rows, dtype=int)
        holding_period = np.zeros(num_rows, dtype=int)
        trailing_stop = np.full(num_rows, np.inf)

        # Get position sizer function
        position_sizer = get_position_sizer(position_sizing_strategy, **position_sizing_params)

        if use_signal_strength:
            buy_signal_strength, sell_signal_strength = calculate_signal_strengths(df, buy_indicators, sell_indicators, indicator_weights)
        else:
            buy_signal_strength = df[buy_indicators].sum(axis=1).values
            sell_signal_strength = df[sell_indicators].sum(axis=1).values

        # Calculate volatility
        df = df.copy()
        df['Volatility'] = df['Close'].pct_change().rolling(window=volatility_window).std()

        close_prices = df['Close'].values
        returns = np.zeros(num_rows)
        returns[1:] = np.diff(close_prices) / close_prices[:-1]

        position_size = 0

        for i in range(1 + delay, num_rows):
            close_price = close_prices[i]
            prev_portfolio_value = portfolio_value[i-1]
            prev_cash_value = cash_value[i-1]
            prev_units = units[i-1]

            # Update holding period
            if prev_units > 0:
                holding_period[i] = holding_period[i-1] + 1
            else:
                holding_period[i] = 0

            # Check for trailing stop loss
            if prev_units > 0 and close_price <= trailing_stop[i-1]:
                units_to_sell[i] = prev_units
                value_to_sell = units_to_sell[i] * close_price
                units[i] = 0
                cash_value[i] = prev_cash_value + value_to_sell
                position_size = 0
                trailing_stop[i] = np.inf
            else:
                # Buy signal
                if (use_signal_strength and buy_signal_strength[i] > buy_threshold) or \
                   (not use_signal_strength and buy_signal_strength[i] > 0):
                    buy_signal_counter[i] = buy_signal_counter[i-1] + 1
                    position_size = min(position_size + position_scaling, 1)
                    
                    if position_sizing_strategy == "volatility_based":
                        units_to_buy[i] = position_sizer(prev_portfolio_value, close_price, df['Volatility'].iloc[i])
                    else:
                        units_to_buy[i] = position_sizer(prev_portfolio_value, close_price)
                    
                    units_to_buy[i] = int(units_to_buy[i] * position_size)
                    
                    if units_to_buy[i] > 0:
                        value_to_buy = units_to_buy[i] * close_price
                        units[i] = prev_units + units_to_buy[i]
                        cash_value[i] = prev_cash_value - value_to_buy
                        trailing_stop[i] = close_price * (1 - trailing_stop_loss)
                    else:
                        units[i] = prev_units
                        cash_value[i] = prev_cash_value
                        trailing_stop[i] = trailing_stop[i-1] if prev_units > 0 else np.inf
                # Sell signal
                elif (use_signal_strength and sell_signal_strength[i] > sell_threshold) or \
                     (not use_signal_strength and sell_signal_strength[i] > 0):
                    if holding_period[i] >= min_holding_period:
                        sell_signal_counter[i] = sell_signal_counter[i-1] + 1
                        position_size = max(position_size - position_scaling, 0)
                        
                        if position_sizing_strategy == "volatility_based":
                            units_to_sell[i] = position_sizer(prev_portfolio_value, close_price, df['Volatility'].iloc[i])
                        else:
                            units_to_sell[i] = position_sizer(prev_portfolio_value, close_price)
                        
                        units_to_sell[i] = min(int(units_to_sell[i] * (1 - position_size)), prev_units)
                        
                        if units_to_sell[i] > 0:
                            value_to_sell = units_to_sell[i] * close_price
                            units[i] = prev_units - units_to_sell[i]
                            cash_value[i] = prev_cash_value + value_to_sell
                            if units[i] == 0:
                                trailing_stop[i] = np.inf
                            else:
                                trailing_stop[i] = max(trailing_stop[i-1], close_price * (1 - trailing_stop_loss))
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
                    trailing_stop[i] = max(trailing_stop[i-1], close_price * (1 - trailing_stop_loss)) if prev_units > 0 else np.inf

            stocks_value[i] = units[i] * close_price
            portfolio_value[i] = cash_value[i] + stocks_value[i]

        # Calculate returns and create result DataFrame
        strategy_returns, cumulative_returns, cumulative_market_returns = calculate_returns(portfolio_value, returns)
        
        result_df = create_result_dataframe(df, units, units_to_buy, units_to_sell, cash_value, stocks_value, portfolio_value,
                                            buy_signal_strength > buy_threshold, sell_signal_strength > sell_threshold,
                                            returns, strategy_returns, cumulative_returns, cumulative_market_returns,
                                            holding_period, trailing_stop)

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


def calculate_returns(portfolio_value: np.ndarray, returns: np.ndarray) -> tuple:
    """Calculate strategy and market returns."""
    strategy_returns = np.zeros_like(returns)
    strategy_returns[1:] = (portfolio_value[1:] - portfolio_value[:-1]) / portfolio_value[:-1]
    cumulative_returns = np.cumprod(1 + strategy_returns)
    cumulative_market_returns = np.cumprod(1 + returns)
    return strategy_returns, cumulative_returns, cumulative_market_returns

def create_result_dataframe(df: pd.DataFrame, units: np.ndarray, units_to_buy: np.ndarray, units_to_sell: np.ndarray, 
                            cash_value: np.ndarray, stocks_value: np.ndarray, portfolio_value: np.ndarray, 
                            buy_position: np.ndarray, sell_position: np.ndarray, returns: np.ndarray, 
                            strategy_returns: np.ndarray, cumulative_returns: np.ndarray, 
                            cumulative_market_returns: np.ndarray, holding_period: np.ndarray,
                            trailing_stop: np.ndarray) -> pd.DataFrame:
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
    sell_indicators: List[str]
) -> pd.DataFrame:
    """
    Convenience function to run a backtest with default Kelly Criterion sizing.
    
    Args:
        df: DataFrame with price data and signals.
        initial_capital: Starting capital.
        buy_indicators: List of buy signal columns.
        sell_indicators: List of sell signal columns.
        
    Returns:
        DataFrame with backtest results.
    """
    position_sizing_params = {
        "win_rate": 0.5,
        "win_loss_ratio": 1.5
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
        min_holding_period=5,
        position_scaling=0.25,
        trailing_stop_loss=0.05,
        volatility_window=20
    )