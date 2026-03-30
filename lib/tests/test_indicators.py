"""
Tests for the indicators module.
"""

import unittest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.signals.indicators import generate_signals, add_indicators


class TestGenerateSignals(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        # Create sample price data with enough rows for indicator calculations
        np.random.seed(42)
        n_rows = 250
        dates = pd.date_range(start='2020-01-01', periods=n_rows, freq='D')
        base_price = 100
        
        # Generate realistic price data
        returns = np.random.randn(n_rows) * 0.02
        prices = base_price * np.exp(np.cumsum(returns))
        
        self.df = pd.DataFrame({
            'Close': prices,
            'High': prices * 1.02,
            'Low': prices * 0.98,
            'Open': prices * 1.001,
            'Volume': np.random.randint(1000000, 10000000, n_rows)
        }, index=dates)

    def test_generate_signals_returns_tuple(self):
        """Test that generate_signals returns a tuple of (DataFrame, list)."""
        df = add_indicators(self.df.copy())
        result = generate_signals(df)
        self.assertIsInstance(result, tuple)
        self.assertEqual(len(result), 2)
        self.assertIsInstance(result[0], pd.DataFrame)
        self.assertIsInstance(result[1], list)

    def test_generate_signals_preserves_original_columns(self):
        """Test that original columns are preserved."""
        df = add_indicators(self.df.copy())
        original_columns = df.columns.tolist()
        result_df, _ = generate_signals(df)
        for col in original_columns:
            self.assertIn(col, result_df.columns)

    def test_generate_signals_adds_signal_columns(self):
        """Test that signal columns are added."""
        df = add_indicators(self.df.copy())
        result_df, signal_headers = generate_signals(df)
        
        # Should have added some buy/sell signal columns
        buy_signals = [col for col in result_df.columns if 'buy' in col.lower()]
        sell_signals = [col for col in result_df.columns if 'sell' in col.lower()]
        
        self.assertGreater(len(buy_signals), 0, "Should have at least one buy signal")
        self.assertGreater(len(sell_signals), 0, "Should have at least one sell signal")

    def test_generate_signals_includes_vwap_columns(self):
        """Test that VWAP cross signal columns are generated."""
        df = add_indicators(self.df.copy())
        result_df, _ = generate_signals(df, {'vwap': {'window': 10}})

        self.assertIn('VWAP', result_df.columns)
        self.assertIn('VWAP_CrossAbove_Buy', result_df.columns)
        self.assertIn('VWAP_CrossBelow_Sell', result_df.columns)

    def test_generate_signals_handles_zero_volume_for_vwap(self):
        """Test VWAP generation remains stable with zero-volume rows."""
        df = add_indicators(self.df.copy())
        df['Volume'] = 0
        result_df, _ = generate_signals(df, {'vwap': {'window': 10}})

        self.assertIn('VWAP', result_df.columns)
        self.assertIn('VWAP_CrossAbove_Buy', result_df.columns)
        self.assertIn('VWAP_CrossBelow_Sell', result_df.columns)
        self.assertTrue(set(result_df['VWAP_CrossAbove_Buy'].dropna().unique()).issubset({0, 1}))
        self.assertTrue(set(result_df['VWAP_CrossBelow_Sell'].dropna().unique()).issubset({0, 1}))

    def test_add_indicators_adds_expected_columns(self):
        """Test that add_indicators adds ADX, ATR, and OBV."""
        result_df = add_indicators(self.df.copy())
        
        self.assertIn('ADX', result_df.columns)
        self.assertIn('ATR', result_df.columns)
        self.assertIn('OBV', result_df.columns)


class TestAddIndicators(unittest.TestCase):

    def setUp(self):
        """Set up test fixtures."""
        np.random.seed(42)
        n_rows = 50
        dates = pd.date_range(start='2020-01-01', periods=n_rows, freq='D')
        
        self.df = pd.DataFrame({
            'Close': np.random.uniform(95, 105, n_rows),
            'High': np.random.uniform(100, 110, n_rows),
            'Low': np.random.uniform(90, 100, n_rows),
            'Open': np.random.uniform(95, 105, n_rows),
            'Volume': np.random.randint(1000000, 10000000, n_rows)
        }, index=dates)

    def test_add_indicators_returns_dataframe(self):
        """Test that add_indicators returns a DataFrame."""
        result = add_indicators(self.df.copy())
        self.assertIsInstance(result, pd.DataFrame)

    def test_add_indicators_preserves_original_data(self):
        """Test that original columns are preserved."""
        original_columns = self.df.columns.tolist()
        result = add_indicators(self.df.copy())
        for col in original_columns:
            self.assertIn(col, result.columns)


if __name__ == '__main__':
    unittest.main()
