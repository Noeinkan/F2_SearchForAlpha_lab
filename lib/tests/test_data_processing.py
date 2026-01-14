"""
Tests for the data processing module.
"""

import unittest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from datetime import datetime

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.data_processing import (
    fetch_data, get_all_tickers, 
    calculate_max_drawdown, calculate_sharpe_ratio,
    calculate_win_rate, calculate_profit_factor,
    calculate_average_trade_duration, create_backtest_results,
    DataFetchError
)


class TestFetchData(unittest.TestCase):
    """Tests for the fetch_data function."""

    @patch('lib.data_processing.yf.Ticker')
    def test_fetch_data_returns_dataframe(self, mock_ticker):
        """Test that fetch_data returns a DataFrame."""
        # Mock the yfinance response
        mock_history = pd.DataFrame({
            'Open': [100, 101],
            'High': [102, 103],
            'Low': [98, 99],
            'Close': [101, 102],
            'Volume': [1000000, 1100000]
        }, index=pd.to_datetime(['2020-01-01', '2020-01-02']))
        
        mock_ticker.return_value.history.return_value = mock_history
        
        result = fetch_data('AAPL', '2020-01-01', '2020-01-03')
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)

    @patch('lib.data_processing.yf.Ticker')
    def test_fetch_data_empty_raises_error(self, mock_ticker):
        """Test that empty data raises DataFetchError."""
        mock_ticker.return_value.history.return_value = pd.DataFrame()
        
        with self.assertRaises(DataFetchError):
            fetch_data('INVALID', '2020-01-01', '2020-01-03')

    def test_fetch_data_invalid_symbol_raises_error(self):
        """Test that invalid symbol raises DataFetchError."""
        with self.assertRaises(DataFetchError):
            fetch_data('', '2020-01-01', '2020-01-03')

    def test_fetch_data_none_symbol_raises_error(self):
        """Test that None symbol raises DataFetchError."""
        with self.assertRaises(DataFetchError):
            fetch_data(None, '2020-01-01', '2020-01-03')


class TestCalculateMetrics(unittest.TestCase):
    """Tests for metric calculation functions."""

    def setUp(self):
        """Set up test fixtures."""
        dates = pd.date_range(start='2020-01-01', periods=100, freq='D')
        
        # Create sample backtest results
        self.df = pd.DataFrame({
            'Close': np.linspace(100, 110, 100),
            'Portfolio_Value': np.linspace(10000, 11000, 100),
            'Cumulative_Returns': np.linspace(1, 1.1, 100),
            'Strategy_Returns': np.random.randn(100) * 0.01,
            'Units': [0] * 30 + [10] * 40 + [0] * 30
        }, index=dates)

    def test_calculate_max_drawdown(self):
        """Test max drawdown calculation."""
        # Create a scenario with known drawdown
        df = pd.DataFrame({
            'Cumulative_Returns': [1.0, 1.1, 1.05, 0.9, 1.0]
        })
        
        max_dd = calculate_max_drawdown(df)
        
        # Peak is 1.1, trough is 0.9, drawdown = (0.9 - 1.1) / 1.1 ≈ -0.182
        self.assertLess(max_dd, 0)
        self.assertAlmostEqual(max_dd, -0.1818, places=2)

    def test_calculate_max_drawdown_missing_column(self):
        """Test max drawdown with missing column."""
        df = pd.DataFrame({'Close': [100, 101, 102]})
        result = calculate_max_drawdown(df)
        self.assertEqual(result, 0.0)

    def test_calculate_sharpe_ratio(self):
        """Test Sharpe ratio calculation."""
        # Create returns with known mean and std
        returns = pd.Series([0.01, 0.02, -0.01, 0.015, 0.005])
        
        sharpe = calculate_sharpe_ratio(returns, risk_free_rate=0.02)
        
        self.assertIsInstance(sharpe, float)

    def test_calculate_sharpe_ratio_zero_std(self):
        """Test Sharpe ratio with zero standard deviation."""
        returns = pd.Series([0.01, 0.01, 0.01])
        sharpe = calculate_sharpe_ratio(returns)
        self.assertEqual(sharpe, 0.0)

    def test_calculate_win_rate(self):
        """Test win rate calculation."""
        df = pd.DataFrame({
            'Strategy_Returns': [0.01, -0.01, 0.02, 0.01, -0.02]
        })
        
        win_rate = calculate_win_rate(df)
        
        # 3 positive out of 5
        self.assertAlmostEqual(win_rate, 0.6, places=2)

    def test_calculate_win_rate_missing_column(self):
        """Test win rate with missing column."""
        df = pd.DataFrame({'Close': [100, 101, 102]})
        result = calculate_win_rate(df)
        self.assertEqual(result, 0.0)

    def test_calculate_profit_factor(self):
        """Test profit factor calculation."""
        df = pd.DataFrame({
            'Strategy_Returns': [0.03, -0.01, 0.02, -0.01]
        })
        
        profit_factor = calculate_profit_factor(df)
        
        # Gross profits = 0.05, Gross losses = 0.02
        # Profit factor = 0.05 / 0.02 = 2.5
        self.assertAlmostEqual(profit_factor, 2.5, places=2)

    def test_calculate_profit_factor_no_losses(self):
        """Test profit factor with no losses."""
        df = pd.DataFrame({
            'Strategy_Returns': [0.01, 0.02, 0.03]
        })
        
        profit_factor = calculate_profit_factor(df)
        
        self.assertEqual(profit_factor, np.inf)

    def test_calculate_average_trade_duration(self):
        """Test average trade duration calculation."""
        result = calculate_average_trade_duration(self.df)
        
        # Should return a non-negative number
        self.assertGreaterEqual(result, 0)


