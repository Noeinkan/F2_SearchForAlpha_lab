# Moving Average Convergence/Divergence MACD module
"""
MACD-based trading strategies.
"""

import logging
import pandas as pd
from typing import Dict, Any
from ta.trend import MACD

from lib.signals.base_strategy import BaseTradingStrategy

logger = logging.getLogger(__name__)


class MACD_TradingStrategy(BaseTradingStrategy):
    """MACD-based trading strategy implementation."""
    
    DEFAULT_CONFIG = {
        'macd': {
            'fast_period': 12,
            'slow_period': 26,
            'signal_period': 9
        },
        'zero_cross': {
            'threshold': 0
        },
        'signal_cross': {
            'threshold': 0
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config, name="MACD_TradingStrategy")

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add MACD indicator to the DataFrame."""
        self.validate_dataframe(df, ['Close'])
        macd = MACD(
            close=df['Close'],
            window_fast=self.config['macd']['fast_period'],
            window_slow=self.config['macd']['slow_period'],
            window_sign=self.config['macd']['signal_period']
        )
        df['MACD'] = macd.macd()
        df['MACD_Signal'] = macd.macd_signal()
        df['MACD_Histogram'] = macd.macd_diff()
        return df

    def macd_zero_cross_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate zero-cross signals."""
        threshold = self.config['zero_cross']['threshold']
        df['MACD_ZeroCross_Buy'] = (
            (df['MACD'] > threshold) & 
            (df['MACD'].shift(1) <= threshold)
        ).astype(int)
        df['MACD_ZeroCross_Sell'] = (
            (df['MACD'] < threshold) & 
            (df['MACD'].shift(1) >= threshold)
        ).astype(int)
        return df

    def macd_signal_cross_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate signal line cross signals."""
        threshold = self.config['signal_cross']['threshold']
        df['MACD_SignalCross_Buy'] = (
            (df['MACD'] > df['MACD_Signal'] + threshold) & 
            (df['MACD'].shift(1) <= df['MACD_Signal'].shift(1) + threshold)
        ).astype(int)
        df['MACD_SignalCross_Sell'] = (
            (df['MACD'] < df['MACD_Signal'] - threshold) & 
            (df['MACD'].shift(1) >= df['MACD_Signal'].shift(1) - threshold)
        ).astype(int)
        return df

    def macd_histogram_reversal_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate histogram reversal signals."""
        df['MACD_Histogram_Buy'] = (
            (df['MACD_Histogram'] > 0) & 
            (df['MACD_Histogram'].shift(1) <= 0)
        ).astype(int)
        df['MACD_Histogram_Sell'] = (
            (df['MACD_Histogram'] < 0) & 
            (df['MACD_Histogram'].shift(1) >= 0)
        ).astype(int)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all MACD-based trading signals."""
        df = self.add_indicators(df)
        df = self.macd_zero_cross_strategy(df)
        df = self.macd_signal_cross_strategy(df)
        df = self.macd_histogram_reversal_strategy(df)
        return df
    
    # Legacy method for backwards compatibility
    def MACD_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Legacy method - use generate_signals() instead."""
        return self.generate_signals(df)
    
    # Keep old method name as alias
    def add_macd(self, df: pd.DataFrame) -> pd.DataFrame:
        """Legacy method - use add_indicators() instead."""
        return self.add_indicators(df)