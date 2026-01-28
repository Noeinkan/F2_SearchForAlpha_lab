# Simple Moving Averages module
"""
SMA-based trading strategies.
"""

import logging
import pandas as pd
from typing import Dict, Any
from ta.trend import SMAIndicator

from lib.signals.base_strategy import BaseTradingStrategy

logger = logging.getLogger(__name__)


class SMA_TradingStrategy(BaseTradingStrategy):
    """SMA-based trading strategy implementation."""
    
    DEFAULT_CONFIG = {
        'sma': {
            'short_window': 5,
            'medium_window': 20,
            'long_window': 50,
            'trend_window': 200
        },
        'crossover': {
            'threshold': 0.001
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config, name="SMA_TradingStrategy")

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add SMA indicators to the DataFrame."""
        self.validate_dataframe(df, ['Close'])
        df['SMA_short'] = SMAIndicator(
            close=df['Close'], 
            window=self.config['sma']['short_window']
        ).sma_indicator()
        df['SMA_medium'] = SMAIndicator(
            close=df['Close'], 
            window=self.config['sma']['medium_window']
        ).sma_indicator()
        df['SMA_long'] = SMAIndicator(
            close=df['Close'], 
            window=self.config['sma']['long_window']
        ).sma_indicator()
        df['SMA_trend'] = SMAIndicator(
            close=df['Close'], 
            window=self.config['sma']['trend_window']
        ).sma_indicator()
        return df

    def sma_triple_crossover_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate triple crossover signals."""
        df['SMA_TripleCross_Buy'] = (
            (df['SMA_short'] > df['SMA_medium']) & 
            (df['SMA_medium'] > df['SMA_long']) & 
            (df['Close'] > df['SMA_short'])
        ).astype(int)
        
        df['SMA_TripleCross_Sell'] = (
            (df['SMA_short'] < df['SMA_medium']) & 
            (df['SMA_medium'] < df['SMA_long']) & 
            (df['Close'] < df['SMA_short'])
        ).astype(int)
        
        return df

    def sma_price_crossover_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate price crossover signals."""
        threshold = self.config['crossover']['threshold']
        
        df['SMA_PriceCross_Buy'] = (
            (df['Close'] > df['SMA_medium'] * (1 + threshold)) & 
            (df['Close'].shift(1) <= df['SMA_medium'].shift(1) * (1 + threshold))
        ).astype(int)
        
        df['SMA_PriceCross_Sell'] = (
            (df['Close'] < df['SMA_medium'] * (1 - threshold)) & 
            (df['Close'].shift(1) >= df['SMA_medium'].shift(1) * (1 - threshold))
        ).astype(int)
        
        return df

    def sma_trend_following_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate trend following signals."""
        df['SMA_TrendFollow_Buy'] = (
            (df['Close'] > df['SMA_trend']) & 
            (df['SMA_short'] > df['SMA_medium']) & 
            (df['SMA_medium'] > df['SMA_long'])
        ).astype(int)
        
        df['SMA_TrendFollow_Sell'] = (
            (df['Close'] < df['SMA_trend']) & 
            (df['SMA_short'] < df['SMA_medium']) & 
            (df['SMA_medium'] < df['SMA_long'])
        ).astype(int)
        
        return df

    def sma_short_slope_flip_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate SMA short slope flip signals."""
        df['SMA_short_slope'] = df['SMA_short'].diff()
        df['SMA_SlopeFlip_Buy'] = (
            (df['SMA_short_slope'] > 0) &
            (df['SMA_short_slope'].shift(1) <= 0)
        ).astype(int)
        df['SMA_SlopeFlip_Sell'] = (
            (df['SMA_short_slope'] < 0) &
            (df['SMA_short_slope'].shift(1) >= 0)
        ).astype(int)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all SMA-based trading signals."""
        df = self.add_indicators(df)
        df = self.sma_triple_crossover_strategy(df)
        df = self.sma_price_crossover_strategy(df)
        df = self.sma_trend_following_strategy(df)
        df = self.sma_short_slope_flip_strategy(df)
        return df
    
    # Legacy method for backwards compatibility
    def SMA_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Legacy method - use generate_signals() instead."""
        return self.generate_signals(df)
    
    # Keep old method name as alias
    def add_sma(self, df: pd.DataFrame) -> pd.DataFrame:
        """Legacy method - use add_indicators() instead."""
        return self.add_indicators(df)