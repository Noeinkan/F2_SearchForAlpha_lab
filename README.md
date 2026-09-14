# SearchForAlpha Lab 📈

A Python-based algorithmic trading research workspace for data fetching, signal generation, backtesting, and strategy optimization. It includes a Dash dashboard for interactive analysis and a modular signal system for technical indicators.

## 🎯 Features

- **Signal generation**: Bollinger Bands, RSI, MACD, CCI, Stochastic, SMA, EMA, VWAP plus ADX/ATR/OBV regime filters and regime-gated strategy variants.
- **Backtesting engine**: Trading, Accumulation (DCA), and Rebalancing modes with position sizing and trailing stops.
- **Optimization tools**: Parameter sweeps, signal-combination testing, and indicator weight optimization.
- **Interactive dashboard**: TradingView Lightweight Charts, signal overlays, symbol search with watchlists, and data tables with configurable views.
- **Performance metrics**: Total return, Sharpe, max drawdown, win rate, profit factor, and trade duration.

What is built and what is still open: [ROADMAP.md](ROADMAP.md).

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
│   ├── config_loader.py            # YAML config loader
│   ├── dash/                       # Dash UI and callbacks
│   ├── signals/                    # Indicator strategies
│   └── tests/                      # Pytest suite
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
- Find symbols with the search modal (`Ctrl + /` or bare `/`): ~13k tickers
  from `config/tickers_universe.csv`, filterable by sector and asset class,
  with named watchlists persisted to `config/watchlists.json`.
- Toggle indicator overlays (RSI, MACD, BB, SMA, EMA, CCI, STOCH, VWAP, ADX, ATR,
  OBV) and tune their windows interactively.
- Pick buy and sell signal columns, run a backtest, and view the equity
  curve, trade markers, and metric cards. The **Execution Type** explainer
  shows how each strategy mode sizes an order, using the real engine on a
  fixed tape.
- Save and reload UI presets via `config/ui_presets.json`.
- Inspect the options **Flow Scanner** at `/flow/<ticker>`. RESCAN NOW fetches
  a fresh chain; while the dashboard runs, reports for the tickers in
  `watchlist.txt` and any ticker you have scanned also refresh on their own
  every 15 minutes of US market hours. Set `SFA_FLOW_REFRESH_MINUTES` to change
  the interval, or `0` to turn it off. The scanner also runs standalone:
  `python scripts/flow_scanner.py <ticker>`.

Three themes ship in `THEMES` in `lib/dash/dash_config.py`: the default
`bloomberg` (dark), a CVD-safe (color-vision-deficiency) palette, and `light`.
The header button cycles through them in that order.

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
  reconnect:
    initial_delay_seconds: 2    # retry after 2s, 4s, 8s ... once the connection drops
    max_delay_seconds: 30
  daily_restart:
    time: "23:45"               # IB Gateway's Auto restart time, this computer's local time
    window_minutes: 15          # a drop inside this window does not stop the runner
runner:
  heartbeat_seconds: 5          # connection, guards and kill requests checked this often
  flatten_timeout_seconds: 30   # how long sfa kill --flatten waits for the closing fill
guards:
  max_daily_loss_pct: 0.02      # stop if daily realised PnL drops 2%
  max_position_pct: 0.25        # stop if any position exceeds 25% of equity
  max_disconnect_seconds: 60    # stop if Gateway is unreachable for 60s
  max_clock_drift_seconds: 5    # stop if local vs IB clock drift exceeds 5s
```

**Match `daily_restart.time` to your Gateway.** In IB Gateway open
*Configure → Settings → Lock and Exit* and copy the *Auto restart* time.
If the two differ, the nightly restart lasts longer than
`max_disconnect_seconds`, trips `broker_disconnected`, and stops the runner.

### Run, observe, kill

```bash
# Terminal 1: start the runner (blocks until killed)
sfa run --name mean_reversion_rsi_bb --mode paper

# Terminal 2: snapshot equity, positions, and guard states
sfa status
sfa status --json                                 # for piping / agents

# Stop a running runner cleanly
sfa kill --name mean_reversion_rsi_bb

# Stop it and close its position with a market order first
sfa kill --name mean_reversion_rsi_bb --flatten
```

The runner writes a PID file to `state/running/<name>.pid` and persists
every fill to the `sfa_fills` table in `state/optuna.db`. Each bar, and
every `heartbeat_seconds` even when no bars arrive, updates
`sfa_runner_state` with the latest equity, positions, connection state and
the result of every guard. If any guard trips, the runner cancels open
orders for that symbol, disconnects, sends an alert (below), and exits.

When the connection drops, the runner keeps retrying and re-subscribes to
bars once it is back, so it survives the Gateway's nightly restart. It
still stops if the outage lasts longer than `max_disconnect_seconds` outside
the restart window. That is what happens on the weekly re-login, when
Gateway waits for you to sign in again.

`sfa kill` does not signal the process. It leaves a stop request that the
runner picks up at its next heartbeat. The runner then cancels its orders,
closes the position when `--flatten` is given, disconnects, and reports
what it did. A runner that does not answer is terminated instead. The
output then says `"graceful": false`, and the command exits with code 3 if
`--flatten` was asked, because nothing was closed. `--flatten` closes only
the strategy's own ticker; the order-size caps do not block it.

### Order types

The runner uses the order model the strategy was backtested with. It reads
the same keys from the strategy's `live_params` in
`config/strategy_config.yaml`, which is where `sfa promote` writes them:

```yaml
live_params:
  rsi_window: 14
  order_type: limit          # market (default), limit, stop, stop_limit
  limit_offset_pct: 0.002    # a fraction: 0.002 rests a buy limit 0.2% under the signal bar's close
  time_in_force: day         # gtc (default), day, ioc
  order_expiry_bars: 12      # cancel after 12 bars unfilled; 0 = never
