"""
Dashboard Helper Functions
Utility functions for data processing and optimization.
"""

import logging
import itertools
from typing import List, Tuple, Dict, Any, Optional

import numpy as np
import pandas as pd
import yfinance as yf

from lib.dash.state import dashboard_state
from lib.strategy import run_backtest
from lib.signals.indicators import classify_signal_columns

logger = logging.getLogger(__name__)


def format_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    Format DataFrame for display in data tables.

    Args:
        df: Input DataFrame

    Returns:
        Formatted DataFrame with rounded floats
    """
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == 'float64':
            df[col] = df[col].round(2)
    return df


def fetch_data_with_cache(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch data with caching support.

    Args:
        ticker: Stock ticker symbol
        start_date: Start date string
        end_date: End date string

    Returns:
        DataFrame with OHLCV data

    Raises:
        ValueError: If no data available for ticker
    """
    cache_key = f"{ticker}_{start_date}_{end_date}"
    cached = dashboard_state.get_cached_data(cache_key)

    if cached is not None:
        logger.debug(f"Cache hit for {cache_key}")
        return cached

    logger.info(f"Fetching data for {ticker}")
    df = yf.download(ticker, start=start_date, end=end_date)
    if df.empty:
        raise ValueError(f"No data available for {ticker}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    # yfinance can append a placeholder row for the current/incomplete
    # period with NaN OHLCV (seen on non-trading days). Such a row blanks
    # the live price header ($nan) and feeds a NaN candle into the chart,
    # so drop any rows that have no usable Close.
    if 'Close' in df.columns:
        df = df[df['Close'].notna()]
    if df.empty:
        raise ValueError(f"No data available for {ticker}")

    dashboard_state.set_cached_data(cache_key, df)
    return df


def extract_signals(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """
    Extract buy and sell signal column names from DataFrame.

    Args:
        df: DataFrame with signal columns

    Returns:
        Tuple of (buy_signals, sell_signals) lists
    """
    classified = classify_signal_columns(df.columns.tolist())
    buy_signals = classified['buy']
    sell_signals = classified['sell']
    return buy_signals, sell_signals


def generate_signal_combinations(
    buy_signals: List[str],
    sell_signals: List[str],
    max_signals: int = 3
) -> List[Tuple[Tuple[str, ...], Tuple[str, ...]]]:
    """
    Generate combinations of buy and sell signals.

    Args:
        buy_signals: List of buy signal column names
        sell_signals: List of sell signal column names
        max_signals: Maximum number of signals per side

    Returns:
        List of (buy_combo, sell_combo) tuples
    """
    all_combinations = []
    for i in range(1, min(max_signals + 1, len(buy_signals) + 1)):
        for j in range(1, min(max_signals + 1, len(sell_signals) + 1)):
            buy_combos = list(itertools.combinations(buy_signals, i))
            sell_combos = list(itertools.combinations(sell_signals, j))
            all_combinations.extend(itertools.product(buy_combos, sell_combos))
    return all_combinations


def evaluate_signal_combination(
    df: pd.DataFrame,
    initial_capital: float,
    buy_combo: Tuple[str, ...],
    sell_combo: Tuple[str, ...]
) -> Dict[str, Any]:
    """
    Evaluate a single combination of buy and sell signals.

    Args:
        df: DataFrame with price data and signals
        initial_capital: Starting capital
        buy_combo: Tuple of buy signal column names
        sell_combo: Tuple of sell signal column names

    Returns:
        Dict with backtest results
    """
    try:
        result_df = run_backtest(
            df=df,
            initial_capital=initial_capital,
            buy_indicators=list(buy_combo),
            sell_indicators=list(sell_combo)
        )

        final_value = result_df['Portfolio_Value'].iloc[-1]
        total_return = (final_value - initial_capital) / initial_capital * 100

        returns = result_df['Strategy_Returns'].dropna()
        sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0

        cumulative = (1 + returns).cumprod()
        peak = cumulative.expanding().max()
        drawdown = ((cumulative - peak) / peak).min() * 100

        return {
            'Buy_Signals': ', '.join(buy_combo),
            'Sell_Signals': ', '.join(sell_combo),
            'Final_Value': final_value,
            'Total_Return_%': total_return,
            'Sharpe_Ratio': sharpe,
            'Max_Drawdown_%': drawdown,
            'Trades': result_df['Position'].diff().abs().sum() / 2
        }
    except Exception as e:
        logger.error(f"Error testing combination: {e}")
        return {
            'Buy_Signals': ', '.join(buy_combo),
            'Sell_Signals': ', '.join(sell_combo),
            'Error': str(e)
        }


def calculate_performance_metrics(result_df: pd.DataFrame, initial_capital: float) -> Dict[str, float]:
    """
    Calculate performance metrics from backtest results.

    Args:
        result_df: DataFrame with backtest results
        initial_capital: Starting capital

    Returns:
        Dict with performance metrics
    """
    final_value = result_df['Portfolio_Value'].iloc[-1]
    total_return = (final_value - initial_capital) / initial_capital * 100

    returns = result_df['Strategy_Returns'].dropna()

    # Sharpe ratio (annualized)
    sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0

    # Max drawdown
    cumulative = (1 + returns).cumprod()
    peak = cumulative.expanding().max()
    drawdown = ((cumulative - peak) / peak).min() * 100

    # Win rate
    trades = result_df[result_df['Position'].diff() != 0]
    if len(trades) > 1:
        winning = (trades['Strategy_Returns'] > 0).sum()
        total_trades = len(trades)
        win_rate = (winning / total_trades) * 100 if total_trades > 0 else 0
    else:
        win_rate = 0

    return {
        'final_value': final_value,
        'total_return': total_return,
        'sharpe_ratio': sharpe,
        'max_drawdown': drawdown,
        'win_rate': win_rate
    }
