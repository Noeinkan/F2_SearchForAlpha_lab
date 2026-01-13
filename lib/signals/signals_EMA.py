# Exponential Moving Averages module

import pandas as pd
import numpy as np
from ta.trend import EMAIndicator
from ta.volatility import AverageTrueRange
from typing import Dict
from dataclasses import dataclass

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

EMA_CONFIG = {
    'ema': EMAConfig()
}

class EMA_TradingStrategy:
    def __init__(self, config: Dict = None):
        self.config = EMA_CONFIG.copy()
        if config:
            self.update_config(config)

    def update_config(self, new_config: Dict):
        if 'ema' in new_config:
            self.config['ema'] = EMAConfig(**new_config['ema'])

    def add_ema(self, df: pd.DataFrame) -> pd.DataFrame:
        df['EMA_short'] = EMAIndicator(close=df['Close'], window=self.config['ema'].short_window).ema_indicator()
        df['EMA_medium'] = EMAIndicator(close=df['Close'], window=self.config['ema'].medium_window).ema_indicator()
        df['EMA_long'] = EMAIndicator(close=df['Close'], window=self.config['ema'].long_window).ema_indicator()
        df['ATR'] = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=self.config['ema'].atr_window).average_true_range()
        return df

    def ema_triple_crossover_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        df['EMA_TripleCross_Buy'] = ((df['EMA_short'] > df['EMA_medium']) & (df['EMA_medium'] > df['EMA_long'])).astype(int)
        df['EMA_TripleCross_Sell'] = ((df['EMA_short'] < df['EMA_medium']) & (df['EMA_medium'] < df['EMA_long'])).astype(int)
        return df

    def ema_distance_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        df['EMA_distance'] = (df['EMA_short'] - df['EMA_long']) / df['EMA_long']
        df['EMA_Distance_Buy'] = ((df['EMA_TripleCross_Buy'] == 1) & (df['EMA_distance'] > self.config['ema'].distance_threshold)).astype(int)
        df['EMA_Distance_Sell'] = ((df['EMA_TripleCross_Sell'] == 1) & (df['EMA_distance'] < -self.config['ema'].distance_threshold)).astype(int)
        return df

    def ema_momentum_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        df['EMA_medium_slope'] = df['EMA_medium'].diff()
        df['EMA_Momentum_Buy'] = ((df['EMA_TripleCross_Buy'] == 1) & (df['EMA_medium_slope'] > 0)).astype(int)
        df['EMA_Momentum_Sell'] = ((df['EMA_TripleCross_Sell'] == 1) & (df['EMA_medium_slope'] < 0)).astype(int)
        return df

    def ema_value_zones_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        df['EMA_ValueZone_Buy'] = ((df['Close'] > df['EMA_long']) & (df['Close'] < df['EMA_medium'])).astype(int)
        df['EMA_ValueZone_Sell'] = ((df['Close'] < df['EMA_long']) & (df['Close'] > df['EMA_medium'])).astype(int)
        return df

    def ema_price_divergence_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        window = self.config['ema'].divergence_window
        df['Close_high'] = df['Close'].rolling(window=window).max()
        df['Close_low'] = df['Close'].rolling(window=window).min()
        df['EMA_short_high'] = df['EMA_short'].rolling(window=window).max()
        df['EMA_short_low'] = df['EMA_short'].rolling(window=window).min()
        
        df['EMA_Divergence_Buy'] = ((df['Close_low'] < df['Close_low'].shift(1)) & 
                                    (df['EMA_short_low'] > df['EMA_short_low'].shift(1))).astype(int)
        df['EMA_Divergence_Sell'] = ((df['Close_high'] > df['Close_high'].shift(1)) & 
                                     (df['EMA_short_high'] < df['EMA_short_high'].shift(1))).astype(int)
        return df

    def ema_volatility_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        df['Volatility_high'] = df['ATR'] > (df['ATR'].rolling(window=20).mean() * self.config['ema'].atr_multiplier)
        df['EMA_Volatility_Buy'] = (df['EMA_TripleCross_Buy'] & df['Volatility_high']).astype(int)
        df['EMA_Volatility_Sell'] = (df['EMA_TripleCross_Sell'] & df['Volatility_high']).astype(int)
        return df

    # no intraday strategy for now
    # def ema_time_filter_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
    #     df['Hour'] = df.index.hour
    #     time_mask = (df['Hour'] >= self.config['ema'].start_hour) & (df['Hour'] <= self.config['ema'].end_hour)
    #     for col in df.columns:
    #         if col.startswith('EMA_') and (col.endswith('_Buy') or col.endswith('_Sell')):
    #             df[col] = df[col] & time_mask
    #     return df

    def EMA_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.add_ema(df)
        df = self.ema_triple_crossover_strategy(df)
        df = self.ema_distance_strategy(df)
        df = self.ema_momentum_strategy(df)
        df = self.ema_value_zones_strategy(df)
        df = self.ema_price_divergence_strategy(df)
        df = self.ema_volatility_strategy(df)
        #df = self.ema_time_filter_strategy(df)
        return df