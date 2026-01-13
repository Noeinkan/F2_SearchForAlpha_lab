import unittest
import pandas as pd
import numpy as np
from unittest.mock import patch, MagicMock
from SearchForAlpha_lab.lib.signal_combo_optimisation import create_combinations, test_combination, process_chunk, filter_results
from dask.distributed import Client

class TestSignalCombination(unittest.TestCase):

    def setUp(self):
        self.df = pd.DataFrame({
            'Close': [100, 101, 102, 103, 104],
            'High': [105, 106, 107, 108, 109],
            'Low': [95, 96, 97, 98, 99],
        })
        self.initial_capital = 10000
        self.percent = 0.01
        self.delay = 1
        self.min_trade_value = 100
        self.max_trade_value = 1000
        self.round_down = True
        self.percentage_of_portfolio = MagicMock()
        self.backtest = MagicMock()

    def test_create_combinations_buy(self):
        signals = ['Signal1', 'Signal2']
        result = create_combinations(signals, combination_type='buy')
        expected = [(('Signal1',), ()), (('Signal2',), ()), (('Signal1', 'Signal2'), ())]
        self.assertEqual(result, expected)

    def test_create_combinations_sell(self):
        signals = ['Signal1', 'Signal2']
        result = create_combinations(signals, combination_type='sell')
        expected = [((), ('Signal1',)), ((), ('Signal2',)), ((), ('Signal1', 'Signal2'))]
        self.assertEqual(result, expected)

    def test_create_combinations_both(self):
        signals = ['Signal1', 'Signal2']
        result = create_combinations(signals, combination_type='both')
        self.assertEqual(len(result), 9)  # 3 buy * 3 sell combinations

    def test_create_combinations_invalid_type(self):
        signals = ['Signal1', 'Signal2']
        with self.assertRaises(ValueError):
            create_combinations(signals, combination_type='invalid')

    @patch('lib.signal_combination.calculate_max_drawdown')
    @patch('lib.signal_combination.calculate_sharpe_ratio')
    @patch('lib.signal_combination.calculate_win_rate')
    @patch('lib.signal_combination.calculate_profit_factor')
    @patch('lib.signal_combination.calculate_average_trade_duration')
    def test_test_combination(self, mock_avg_duration, mock_profit_factor, mock_win_rate, mock_sharpe, mock_drawdown):
        mock_drawdown.return_value = 0.1
        mock_sharpe.return_value = 1.5
        mock_win_rate.return_value = 0.6
        mock_profit_factor.return_value = 1.2
        mock_avg_duration.return_value = 3

        self.backtest.return_value = pd.DataFrame({
            'Portfolio_Value': [10000, 10100, 10200],
            'Cumulative_Returns': [1.0, 1.01, 1.02],
            'Strategy_Returns': [0, 0.01, 0.01],
            'Signal1': [1, 0, 1],
            'Signal2': [0, 1, 0]
        })

        result = test_combination(
            self.df, self.initial_capital, ('Signal1',), ('Signal2',),
            self.percent, self.delay, self.min_trade_value, self.max_trade_value,
            self.round_down, self.percentage_of_portfolio, self.backtest
        )

        self.assertEqual(result['Buy_Signals'], ('Signal1',))
        self.assertEqual(result['Sell_Signals'], ('Signal2',))
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
        
        with patch('lib.signal_combination.test_combination') as mock_test:
            mock_test.side_effect = [
                pd.Series({'Buy_Signals': ('Signal1',), 'Sell_Signals': ('Signal2',), 'Final_Portfolio_Value': 11000}),
                pd.Series({'Buy_Signals': ('Signal2',), 'Sell_Signals': ('Signal1',), 'Final_Portfolio_Value': 10500})
            ]
            
            result = process_chunk(
                chunk, self.df, self.initial_capital, self.percent, self.delay,
                self.min_trade_value, self.max_trade_value, self.round_down,
                self.percentage_of_portfolio, self.backtest
            )
        
        self.assertIsInstance(result, pd.DataFrame)
        self.assertEqual(len(result), 2)
        self.assertEqual(result.iloc[0]['Final_Portfolio_Value'], 11000)
        self.assertEqual(result.iloc[1]['Final_Portfolio_Value'], 10500)

    def test_filter_results(self):
        df = pd.DataFrame({
            'Buy_Signals': ["['Signal1']", "[]", "['Signal2']"],
            'Sell_Signals': ["['Signal3']", "['Signal4']", "[]"]
        })

        result = filter_results(df, hide_zero_buy=True, hide_zero_sell=True)
        self.assertEqual(len(result), 1)
        self.assertEqual(result.iloc[0]['Buy_Signals'], "['Signal1']")
        self.assertEqual(result.iloc[0]['Sell_Signals'], "['Signal3']")

        result = filter_results(df, hide_zero_buy=True, hide_zero_sell=False)
        self.assertEqual(len(result), 2)

        result = filter_results(df, hide_zero_buy=False, hide_zero_sell=True)
        self.assertEqual(len(result), 2)

        result = filter_results(df, hide_zero_buy=False, hide_zero_sell=False)
        self.assertEqual(len(result), 3)

if __name__ == '__main__':
    unittest.main()
