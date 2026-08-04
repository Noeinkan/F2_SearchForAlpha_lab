"""
Dashboard Helper Functions
Utility functions for data processing and optimization.
"""

import logging
import itertools
from typing import List, Tuple, Dict, Any, Optional

import numpy as np
import pandas as pd

from lib.dash.state import dashboard_state
from lib.strategy import run_backtest
from lib.backtest_result import metrics_from_result_df
from lib.signals.indicators import classify_signal_columns
from lib.timeframes import periods_per_year as periods_per_year_for


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


def fetch_data_with_cache(
    ticker: str,
    start_date: str,
    end_date: str,
    interval: str = "1d",
    force: bool = False,
) -> pd.DataFrame:
    """
    Fetch data with caching support via shared ``fetch_data``.

    Args:
        ticker: Stock ticker symbol
        start_date: Start date string
        end_date: End date string
        interval: Bar size ``1d`` / ``1h`` / ``4h``
        force: Skip the cache read and overwrite the entry. The cache is a plain
            LRU with no TTL, and the window is now derived from the interval
            rather than typed by the user, so the key is stable for a whole
            trading day — without this a manual refresh would serve the same
            bars back and never pick up today's new ones.

    Returns:
        DataFrame with OHLCV data

    Raises:
        ValueError: If no data available for ticker
    """
    from lib.data_processing import DataFetchError, fetch_data
    from lib.timeframes import normalize_interval

    canon = normalize_interval(interval)
    cache_key = f"{ticker}_{canon}_{start_date}_{end_date}"
    cached = None if force else dashboard_state.get_cached_data(cache_key)

    if cached is not None:
        logger.debug(f"Cache hit for {cache_key}")
        return cached

    logger.info(f"Fetching data for {ticker} (interval={canon})")
    try:
        df = fetch_data(ticker, start_date, end_date, interval=canon)
    except DataFetchError as exc:
        raise ValueError(str(exc)) from exc

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

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

        # Reuse the tested metrics engine instead of hand-rolling a fragile
        # subset here (return, Sharpe, Sortino, Calmar, DD, trades, win rate,
        # profit factor, turnover all computed from the actual result columns).
        m = metrics_from_result_df(result_df, initial_capital)

        # Buy-and-hold benchmark over the same window: the single clearest
        # "is this strategy actually adding value?" signal.
        close = result_df['Close']
        first_close = close.iloc[0]
        buy_hold_return = ((close.iloc[-1] / first_close) - 1.0) * 100 if first_close else 0.0
        total_return_pct = m.total_return * 100

        return {
            'Buy_Signals': ', '.join(buy_combo),
            'Sell_Signals': ', '.join(sell_combo),
            'Final_Value': result_df['Portfolio_Value'].iloc[-1],
            'Total_Return_%': total_return_pct,
            'BuyHold_Return_%': buy_hold_return,
            'Alpha_%': total_return_pct - buy_hold_return,
            'Sharpe_Ratio': m.sharpe,
            'Sortino': m.sortino,
            'Calmar': m.calmar,
            # Keep the existing negative-drawdown convention (engine reports
            # max_drawdown as a positive magnitude).
            'Max_Drawdown_%': -m.max_drawdown * 100,
            'Win_Rate_%': m.win_rate * 100,
            'Profit_Factor': m.profit_factor,
            'Turnover': m.turnover,
            'Trades': int(m.num_trades),
        }
    except Exception as e:
        logger.warning(f"Error testing combination {buy_combo}/{sell_combo}: {e}")
        return {
            'Buy_Signals': ', '.join(buy_combo),
            'Sell_Signals': ', '.join(sell_combo),
            'Error': str(e)
        }


def compute_robustness_scores(results_df: pd.DataFrame, min_trades: int) -> pd.DataFrame:
    """
    Add a robustness-weighted score and a low-sample flag to optimization results.

    The score rewards risk-adjusted performance (Sharpe, with Calmar as a mild
    bonus) and penalises combinations that traded too few times to be credible,
    via a confidence factor that ramps from 0 to 1 as trade count approaches
    ``min_trades``. Raw return is folded in only as a small tiebreaker.

    Best practice: a strong ratio on a handful of trades is noise, not edge.
    """
    df = results_df.copy()
    if df.empty:
        return df

    min_trades = max(1, int(min_trades or 1))
    trades = df.get('Trades', pd.Series(0, index=df.index)).fillna(0).clip(lower=0)
    confidence = (trades / min_trades).clip(upper=1.0)

    sharpe = df.get('Sharpe_Ratio', pd.Series(0.0, index=df.index)).fillna(0.0)
    calmar = df.get('Calmar', pd.Series(0.0, index=df.index)).fillna(0.0)
    total_return = df.get('Total_Return_%', pd.Series(0.0, index=df.index)).fillna(0.0)

    df['Low_Sample'] = trades < min_trades
    df['Robustness_Score'] = (
        (sharpe + 0.25 * calmar) * confidence + 0.001 * total_return
    )
    return df


def calculate_performance_metrics(
    result_df: pd.DataFrame,
    initial_capital: float,
    interval: str = "1d",
) -> Dict[str, float]:
    """
    Calculate performance metrics from backtest results.

    Args:
        result_df: DataFrame with backtest results
        initial_capital: Starting capital
        interval: Bar interval for Sharpe annualization

    Returns:
        Dict with performance metrics
    """
    final_value = result_df['Portfolio_Value'].iloc[-1]
    total_return = (final_value - initial_capital) / initial_capital * 100

    returns = result_df['Strategy_Returns'].dropna()

    # Sharpe ratio (annualized)
    ppy = periods_per_year_for(interval)
    sharpe = (returns.mean() / returns.std() * np.sqrt(ppy)) if returns.std() > 0 else 0

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
