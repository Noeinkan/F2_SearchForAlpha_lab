# Relative Strength Index module

import pandas as pd
from typing import Dict
from ta.momentum import RSIIndicator

RSI_CONFIG = {
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

class RSI_TradingStrategy:
    def __init__(self, config: Dict = None):
        self.config = RSI_CONFIG.copy()
        if config:
            self.update_config(config)

    def update_config(self, new_config: Dict):
        for key, value in new_config.items():
            if key in self.config:
                if isinstance(self.config[key], dict) and isinstance(value, dict):
                    self.config[key].update(value)
                else:
                    self.config[key] = value
            else:
                self.config[key] = value

    def add_rsi(self, df: pd.DataFrame) -> pd.DataFrame:
        rsi = RSIIndicator(
            close=df['Close'],
            window=self.config['rsi']['window']
        )
        df['RSI'] = rsi.rsi()
        return df

    def rsi_overbought_oversold_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        upper = self.config['overbought_oversold']['upper_threshold']
        lower = self.config['overbought_oversold']['lower_threshold']
        df['RSI_Overbought_Sell'] = (df['RSI'] > upper).astype(int)
        df['RSI_Oversold_Buy'] = (df['RSI'] < lower).astype(int)
        return df

    def rsi_divergence_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        lookback = self.config['divergence']['lookback_period']
        df['Price_High'] = df['Close'].rolling(window=lookback).max()
        df['RSI_High'] = df['RSI'].rolling(window=lookback).max()
        df['Price_Low'] = df['Close'].rolling(window=lookback).min()
        df['RSI_Low'] = df['RSI'].rolling(window=lookback).min()
        
        df['RSI_Bullish_Divergence'] = ((df['Close'] < df['Price_Low']) & (df['RSI'] > df['RSI_Low'])).astype(int)
        df['RSI_Bearish_Divergence'] = ((df['Close'] > df['Price_High']) & (df['RSI'] < df['RSI_High'])).astype(int)
        
        return df

    def RSI_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.add_rsi(df)
        df = self.rsi_overbought_oversold_strategy(df)
        df = self.rsi_divergence_strategy(df)
        return df