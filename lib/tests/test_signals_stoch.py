"""Tests for the Stochastic oscillator strategy and its registry wiring."""

import unittest

import numpy as np
import pandas as pd

from lib.signals.indicators import (
    generate_signals,
    get_registered_strategies,
    get_signal_categories,
    get_signal_category_map,
)
from lib.signals.signals_STOCH import STOCH_TradingStrategy


def _frame(n: int = 300, seed: int = 7) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    prices = 100 * np.exp(np.cumsum(rng.standard_normal(n) * 0.02))
    return pd.DataFrame(
        {
            'Open': prices * 1.001,
            'High': prices * 1.02,
            'Low': prices * 0.98,
            'Close': prices,
            'Volume': rng.integers(1_000_000, 10_000_000, n),
        },
        index=pd.date_range('2022-01-01', periods=n, freq='D'),
    )


class TestStochIndicator(unittest.TestCase):

    def setUp(self):
        self.df = STOCH_TradingStrategy().generate_signals(_frame())

    def test_k_and_d_are_bounded_percentages(self):
        for column in ('STOCH_K', 'STOCH_D'):
            values = self.df[column].dropna()
            self.assertGreater(len(values), 0)
            self.assertGreaterEqual(values.min(), 0.0)
            self.assertLessEqual(values.max(), 100.0)

    def test_d_is_the_smoothed_mean_of_k(self):
        smooth = STOCH_TradingStrategy.DEFAULT_CONFIG['stoch']['smooth_window']
        expected = self.df['STOCH_K'].rolling(smooth, min_periods=smooth).mean()
        pd.testing.assert_series_equal(
            self.df['STOCH_D'].dropna(),
            expected.dropna(),
            check_names=False,
        )

    def test_signals_are_zero_one_integers(self):
        for column in STOCH_TradingStrategy.SIGNAL_METADATA:
            self.assertTrue(set(self.df[column].unique()) <= {0, 1}, column)

    def test_every_documented_signal_column_exists(self):
        for column in STOCH_TradingStrategy.SIGNAL_METADATA:
            self.assertIn(column, self.df.columns)

    def test_level_signals_respect_their_thresholds(self):
        upper = STOCH_TradingStrategy.DEFAULT_CONFIG['overbought_oversold']['upper_threshold']
        lower = STOCH_TradingStrategy.DEFAULT_CONFIG['overbought_oversold']['lower_threshold']
        self.assertTrue((self.df.loc[self.df['STOCH_Oversold_Buy'] == 1, 'STOCH_K'] < lower).all())
        self.assertTrue((self.df.loc[self.df['STOCH_Overbought_Sell'] == 1, 'STOCH_K'] > upper).all())

    def test_reversal_is_a_subset_of_the_plain_cross(self):
        """A reversal is a cross that also left an extreme zone — never a new event."""
        self.assertTrue((self.df['STOCH_Reversal_Buy'] <= self.df['STOCH_Cross_Buy']).all())
        self.assertTrue((self.df['STOCH_Reversal_Sell'] <= self.df['STOCH_Cross_Sell']).all())

    def test_buy_and_sell_crosses_never_fire_on_the_same_bar(self):
        both = (self.df['STOCH_Cross_Buy'] == 1) & (self.df['STOCH_Cross_Sell'] == 1)
        self.assertFalse(both.any())

    def test_signals_use_only_past_and_present_bars(self):
        """Truncating the tape must not change the signals on the bars that remain."""
        full = self.df
        cut = STOCH_TradingStrategy().generate_signals(_frame().iloc[:200])
        columns = list(STOCH_TradingStrategy.SIGNAL_METADATA)
        pd.testing.assert_frame_equal(cut[columns], full[columns].iloc[:200])

    def test_config_overrides_reach_the_indicator(self):
        """Assert on %K itself, not only on threshold hits.

        A threshold assertion alone passes vacuously whenever the override
        happens to fire nothing, which is exactly the case a broken config
        path would produce.
        """
        out = STOCH_TradingStrategy({
            'stoch': {'window': 5, 'smooth_window': 2},
            'overbought_oversold': {'upper_threshold': 90, 'lower_threshold': 10},
        }).generate_signals(_frame())

        # The window override changes %K, so it cannot equal the default run.
        self.assertFalse(out['STOCH_K'].equals(self.df['STOCH_K']))
        # The smoothing override changes how %D is derived from %K.
        expected = out['STOCH_K'].rolling(2, min_periods=2).mean()
        pd.testing.assert_series_equal(
            out['STOCH_D'].dropna(), expected.dropna(), check_names=False
        )
        # And the threshold override is the one actually applied.
        fired = out.loc[out['STOCH_Oversold_Buy'] == 1, 'STOCH_K']
        self.assertTrue((fired < 10).all())
        self.assertTrue((self.df['STOCH_K'].dropna() < 10).any(),
                        "fixture never reaches K < 10; the threshold check is vacuous")


