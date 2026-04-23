Run a quick backtest for a given ticker and date range.

Usage: /backtest [TICKER] [START_DATE] [END_DATE] [STRATEGY_MODE]

Examples:
- /backtest SPY 2020-01-01 2024-01-01
- /backtest AAPL 2022-01-01 2024-01-01 accumulation
- /backtest TSLA 2021-01-01 2023-01-01 trend_following

Steps to follow:
1. If no ticker provided, ask the user for one.
2. Fetch data using `lib/data_processing.fetch_data(ticker, start, end)`.
3. Add all indicators with `lib/signals/indicators.add_indicators(df)`.
4. Generate signals with `lib/signals/indicators.generate_signals(df)`.
5. Run `lib/strategy.backtest()` with sensible defaults:
   - initial_capital=100_000
   - position_sizing_strategy="percentage_of_portfolio"
   - position_sizing_params={"percentage": 0.1}
   - All available buy/sell signals (use all_signals from generate_signals)
   - strategy_mode from argument (default: "trading")
6. Print a clean summary of results: total_return, sharpe_ratio, max_drawdown, win_rate, num_trades.

Write a self-contained Python script to `results/quick_backtest_{TICKER}.py` and execute it.
