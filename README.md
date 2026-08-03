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

The Dash app is the interactive UI for browsing tickers, overlaying signals,
running ad hoc backtests, and inspecting trade logs. It runs entirely
locally and does not need IB Gateway.

```bash
python main.py
```

The app auto-opens your browser at the default ticker terminal
(`http://127.0.0.1:8050/ticker/TSLA`). Dev mode is on by default
(`DASH_DEV=1`): it serves debug error pages and CSS with `no-store`, so a
hard refresh is rarely needed after an asset edit.

Auto-restart on file edits (the Werkzeug reloader) is **opt-in** via
`DASH_RELOAD=1`; it is off by default because the reloader is unreliable on
Windows (the child process can silently exit the parent):

```bash
# Linux / macOS
DASH_RELOAD=1 python main.py

# Windows (PowerShell)
$env:DASH_RELOAD = "1"; python main.py
```

To disable dev mode entirely (faster startup, cached assets, plain error
pages) set `DASH_DEV=0`:

```bash
# Linux / macOS
DASH_DEV=0 python main.py

# Windows (cmd)
set DASH_DEV=0 && python main.py

# Windows (PowerShell)
$env:DASH_DEV = "0"; python main.py
```

What you can do from the UI:

- Pick a ticker and date range, fetch OHLCV from Yahoo, and chart it.
- Toggle indicator overlays (RSI, MACD, BB, SMA, EMA, CCI, VWAP) and tune
  their windows interactively.
- Pick buy and sell signal columns, run a backtest, and view the equity
  curve, trade markers, and metric cards.
- Save and reload UI presets via `config/ui_presets.json`.
- Inspect the options **Flow Scanner** at `/flow/<ticker>` (or the standalone
  `/flow_report.html`); regenerate the report with
  `python scripts/flow_scanner.py <ticker>`.

The default CVD-safe (color-vision-deficiency) theme keeps charts and signal
overlays readable; override it via the `theme` key in
`config/strategy_config.yaml`.

The dashboard does not place orders. For live (paper) execution use the
`sfa run` command described below.

## 🏦 Paper Trading via Interactive Brokers

`sfa run --mode paper` connects to an IB Gateway on the loopback,
subscribes to real time bars, and translates the strategy's signals into
market orders. `--mode live` is always refused, so you cannot accidentally
fire real money trades from this build.

### Prerequisites

1. Download **IB Gateway** (lighter than TWS) from the Interactive Brokers
   client portal and install it.
2. Create a **paper trading account** in your IB account portal if you do
   not already have one.
3. Launch IB Gateway, sign in with your **paper** credentials, and confirm
   the API socket is listening on port **4002** (paper). The live port is
   4001 and is intentionally never used by this build.
4. In Gateway's API settings, enable *Enable ActiveX and Socket Clients*
   and confirm `127.0.0.1` is in the list of trusted IPs.

### Configure

Defaults are in [config/agent.yaml](config/agent.yaml). Override host,
port, client id, guard thresholds, or promotion thresholds there:

```yaml
ib:
  host: 127.0.0.1
  port: 4002
  client_id: 7
guards:
  max_daily_loss_pct: 0.02      # stop if daily realised PnL drops 2%
  max_position_pct: 0.25        # stop if any position exceeds 25% of equity
  max_disconnect_seconds: 60    # stop if Gateway is unreachable for 60s
  max_clock_drift_seconds: 5    # stop if local vs IB clock drift exceeds 5s
```

### Run, observe, kill

```bash
# Terminal 1: start the runner (blocks until killed)
sfa run --name mean_reversion_rsi_bb --mode paper

# Terminal 2: snapshot equity, positions, and guard states
sfa status
sfa status --json                                 # for piping / agents

# Stop a running runner cleanly
sfa kill --name mean_reversion_rsi_bb
```

The runner writes a PID file to `state/running/<name>.pid` and persists
every fill to the `sfa_fills` table in `state/optuna.db`. Each bar updates
`sfa_runner_state` with the latest equity, positions, and the result of
every guard. If any guard trips, the runner cancels open orders for that
symbol, disconnects, and exits.

### Trouble shooting

- `unknown_strategy`: run `sfa list` to see what bundles exist; names must
  match exactly.
- `live_mode_disabled`: you passed `--mode live`. Use `--mode paper`.
- Connection hangs: confirm Gateway is on port 4002, signed in (not
  logged out for daily reset), and that no other client is using
  `client_id: 7`.
- Want to force a stuck runner off without IB calls: delete the
  `state/running/<name>.pid` file and the matching row in
  `sfa_runner_state`, or run `just clean-state`.

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
[AGENTS.md](AGENTS.md) and [docs/openclaw-research.md](docs/openclaw-research.md).

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