class TestStochRegistryWiring(unittest.TestCase):

    def test_strategy_is_auto_discovered(self):
        self.assertIn('stoch', [r.key for r in get_registered_strategies()])

    def test_category_is_registered(self):
        self.assertIn('STOCH', get_signal_categories())

    def test_signals_map_to_their_category(self):
        mapping = get_signal_category_map()
        self.assertEqual(mapping['STOCH_Cross_Buy'], 'STOCH')
        self.assertEqual(mapping['STOCH_Reversal_Sell'], 'STOCH')

    def test_pipeline_emits_the_signal_columns(self):
        out, _ = generate_signals(_frame())
        for column in STOCH_TradingStrategy.SIGNAL_METADATA:
            self.assertIn(column, out.columns)

    def test_runtime_settings_reach_the_strategy(self):
        """The flat runtime settings shape must drive the strategy, not just the YAML."""
        default, _ = generate_signals(_frame())
        tuned, _ = generate_signals(
            _frame(), {'stoch': {'period': 5, 'smooth_window': 2, 'oversold': 10, 'overbought': 90}}
        )
        self.assertFalse(tuned['STOCH_K'].equals(default['STOCH_K']))
        pd.testing.assert_series_equal(
            tuned['STOCH_D'].dropna(),
            tuned['STOCH_K'].rolling(2, min_periods=2).mean().dropna(),
            check_names=False,
        )
        self.assertTrue((tuned.loc[tuned['STOCH_Oversold_Buy'] == 1, 'STOCH_K'] < 10).all())

    def test_agent_param_keys_are_mapped(self):
        from lib.agent_strategy import PARAM_KEY_MAP

        for key in ('stoch_window', 'stoch_smooth', 'stoch_overbought', 'stoch_oversold'):
            self.assertIn(key, PARAM_KEY_MAP)
            self.assertEqual(PARAM_KEY_MAP[key][0], 'stoch')

    def test_stays_off_by_default_so_existing_runs_are_unchanged(self):
        from lib.dash.bootstrap import DEFAULT_SELECTED_PLOTS
        from lib.dash.dash_config import DEFAULT_OFF_SIGNAL_CATEGORIES

        self.assertIn('STOCH', DEFAULT_OFF_SIGNAL_CATEGORIES)
        self.assertNotIn('stoch', DEFAULT_SELECTED_PLOTS)

    def test_chart_pane_is_available(self):
        from lib.dash.chart_payload import INDICATOR_PANES

        self.assertIn('stoch', INDICATOR_PANES)

    def test_signal_descriptions_exist_for_the_ui(self):
        from lib.dash.callbacks.shared_signals import SIGNAL_DESCRIPTIONS

        for column in STOCH_TradingStrategy.SIGNAL_METADATA:
            self.assertIn(column, SIGNAL_DESCRIPTIONS)


if __name__ == '__main__':
    unittest.main()
