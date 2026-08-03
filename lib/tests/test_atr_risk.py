"""
Tests for ATR-driven risk management in the backtest engine.

Covers the two things that were previously computed but never used: the
``ATR_Stop_Long`` column as a trailing stop source (``stop_mode='atr'``) and
ATR as the risk denominator for position sizing (``atr_risk_based``).
"""

import logging
import unittest

import numpy as np
import pandas as pd

from lib.strategy import (
    ATR_STOP_COLUMN,
    ValidationError,
    atr_risk_based,
    backtest,
    get_position_sizer,
    run_backtest,
)


def _frame(n: int = 60, atr_stop: bool = True, atr: bool = True) -> pd.DataFrame:
    """A frame that buys on bar 5 and then drifts down, so a stop must fire."""
    idx = pd.date_range('2022-01-03', periods=n, freq='B')
    # Rise for 20 bars, then fall hard enough to take out any sane stop.
    close = np.concatenate([
        np.linspace(100, 120, 20),
        np.linspace(120, 70, n - 20),
    ])
    df = pd.DataFrame({
        'Open': close,
        'High': close * 1.01,
        'Low': close * 0.99,
        'Close': close,
        'Volume': np.full(n, 1_000_000),
        'Buy_Signal': np.zeros(n, dtype=int),
        'Sell_Signal': np.zeros(n, dtype=int),
    }, index=idx)
    df.loc[df.index[5], 'Buy_Signal'] = 1

    if atr:
        df['ATR'] = 2.0
    if atr_stop:
        # Chandelier-style: rolling high minus 1.5 ATR.
        df[ATR_STOP_COLUMN] = df['High'].rolling(14, min_periods=1).max() - 3.0
    return df


