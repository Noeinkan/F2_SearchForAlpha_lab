# Bollinger Bands module
"""
Bollinger Bands-based trading strategies.
"""

import logging
import pandas as pd
from typing import Dict, Any, Callable
from ta.volatility import BollingerBands

from lib.signals.base_strategy import BaseTradingStrategy

logger = logging.getLogger(__name__)


class BB_TradingStrategy(BaseTradingStrategy):
    """Bollinger Bands-based trading strategy implementation."""

    STRATEGY_KEY = 'bollinger'
    STRATEGY_PRIORITY = 10
    SIGNAL_METADATA = {
        'BB_Breakout_Buy': 'Price breaks above the upper Bollinger Band.',
        'BB_Breakout_Sell': 'Price breaks below the lower Bollinger Band.',
        'BB_MeanReversion_Buy': 'Price crosses back above the lower band.',
        'BB_MeanReversion_Sell': 'Price crosses back below the upper band.',
        'BB_Squeeze_Buy': 'Breakout up after a Bollinger squeeze.',
        'BB_Squeeze_Sell': 'Breakdown down after a Bollinger squeeze.',
        'BB_DoubleBottom_Buy': 'Two lower-band touches followed by a rebound.',
        'BB_DoubleTop_Sell': 'Two upper-band touches followed by a drop.',
    }
    
    DEFAULT_CONFIG = {
        'bollinger_bands': {
            'window': 20,
            'window_dev': 2
        },
        'squeeze_strategy': {
            'squeeze_threshold': 0.1
        },
        'double_bottom_top_strategy': {
            'threshold': 0.02,
            'lookback_window': 10,
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config, name="BB_TradingStrategy")

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add Bollinger Bands indicators to the DataFrame."""
        self.validate_dataframe(df, ['Close'])
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
        """Generate breakout signals."""
        df['BB_Breakout_Buy'] = (df['Close'] > df['BB_upper']).astype(int)
        df['BB_Breakout_Sell'] = (df['Close'] < df['BB_lower']).astype(int)
        return df

    def BB_mean_reversion_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate mean reversion signals."""
        df['BB_MeanReversion_Buy'] = (
            (df['Close'] < df['BB_lower']) & 
            (df['Close'].shift(1) >= df['BB_lower'])
        ).astype(int)
        df['BB_MeanReversion_Sell'] = (
            (df['Close'] > df['BB_upper']) & 
            (df['Close'].shift(1) <= df['BB_upper'])
        ).astype(int)
        return df

    def BB_squeeze_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate squeeze-based signals."""
        squeeze_threshold = self.config['squeeze_strategy']['squeeze_threshold']
        df['BB_width'] = (df['BB_upper'] - df['BB_lower']) / df['BB_middle']
        df['Squeeze'] = df['BB_width'] < squeeze_threshold
        df['BB_Squeeze_Buy'] = (
            df['Squeeze'].shift(1) & (df['Close'] > df['BB_upper'])
        ).astype(int)
        df['BB_Squeeze_Sell'] = (
            df['Squeeze'].shift(1) & (df['Close'] < df['BB_lower'])
        ).astype(int)
        return df

    def BB_double_bottom_top_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate double bottom/top signals using a rolling lookback window.

        A double bottom fires when:
          - At least 2 lower-band touches occurred within the last `lookback_window` bars.
          - The previous bar was a touch (Close < BB_lower).
          - The current bar rebounded above the lower band (entry confirmation).

        A double top mirrors this logic using the upper band.

        The previous implementation required two *consecutive* bars below the band
        AND a same-day >2% move *while still below the band* — a condition that
        essentially never fired on daily SPY, producing 0 trades.
        """
        lookback = int(self.config['double_bottom_top_strategy'].get('lookback_window', 10))

        below_lower = df['Close'] < df['BB_lower']
        above_upper = df['Close'] > df['BB_upper']

        lower_touch_count = below_lower.rolling(window=lookback, min_periods=1).sum()
        upper_touch_count = above_upper.rolling(window=lookback, min_periods=1).sum()

        df['BB_DoubleBottom_Buy'] = (
            (lower_touch_count >= 2) &
            (below_lower.shift(1)) &   # was at lower band yesterday
            (~below_lower)             # today closed back above lower band
        ).astype(int)

        df['BB_DoubleTop_Sell'] = (
            (upper_touch_count >= 2) &
            (above_upper.shift(1)) &   # was at upper band yesterday
            (~above_upper)             # today closed back below upper band
        ).astype(int)

        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all BB-based trading signals."""
        strategies: Dict[str, Callable[[pd.DataFrame], pd.DataFrame]] = {
            'BB_Breakout': self.BB_breakout_strategy,
            'BB_Mean_Reversion': self.BB_mean_reversion_strategy,
            'BB_Squeeze': self.BB_squeeze_strategy,
            'BB_Double_Bottom_Top': self.BB_double_bottom_top_strategy
        }
        
        df = self.add_indicators(df)
        
        for strategy_func in strategies.values():
            df = strategy_func(df)
        
        return df
    
    # Legacy method for backwards compatibility
    def BB_generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Legacy method - use generate_signals() instead."""
        return self.generate_signals(df)
    
    # Keep old method name as alias
    def add_bollinger_bands(self, df: pd.DataFrame) -> pd.DataFrame:
        """Legacy method - use add_indicators() instead."""
        return self.add_indicators(df)