class TestCreateBacktestResults(unittest.TestCase):
    """Tests for create_backtest_results function."""

    def setUp(self):
        """Set up test fixtures."""
        dates = pd.date_range(start='2020-01-01', periods=100, freq='D')
        
        self.df = pd.DataFrame({
            'Close': np.linspace(100, 110, 100),
            'Portfolio_Value': np.linspace(10000, 11000, 100),
            'Cumulative_Returns': np.linspace(1, 1.1, 100),
            'Strategy_Returns': np.random.randn(100) * 0.01,
            'Units': [0] * 30 + [10] * 40 + [0] * 30
        }, index=dates)

    def test_create_backtest_results_returns_dict(self):
        """Test that create_backtest_results returns a dictionary."""
        result = create_backtest_results(
            self.df, 'SPY', 10000,
            ['Buy_Signal'], ['Sell_Signal']
        )
        
        self.assertIsInstance(result, dict)

    def test_create_backtest_results_has_required_keys(self):
        """Test that result has all required keys."""
        result = create_backtest_results(
            self.df, 'SPY', 10000,
            ['Buy_Signal'], ['Sell_Signal']
        )
        
        required_keys = [
            'ticker', 'start_date', 'end_date', 'initial_capital',
            'final_portfolio_value', 'total_return', 'market_return',
            'buy_strategy', 'sell_strategy', 'max_drawdown',
            'sharpe_ratio', 'win_rate', 'profit_factor', 'avg_trade_duration'
        ]
        
        for key in required_keys:
            self.assertIn(key, result, f"Missing key: {key}")

    def test_create_backtest_results_correct_values(self):
        """Test that result values are correct."""
        result = create_backtest_results(
            self.df, 'SPY', 10000,
            ['Buy_Signal'], ['Sell_Signal']
        )
        
        self.assertEqual(result['ticker'], 'SPY')
        self.assertEqual(result['initial_capital'], 10000)
        self.assertAlmostEqual(result['final_portfolio_value'], 11000, places=0)
        self.assertEqual(result['buy_strategy'], ['Buy_Signal'])
        self.assertEqual(result['sell_strategy'], ['Sell_Signal'])


class TestGetAllTickers(unittest.TestCase):
    """Tests for get_all_tickers function."""

    @patch('lib.data_processing.pd.read_html')
    def test_get_all_tickers_returns_dataframe(self, mock_read_html):
        """Test that get_all_tickers returns a DataFrame."""
        # Mock Wikipedia responses
        sp500_df = pd.DataFrame({
            'Symbol': ['AAPL', 'MSFT'],
            'Security': ['Apple Inc.', 'Microsoft Corp.']
        })
        nasdaq_df = pd.DataFrame({
            'Ticker': ['GOOGL', 'AMZN'],
            'Company': ['Alphabet Inc.', 'Amazon.com Inc.']
        })
        
        mock_read_html.side_effect = [
            [sp500_df],  # S&P 500
            [None, None, None, None, nasdaq_df]  # NASDAQ-100 (index 4)
        ]
        
        result = get_all_tickers()
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertIn('Symbol', result.columns)
        self.assertIn('Security', result.columns)

    @patch('lib.data_processing.pd.read_html')
    def test_get_all_tickers_includes_etfs(self, mock_read_html):
        """Test that ETFs are included."""
        sp500_df = pd.DataFrame({
            'Symbol': ['AAPL'],
            'Security': ['Apple Inc.']
        })
        nasdaq_df = pd.DataFrame({
            'Ticker': ['GOOGL'],
            'Company': ['Alphabet Inc.']
        })
        
        mock_read_html.side_effect = [
            [sp500_df],
            [None, None, None, None, nasdaq_df]
        ]
        
        result = get_all_tickers()
        
        # Check that ETFs are included
        self.assertIn('SPY', result['Symbol'].values)
        self.assertIn('QQQ', result['Symbol'].values)


if __name__ == '__main__':
    unittest.main()
