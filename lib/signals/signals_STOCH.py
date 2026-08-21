# Stochastic Oscillator module
"""
Stochastic-oscillator-based trading strategies.

%K is the close's position inside the High/Low range of the last ``window``
bars; %D is the ``smooth_window`` SMA of %K.  Both come from ``ta`` so the
lookback conventions match the other indicators in this package.

Promoted from ``lib/WIP/WIP_Stochastic_oscillator.py`` (deleted 2026-08-21).
Only the oscillator survived that file: its parameter search scored on an
inline Sharpe that the metrics engine now owns, and its Random Forest was
trained on a ``Close.shift(-1)`` target through a shuffled ``train_test_split``
— look-ahead twice over.
"""

import logging
import pandas as pd
from typing import Dict, Any
from ta.momentum import StochasticOscillator

from lib.signals.base_strategy import BaseTradingStrategy

logger = logging.getLogger(__name__)


class STOCH_TradingStrategy(BaseTradingStrategy):
    """Stochastic-oscillator-based trading strategy implementation."""

    STRATEGY_KEY = 'stoch'
    STRATEGY_PRIORITY = 45
    SIGNAL_METADATA = {
        'STOCH_Oversold_Buy': '%K sits below the oversold threshold.',
        'STOCH_Overbought_Sell': '%K sits above the overbought threshold.',
        'STOCH_Cross_Buy': '%K crosses above %D.',
        'STOCH_Cross_Sell': '%K crosses below %D.',
        'STOCH_Reversal_Buy': '%K crosses above %D while leaving the oversold zone.',
        'STOCH_Reversal_Sell': '%K crosses below %D while leaving the overbought zone.',
    }

    DEFAULT_CONFIG = {
        'stoch': {
            'window': 14,
            'smooth_window': 3
        },
        'overbought_oversold': {
            'upper_threshold': 80,
            'lower_threshold': 20
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config, name="STOCH_TradingStrategy")

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add %K and %D to the DataFrame."""
        self.validate_dataframe(df, ['High', 'Low', 'Close'])
        stoch = StochasticOscillator(
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            window=self.config['stoch']['window'],
            smooth_window=self.config['stoch']['smooth_window']
        )
        df['STOCH_K'] = stoch.stoch()
        df['STOCH_D'] = stoch.stoch_signal()
        return df

    def stoch_overbought_oversold_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate overbought/oversold level signals."""
        upper = self.config['overbought_oversold']['upper_threshold']
        lower = self.config['overbought_oversold']['lower_threshold']
        df['STOCH_Overbought_Sell'] = (df['STOCH_K'] > upper).astype(int)
        df['STOCH_Oversold_Buy'] = (df['STOCH_K'] < lower).astype(int)
        return df

    def stoch_cross_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate plain %K / %D crossover signals."""
        df['STOCH_Cross_Buy'] = (
            (df['STOCH_K'] > df['STOCH_D']) &
            (df['STOCH_K'].shift(1) <= df['STOCH_D'].shift(1))
        ).astype(int)
        df['STOCH_Cross_Sell'] = (
            (df['STOCH_K'] < df['STOCH_D']) &
            (df['STOCH_K'].shift(1) >= df['STOCH_D'].shift(1))
        ).astype(int)
        return df

    def stoch_reversal_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate zone-qualified crossover signals.

        The cross must happen on the way *out* of an extreme zone — the prior
        bar was oversold (Buy) or overbought (Sell).  This is the same
        exit-the-zone framing as CCI_Reversal_*: crossing while still sinking
        deeper into the zone is a falling knife, not a reversal.
        """
        upper = self.config['overbought_oversold']['upper_threshold']
        lower = self.config['overbought_oversold']['lower_threshold']
        df['STOCH_Reversal_Buy'] = (
            (df['STOCH_Cross_Buy'] == 1) &
            (df['STOCH_K'].shift(1) < lower)
        ).astype(int)
        df['STOCH_Reversal_Sell'] = (
            (df['STOCH_Cross_Sell'] == 1) &
            (df['STOCH_K'].shift(1) > upper)
        ).astype(int)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all Stochastic-based trading signals."""
        df = self.add_indicators(df)
        df = self.stoch_overbought_oversold_strategy(df)
        df = self.stoch_cross_strategy(df)
        df = self.stoch_reversal_strategy(df)
        return df
