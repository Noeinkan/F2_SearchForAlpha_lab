"""Turn the loop's arrays into the result frame callers read."""

from typing import Optional

import numpy as np
import pandas as pd


def market_returns(prices: np.ndarray) -> np.ndarray:
    """Bar-on-bar returns of *prices*, guarded against a zero/NaN previous price."""
    num_rows = len(prices)
    returns = np.zeros(num_rows)
    if num_rows > 1:
        prev_close = prices[:-1]
        positive = prev_close > 0
        with np.errstate(divide='ignore', invalid='ignore'):
            step = np.where(
                positive,
                np.diff(prices) / np.where(positive, prev_close, 1.0),
                0.0,
            )
        returns[1:] = np.nan_to_num(step, nan=0.0, posinf=0.0, neginf=0.0)
    return returns


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
    avg_cost_basis: Optional[np.ndarray] = None,
    session_start: Optional[np.ndarray] = None,
    holding_sessions: Optional[np.ndarray] = None
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
    # Session_Start is written even when it came in on df, so the result always
    # states which boundaries the run actually used rather than leaving the
    # reader to re-infer them.
    if session_start is not None:
        df['Session_Start'] = session_start
    if holding_sessions is not None:
        df['Holding_Sessions'] = holding_sessions
    return df
