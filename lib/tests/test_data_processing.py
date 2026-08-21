"""
Tests for the data processing module.
"""

import unittest
import pandas as pd
from unittest.mock import patch

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

import lib.data_processing as dp
from lib.data_processing import (
    fetch_data, get_all_tickers,
    DataFetchError
)


class TestFetchData(unittest.TestCase):
    """Tests for the fetch_data function."""

    @patch('lib.data_processing.yf.Ticker')
    def test_fetch_data_returns_dataframe(self, mock_ticker):
        """Test that fetch_data returns a DataFrame."""
        # Mock the yfinance response. Note this is the real column set: with
        # actions=True (yfinance's default) two corporate-action columns ride
        # along. The old fixture had only the five OHLCV columns, which is why
        # those columns leaking into the pipeline went unnoticed.
        mock_history = pd.DataFrame({
            'Open': [100, 101],
            'High': [102, 103],
            'Low': [98, 99],
            'Close': [101, 102],
            'Volume': [1000000, 1100000],
            'Dividends': [0.0, 0.22],
            'Stock Splits': [0.0, 0.0],
        }, index=pd.to_datetime(['2020-01-01', '2020-01-02']))

        mock_ticker.return_value.history.return_value = mock_history

        result = fetch_data('AAPL', '2020-01-01', '2020-01-03')

        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result.index, pd.DatetimeIndex)

    @patch('lib.data_processing.yf.Ticker')
    def test_fetch_data_requests_explicit_adjustment(self, mock_ticker):
        """Adjustment must be stated, not inherited from yfinance defaults."""
        mock_history = pd.DataFrame({
            'Open': [100.0], 'High': [102.0], 'Low': [98.0],
            'Close': [101.0], 'Volume': [1000000],
        }, index=pd.to_datetime(['2020-01-02']))
        mock_ticker.return_value.history.return_value = mock_history

        fetch_data('AAPL', '2020-01-01', '2020-01-03')

        kwargs = mock_ticker.return_value.history.call_args.kwargs
        self.assertTrue(kwargs['auto_adjust'])
        self.assertFalse(kwargs['actions'])

    @patch('lib.data_processing.yf.Ticker')
    def test_fetch_data_drops_corporate_action_columns(self, mock_ticker):
        """Dividends / Stock Splits must not reach the indicator pipeline."""
        mock_history = pd.DataFrame({
            'Open': [100, 101],
            'High': [102, 103],
            'Low': [98, 99],
            'Close': [101, 102],
            'Volume': [1000000, 1100000],
            'Dividends': [0.0, 0.22],
            'Stock Splits': [0.0, 4.0],
        }, index=pd.to_datetime(['2020-01-01', '2020-01-02']))
        mock_ticker.return_value.history.return_value = mock_history

        result = fetch_data('AAPL', '2020-01-01', '2020-01-03')

        # actions=False is what normally prevents these; assert on the output
        # so a vendor that ignores the flag is still caught.
        for column in ('Dividends', 'Stock Splits'):
            self.assertNotIn(column, result.columns)

    @patch('lib.data_processing.yf.Ticker')
    def test_fetch_data_tags_its_source(self, mock_ticker):
        mock_history = pd.DataFrame({
            'Open': [100.0], 'High': [102.0], 'Low': [98.0],
            'Close': [101.0], 'Volume': [1000000],
        }, index=pd.to_datetime(['2020-01-02']))
        mock_ticker.return_value.history.return_value = mock_history

        result = fetch_data('AAPL', '2020-01-01', '2020-01-03')
        self.assertEqual(result.attrs['source'], 'yahoo')

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


# The performance-metric tests that used to live here moved to
# lib/tests/test_metrics.py along with the functions themselves, which now
# have one implementation each in lib/metrics/.


class TestGetAllTickers(unittest.TestCase):
    """Tests for get_all_tickers function."""

    def setUp(self):
        dp._TICKER_CACHE = None
        dp._TICKER_CACHE_TIME = None

    @patch('lib.data_processing._get_default_tickers')
    @patch('lib.data_processing._fetch_russell2000_from_wikipedia')
    @patch('lib.data_processing._fetch_nasdaq100_from_wikipedia')
    @patch('lib.data_processing._fetch_sp500_from_github')
    def test_get_all_tickers_returns_dataframe(
        self,
        mock_sp500,
        mock_nasdaq100,
        mock_russell2000,
        mock_default_tickers,
    ):
        """Test that get_all_tickers returns a DataFrame."""
        mock_sp500.return_value = pd.DataFrame({
            'Symbol': ['AAPL', 'MSFT'],
            'Security': ['Apple Inc.', 'Microsoft Corp.'],
            'Index': ['S&P 500', 'S&P 500'],
            'Exchange': ['NASDAQ', 'NASDAQ'],
        })
        mock_nasdaq100.return_value = pd.DataFrame({
            'Symbol': ['GOOGL'],
            'Security': ['Alphabet Inc.'],
            'Index': ['NASDAQ-100'],
            'Exchange': ['NASDAQ'],
        })
        mock_russell2000.return_value = pd.DataFrame({
            'Symbol': ['RKLB'],
            'Security': ['Rocket Lab Corporation'],
            'Index': ['Russell 2000'],
            'Exchange': ['NASDAQ'],
        })
        mock_default_tickers.return_value = pd.DataFrame(
            columns=['Symbol', 'Security', 'Index', 'Exchange']
        )

        result = get_all_tickers()

        self.assertIsInstance(result, pd.DataFrame)
        self.assertIn('Symbol', result.columns)
        self.assertIn('Security', result.columns)
        self.assertIn('RKLB', result['Symbol'].values)

    @patch('lib.data_processing._get_default_tickers')
    @patch('lib.data_processing._fetch_russell2000_from_wikipedia', return_value=None)
    @patch('lib.data_processing._fetch_nasdaq100_from_wikipedia', return_value=None)
    @patch('lib.data_processing._fetch_sp500_from_github')
    def test_get_all_tickers_includes_etfs(
        self,
        mock_sp500,
        mock_nasdaq100,
        mock_russell2000,
        mock_default_tickers,
    ):
        """Test that ETFs from local config are included."""
        mock_sp500.return_value = pd.DataFrame({
            'Symbol': ['AAPL'],
            'Security': ['Apple Inc.'],
            'Index': ['S&P 500'],
            'Exchange': ['NASDAQ'],
        })
        mock_default_tickers.return_value = pd.DataFrame({
            'Symbol': ['SPY', 'QQQ'],
            'Security': ['SPDR S&P 500 ETF', 'Invesco QQQ Trust'],
            'Index': ['Index ETF', 'Index ETF'],
            'Exchange': ['NYSE', 'NASDAQ'],
        })

        result = get_all_tickers()

        self.assertIn('SPY', result['Symbol'].values)
        self.assertIn('QQQ', result['Symbol'].values)


if __name__ == '__main__':
    unittest.main()
