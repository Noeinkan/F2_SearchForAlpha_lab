Run signal combination optimization for a ticker to find the best buy/sell signal combination.

Usage: /optimize [TICKER] [START_DATE] [END_DATE] [METRIC]

Examples:
- /optimize SPY 2020-01-01 2024-01-01
- /optimize AAPL 2022-01-01 2024-01-01 sharpe_ratio
- /optimize QQQ 2019-01-01 2024-01-01 total_return

Available metrics: total_return (default), sharpe_ratio, profit_factor, win_rate

Steps to follow:
1. Fetch and prepare data (fetch_data → add_indicators → generate_signals).
2. Run `lib/signal_combo_optimisation.test_all_combinations()` with:
   - combination_type="Buy_&_Sell"
   - max_combinations=200 (keep it fast unless user says otherwise)
   - optimise_for=METRIC
3. Display top 5 combinations in a markdown table with columns: buy_signals, sell_signals, metric_value.
4. Show the best combination's full backtest stats.
5. Save full results to `results/optimization_{TICKER}_{DATE}.xlsx`.
