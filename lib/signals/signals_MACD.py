# Moving Average Convergence/Divergence MACD module

import pandas as pd
from typing import Dict
from ta.trend import MACD

MACD_CONFIG = {
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

class MACD_TradingStrategy:
    def __init__(self, config: Dict = None):
        self.config = MACD_CONFIG.copy()
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

    def add_macd(self, df: pd.DataFrame) -> pd.DataFrame:
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
        threshold = self.config['zero_cross']['threshold']
        df['MACD_ZeroCross_Buy'] = ((df['MACD'] > threshold) & (df['MACD'].shift(1) <= threshold)).astype(int)
        df['MACD_ZeroCross_Sell'] = ((df['MACD'] < threshold) & (df['MACD'].shift(1) >= threshold)).astype(int)
        return df

    def macd_signal_cross_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        threshold = self.config['signal_cross']['threshold']
        df['MACD_SignalCross_Buy'] = ((df['MACD'] > df['MACD_Signal'] + threshold) & 
                                      (df['MACD'].shift(1) <= df['MACD_Signal'].shift(1) + threshold)).astype(int)
        df['MACD_SignalCross_Sell'] = ((df['MACD'] < df['MACD_Signal'] - threshold) & 
                                       (df['MACD'].shift(1) >= df['MACD_Signal'].shift(1) - threshold)).astype(int)
        return df

    def macd_histogram_reversal_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        df['MACD_Histogram_Buy'] = ((df['MACD_Histogram'] > 0) & (df['MACD_Histogram'].shift(1) <= 0)).astype(int)
        df['MACD_Histogram_Sell'] = ((df['MACD_Histogram'] < 0) & (df['MACD_Histogram'].shift(1) >= 0)).astype(int)
        return df

    def MACD_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.add_macd(df)
        df = self.macd_zero_cross_strategy(df)
        df = self.macd_signal_cross_strategy(df)
        df = self.macd_histogram_reversal_strategy(df)
        return df