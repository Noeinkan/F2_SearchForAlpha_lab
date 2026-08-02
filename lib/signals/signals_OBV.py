# On-Balance Volume module
"""
OBV-based volume strategies.

OBV is the only volume dimension in the registry that is independent of price
level, so it complements the price oscillators (RSI/CCI/MACD) rather than
duplicating them. ``OBV_Confirmation_*`` is a gate meant to be ANDed onto
another entry; the cross and divergence columns are standalone events.
"""

import logging
from typing import Any, Dict

import numpy as np
import pandas as pd

from lib.signals.base_strategy import BaseTradingStrategy

logger = logging.getLogger(__name__)


class OBV_TradingStrategy(BaseTradingStrategy):
    """On-Balance Volume strategy implementation."""

    STRATEGY_KEY = 'obv'
    STRATEGY_PRIORITY = 100
    SIGNAL_METADATA = {
        'OBV_MACross_Buy': 'OBV crosses above its moving average (accumulation).',
        'OBV_MACross_Sell': 'OBV crosses below its moving average (distribution).',
        'OBV_Divergence_Buy': 'Price prints a new low while OBV holds above its low.',
        'OBV_Divergence_Sell': 'Price prints a new high while OBV fails to confirm.',
        'OBV_Confirmation_Buy': 'Price and OBV both rising over the lookback — volume confirms longs.',
        'OBV_Confirmation_Sell': 'Price and OBV both falling over the lookback — volume confirms shorts.',
    }

    DEFAULT_CONFIG = {
        'obv': {
            'ma_period': 20
        },
        'divergence': {
            'lookback_period': 20
        },
        'confirmation': {
            'lookback_period': 5
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config, name="OBV_TradingStrategy")

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add OBV and its moving average to the DataFrame."""
        self.validate_dataframe(df, ['Close', 'Volume'])

        ma_period = max(1, int(self.config['obv'].get('ma_period', 20)))
        volume = df['Volume'].fillna(0)

        # Same accumulation formula as lib.signals.indicators.add_indicators,
        # recomputed here so the strategy works on a bare OHLCV frame too.
        df['OBV'] = (np.sign(df['Close'].diff()) * volume).fillna(0).cumsum()
        df['OBV_MA'] = df['OBV'].rolling(window=ma_period, min_periods=ma_period).mean()
        return df

    def obv_ma_cross_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate OBV / OBV-MA crossover signals."""
        obv = df['OBV']
        obv_ma = df['OBV_MA']
        obv_prev = obv.shift(1)
        ma_prev = obv_ma.shift(1)

        valid = obv_ma.notna() & ma_prev.notna() & obv_prev.notna()

        df['OBV_MACross_Buy'] = (valid & (obv > obv_ma) & (obv_prev <= ma_prev)).astype(int)
        df['OBV_MACross_Sell'] = (valid & (obv < obv_ma) & (obv_prev >= ma_prev)).astype(int)
        return df

    def obv_divergence_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate price/OBV divergence signals over a rolling window.

        Bullish: price is at its lookback low but OBV is not — sellers are not
        being confirmed by volume. Bearish is the mirror image.
        """
        lookback = max(2, int(self.config['divergence'].get('lookback_period', 20)))

        price_min = df['Close'].rolling(window=lookback, min_periods=lookback).min()
        price_max = df['Close'].rolling(window=lookback, min_periods=lookback).max()
        obv_min = df['OBV'].rolling(window=lookback, min_periods=lookback).min()
        obv_max = df['OBV'].rolling(window=lookback, min_periods=lookback).max()

        valid = price_min.notna() & price_max.notna() & obv_min.notna() & obv_max.notna()

        df['OBV_Divergence_Buy'] = (
            valid & (df['Close'] <= price_min) & (df['OBV'] > obv_min)
        ).astype(int)
        df['OBV_Divergence_Sell'] = (
            valid & (df['Close'] >= price_max) & (df['OBV'] < obv_max)
        ).astype(int)
        return df

    def obv_confirmation_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flag bars where volume flow agrees with the price trend."""
        lookback = max(1, int(self.config['confirmation'].get('lookback_period', 5)))

        price_change = df['Close'].diff(lookback)
        obv_change = df['OBV'].diff(lookback)
        valid = price_change.notna() & obv_change.notna()

        df['OBV_Confirmation_Buy'] = (valid & (price_change > 0) & (obv_change > 0)).astype(int)
        df['OBV_Confirmation_Sell'] = (valid & (price_change < 0) & (obv_change < 0)).astype(int)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all OBV-based volume signals."""
        df = self.add_indicators(df)
        df = self.obv_ma_cross_strategy(df)
        df = self.obv_divergence_strategy(df)
        df = self.obv_confirmation_strategy(df)
        return df
