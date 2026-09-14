"""Collapse a frame's signal columns into the one buy and one sell array the loop reads.

Each symbol does this on its own frame. In a portfolio run every member carries
its own ``{INDICATOR}_{CONDITION}_{Buy|Sell}`` columns, computed on its own tape
before alignment, so combining them is per-symbol work with nothing shared.
"""

from typing import Dict, List, Optional

import numpy as np
import pandas as pd


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


def raw_signals(
    df: pd.DataFrame,
    buy_indicators: List[str],
    sell_indicators: List[str],
    *,
    use_signal_strength: bool,
    indicator_weights: Optional[Dict[str, float]],
    buy_threshold: float,
    sell_threshold: float,
    signal_logic: str,
    signal_window: int,
) -> tuple:
    """The boolean buy and sell arrays the bar loop reads, one entry per bar."""
    num_rows = len(df)
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
    return np.asarray(buy_signal_raw, dtype=bool), np.asarray(sell_signal_raw, dtype=bool)
