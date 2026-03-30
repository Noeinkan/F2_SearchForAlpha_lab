# Volume Weighted Average Price module
"""
VWAP-based trading strategy.
"""

import logging
from typing import Dict, Any

import numpy as np
import pandas as pd
from ta.volume import VolumeWeightedAveragePrice

from lib.signals.base_strategy import BaseTradingStrategy

logger = logging.getLogger(__name__)


class VWAP_TradingStrategy(BaseTradingStrategy):
    """VWAP cross strategy implementation."""

    STRATEGY_KEY = 'vwap'
    STRATEGY_PRIORITY = 70
    SIGNAL_METADATA = {
        'VWAP_CrossAbove_Buy': 'Price crosses above VWAP.',
        'VWAP_CrossBelow_Sell': 'Price crosses below VWAP.',
    }

    DEFAULT_CONFIG = {
        'vwap': {
            'window': 20
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config, name="VWAP_TradingStrategy")

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add VWAP indicator to the DataFrame."""
        self.validate_dataframe(df, ['High', 'Low', 'Close', 'Volume'])

        window = max(1, int(self.config['vwap'].get('window', 20)))
        volume = df['Volume'].fillna(0)

        vwap = VolumeWeightedAveragePrice(
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            volume=volume,
            window=window
        )
        df['VWAP'] = vwap.volume_weighted_average_price().replace([np.inf, -np.inf], np.nan)
        return df

    def vwap_cross_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate VWAP cross buy/sell signals."""
        close_prev = df['Close'].shift(1)
        vwap_prev = df['VWAP'].shift(1)

        buy_cross = (df['Close'] > df['VWAP']) & (close_prev <= vwap_prev)
        sell_cross = (df['Close'] < df['VWAP']) & (close_prev >= vwap_prev)

        valid = df['VWAP'].notna() & vwap_prev.notna()
        df['VWAP_CrossAbove_Buy'] = (buy_cross & valid).astype(int)
        df['VWAP_CrossBelow_Sell'] = (sell_cross & valid).astype(int)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all VWAP-based signals."""
        df = self.add_indicators(df)
        df = self.vwap_cross_strategy(df)
        return df
