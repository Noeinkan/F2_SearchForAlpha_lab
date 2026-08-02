# Average Directional Index module
"""
ADX-based regime strategies.

ADX measures trend *strength*, not direction, so most of these columns are
meant to be combined with an entry signal using AND logic rather than traded
standalone: ``ADX_TrendRegime_*`` gates trend followers, ``ADX_RangeRegime_*``
gates mean-reversion entries. ``ADX_DICross_*`` and ``ADX_Rising_*`` are
genuine events and can be used on their own.
"""

import logging
from typing import Any, Dict

import pandas as pd
from ta.trend import ADXIndicator

from lib.signals.base_strategy import BaseTradingStrategy

logger = logging.getLogger(__name__)


class ADX_TradingStrategy(BaseTradingStrategy):
    """ADX trend-strength regime strategy implementation."""

    STRATEGY_KEY = 'adx'
    STRATEGY_PRIORITY = 80
    SIGNAL_METADATA = {
        'ADX_TrendRegime_Buy': 'ADX above the trend threshold with +DI leading (strong uptrend).',
        'ADX_TrendRegime_Sell': 'ADX above the trend threshold with -DI leading (strong downtrend).',
        'ADX_RangeRegime_Buy': 'ADX below the range threshold — chop filter for mean-reversion longs.',
        'ADX_RangeRegime_Sell': 'ADX below the range threshold — chop filter for mean-reversion shorts.',
        'ADX_DICross_Buy': '+DI crosses above -DI while ADX confirms trend strength.',
        'ADX_DICross_Sell': '-DI crosses above +DI while ADX confirms trend strength.',
        'ADX_Rising_Buy': 'ADX breaks up through the trend threshold with +DI leading.',
        'ADX_Rising_Sell': 'ADX breaks up through the trend threshold with -DI leading.',
    }

    DEFAULT_CONFIG = {
        'adx': {
            'window': 14
        },
        'trend_regime': {
            'threshold': 25
        },
        'range_regime': {
            'threshold': 20
        }
    }

    def __init__(self, config: Dict[str, Any] = None):
        super().__init__(config, name="ADX_TradingStrategy")

    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """Add ADX and the directional movement lines to the DataFrame."""
        self.validate_dataframe(df, ['High', 'Low', 'Close'])

        window = max(1, int(self.config['adx'].get('window', 14)))
        adx = ADXIndicator(
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            window=window
        )
        df['ADX'] = adx.adx()
        df['ADX_Pos_DI'] = adx.adx_pos()
        df['ADX_Neg_DI'] = adx.adx_neg()
        return df

    def _valid_mask(self, df: pd.DataFrame) -> pd.Series:
        """Rows where ADX is actually initialised.

        ``ta`` back-fills the warmup period with 0.0 rather than NaN, so a
        plain notna() check would let the range-regime gate fire on every bar
        before the window is populated. ADX is bounded to [0, 100] and only
        genuinely reaches 0 on perfectly flat data, so treat 0 as warmup.
        """
        return (
            df['ADX'].notna() & (df['ADX'] > 0)
            & df['ADX_Pos_DI'].notna() & df['ADX_Neg_DI'].notna()
        )

    def adx_regime_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Flag trending vs ranging regimes.

        The range columns are deliberately identical on both sides: they are a
        symmetric "market is chopping" gate, so the same mask can be ANDed onto
        either a long or a short mean-reversion entry.
        """
        trend_threshold = float(self.config['trend_regime'].get('threshold', 25))
        range_threshold = float(self.config['range_regime'].get('threshold', 20))

        valid = self._valid_mask(df)
        trending = valid & (df['ADX'] > trend_threshold)
        bullish = df['ADX_Pos_DI'] > df['ADX_Neg_DI']

        df['ADX_TrendRegime_Buy'] = (trending & bullish).astype(int)
        df['ADX_TrendRegime_Sell'] = (trending & ~bullish).astype(int)

        ranging = valid & (df['ADX'] < range_threshold)
        df['ADX_RangeRegime_Buy'] = ranging.astype(int)
        df['ADX_RangeRegime_Sell'] = ranging.astype(int)
        return df

    def adx_di_cross_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate directional-index crossover signals confirmed by ADX."""
        threshold = float(self.config['trend_regime'].get('threshold', 25))

        pos_di = df['ADX_Pos_DI']
        neg_di = df['ADX_Neg_DI']
        pos_prev = pos_di.shift(1)
        neg_prev = neg_di.shift(1)

        valid = self._valid_mask(df) & pos_prev.notna() & neg_prev.notna()
        confirmed = valid & (df['ADX'] > threshold)

        df['ADX_DICross_Buy'] = (
            confirmed & (pos_di > neg_di) & (pos_prev <= neg_prev)
        ).astype(int)
        df['ADX_DICross_Sell'] = (
            confirmed & (neg_di > pos_di) & (neg_prev <= pos_prev)
        ).astype(int)
        return df

    def adx_rising_strategy(self, df: pd.DataFrame) -> pd.DataFrame:
        """Fire when ADX crosses up through the trend threshold (trend ignition)."""
        threshold = float(self.config['trend_regime'].get('threshold', 25))

        adx = df['ADX']
        adx_prev = adx.shift(1)
        valid = self._valid_mask(df) & adx_prev.notna()

        ignition = valid & (adx > threshold) & (adx_prev <= threshold)
        bullish = df['ADX_Pos_DI'] > df['ADX_Neg_DI']

        df['ADX_Rising_Buy'] = (ignition & bullish).astype(int)
        df['ADX_Rising_Sell'] = (ignition & ~bullish).astype(int)
        return df

    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """Generate all ADX-based regime signals."""
        df = self.add_indicators(df)
        df = self.adx_regime_strategy(df)
        df = self.adx_di_cross_strategy(df)
        df = self.adx_rising_strategy(df)
        return df
