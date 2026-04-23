# SearchForAlpha Lab 📈

A Python-based algorithmic trading research workspace for data fetching, signal generation, backtesting, and strategy optimization. It includes a Dash dashboard for interactive analysis and a modular signal system for technical indicators.

## 🎯 Features

- **Signal generation**: Bollinger Bands, RSI, MACD, CCI, SMA, EMA plus ADX/ATR/OBV indicator support.
- **Backtesting engine**: Trading, Accumulation (DCA), and Rebalancing modes with position sizing and trailing stops.
- **Optimization tools**: Parameter sweeps, signal-combination testing, and indicator weight optimization.
- **Interactive dashboard**: Plotly charts, signal overlays, and data tables with configurable views.
- **Performance metrics**: Total return, Sharpe, max drawdown, win rate, profit factor, and trade duration.

## 📁 Project Structure

```
F2_SearchForAlpha_lab/
├── main.py                        # Entry point (launches Dash app)
├── config/
│   └── strategy_config.yaml        # Strategy and indicator defaults
├── lib/
│   ├── data_processing.py          # Data fetching + metrics
│   ├── strategy.py                 # Backtesting engine
│   ├── visualization.py            # Matplotlib chart utilities
│   ├── utils.py                    # Input helpers and Excel export
│   ├── params_optimization.py      # Parameter optimization
│   ├── signal_combo_optimisation.py# Signal combination testing
│   ├── weights_optimization.py     # Indicator weight optimization
│   ├── config_loader.py            # YAML config loader
│   ├── dash/                       # Dash UI and callbacks
│   ├── signals/                    # Indicator strategies
│   ├── tests/                      # Pytest suite
│   └── WIP/                        # Experimental ideas
├── export/                         # Exported Excel results
├── results/                        # Parquet outputs
└── Signal_Combination.pbix         # Power BI report
```

## 🚀 Getting Started

### Prerequisites

- Python 3.11+ (raised from 3.8 because `ib_async` requires 3.10+)
- pip or conda package manager

### Install dependencies

```bash
pip install -e ".[dev]"
```

The editable install pulls every dependency declared in `pyproject.toml` and
exposes the `sfa` console script (see CLI section below).

## ▶️ Run the Dashboard

```bash
python main.py
```

By default `main.py` enables a development mode reload. To disable:

```bash
set DASH_DEV=0
python main.py
```

## 📊 Programmatic Usage

### Running a Backtest

```python
from lib.data_processing import fetch_data
from lib.signals.indicators import add_indicators, generate_signals
from lib.strategy import backtest

df = fetch_data("SPY", "2020-01-01", "2024-01-01")
df = add_indicators(df)
df, all_signals = generate_signals(df)

buy_indicators = ["RSI_Oversold_Buy", "BB_Lower_Buy"]
sell_indicators = ["RSI_Overbought_Sell", "BB_Upper_Sell"]

results = backtest(
    df=df,
    initial_capital=100000,
    position_sizing_strategy="percentage_of_portfolio",
    position_sizing_params={"percentage": 0.1},
    buy_indicators=buy_indicators,
    sell_indicators=sell_indicators,
    trailing_stop_loss=0.05,
)
```

### Customizing Signal Strategies

```python
from lib.signals.signals_RSI import RSI_TradingStrategy

rsi_strategy = RSI_TradingStrategy(config={
    "rsi": {"window": 14},
    "overbought_oversold": {"upper_threshold": 70, "lower_threshold": 30},
})

df = rsi_strategy.RSI_generate_signals(df)
```

### Signal Combination Optimization

```python
from lib.signal_combo_optimisation import test_all_combinations

results, buy_combo, sell_combo, best_value, output_file = test_all_combinations(
    df=df,
    initial_capital=100000,
    combination_type="Buy_&_Sell",
    max_combinations=500,
    max_signals=5,
)
```

## 📈 Strategy Modes

| Mode | Description | Sell Signals Required? |
|------|-------------|------------------------|
| **Trading** | Traditional buy/sell cycles with position scaling | Yes |
| **Accumulation (DCA)** | Fixed dollar amount per buy signal, hold until end | No |
| **Rebalancing** | Percentage-based partial buys/sells | No (optional) |
| **Swing Trading** | Multi-day holds targeting short-to-medium trends | Yes |
| **Position Trading** | Multi-week/month holds based on long-term trends | Yes |
| **Trend Following** | Stay in trend until exit signal or reversal | Yes |

```python
from lib.strategy import run_backtest

results = run_backtest(
    df=df,
    initial_capital=100000,
    buy_indicators=["RSI_Oversold_Buy"],
    sell_indicators=[],
    strategy_mode="accumulation",
    amount_per_buy=1000,
)
```

## 🤖 CLI (`sfa`)

The `sfa` console script is the only surface an external agent or operator
should touch. Every command supports `--json` for machine readable output.
For full operating instructions for an external agent runtime see
[AGENTS.md](AGENTS.md).

```bash
sfa list --json
sfa backtest --name mean_reversion_rsi_bb --from 2024-01-01 --to 2024-06-30 --json
sfa optimise --name mean_reversion_rsi_bb --trials 100 --metric sortino --from 2023-01-01 --to 2024-12-31 --json
sfa trials --name mean_reversion_rsi_bb --top 10 --json
sfa walkforward --name mean_reversion_rsi_bb --params <trial_id> --json
sfa promote --name mean_reversion_rsi_bb --trial <trial_id> --json
sfa run --name mean_reversion_rsi_bb --mode paper
sfa status --json
sfa kill --name mean_reversion_rsi_bb
```

`--mode live` is always refused. Use `--mode paper` against an Interactive
Brokers Gateway running on the loopback (port 4002 by default; override in
`config/agent.yaml`). Promotion is gated: a strategy's `live_params` only
update if a recent walk forward record passes thresholds (OOS Sharpe,
degradation, age) declared in `config/agent.yaml`.

## 🧪 Testing

```bash
python -m pytest lib/tests/
```

## 📝 Notes

- Data is fetched from Yahoo Finance via `yfinance`.
- Results are saved in `results/` (Parquet) and `export/` (Excel).
- Default strategy settings live in `config/strategy_config.yaml`.

## ⚠️ Disclaimer

This software is for educational and research purposes only and is not financial advice. Trading involves risk and past performance does not guarantee future results.

## 📄 License

Provided as-is for educational purposes.

## 🤝 Contributing

Contributions are welcome. Please open issues or pull requests for fixes and improvements.
