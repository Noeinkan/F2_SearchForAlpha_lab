# Commodity Channel Index module
"""
CCI-based trading strategies.
"""

import logging
import pandas as pd
from typing import Dict, Any
from ta.trend import CCIIndicator

from lib.signals.base_strategy import BaseTradingStrategy

logger = logging.getLogger(__name__)


class CCI_TradingStrategy(BaseTradingStrategy):
    """CCI-based trading strategy implementation."""

    STRATEGY_KEY = 'cci'
    STRATEGY_PRIORITY = 40
    SIGNAL_METADATA = {
        'CCI_Oversold_Buy': 'CCI drops below the oversold threshold.',
        'CCI_Overbought_Sell': 'CCI rises above the overbought threshold.',
        'CCI_Reversal_Buy': 'CCI rebounds up from an extreme low.',
        'CCI_Reversal_Sell': 'CCI turns down from an extreme high.',
        'CCI_ZeroCross_Buy': 'CCI crosses above zero.',
        'CCI_ZeroCross_Sell': 'CCI crosses below zero.',
    }
    
    DEFAULT_CONFIG = {
        'cci': {
            'window': 20
        },
        'overbought_oversold': {
            'upper_threshold': 100,
            'lower_threshold': -100
        },
        'trend_reversal': {
            'extreme_threshold': 180
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config, name="CCI_TradingStrategy")

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add CCI indicator to the DataFrame."""
        self.validate_dataframe(df, ['High', 'Low', 'Close'])
        cci = CCIIndicator(
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            window=self.config['cci']['window']
        )
        df['CCI'] = cci.cci()
        return df

    def cci_overbought_oversold_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate overbought/oversold signals."""
        upper = self.config['overbought_oversold']['upper_threshold']
        lower = self.config['overbought_oversold']['lower_threshold']
        df['CCI_Overbought_Sell'] = (df['CCI'] > upper).astype(int)
        df['CCI_Oversold_Buy'] = (df['CCI'] < lower).astype(int)
        return df

    def cci_trend_reversal_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate trend reversal signals.

        Fires when CCI *exits* the extreme zone — i.e. a rebound above -extreme
        (Buy) or a turn-down below +extreme (Sell).  The previous (broken)
        implementation fired on the *entry* into the extreme zone, which was a
        falling-knife / rising-knife signal and explains the catastrophic Sharpe.
        """
        extreme = self.config['trend_reversal']['extreme_threshold']
        df['CCI_Reversal_Buy'] = (
            (df['CCI'] > -extreme) &          # CCI has rebounded above -extreme
            (df['CCI'].shift(1) <= -extreme)  # CCI was in (or at) the extreme low zone
        ).astype(int)
        df['CCI_Reversal_Sell'] = (
            (df['CCI'] < extreme) &           # CCI has pulled back below +extreme
            (df['CCI'].shift(1) >= extreme)   # CCI was in (or at) the extreme high zone
        ).astype(int)
        return df

    def cci_zero_cross_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate zero-cross signals."""
        df['CCI_ZeroCross_Buy'] = (
            (df['CCI'] > 0) & 
            (df['CCI'].shift(1) <= 0)
        ).astype(int)
        df['CCI_ZeroCross_Sell'] = (
            (df['CCI'] < 0) & 
            (df['CCI'].shift(1) >= 0)
        ).astype(int)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all CCI-based trading signals."""
        df = self.add_indicators(df)
        df = self.cci_overbought_oversold_strategy(df)
        df = self.cci_trend_reversal_strategy(df)
        df = self.cci_zero_cross_strategy(df)
        return df
    
    # Legacy method for backwards compatibility
    def CCI_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Legacy method - use generate_signals() instead."""
        return self.generate_signals(df)
    
    # Keep old method name as alias
    def add_cci(self, df: pd.DataFrame) -> pd.DataFrame:
        """Legacy method - use add_indicators() instead."""
        return self.add_indicators(df)