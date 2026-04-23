# SearchForAlpha Lab — Claude Code Guide

## Project Overview

Python-based algorithmic trading research platform. Fetches OHLCV data from Yahoo Finance, generates technical indicator signals, backtests strategies, and visualises results in an interactive Dash web dashboard.

**Start the dashboard:** `python main.py`
**Run tests:** `python -m pytest lib/tests/`

---

## Architecture

```
main.py                         # Entry point — launches Dash app
config/
  strategy_config.yaml          # Default indicator parameters (SMA, EMA, RSI, BB, CCI, MACD, VWAP)
  ui_presets.json               # Saved UI presets
lib/
  data_processing.py            # Yahoo Finance fetch + performance metrics
  strategy.py                   # Core backtesting engine (6 strategy modes)
  visualization.py              # Matplotlib static charts
  utils.py                      # Input helpers, Excel export
  config_loader.py              # YAML config loader
  params_optimization.py        # Per-indicator parameter sweeps
  signal_combo_optimisation.py  # Exhaustive signal combination testing
  weights_optimization.py       # Indicator weight optimisation
  signals/
    base_strategy.py            # Abstract base for all indicator strategies
    indicators.py               # add_indicators() + generate_signals() aggregator
    signals_RSI.py              # RSI_TradingStrategy
    signals_BB.py               # BB_TradingStrategy
    signals_MACD.py             # MACD_TradingStrategy
    signals_EMA.py              # EMA_TradingStrategy
    signals_SMA.py              # SMA_TradingStrategy
    signals_CCI.py              # CCI_TradingStrategy
    signals_VWAP.py             # VWAP_TradingStrategy
  dash/
    integrated_dashboard.py     # Main Dash app (~86 KB) — layout + app init
    chart_builder.py            # Plotly chart factory + overlay registry
    callbacks/                  # 14 separate callback modules
  tests/                        # pytest suite
  WIP/                          # Experimental / in-progress modules
results/                        # Parquet outputs
export/                         # Excel exports
```

---

## Key Conventions

### Signal Naming
Buy signals end in `_Buy`, sell signals end in `_Sell` (e.g. `RSI_Oversold_Buy`, `BB_Upper_Sell`). The `generate_signals()` aggregator collects all columns matching these patterns.

### Adding a New Indicator Strategy
1. Create `lib/signals/signals_MYINDICATOR.py` inheriting from `BaseStrategy`.
2. Implement `generate_signals(df)` returning df with new `_Buy`/`_Sell` columns.
3. Register it in `lib/signals/indicators.py` inside `add_indicators()` and `generate_signals()`.
4. Add default params to `config/strategy_config.yaml`.

### Strategy Modes (`lib/strategy.py`)
| Mode | Key Parameter |
|------|--------------|
| `trading` | Traditional buy/sell cycles |
| `accumulation` | DCA — `amount_per_buy` |
| `rebalancing` | Partial buys/sells by % |
| `swing_trading` | Multi-day holds |
| `position_trading` | Multi-week/month holds |
| `trend_following` | Hold until reversal signal |

### Backtesting Entry Point
```python
from lib.data_processing import fetch_data
from lib.signals.indicators import add_indicators, generate_signals
from lib.strategy import backtest

df = fetch_data("SPY", "2020-01-01", "2024-01-01")
df = add_indicators(df)
df, all_signals = generate_signals(df)
results = backtest(df, initial_capital=100_000, buy_indicators=[...], sell_indicators=[...])
```

### Dash Callbacks
Each callback file in `lib/dash/callbacks/` is imported by `integrated_dashboard.py`. New callbacks go in their own file and must be imported there. Use `@app.callback` with explicit `prevent_initial_call=True` where appropriate.

### Configuration
Read strategy params via `lib/config_loader.py`. Never hardcode indicator windows — always pull from `config/strategy_config.yaml`.

---

## Testing

- Tests live in `lib/tests/` and use pytest.
- Run: `python -m pytest lib/tests/ -v`
- Syntax check only: `python -m py_compile <file.py>`
- Tests should not hit Yahoo Finance network — mock `fetch_data` where needed.

---

## Output Files
- Parquet results → `results/`
- Excel exports → `export/` (created by `lib/utils.py`)

---

## Disclaimer
Educational/research use only. Not financial advice.
