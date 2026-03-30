# Exponential Moving Averages module
"""
EMA-based trading strategies.
"""

import logging
import pandas as pd
import numpy as np
from typing import Dict, Any
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange
from dataclasses import dataclass

from lib.signals.base_strategy import BaseTradingStrategy

logger = logging.getLogger(__name__)


@dataclass
class EMAConfig:
    short_window: int = 12
    medium_window: int = 26
    long_window: int = 50
    atr_window: int = 14
    distance_threshold: float = 0.01
    divergence_window: int = 14
    atr_multiplier: float = 1.5
    start_hour: int = 9
    end_hour: int = 16


class EMA_TradingStrategy(BaseTradingStrategy):
    """EMA-based trading strategy implementation."""

    STRATEGY_KEY = 'ema'
    STRATEGY_PRIORITY = 60
    SIGNAL_METADATA = {
        'EMA_TripleCross_Buy': 'Short, medium, and long EMA align bullishly.',
        'EMA_TripleCross_Sell': 'Short, medium, and long EMA align bearishly.',
        'EMA_Distance_Buy': 'Bullish EMA alignment with wide separation.',
        'EMA_Distance_Sell': 'Bearish EMA alignment with wide separation.',
        'EMA_Momentum_Buy': 'Bullish EMA alignment with rising momentum.',
        'EMA_Momentum_Sell': 'Bearish EMA alignment with falling momentum.',
        'EMA_ValueZone_Buy': 'Price enters bullish EMA value zone.',
        'EMA_ValueZone_Sell': 'Price enters bearish EMA value zone.',
        'EMA_Divergence_Buy': 'Price weakens while short EMA improves.',
        'EMA_Divergence_Sell': 'Price strengthens while short EMA weakens.',
        'EMA_Volatility_Buy': 'Bullish EMA setup during high volatility.',
        'EMA_Volatility_Sell': 'Bearish EMA setup during high volatility.',
    }
    
    DEFAULT_CONFIG = {
        'ema': EMAConfig()
    }

    def __init__(self, config: Dict[str, Any] = None):
        # Handle special EMA config initialization
        self.config = {'ema': EMAConfig()}
        if config and 'ema' in config:
            if isinstance(config['ema'], dict):
                self.config['ema'] = EMAConfig(**config['ema'])
            elif isinstance(config['ema'], EMAConfig):
                self.config['ema'] = config['ema']
        self.name = "EMA_TradingStrategy"

    def _get_default_config(self) -> Dict[str, Any]:
        return {'ema': EMAConfig()}

    def update_config(self, new_config: Dict[str, Any]) -> None:
        """Update config - special handling for EMAConfig dataclass."""
        if 'ema' in new_config:
            if isinstance(new_config['ema'], dict):
                self.config['ema'] = EMAConfig(**new_config['ema'])
            elif isinstance(new_config['ema'], EMAConfig):
                self.config['ema'] = new_config['ema']

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add EMA indicators to the DataFrame."""
        df['EMA_short'] = EMAIndicator(
            close=df['Close'], 
            window=self.config['ema'].short_window
        ).ema_indicator()
        df['EMA_medium'] = EMAIndicator(
            close=df['Close'], 
            window=self.config['ema'].medium_window
        ).ema_indicator()
        df['EMA_long'] = EMAIndicator(
            close=df['Close'], 
            window=self.config['ema'].long_window
        ).ema_indicator()
        df['ATR'] = AverageTrueRange(
            high=df['High'], 
            low=df['Low'], 
            close=df['Close'], 
            window=self.config['ema'].atr_window
        ).average_true_range()
        return df

    def ema_triple_crossover_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate triple crossover signals."""
        df['EMA_TripleCross_Buy'] = (
            (df['EMA_short'] > df['EMA_medium']) & 
            (df['EMA_medium'] > df['EMA_long'])
        ).astype(int)
        df['EMA_TripleCross_Sell'] = (
            (df['EMA_short'] < df['EMA_medium']) & 
            (df['EMA_medium'] < df['EMA_long'])
        ).astype(int)
        return df

    def ema_distance_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate distance-based signals."""
        df['EMA_distance'] = (df['EMA_short'] - df['EMA_long']) / df['EMA_long']
        df['EMA_Distance_Buy'] = (
            (df['EMA_TripleCross_Buy'] == 1) & 
            (df['EMA_distance'] > self.config['ema'].distance_threshold)
        ).astype(int)
        df['EMA_Distance_Sell'] = (
            (df['EMA_TripleCross_Sell'] == 1) & 
            (df['EMA_distance'] < -self.config['ema'].distance_threshold)
        ).astype(int)
        return df

    def ema_momentum_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate momentum-based signals."""
        df['EMA_medium_slope'] = df['EMA_medium'].diff()
        df['EMA_Momentum_Buy'] = (
            (df['EMA_TripleCross_Buy'] == 1) & 
            (df['EMA_medium_slope'] > 0)
        ).astype(int)
        df['EMA_Momentum_Sell'] = (
            (df['EMA_TripleCross_Sell'] == 1) & 
            (df['EMA_medium_slope'] < 0)
        ).astype(int)
        return df

    def ema_value_zones_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate value zone signals."""
        df['EMA_ValueZone_Buy'] = (
            (df['Close'] > df['EMA_long']) & 
            (df['Close'] < df['EMA_medium'])
        ).astype(int)
        df['EMA_ValueZone_Sell'] = (
            (df['Close'] < df['EMA_long']) & 
            (df['Close'] > df['EMA_medium'])
        ).astype(int)
        return df

    def ema_price_divergence_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate divergence-based signals."""
        window = self.config['ema'].divergence_window
        df['Close_high'] = df['Close'].rolling(window=window).max()
        df['Close_low'] = df['Close'].rolling(window=window).min()
        df['EMA_short_high'] = df['EMA_short'].rolling(window=window).max()
        df['EMA_short_low'] = df['EMA_short'].rolling(window=window).min()
        
        df['EMA_Divergence_Buy'] = (
            (df['Close_low'] < df['Close_low'].shift(1)) & 
            (df['EMA_short_low'] > df['EMA_short_low'].shift(1))
        ).astype(int)
        df['EMA_Divergence_Sell'] = (
            (df['Close_high'] > df['Close_high'].shift(1)) & 
            (df['EMA_short_high'] < df['EMA_short_high'].shift(1))
        ).astype(int)
        return df

    def ema_volatility_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate volatility-based signals."""
        df['Volatility_high'] = df['ATR'] > (
            df['ATR'].rolling(window=20).mean() * self.config['ema'].atr_multiplier
        )
        df['EMA_Volatility_Buy'] = (
            df['EMA_TripleCross_Buy'] & df['Volatility_high']
        ).astype(int)
        df['EMA_Volatility_Sell'] = (
            df['EMA_TripleCross_Sell'] & df['Volatility_high']
        ).astype(int)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all EMA-based trading signals."""
        df = self.add_indicators(df)
        df = self.ema_triple_crossover_strategy(df)
        df = self.ema_distance_strategy(df)
        df = self.ema_momentum_strategy(df)
        df = self.ema_value_zones_strategy(df)
        df = self.ema_price_divergence_strategy(df)
        df = self.ema_volatility_strategy(df)
        return df
    
    # Legacy method for backwards compatibility
    def EMA_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Legacy method - use generate_signals() instead."""
        return self.generate_signals(df)
    
    # Keep old method name as alias
    def add_ema(self, df: pd.DataFrame) -> pd.DataFrame:
        """Legacy method - use add_indicators() instead."""
        return self.add_indicators(df)