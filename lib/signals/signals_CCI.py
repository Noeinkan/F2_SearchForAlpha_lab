# Commodity Channel Index module

import pandas as pd
from typing import Dict
from ta.trend import CCIIndicator

CCI_CONFIG = {
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

class CCI_TradingStrategy:
    def __init__(self, config: Dict = None):
        self.config = CCI_CONFIG.copy()
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

    def add_cci(self, df: pd.DataFrame) -> pd.DataFrame:
        cci = CCIIndicator(
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            window=self.config['cci']['window']
        )
        df['CCI'] = cci.cci()
        return df

    def cci_overbought_oversold_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        upper = self.config['overbought_oversold']['upper_threshold']
        lower = self.config['overbought_oversold']['lower_threshold']
        df['CCI_Overbought_Sell'] = (df['CCI'] > upper).astype(int)
        df['CCI_Oversold_Buy'] = (df['CCI'] < lower).astype(int)
        return df

    def cci_trend_reversal_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        extreme = self.config['trend_reversal']['extreme_threshold']
        df['CCI_Reversal_Buy'] = ((df['CCI'] < -extreme) & (df['CCI'].shift(1) >= -extreme)).astype(int)
        df['CCI_Reversal_Sell'] = ((df['CCI'] > extreme) & (df['CCI'].shift(1) <= extreme)).astype(int)
        return df

    def cci_zero_cross_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        df['CCI_ZeroCross_Buy'] = ((df['CCI'] > 0) & (df['CCI'].shift(1) <= 0)).astype(int)
        df['CCI_ZeroCross_Sell'] = ((df['CCI'] < 0) & (df['CCI'].shift(1) >= 0)).astype(int)
        return df

    def CCI_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        df = self.add_cci(df)
        df = self.cci_overbought_oversold_strategy(df)
        df = self.cci_trend_reversal_strategy(df)
        df = self.cci_zero_cross_strategy(df)
        return df