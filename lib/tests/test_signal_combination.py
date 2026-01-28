"""
Tests for the signal combination optimization module.
"""

import unittest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.signal_combo_optimisation import generate_ordered_combinations, test_combination, process_chunk

class TestSignalCombination(unittest.TestCase):

    def setUp(self):
        self.df = pd.DataFrame({
            'Close': [100, 101, 102, 103, 104],
            'High': [105, 106, 107, 108, 109],
            'Low': [95, 96, 97, 98, 99],
        })
        self.initial_capital = 10000

    def test_generate_ordered_combinations(self):
        buy_signals = ('Signal1', 'Signal2')
        sell_signals = ('Signal3', 'Signal4')
        result = generate_ordered_combinations(buy_signals, sell_signals, max_signals=2)
        expected = [
            (('Signal1',), ('Signal3',)),
            (('Signal1',), ('Signal4',)),
            (('Signal2',), ('Signal3',)),
            (('Signal2',), ('Signal4',)),
            (('Signal1', 'Signal2'), ('Signal3', 'Signal4')),
        ]
        self.assertEqual(result, expected)

    @patch('lib.signal_combo_optimisation.calculate_max_drawdown')
    @patch('lib.signal_combo_optimisation.calculate_sharpe_ratio')
    @patch('lib.signal_combo_optimisation.calculate_win_rate')
    @patch('lib.signal_combo_optimisation.calculate_profit_factor')
    @patch('lib.signal_combo_optimisation.calculate_average_trade_duration')
    @patch('lib.signal_combo_optimisation.run_backtest')
    def test_test_combination(self, mock_run_backtest, mock_avg_duration, mock_profit_factor, mock_win_rate, mock_sharpe, mock_drawdown):
        mock_drawdown.return_value = 0.1
        mock_sharpe.return_value = 1.5
        mock_win_rate.return_value = 0.6
        mock_profit_factor.return_value = 1.2
        mock_avg_duration.return_value = 3

        mock_run_backtest.return_value = pd.DataFrame({
            'Portfolio_Value': [10000, 10100, 10200],
            'Cumulative_Returns': [1.0, 1.01, 1.02],
            'Strategy_Returns': [0, 0.01, 0.01],
            'Signal1': [1, 0, 1],
            'Signal2': [0, 1, 0]
        })

        params = {
            'initial_capital': self.initial_capital,
            'buy_combo': ('Signal1',),
            'sell_combo': ('Signal2',)
        }
        result = test_combination(self.df, params)

        self.assertEqual(result['Buy_Signals'], "('Signal1',)")
        self.assertEqual(result['Sell_Signals'], "('Signal2',)")
        self.assertEqual(result['Buy_Signals_Count'], 2)
        self.assertEqual(result['Sell_Signals_Count'], 1)
        self.assertEqual(result['Final_Portfolio_Value'], 10200)
        self.assertAlmostEqual(result['Total_Return'], 0.02)
        self.assertAlmostEqual(result['Annual_Return'], 1.02 ** (252 / 3) - 1)
        self.assertEqual(result['Max_Drawdown'], 0.1)
        self.assertEqual(result['Sharpe_Ratio'], 1.5)
        self.assertEqual(result['Win_Rate'], 0.6)
        self.assertEqual(result['Profit_Factor'], 1.2)
        self.assertEqual(result['Average_Trade_Duration'], 3)

    def test_process_chunk(self):
        chunk = [(('Signal1',), ('Signal2',)), (('Signal2',), ('Signal1',))]
        
        with patch('lib.signal_combo_optimisation.test_combination') as mock_test:
            mock_test.side_effect = [
                pd.Series({'Buy_Signals': ('Signal1',), 'Sell_Signals': ('Signal2',), 'Final_Portfolio_Value': 11000}),
                pd.Series({'Buy_Signals': ('Signal2',), 'Sell_Signals': ('Signal1',), 'Final_Portfolio_Value': 10500})
            ]
            
            params = {'initial_capital': self.initial_capital}
            result = process_chunk(chunk, self.df, params)
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
        self.assertEqual(result.iloc[0]['Final_Portfolio_Value'], 11000)
        self.assertEqual(result.iloc[1]['Final_Portfolio_Value'], 10500)

if __name__ == '__main__':
    unittest.main()
