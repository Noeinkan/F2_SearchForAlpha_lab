"""
Tests for the strategy module (backtest and position sizing).
"""

import unittest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.strategy import (
    backtest, run_backtest, validate_backtest_inputs,
    percentage_of_portfolio, fixed_dollar_amount, volatility_based,
    kelly_criterion, risk_based, get_position_sizer,
    calculate_signal_strengths, calculate_returns,
    ValidationError, BacktestError
)


class TestValidateBacktestInputs(unittest.TestCase):
    """Tests for input validation."""

    def setUp(self):
        """Set up test fixtures."""
        dates = pd.date_range(start='2020-01-01', periods=100, freq='D')
        self.valid_df = pd.DataFrame({
            'Close': np.random.uniform(95, 105, 100),
            'High': np.random.uniform(100, 110, 100),
            'Low': np.random.uniform(90, 100, 100),
            'Buy_Signal': np.random.randint(0, 2, 100),
            'Sell_Signal': np.random.randint(0, 2, 100)
        }, index=dates)

    def test_valid_inputs_pass(self):
        """Test that valid inputs pass validation."""
        try:
            validate_backtest_inputs(
                self.valid_df, 10000,
                ['Buy_Signal'], ['Sell_Signal']
            )
        except ValidationError:
            self.fail("validate_backtest_inputs raised ValidationError unexpectedly")

    def test_empty_df_raises_error(self):
        """Test that empty DataFrame raises ValidationError."""
        with self.assertRaises(ValidationError):
            validate_backtest_inputs(
                pd.DataFrame(), 10000,
                ['Buy_Signal'], ['Sell_Signal']
            )

    def test_negative_capital_raises_error(self):
        """Test that negative capital raises ValidationError."""
        with self.assertRaises(ValidationError):
            validate_backtest_inputs(
                self.valid_df, -10000,
                ['Buy_Signal'], ['Sell_Signal']
            )

    def test_missing_close_column_raises_error(self):
        """Test that missing Close column raises ValidationError."""
        df = self.valid_df.drop(columns=['Close'])
        with self.assertRaises(ValidationError):
            validate_backtest_inputs(
                df, 10000,
                ['Buy_Signal'], ['Sell_Signal']
            )

    def test_missing_buy_indicator_raises_error(self):
        """Test that missing buy indicator column raises ValidationError."""
        with self.assertRaises(ValidationError):
            validate_backtest_inputs(
                self.valid_df, 10000,
                ['NonExistent_Buy'], ['Sell_Signal']
            )


class TestPositionSizing(unittest.TestCase):
    """Tests for position sizing functions."""

    def test_percentage_of_portfolio(self):
        """Test percentage of portfolio sizing."""
        units = percentage_of_portfolio(100000, 50, 0.10)
        # 10% of 100000 = 10000, 10000 / 50 = 200 units
        self.assertEqual(units, 200)

    def test_percentage_of_portfolio_zero_price(self):
        """Test percentage of portfolio with zero price."""
        units = percentage_of_portfolio(100000, 0, 0.10)
        self.assertEqual(units, 0)

    def test_fixed_dollar_amount(self):
        """Test fixed dollar amount sizing."""
        units = fixed_dollar_amount(50, 1000)
        # 1000 / 50 = 20 units
        self.assertEqual(units, 20)

    def test_fixed_dollar_amount_zero_price(self):
        """Test fixed dollar amount with zero price."""
        units = fixed_dollar_amount(0, 1000)
        self.assertEqual(units, 0)

    def test_kelly_criterion(self):
        """Test Kelly criterion sizing."""
        # Kelly = 0.6 - (0.4 / 2) = 0.4
        # Position = 0.4 * 100000 = 40000
        # Units = 40000 / 50 = 800
        units = kelly_criterion(0.6, 2.0, 100000, 50)
        self.assertEqual(units, 800)

    def test_kelly_criterion_negative(self):
        """Test Kelly criterion with negative expectation."""
        # Low win rate should give 0 or positive clamped
        units = kelly_criterion(0.2, 1.0, 100000, 50)
        self.assertGreaterEqual(units, 0)

    def test_risk_based(self):
        """Test risk-based sizing."""
        # Risk amount = 100000 * 0.01 = 1000
        # Stop loss amount = 50 * 0.05 = 2.5
        # Position = 1000 / 2.5 = 400 units
        units = risk_based(100000, 50, 0.05, 0.01)
        self.assertEqual(units, 400)


class TestGetPositionSizer(unittest.TestCase):
    """Tests for get_position_sizer factory function."""

    def test_percentage_strategy(self):
        """Test getting percentage strategy."""
        sizer = get_position_sizer('percentage_of_portfolio', percent=0.1)
        units = sizer(100000, 50)
        self.assertEqual(units, 200)

    def test_fixed_dollar_strategy(self):
        """Test getting fixed dollar strategy."""
        sizer = get_position_sizer('fixed_dollar_amount', amount=1000)
        units = sizer(100000, 50)
        self.assertEqual(units, 20)

    def test_unknown_strategy_raises_error(self):
        """Test that unknown strategy raises ValueError."""
        with self.assertRaises(ValueError):
            get_position_sizer('unknown_strategy')


