"""
Tests for the ADX / ATR / OBV regime and confirmation strategies.

These three are registered like any other strategy but ship default-off in the
dashboard SIGNALS panel, so the tests cover both the signal maths and that
default-off wiring.
"""

import os
import sys
import unittest

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.signals.indicators import (
    generate_signals,
    get_registered_strategy_keys,
    get_signal_categories,
    get_signal_category_map,
)
from lib.signals.signals_ADX import ADX_TradingStrategy
from lib.signals.signals_ATR import ATR_TradingStrategy
from lib.signals.signals_OBV import OBV_TradingStrategy


def _sample_ohlcv(n_rows: int = 300, seed: int = 7) -> pd.DataFrame:
    """Trending-then-ranging series so both regimes are exercised."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range(start='2020-01-01', periods=n_rows, freq='D')

    drift = np.concatenate([
        np.full(n_rows // 2, 0.004),   # trending leg
        np.full(n_rows - n_rows // 2, 0.0),  # ranging leg
    ])
    returns = drift + rng.normal(0, 0.015, n_rows)
    close = 100 * np.exp(np.cumsum(returns))

    return pd.DataFrame({
        'Open': close * (1 + rng.normal(0, 0.002, n_rows)),
        'High': close * (1 + np.abs(rng.normal(0, 0.008, n_rows))),
        'Low': close * (1 - np.abs(rng.normal(0, 0.008, n_rows))),
        'Close': close,
        'Volume': rng.integers(1_000_000, 10_000_000, n_rows),
    }, index=dates)


class RegimeStrategyTestMixin:
    """Shared assertions for the three filter strategies."""

    strategy_class = None

    def setUp(self):
        self.df = _sample_ohlcv()

    def test_emits_all_declared_signal_columns(self):
        result = self.strategy_class().generate_signals(self.df.copy())
        for column in self.strategy_class.SIGNAL_METADATA:
            self.assertIn(column, result.columns)

    def test_signal_columns_are_binary(self):
        result = self.strategy_class().generate_signals(self.df.copy())
        for column in self.strategy_class.SIGNAL_METADATA:
            values = set(result[column].unique())
            self.assertTrue(
                values.issubset({0, 1}),
                f"{column} produced non-binary values: {values}",
            )

    def test_warmup_rows_emit_no_signals(self):
        """No signal should fire before its indicator window is populated.

        ``ta`` back-fills warmup bars with 0.0 rather than NaN, so this guards
        the regression where the range/compression gates fired on every bar of
        the warmup period.
        """
        result = self.strategy_class().generate_signals(self.df.copy())
        for column in self.strategy_class.SIGNAL_METADATA:
            self.assertEqual(
                int(result[column].iloc[0]), 0,
                f"{column} fired on the first bar",
            )

    def test_no_signal_is_degenerate(self):
        """Every column must fire sometimes, and none may fire nearly always.

        Catches both a dead signal (thresholds mis-calibrated so it never
        triggers) and a runaway one, either of which would pass the binary and
        mutual-exclusivity checks silently.
        """
        long_df = _sample_ohlcv(1200)
        result = self.strategy_class().generate_signals(long_df)
        for column in self.strategy_class.SIGNAL_METADATA:
            rate = float(result[column].mean())
            self.assertGreater(rate, 0.0, f"{column} never fires")
            self.assertLess(rate, 0.75, f"{column} fires on {rate:.0%} of bars")


class TestADXStrategy(RegimeStrategyTestMixin, unittest.TestCase):

    strategy_class = ADX_TradingStrategy

    def test_adds_directional_lines(self):
        result = ADX_TradingStrategy().generate_signals(self.df.copy())
        for column in ('ADX', 'ADX_Pos_DI', 'ADX_Neg_DI'):
            self.assertIn(column, result.columns)

    def test_trend_and_range_regimes_are_mutually_exclusive(self):
        result = ADX_TradingStrategy().generate_signals(self.df.copy())
        overlap = (
            (result['ADX_TrendRegime_Buy'] | result['ADX_TrendRegime_Sell'])
            & result['ADX_RangeRegime_Buy']
        )
        self.assertEqual(int(overlap.sum()), 0)

    def test_range_regime_is_symmetric(self):
        """The chop gate must be identical on both sides so it can gate either."""
        result = ADX_TradingStrategy().generate_signals(self.df.copy())
        pd.testing.assert_series_equal(
            result['ADX_RangeRegime_Buy'],
            result['ADX_RangeRegime_Sell'],
            check_names=False,
        )

    def test_threshold_is_config_driven(self):
        loose = ADX_TradingStrategy({'trend_regime': {'threshold': 5}})
        strict = ADX_TradingStrategy({'trend_regime': {'threshold': 60}})

        loose_hits = loose.generate_signals(self.df.copy())['ADX_TrendRegime_Buy'].sum()
        strict_hits = strict.generate_signals(self.df.copy())['ADX_TrendRegime_Buy'].sum()
        self.assertGreater(loose_hits, strict_hits)

    def test_di_cross_requires_trend_confirmation(self):
        """A DI cross must never fire while ADX is below the threshold."""
        strategy = ADX_TradingStrategy()
        result = strategy.generate_signals(self.df.copy())
        threshold = strategy.config['trend_regime']['threshold']

        fired = result['ADX_DICross_Buy'].astype(bool) | result['ADX_DICross_Sell'].astype(bool)
        self.assertTrue((result.loc[fired, 'ADX'] > threshold).all())


class TestATRStrategy(RegimeStrategyTestMixin, unittest.TestCase):

    strategy_class = ATR_TradingStrategy

    def test_adds_volatility_columns_and_stops(self):
        result = ATR_TradingStrategy().generate_signals(self.df.copy())
        for column in ('ATR', 'ATR_Pct', 'ATR_Pct_MA', 'ATR_Stop_Long', 'ATR_Stop_Short'):
            self.assertIn(column, result.columns)

    def test_stops_sit_on_the_correct_side_of_price(self):
        strategy = ATR_TradingStrategy()
        result = strategy.generate_signals(self.df.copy())
        window = strategy.config['atr']['window']

        valid = result['ATR_Stop_Long'].notna()
        self.assertTrue(valid.any(), "stop levels never initialised")

        rolling_high = result['High'].rolling(window=window, min_periods=1).max()
        rolling_low = result['Low'].rolling(window=window, min_periods=1).min()
        self.assertTrue((result.loc[valid, 'ATR_Stop_Long'] < rolling_high[valid]).all())
        self.assertTrue((result.loc[valid, 'ATR_Stop_Short'] > rolling_low[valid]).all())

    def test_stops_are_masked_during_warmup(self):
        result = ATR_TradingStrategy().generate_signals(self.df.copy())
        self.assertTrue(pd.isna(result['ATR_Stop_Long'].iloc[0]))
        self.assertTrue(pd.isna(result['ATR_Pct'].iloc[0]))

    def test_expansion_and_compression_never_coincide(self):
        result = ATR_TradingStrategy().generate_signals(self.df.copy())
        expanding = result['ATR_Expansion_Buy'] | result['ATR_Expansion_Sell']
        overlap = expanding & result['ATR_Compression_Buy']
        self.assertEqual(int(overlap.sum()), 0)

    def test_compression_is_symmetric(self):
        result = ATR_TradingStrategy().generate_signals(self.df.copy())
        pd.testing.assert_series_equal(
            result['ATR_Compression_Buy'],
            result['ATR_Compression_Sell'],
            check_names=False,
        )

    def test_breakout_multiplier_is_config_driven(self):
        loose = ATR_TradingStrategy({'breakout': {'multiplier': 0.25}})
        strict = ATR_TradingStrategy({'breakout': {'multiplier': 5.0}})

        loose_hits = loose.generate_signals(self.df.copy())['ATR_Breakout_Buy'].sum()
        strict_hits = strict.generate_signals(self.df.copy())['ATR_Breakout_Buy'].sum()
        self.assertGreater(loose_hits, strict_hits)

    def test_zero_price_rows_do_not_raise(self):
        df = self.df.copy()
        df.loc[df.index[10:15], 'Close'] = 0
        result = ATR_TradingStrategy().generate_signals(df)
        self.assertIn('ATR_Pct', result.columns)


class TestOBVStrategy(RegimeStrategyTestMixin, unittest.TestCase):

    strategy_class = OBV_TradingStrategy

    def test_adds_obv_and_moving_average(self):
        result = OBV_TradingStrategy().generate_signals(self.df.copy())
        self.assertIn('OBV', result.columns)
        self.assertIn('OBV_MA', result.columns)

    def test_confirmation_matches_price_direction(self):
        strategy = OBV_TradingStrategy()
        result = strategy.generate_signals(self.df.copy())
        lookback = strategy.config['confirmation']['lookback_period']

        price_change = result['Close'].diff(lookback)
        fired = result['OBV_Confirmation_Buy'].astype(bool)
        self.assertTrue((price_change[fired] > 0).all())

    def test_divergence_buy_requires_a_new_price_low(self):
        strategy = OBV_TradingStrategy()
        result = strategy.generate_signals(self.df.copy())
        lookback = strategy.config['divergence']['lookback_period']

        rolling_min = result['Close'].rolling(window=lookback, min_periods=lookback).min()
        fired = result['OBV_Divergence_Buy'].astype(bool)
        self.assertTrue((result.loc[fired, 'Close'] <= rolling_min[fired]).all())

    def test_zero_volume_is_stable(self):
        df = self.df.copy()
        df['Volume'] = 0
        result = OBV_TradingStrategy().generate_signals(df)
        for column in OBV_TradingStrategy.SIGNAL_METADATA:
            self.assertIn(column, result.columns)
        self.assertEqual(int(result['OBV_MACross_Buy'].sum()), 0)


class TestRegistryIntegration(unittest.TestCase):

    def setUp(self):
        self.df = _sample_ohlcv()

    def test_strategies_are_auto_discovered(self):
        keys = get_registered_strategy_keys()
        for key in ('adx', 'atr', 'obv'):
            self.assertIn(key, keys)

    def test_pipeline_emits_new_signal_columns(self):
        result_df, _ = generate_signals(self.df.copy())
        for column in ('ADX_TrendRegime_Buy', 'ATR_Breakout_Buy', 'OBV_MACross_Buy'):
            self.assertIn(column, result_df.columns)

    def test_runtime_settings_reach_the_strategies(self):
        """Dashboard-shaped indicator_settings must drive the new strategies."""
        loose, _ = generate_signals(self.df.copy(), {'adx': {'threshold': 5}})
        strict, _ = generate_signals(self.df.copy(), {'adx': {'threshold': 60}})
        self.assertGreater(
            loose['ADX_TrendRegime_Buy'].sum(),
            strict['ADX_TrendRegime_Buy'].sum(),
        )

    def test_categories_are_registered(self):
        categories = get_signal_categories()
        for category in ('ADX', 'ATR', 'OBV'):
            self.assertIn(category, categories)

    def test_signals_map_to_their_category(self):
        mapping = get_signal_category_map()
        self.assertEqual(mapping['ADX_TrendRegime_Buy'], 'ADX')
        self.assertEqual(mapping['ATR_Breakout_Sell'], 'ATR')
        self.assertEqual(mapping['OBV_Divergence_Buy'], 'OBV')


class TestDefaultOffWiring(unittest.TestCase):

    def test_new_categories_are_default_off(self):
        from lib.dash.dash_config import DEFAULT_OFF_SIGNAL_CATEGORIES

        self.assertEqual(
            DEFAULT_OFF_SIGNAL_CATEGORIES,
            frozenset({'ADX', 'ATR', 'OBV', 'SMA', 'EMA', 'VWAP'}),
        )

    def test_default_category_selection_excludes_them(self):
        from lib.dash.dash_config import DEFAULT_OFF_SIGNAL_CATEGORIES

        selected = [
            category for category in get_signal_categories()
            if category not in DEFAULT_OFF_SIGNAL_CATEGORIES
        ]
        self.assertEqual(set(selected), {'BB', 'MACD', 'RSI', 'CCI'})

    def test_chart_panes_stay_off_by_default(self):
        from lib.dash.bootstrap import DEFAULT_SELECTED_PLOTS

        for plot in ('adx', 'atr', 'obv'):
            self.assertNotIn(plot, DEFAULT_SELECTED_PLOTS)

    def test_agent_param_keys_are_mapped(self):
        from lib.agent_strategy import PARAM_KEY_MAP

        for key in ('adx_window', 'adx_trend_threshold', 'atr_breakout_multiplier', 'obv_ma_period'):
            self.assertIn(key, PARAM_KEY_MAP)


if __name__ == '__main__':
    unittest.main()
