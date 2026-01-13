# Simple Moving Averages module

import pandas as pd
from typing import Dict
from ta.trend import SMAIndicator

SMA_CONFIG = {
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

class SMA_TradingStrategy:
    def __init__(self, config: Dict = None):
        self.config = SMA_CONFIG.copy()
        if config:
            self.update_config(config)

    def update_config(self, new_config: Dict):
        """Aggiorna la configurazione con nuovi valori."""
        for key, value in new_config.items():
            if key in self.config:
                if isinstance(self.config[key], dict) and isinstance(value, dict):
                    self.config[key].update(value)
                else:
                    self.config[key] = value
            else:
                self.config[key] = value

    def add_sma(self, df: pd.DataFrame) -> pd.DataFrame:
        df['SMA_short'] = SMAIndicator(close=df['Close'], window=self.config['sma']['short_window']).sma_indicator()
        df['SMA_medium'] = SMAIndicator(close=df['Close'], window=self.config['sma']['medium_window']).sma_indicator()
        df['SMA_long'] = SMAIndicator(close=df['Close'], window=self.config['sma']['long_window']).sma_indicator()
        df['SMA_trend'] = SMAIndicator(close=df['Close'], window=self.config['sma']['trend_window']).sma_indicator()
        return df

    def sma_triple_crossover_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
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

    def SMA_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.add_sma(df)
        df = self.sma_triple_crossover_strategy(df)
        df = self.sma_price_crossover_strategy(df)
        df = self.sma_trend_following_strategy(df)
        return df