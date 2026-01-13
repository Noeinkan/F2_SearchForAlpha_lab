import numpy as np
import pandas as pd
from typing import List, Callable, Dict, Union

def backtest(df: pd.DataFrame, 
             initial_capital: float,
             position_sizing_strategy: str,
             position_sizing_params: dict,
             buy_indicators: List[str],
             sell_indicators: List[str],
             use_signal_strength: bool = False,
             indicator_weights: Dict[str, float] = None,
             buy_threshold: float = 0.5,
             sell_threshold: float = 0.5,
             delay: int = 1,
             min_holding_period: int = 0,
             position_scaling: float = 0.25,
             trailing_stop_loss: float = 0.05,
             volatility_window: int = 20) -> pd.DataFrame:

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
        buy_signal_strength = df[buy_indicators].sum(axis=1)
        sell_signal_strength = df[sell_indicators].sum(axis=1)

    # Calculate volatility
    df['Volatility'] = df['Close'].pct_change().rolling(window=volatility_window).std()

    close_prices = df['Close'].values
    returns = np.zeros(num_rows)
    returns[1:] = (close_prices[1:] - close_prices[:-1]) / close_prices[:-1]

    last_buy_price = 0
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
            last_buy_price = 0
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
                    last_buy_price = close_price
                    trailing_stop[i] = close_price * (1 - trailing_stop_loss)
                else:
                    units[i] = prev_units
                    cash_value[i] = prev_cash_value
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
                            last_buy_price = 0
                            trailing_stop[i] = np.inf
                        else:
                            trailing_stop[i] = max(trailing_stop[i-1], close_price * (1 - trailing_stop_loss))
                    else:
                        units[i] = prev_units
                        cash_value[i] = prev_cash_value
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

    return result_df



def calculate_signal_strengths(df: pd.DataFrame, buy_indicators: List[str], sell_indicators: List[str], indicator_weights: Dict[str, float] = None) -> tuple:
    num_rows = len(df)
    buy_signal_strength = np.zeros(num_rows)
    sell_signal_strength = np.zeros(num_rows)

    for i in range(num_rows):
        if indicator_weights is not None:
            buy_signal_strength[i] = sum(df.loc[df.index[i], ind] * indicator_weights.get(ind, 1.0) for ind in buy_indicators)
            sell_signal_strength[i] = sum(df.loc[df.index[i], ind] * indicator_weights.get(ind, 1.0) for ind in sell_indicators)
        else:
            buy_signal_strength[i] = sum(df.loc[df.index[i], ind] for ind in buy_indicators)
            sell_signal_strength[i] = sum(df.loc[df.index[i], ind] for ind in sell_indicators)

    return buy_signal_strength, sell_signal_strength

def calculate_returns(portfolio_value: np.ndarray, returns: np.ndarray) -> tuple:
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
    if strategy == "percentage_of_portfolio":
        return lambda portfolio_value, close_price: percentage_of_portfolio(portfolio_value, close_price, kwargs.get('percent', 0.01))
    elif strategy == "fixed_dollar_amount":
        return lambda portfolio_value, close_price: fixed_dollar_amount(close_price, kwargs.get('amount', 1000))
    elif strategy == "volatility_based":
        return lambda portfolio_value, close_price, volatility: volatility_based(portfolio_value, close_price, volatility, kwargs.get('target_volatility', 0.01))
    elif strategy == "kelly_criterion":
        return lambda portfolio_value, close_price: kelly_criterion(kwargs['win_rate'], kwargs['win_loss_ratio'], portfolio_value, close_price)
    elif strategy == "risk_based":
        return lambda portfolio_value, close_price: risk_based(portfolio_value, close_price, kwargs['stop_loss_percent'], kwargs.get('risk_percent', 0.01))
    else:
        raise ValueError(f"Unknown position sizing strategy: {strategy}")

def percentage_of_portfolio(portfolio_value: float, close_price: float, percent: float = 0.02) -> int:
    return int((portfolio_value * percent) // close_price)

def fixed_dollar_amount(close_price: float, amount: float = 500) -> int:
    """Calcola la dimensione della posizione in base a un importo fisso in dollari."""
    return int(amount // close_price)

def volatility_based(portfolio_value: float, close_price: float, volatility: float, target_volatility: float = 0.01) -> int:
    """Calcola la dimensione della posizione in base alla volatilità dell'asset."""
    position_size = (target_volatility / volatility) * portfolio_value
    return int(position_size // close_price)

def kelly_criterion(win_rate: float, win_loss_ratio: float, portfolio_value: float, close_price: float) -> int:
    """Calcola la dimensione della posizione in base al criterio di Kelly."""
    kelly_percentage = win_rate - ((1 - win_rate) / win_loss_ratio)
    kelly_percentage = max(0, min(kelly_percentage, 1))  # Ensure it's between 0 and 1
    position_size = kelly_percentage * portfolio_value
    return int(position_size // close_price)

def risk_based(portfolio_value: float, close_price: float, stop_loss_percent: float, risk_percent: float = 0.01) -> int:
    """Calcola la dimensione della posizione in base a un rischio fisso per trade."""
    risk_amount = portfolio_value * risk_percent
    stop_loss_amount = close_price * stop_loss_percent
    position_size = risk_amount / stop_loss_amount
    return int(position_size)

def calculate_max_drawdown(df: pd.DataFrame) -> float:
    """Calcola il massimo drawdown."""
    cumulative_returns = df['Cumulative_Returns']
    peak = cumulative_returns.expanding(min_periods=1).max()
    drawdown = (cumulative_returns / peak) - 1
    return drawdown.min()

def run_backtest(df: pd.DataFrame, initial_capital: float, buy_indicators: List[str], sell_indicators: List[str]) -> pd.DataFrame:
    position_sizing_params = {
        "win_rate": 0.5,  # You may want to calculate this dynamically
        "win_loss_ratio": 1.5  # You may want to calculate this dynamically
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