```

A market order is sent and waited for. Any other type is placed at IB and
left working while the runner carries on. `sfa status` lists it under
`working_orders`. Each later bar either finds it filled or counts one more
bar against it. `ioc` gives it exactly one bar, as in the backtest. A new
signal on the same side cancels the old order and places a fresh one.
Every order's end is recorded in `sfa_fills`: `filled`, `partially_filled`,
`cancelled` or `rejected`. A rejection also sends an alert.

**A bar here is IB's 5-second bar**, not the daily bar most strategies
are researched on. `order_expiry_bars: 12` therefore means one minute
live. ROADMAP 8.15 tracks this and the other differences between paper
and research.

`sfa run` refuses to start when `live_params` asks for something the
runner does not do:

- exits: `trailing_stop_loss`, `take_profit`, `use_brackets`, `trailing_stop_orders`;
- sizing: `position_size_pct`, `position_scaling`, `amount_per_buy`;
- signal gating: `signal_logic: and`, `signal_window`, `min_holding_period`,
  `cooldown_bars`.

The error (`unsupported_live_params`) names each key. Remove those keys or
set them to off (`0`), then run again.

### Alerts on your phone

Set `SFA_ALERT_WEBHOOK` and the runner posts to it when a guard trips,
when the broker refuses an order, and when the runner crashes. Without it,
these events are only logged. The quickest setup uses
[ntfy](https://ntfy.sh), which is free and needs no account:

1. On your phone, install the **ntfy** app, tap **+**, and subscribe to a
   topic with a hard-to-guess name, e.g. `sfa-alerts-7f3k9q`. Anyone who
   knows the name can read the topic, so do not use a guessable one.
2. On the computer that runs `sfa run`, set the variable in the terminal
   you will start the runner from:
   ```powershell
   $env:SFA_ALERT_WEBHOOK = "https://ntfy.sh/sfa-alerts-7f3k9q"
   ```
   To keep it for every new terminal, run
   `setx SFA_ALERT_WEBHOOK "https://ntfy.sh/sfa-alerts-7f3k9q"` once, then
   open a new terminal. `setx` does not change the one you are in.
3. Check that it reaches the phone before relying on it:
   ```powershell
   Invoke-RestMethod -Method Post -Uri $env:SFA_ALERT_WEBHOOK -Body "sfa test"
   ```
   If no notification arrives, check the topic name in the app matches
   the URL exactly.

Slack and Discord webhooks work too. Paste the URL from Slack's
*Incoming Webhooks* app, or from Discord's *Server Settings → Integrations
→ Webhooks → New Webhook → Copy Webhook URL*. The payload carries both
fields those services display (`text` and `content`). ntfy.sh URLs get a plain-text
message instead; set `SFA_ALERT_FORMAT=text` for a self-hosted ntfy.

### Trouble shooting

- `unknown_strategy`: run `sfa list` to see what bundles exist; names must
  match exactly.
- `live_mode_disabled`: you passed `--mode live`. Use `--mode paper`.
- `unsupported_live_params`: see *Order types* above; the `keys` field
  lists what to remove.
- An order sits in `working_orders` far longer than expected: check its
  `time_in_force`. A `gtc` limit far from the market can wait for days.
  `sfa kill` cancels it.
- Connection hangs: confirm Gateway is on port 4002, signed in (not
  logged out for daily reset), and that no other client is using
  `client_id: 7`.
- `pid_mismatch` from `sfa kill`: the PID in `state/running/<name>.pid`
  belongs to a process that is not this runner, so nothing was terminated.
  Check the process yourself before deleting the file.
- Want to force a stuck runner off without IB calls: delete the
  `state/running/<name>.pid` file and the matching row in
  `sfa_runner_state`.

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

Three engine modes (`strategy_mode`), sized in `size_buy` / `size_sell` (`lib/engine/steps.py`):

| Mode | Description | Sell Signals Required? |
|------|-------------|------------------------|
| **Trading** | Kelly size × `position_scaling`; scaling ramps each order and stacks, with no target cap | Yes |
| **Accumulation (DCA)** | Fixed `amount_per_buy`; sell signals are discarded and the trailing stop is pinned to `inf` | No |
| **Rebalancing** | `position_size_pct` of **portfolio value** on both sides (not of cash or units held) | No (optional) |

Swing / Position / Trend Following are dashboard quick-presets
(`strategy-preset` in `right_panel.py`) that bundle mode plus parameters —
they are not separate engine modes.

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
