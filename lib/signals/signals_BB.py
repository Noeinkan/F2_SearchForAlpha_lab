# Bollinger Bands module

import pandas as pd
from typing import Dict, Callable
from ta.volatility import BollingerBands
import pandas_ta as ta

# Configurazione predefinita
BB_CONFIG = {
    'bollinger_bands': {
        'window': 20,
        'window_dev': 2
    },
    'squeeze_strategy': {
        'squeeze_threshold': 0.1
    },
    'double_bottom_top_strategy': {
        'threshold': 0.02
    }
}

class BB_TradingStrategy:
    def __init__(self, config: Dict = None):
        self.config = BB_CONFIG.copy()
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

    def add_bollinger_bands(self, df: pd.DataFrame) -> pd.DataFrame:
        bb = BollingerBands(
            close=df['Close'], 
            window=self.config['bollinger_bands']['window'], 
            window_dev=self.config['bollinger_bands']['window_dev']
        )
        df['BB_upper'] = bb.bollinger_hband()
        df['BB_middle'] = bb.bollinger_mavg()
        df['BB_lower'] = bb.bollinger_lband()
        return df

    def BB_breakout_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        df['BB_Breakout_Buy'] = (df['Close'] > df['BB_upper']).astype(int)
        df['BB_Breakout_Sell'] = (df['Close'] < df['BB_lower']).astype(int)
        return df

    def BB_mean_reversion_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        df['BB_MeanReversion_Buy'] = ((df['Close'] < df['BB_lower']) & (df['Close'].shift(1) >= df['BB_lower'])).astype(int)
        df['BB_MeanReversion_Sell'] = ((df['Close'] > df['BB_upper']) & (df['Close'].shift(1) <= df['BB_upper'])).astype(int)
        return df

    def BB_squeeze_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        squeeze_threshold = self.config['squeeze_strategy']['squeeze_threshold']
        df['BB_width'] = (df['BB_upper'] - df['BB_lower']) / df['BB_middle']
        df['Squeeze'] = df['BB_width'] < squeeze_threshold
        df['BB_Squeeze_Buy'] = (df['Squeeze'].shift(1) & (df['Close'] > df['BB_upper'])).astype(int)
        df['BB_Squeeze_Sell'] = (df['Squeeze'].shift(1) & (df['Close'] < df['BB_lower'])).astype(int)
        return df

    def BB_double_bottom_top_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        threshold = self.config['double_bottom_top_strategy']['threshold']
        df['Lower_Touch'] = (df['Close'] < df['BB_lower']).astype(int)
        df['Upper_Touch'] = (df['Close'] > df['BB_upper']).astype(int)
        
        df['BB_DoubleBottom_Buy'] = (
            (df['Lower_Touch'] == 1) &
            (df['Lower_Touch'].shift(1) == 1) &
            (df['Close'] > df['Close'].shift(1)) &
            (df['Close'].pct_change().abs() > threshold)
        ).astype(int)
        
        df['BB_DoubleTop_Sell'] = (
            (df['Upper_Touch'] == 1) &
            (df['Upper_Touch'].shift(1) == 1) &
            (df['Close'] < df['Close'].shift(1)) &
            (df['Close'].pct_change().abs() > threshold)
        ).astype(int)
        
        return df

    def BB_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        strategies: Dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
            'BB_Breakout': self.BB_breakout_strategy,
            'BB_Mean_Reversion': self.BB_mean_reversion_strategy,
            'BB_Squeeze': self.BB_squeeze_strategy,
            'BB_Double_Bottom_Top': self.BB_double_bottom_top_strategy
        }
        
        df = self.add_bollinger_bands(df)
        
        for strategy_func in strategies.values():
            df = strategy_func(df)
        
        return df