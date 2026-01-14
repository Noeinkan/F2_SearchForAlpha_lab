# Relative Strength Index module
"""
RSI-based trading strategies.
"""

import logging
import pandas as pd
from typing import Dict, Any
from ta.momentum import RSIIndicator

from lib.signals.base_strategy import BaseTradingStrategy

logger = logging.getLogger(__name__)


class RSI_TradingStrategy(BaseTradingStrategy):
    """RSI-based trading strategy implementation."""
    
    DEFAULT_CONFIG = {
        'rsi': {
            'window': 14
        },
        'overbought_oversold': {
            'upper_threshold': 70,
            'lower_threshold': 30
        },
        'divergence': {
            'lookback_period': 10
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config, name="RSI_TradingStrategy")

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add RSI indicator to the DataFrame."""
        self.validate_dataframe(df, ['Close'])
        rsi = RSIIndicator(
            close=df['Close'],
            window=self.config['rsi']['window']
        )
        df['RSI'] = rsi.rsi()
        return df

    def rsi_overbought_oversold_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate overbought/oversold signals."""
        upper = self.config['overbought_oversold']['upper_threshold']
        lower = self.config['overbought_oversold']['lower_threshold']
        df['RSI_Overbought_Sell'] = (df['RSI'] > upper).astype(int)
        df['RSI_Oversold_Buy'] = (df['RSI'] < lower).astype(int)
        return df

    def rsi_divergence_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate divergence-based signals."""
        lookback = self.config['divergence']['lookback_period']
        df['Price_High'] = df['Close'].rolling(window=lookback).max()
        df['RSI_High'] = df['RSI'].rolling(window=lookback).max()
        df['Price_Low'] = df['Close'].rolling(window=lookback).min()
        df['RSI_Low'] = df['RSI'].rolling(window=lookback).min()
        
        df['RSI_Bullish_Divergence'] = (
            (df['Close'] < df['Price_Low']) & (df['RSI'] > df['RSI_Low'])
        ).astype(int)
        df['RSI_Bearish_Divergence'] = (
            (df['Close'] > df['Price_High']) & (df['RSI'] < df['RSI_High'])
        ).astype(int)
        
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all RSI-based trading signals."""
        df = self.add_indicators(df)
        df = self.rsi_overbought_oversold_strategy(df)
        df = self.rsi_divergence_strategy(df)
        return df
    
    # Legacy method for backwards compatibility
    def RSI_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Legacy method - use generate_signals() instead."""
        return self.generate_signals(df)