class TestCalculateSignalStrengths(unittest.TestCase):
    """Tests for signal strength calculation."""

    def setUp(self):
        """Set up test fixtures."""
        self.df = pd.DataFrame({
            'Buy_1': [1, 0, 1, 0],
            'Buy_2': [0, 1, 1, 0],
            'Sell_1': [0, 0, 1, 1],
            'Sell_2': [0, 1, 0, 1]
        })

    def test_unweighted_strengths(self):
        """Test unweighted signal strength calculation."""
        buy_strength, sell_strength = calculate_signal_strengths(
            self.df, ['Buy_1', 'Buy_2'], ['Sell_1', 'Sell_2'], None
        )
        
        np.testing.assert_array_equal(buy_strength, [1, 1, 2, 0])
        np.testing.assert_array_equal(sell_strength, [0, 1, 1, 2])

    def test_weighted_strengths(self):
        """Test weighted signal strength calculation."""
        weights = {'Buy_1': 2.0, 'Buy_2': 1.0, 'Sell_1': 1.5, 'Sell_2': 0.5}
        buy_strength, sell_strength = calculate_signal_strengths(
            self.df, ['Buy_1', 'Buy_2'], ['Sell_1', 'Sell_2'], weights
        )
        
        # Row 0: Buy = 2*1 + 1*0 = 2, Sell = 1.5*0 + 0.5*0 = 0
        # Row 2: Buy = 2*1 + 1*1 = 3, Sell = 1.5*1 + 0.5*0 = 1.5
        np.testing.assert_array_equal(buy_strength, [2, 1, 3, 0])
        np.testing.assert_array_almost_equal(sell_strength, [0, 0.5, 1.5, 2])


class TestBacktest(unittest.TestCase):
    """Integration tests for the backtest function."""

    def setUp(self):
        """Set up test fixtures with realistic data."""
        np.random.seed(42)
        n_rows = 252  # One trading year
        dates = pd.date_range(start='2020-01-01', periods=n_rows, freq='D')
        
        # Generate realistic price data
        returns = np.random.randn(n_rows) * 0.02
        prices = 100 * np.exp(np.cumsum(returns))
        
        self.df = pd.DataFrame({
            'Close': prices,
            'High': prices * 1.02,
            'Low': prices * 0.98,
            'Open': prices * 1.001,
            'Volume': np.random.randint(1000000, 10000000, n_rows),
            'RSI_Oversold_Buy': (np.random.rand(n_rows) > 0.9).astype(int),
            'RSI_Overbought_Sell': (np.random.rand(n_rows) > 0.9).astype(int)
        }, index=dates)

    def test_backtest_returns_dataframe(self):
        """Test that backtest returns a DataFrame."""
        result = backtest(
            df=self.df,
            initial_capital=10000,
            position_sizing_strategy='percentage_of_portfolio',
            position_sizing_params={'percent': 0.1},
            buy_indicators=['RSI_Oversold_Buy'],
            sell_indicators=['RSI_Overbought_Sell']
        )
        
        self.assertIsInstance(result, pd.DataFrame)

    def test_backtest_has_required_columns(self):
        """Test that backtest result has all required columns."""
        result = backtest(
            df=self.df,
            initial_capital=10000,
            position_sizing_strategy='percentage_of_portfolio',
            position_sizing_params={'percent': 0.1},
            buy_indicators=['RSI_Oversold_Buy'],
            sell_indicators=['RSI_Overbought_Sell']
        )
        
        required_columns = [
            'Units', 'Cash_Value', 'Portfolio_Value',
            'Strategy_Returns', 'Cumulative_Returns'
        ]
        for col in required_columns:
            self.assertIn(col, result.columns, f"Missing column: {col}")

    def test_backtest_preserves_capital(self):
        """Test that total portfolio value is always positive."""
        result = backtest(
            df=self.df,
            initial_capital=10000,
            position_sizing_strategy='percentage_of_portfolio',
            position_sizing_params={'percent': 0.1},
            buy_indicators=['RSI_Oversold_Buy'],
            sell_indicators=['RSI_Overbought_Sell']
        )
        
        self.assertTrue((result['Portfolio_Value'] > 0).all())

    def test_backtest_initial_portfolio_value(self):
        """Test that initial portfolio value equals initial capital."""
        result = backtest(
            df=self.df,
            initial_capital=10000,
            position_sizing_strategy='percentage_of_portfolio',
            position_sizing_params={'percent': 0.1},
            buy_indicators=['RSI_Oversold_Buy'],
            sell_indicators=['RSI_Overbought_Sell']
        )
        
        self.assertEqual(result['Portfolio_Value'].iloc[0], 10000)


class TestRunBacktest(unittest.TestCase):
    """Tests for the run_backtest convenience function."""

    def setUp(self):
        """Set up test fixtures."""
        np.random.seed(42)
        n_rows = 100
        dates = pd.date_range(start='2020-01-01', periods=n_rows, freq='D')
        prices = 100 + np.cumsum(np.random.randn(n_rows))
        
        self.df = pd.DataFrame({
            'Close': prices,
            'High': prices * 1.02,
            'Low': prices * 0.98,
            'Buy_Signal': (np.random.rand(n_rows) > 0.9).astype(int),
            'Sell_Signal': (np.random.rand(n_rows) > 0.9).astype(int)
        }, index=dates)

    def test_run_backtest_works(self):
        """Test that run_backtest works with defaults."""
        result = run_backtest(
            self.df, 10000,
            ['Buy_Signal'], ['Sell_Signal']
        )
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertIn('Portfolio_Value', result.columns)


if __name__ == '__main__':
    unittest.main()
