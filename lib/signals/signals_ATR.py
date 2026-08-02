# Average True Range module
"""
ATR-based volatility strategies.

ATR is directionless, so the columns here fall into two groups:
``ATR_Compression_*`` is a symmetric low-volatility gate meant to be ANDed onto
another entry, while ``ATR_Expansion_*`` and ``ATR_Breakout_*`` are directional
volatility events. ``ATR_Stop_Long`` / ``ATR_Stop_Short`` are informational
Chandelier-style stop levels for volatility-scaled exits and position sizing.
"""

import logging
from typing import Any, Dict

import numpy as np
import pandas as pd
from ta.volatility import AverageTrueRange

from lib.signals.base_strategy import BaseTradingStrategy

logger = logging.getLogger(__name__)


class ATR_TradingStrategy(BaseTradingStrategy):
    """ATR volatility-regime strategy implementation."""

    STRATEGY_KEY = 'atr'
    STRATEGY_PRIORITY = 90
    SIGNAL_METADATA = {
        'ATR_Expansion_Buy': 'Volatility expands above its average while price closes up.',
        'ATR_Expansion_Sell': 'Volatility expands above its average while price closes down.',
        'ATR_Compression_Buy': 'Volatility compressed below its average — low-vol gate for longs.',
        'ATR_Compression_Sell': 'Volatility compressed below its average — low-vol gate for shorts.',
        'ATR_Breakout_Buy': 'Close advances more than the ATR multiple in one bar.',
        'ATR_Breakout_Sell': 'Close drops more than the ATR multiple in one bar.',
    }

    DEFAULT_CONFIG = {
        'atr': {
            'window': 14
        },
        # Factors are ratios of ATR% to its own rolling mean. On daily equities
        # that ratio sits roughly in [0.75, 1.5], so 1.2 / 0.9 select about the
        # top decile and bottom quintile — selective enough to mean something,
        # frequent enough to be usable as a gate.
        'expansion': {
            'lookback': 20,
            'factor': 1.2
        },
        'compression': {
            'factor': 0.9
        },
        'breakout': {
            'multiplier': 1.5
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config, name="ATR_TradingStrategy")

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add ATR, its normalised percentage form, and volatility stop levels."""
        self.validate_dataframe(df, ['High', 'Low', 'Close'])

        window = max(1, int(self.config['atr'].get('window', 14)))
        lookback = max(1, int(self.config['expansion'].get('lookback', 20)))
        multiplier = float(self.config['breakout'].get('multiplier', 1.5))

        atr = AverageTrueRange(
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            window=window
        )
        df['ATR'] = atr.average_true_range()

        # ``ta`` back-fills the warmup period with 0.0 rather than NaN. Mask it
        # out here so the derived columns stay NaN until ATR is initialised and
        # no signal can fire on an uninitialised window. df['ATR'] itself is
        # left as-is because other strategies and the chart pane read it.
        warm_atr = df['ATR'].where(df['ATR'] > 0)

        # Normalise by price so the volatility regime is comparable across
        # tickers and across long date ranges where price level drifts.
        close = df['Close'].replace(0, np.nan)
        df['ATR_Pct'] = (warm_atr / close).replace([np.inf, -np.inf], np.nan)
        df['ATR_Pct_MA'] = df['ATR_Pct'].rolling(window=lookback, min_periods=lookback).mean()

        df['ATR_Stop_Long'] = df['High'].rolling(window=window, min_periods=1).max() - multiplier * warm_atr
        df['ATR_Stop_Short'] = df['Low'].rolling(window=window, min_periods=1).min() + multiplier * warm_atr
        return df

    def atr_expansion_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flag volatility expansion, split by the direction of the close."""
        factor = float(self.config['expansion'].get('factor', 1.5))

        valid = df['ATR_Pct'].notna() & df['ATR_Pct_MA'].notna()
        expanding = valid & (df['ATR_Pct'] > df['ATR_Pct_MA'] * factor)

        close_prev = df['Close'].shift(1)
        df['ATR_Expansion_Buy'] = (expanding & (df['Close'] > close_prev)).astype(int)
        df['ATR_Expansion_Sell'] = (expanding & (df['Close'] < close_prev)).astype(int)
        return df

    def atr_compression_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flag the low-volatility regime that typically precedes expansion.

        Both sides carry the same mask — it is a symmetric gate, not a
        directional call, so it can be ANDed onto either a long or a short.
        """
        factor = float(self.config['compression'].get('factor', 0.75))

        valid = df['ATR_Pct'].notna() & df['ATR_Pct_MA'].notna()
        compressed = valid & (df['ATR_Pct'] < df['ATR_Pct_MA'] * factor)

        df['ATR_Compression_Buy'] = compressed.astype(int)
        df['ATR_Compression_Sell'] = compressed.astype(int)
        return df

    def atr_breakout_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fire when a single bar's move exceeds the ATR multiple (thrust)."""
        multiplier = float(self.config['breakout'].get('multiplier', 1.5))

        close = df['Close']
        close_prev = close.shift(1)
        atr_prev = df['ATR'].shift(1)

        valid = close.notna() & close_prev.notna() & atr_prev.notna() & (atr_prev > 0)
        thrust = atr_prev * multiplier

        df['ATR_Breakout_Buy'] = (valid & ((close - close_prev) > thrust)).astype(int)
        df['ATR_Breakout_Sell'] = (valid & ((close_prev - close) > thrust)).astype(int)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all ATR-based volatility signals."""
        df = self.add_indicators(df)
        df = self.atr_expansion_strategy(df)
        df = self.atr_compression_strategy(df)
        df = self.atr_breakout_strategy(df)
        return df