def _run(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    params = dict(
        initial_capital=10_000.0,
        position_sizing_strategy='percentage_of_portfolio',
        position_sizing_params={'percent': 0.5},
        buy_indicators=['Buy_Signal'],
        sell_indicators=['Sell_Signal'],
        position_scaling=1.0,
        min_holding_period=0,
    )
    params.update(kwargs)
    return backtest(df=df, **params)


class TestAtrRiskBasedSizer(unittest.TestCase):
    """The sizer itself, independent of the engine."""

    def test_sizes_by_atr_distance(self):
        # 1% of 100k = $1000 risk; 1.5 x ATR(4) = $6 stop distance -> 166 units.
        self.assertEqual(atr_risk_based(100_000, 50, 4.0, 1.5, 0.01), 166)

    def test_wider_atr_gives_smaller_position(self):
        tight = atr_risk_based(100_000, 50, 1.0)
        wide = atr_risk_based(100_000, 50, 8.0)
        self.assertGreater(tight, wide)

    def test_warmup_atr_yields_no_position(self):
        """NaN/zero ATR means risk is unmeasurable — take nothing, don't guess."""
        self.assertEqual(atr_risk_based(100_000, 50, float('nan')), 0)
        self.assertEqual(atr_risk_based(100_000, 50, 0.0), 0)
        self.assertEqual(atr_risk_based(100_000, 50, -1.0), 0)

    def test_zero_price_yields_no_position(self):
        self.assertEqual(atr_risk_based(100_000, 0, 4.0), 0)

    def test_registered_in_sizer_registry(self):
        sizer = get_position_sizer('atr_risk_based', risk_percent=0.01, atr_multiplier=1.5)
        self.assertEqual(sizer(100_000, 50, 4.0), 166)

    def test_default_multiplier_matches_atr_strategy(self):
        """Default 1.5 keeps sizing and stop_mode='atr' on the same risk unit."""
        from lib.signals.signals_ATR import ATR_TradingStrategy

        strategy_multiplier = ATR_TradingStrategy.DEFAULT_CONFIG['breakout']['multiplier']
        self.assertEqual(
            atr_risk_based(100_000, 50, 4.0),
            atr_risk_based(100_000, 50, 4.0, strategy_multiplier),
        )


class TestAtrStopMode(unittest.TestCase):
    """stop_mode='atr' driving the trailing stop off ATR_Stop_Long."""

    def test_atr_mode_uses_the_atr_stop_column(self):
        df = _frame()
        result = _run(df, stop_mode='atr', trailing_stop_loss=0.05)
        self.assertEqual(result.attrs['stop_mode'], 'atr')

        held = result[result['Units'] > 0]
        self.assertFalse(held.empty, "fixture should open a position")
        # While held, the stop must track the ATR column, not close * 0.95.
        entry = held.index[0]
        self.assertAlmostEqual(
            result.loc[entry, 'Trailing_Stop'],
            df.loc[entry, ATR_STOP_COLUMN],
            places=6,
        )

    def test_percent_and_atr_modes_produce_different_stops(self):
        df = _frame()
        pct = _run(df.copy(), stop_mode='percent', trailing_stop_loss=0.05)
        atr = _run(df.copy(), stop_mode='atr', trailing_stop_loss=0.05)
        finite = np.isfinite(pct['Trailing_Stop']) & np.isfinite(atr['Trailing_Stop'])
        self.assertTrue(finite.any(), "fixture should produce finite stops")
        self.assertFalse(
            np.allclose(pct.loc[finite, 'Trailing_Stop'], atr.loc[finite, 'Trailing_Stop']),
            "ATR stop should not coincide with the 5% trail",
        )

    def test_stop_ratchets_up_and_never_down(self):
        df = _frame()
        result = _run(df, stop_mode='atr')
        held = result[result['Units'] > 0]['Trailing_Stop']
        if len(held) > 1:
            diffs = np.diff(held.values)
            self.assertTrue((diffs >= -1e-9).all(), "trailing stop moved down while held")

    def test_missing_atr_column_falls_back_to_percent(self):
        """A bundle without ATR params still runs — degraded, logged, not raised."""
        df = _frame(atr_stop=False)
        with self.assertLogs('lib.strategy', level='WARNING') as captured:
            result = _run(df, stop_mode='atr', trailing_stop_loss=0.05)
        self.assertEqual(result.attrs['stop_mode'], 'percent')
        self.assertTrue(any(ATR_STOP_COLUMN in msg for msg in captured.output))

    def test_all_nan_atr_column_falls_back_to_percent(self):
        df = _frame()
        df[ATR_STOP_COLUMN] = np.nan
        with self.assertLogs('lib.strategy', level='WARNING'):
            result = _run(df, stop_mode='atr')
        self.assertEqual(result.attrs['stop_mode'], 'percent')

    def test_stop_above_close_falls_back_for_that_bar(self):
        """A Chandelier stop anchored to a rolling high can exceed the close.

        Using it there would exit on the next bar regardless of the trade, so
        those bars use the percentage stop instead — the recorded stop must stay
        strictly below the close.
        """
        df = _frame()
        df[ATR_STOP_COLUMN] = df['Close'] * 1.5  # always above price
        result = _run(df, stop_mode='atr', trailing_stop_loss=0.05)
        held = result[result['Units'] > 0]
        self.assertFalse(held.empty)
        self.assertTrue((held['Trailing_Stop'] < held['Close']).all())

    def test_unknown_stop_mode_raises(self):
        with self.assertRaises(ValidationError):
            _run(_frame(), stop_mode='chandelier')

    def test_default_stop_mode_is_percent(self):
        result = _run(_frame())
        self.assertEqual(result.attrs['stop_mode'], 'percent')

    def test_accumulation_mode_ignores_atr_stops(self):
        """Accumulation is a long-term hold; no stop of any kind should apply."""
        result = _run(_frame(), stop_mode='atr', strategy_mode='accumulation',
                      amount_per_buy=1000)
        self.assertTrue(np.isinf(result['Trailing_Stop']).all())


class TestAtrSizingInEngine(unittest.TestCase):
    """atr_risk_based wired through backtest()."""

    def test_engine_passes_per_bar_atr_to_the_sizer(self):
        df = _frame()
        result = backtest(
            df=df,
            initial_capital=100_000.0,
            position_sizing_strategy='atr_risk_based',
            position_sizing_params={'risk_percent': 0.01, 'atr_multiplier': 1.5},
            buy_indicators=['Buy_Signal'],
            sell_indicators=['Sell_Signal'],
            position_scaling=1.0,
        )
        self.assertEqual(result.attrs['position_sizing_strategy'], 'atr_risk_based')
        # 1% of 100k over 1.5 x ATR(2.0) = $3 -> 333 units, cash permitting.
        self.assertEqual(int(result['Units_to_buy'].max()), 333)

    def test_missing_atr_falls_back_to_percent_risk_sizing(self):
        df = _frame(atr=False)
        with self.assertLogs('lib.strategy', level='WARNING') as captured:
            result = backtest(
                df=df,
                initial_capital=100_000.0,
                position_sizing_strategy='atr_risk_based',
                position_sizing_params={'risk_percent': 0.01},
                buy_indicators=['Buy_Signal'],
                sell_indicators=['Sell_Signal'],
                position_scaling=1.0,
                trailing_stop_loss=0.05,
            )
        self.assertEqual(result.attrs['position_sizing_strategy'], 'risk_based')
        self.assertTrue(any('atr_risk_based' in msg for msg in captured.output))
        self.assertGreater(result['Units_to_buy'].max(), 0)

    def test_volatility_based_sizing_still_works(self):
        """The shared per-bar-argument path must not regress the existing sizer."""
        df = _frame()
        # Buy after the 20-bar volatility warmup, otherwise the sizer correctly
        # declines to size a position it cannot measure the risk of.
        df['Buy_Signal'] = 0
        df.loc[df.index[25], 'Buy_Signal'] = 1
        result = backtest(
            df=df,
            initial_capital=100_000.0,
            position_sizing_strategy='volatility_based',
            position_sizing_params={'target_volatility': 0.01},
            buy_indicators=['Buy_Signal'],
            sell_indicators=['Sell_Signal'],
            position_scaling=1.0,
        )
        self.assertGreater(result['Units_to_buy'].max(), 0)


class TestRunBacktestPassthrough(unittest.TestCase):
    def test_run_backtest_forwards_stop_mode(self):
        df = _frame()
        result = run_backtest(
            df, 10_000.0, ['Buy_Signal'], ['Sell_Signal'],
            stop_mode='atr', min_holding_period=0,
        )
        self.assertEqual(result.attrs['stop_mode'], 'atr')


class TestBacktestResultRecordsStopMode(unittest.TestCase):
    def test_effective_stop_mode_lands_in_params(self):
        from lib.backtest_result import run_backtest_result

        df = _frame()
        result = run_backtest_result(
            df,
            strategy_name='fixture',
            ticker='TEST',
            window_from='2022-01-03',
            window_to='2022-03-25',
            params={'atr_window': 14},
            buy_signals=['Buy_Signal'],
            sell_signals=['Sell_Signal'],
            backtest_kwargs={'stop_mode': 'atr'},
        )
        self.assertEqual(result.params['stop_mode'], 'atr')
        self.assertEqual(result.params['atr_window'], 14)

    def test_records_the_fallback_not_the_request(self):
        from lib.backtest_result import run_backtest_result

        df = _frame(atr_stop=False)
        result = run_backtest_result(
            df,
            strategy_name='fixture',
            ticker='TEST',
            window_from='2022-01-03',
            window_to='2022-03-25',
            params={},
            buy_signals=['Buy_Signal'],
            sell_signals=['Sell_Signal'],
            backtest_kwargs={'stop_mode': 'atr'},
        )
        self.assertEqual(result.params['stop_mode'], 'percent')


if __name__ == '__main__':
    logging.disable(logging.CRITICAL)
    unittest.main()
