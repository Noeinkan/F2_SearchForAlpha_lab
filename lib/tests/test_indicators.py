import unittest
import pandas as pd
import numpy as np
from lib.signals.indicators import generate_signals
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import pandas as pd
import numpy as np
from lib.signals.indicators import generate_signals
from unittest.mock import patch, MagicMock

class TestGenerateSignals(unittest.TestCase):

    def setUp(self):
        self.df = pd.DataFrame({
            'Close': [100, 101, 102, 103, 104],
            'High': [105, 106, 107, 108, 109],
            'Low': [95, 96, 97, 98, 99],
        })

    @patch('lib.indicators.BB_TradingStrategy')
    @patch('lib.indicators.MACD_TradingStrategy')
    @patch('lib.indicators.RSI_TradingStrategy')
    @patch('lib.indicators.CCI_TradingStrategy')
    def test_generate_signals_calls_all_strategies(self, mock_cci, mock_rsi, mock_macd, mock_bb):
        generate_signals(self.df)
        
        mock_bb.return_value.BB_generate_signals.assert_called_once()
        mock_macd.return_value.MACD_generate_signals.assert_called_once()
        mock_rsi.return_value.RSI_generate_signals.assert_called_once()
        mock_cci.return_value.CCI_generate_signals.assert_called_once()

    def test_generate_signals_returns_dataframe(self):
        result = generate_signals(self.df)
        self.assertIsInstance(result, pd.DataFrame)

    def test_generate_signals_preserves_original_columns(self):
        original_columns = self.df.columns.tolist()
        result = generate_signals(self.df)
        for col in original_columns:
            self.assertIn(col, result.columns)

    def test_generate_signals_adds_new_columns(self):
        with patch('lib.indicators.BB_TradingStrategy') as mock_bb:
            mock_bb.return_value.BB_generate_signals.side_effect = lambda df: df.assign(BB_Signal=1)
            
            result = generate_signals(self.df)
            self.assertIn('BB_Signal', result.columns)

    def test_generate_signals_does_not_modify_input_dataframe(self):
        original_df = self.df.copy()
        generate_signals(self.df)
        pd.testing.assert_frame_equal(self.df, original_df)

    def test_generate_signals_handles_empty_dataframe(self):
        empty_df = pd.DataFrame()
        result = generate_signals(empty_df)
        self.assertTrue(result.empty)

    def test_generate_signals_with_nan_values(self):
        df_with_nan = self.df.copy()
        df_with_nan.loc[2, 'Close'] = np.nan
        result = generate_signals(df_with_nan)
        self.assertFalse(result.isnull().values.any())
