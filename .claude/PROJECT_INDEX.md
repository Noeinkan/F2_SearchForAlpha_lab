# SearchForAlpha Lab — Project Index

Navigation hub for agents. **Don't load this entire file every turn** — jump to the section you need.

## Instruction tiers (token efficiency)

| Layer | File | When loaded |
|-------|------|-------------|
| Always-on | `.cursor/rules/token-efficiency.mdc` | Every Cursor session — rtk + context discipline |
| Always-on | `CLAUDE.md` | Every session — essentials only (~15 lines) |
| On-demand | `.cursor/rules/sfa-python.mdc` | Editing `lib/**/*.py` |
| On-demand | `.cursor/rules/dash-callbacks.mdc` | Editing `lib/dash/**` |
| Research only | `AGENTS.md` + `docs/openclaw-research.md` | OpenClaw sfa CLI (not code edits) |
| On-demand | `.cursor/rules/sfa-cli-research.mdc` | Editing `lib/cli/**` |
| Shell hook | `.cursor/hooks.json` | Auto-prefixes `rtk` on Shell tool calls |

Shell commands: prefix with `rtk` (see `.github/copilot-instructions.md`).

Full rationale (IT): [docs/token-efficiency.md](../docs/token-efficiency.md)

---

## Entry Points
| File | Purpose |
|------|---------|
| [main.py](../main.py) | Launch Dash app (dev mode with auto-reload) |
| `python -m pytest lib/tests/` | Run test suite |

---

## Core Modules

### Data
| File | Key Functions |
|------|--------------|
| [lib/data_processing.py](../lib/data_processing.py) | `fetch_data(ticker, start, end)`, `calculate_metrics(trades_df)`, `calculate_performance_stats()` |
| [lib/config_loader.py](../lib/config_loader.py) | `load_config()` → reads `config/strategy_config.yaml` |
| [lib/utils.py](../lib/utils.py) | `export_to_excel()`, input validation helpers |

### Backtesting Engine
| File | Key Functions |
|------|--------------|
| [lib/strategy.py](../lib/strategy.py) | `backtest()`, `run_backtest()` — 6 strategy modes |

**Strategy modes:** `trading`, `accumulation`, `rebalancing`, `swing_trading`, `position_trading`, `trend_following`

### Signals & Indicators
| File | Class / Function |
|------|-----------------|
| [lib/signals/base_strategy.py](../lib/signals/base_strategy.py) | `BaseStrategy` ABC |
| [lib/signals/indicators.py](../lib/signals/indicators.py) | `add_indicators(df)`, `generate_signals(df)` |
| [lib/signals/signals_RSI.py](../lib/signals/signals_RSI.py) | `RSI_TradingStrategy` |
| [lib/signals/signals_BB.py](../lib/signals/signals_BB.py) | `BB_TradingStrategy` (Bollinger Bands) |
| [lib/signals/signals_MACD.py](../lib/signals/signals_MACD.py) | `MACD_TradingStrategy` |
| [lib/signals/signals_EMA.py](../lib/signals/signals_EMA.py) | `EMA_TradingStrategy` |
| [lib/signals/signals_SMA.py](../lib/signals/signals_SMA.py) | `SMA_TradingStrategy` |
| [lib/signals/signals_CCI.py](../lib/signals/signals_CCI.py) | `CCI_TradingStrategy` |
| [lib/signals/signals_VWAP.py](../lib/signals/signals_VWAP.py) | `VWAP_TradingStrategy` |

### Optimisation
| File | Key Functions |
|------|--------------|
| [lib/signal_combo_optimisation.py](../lib/signal_combo_optimisation.py) | `test_all_combinations(df, ...)` |
| [lib/params_optimization.py](../lib/params_optimization.py) | Per-indicator parameter sweeps |
| [lib/weights_optimization.py](../lib/weights_optimization.py) | Indicator weight optimisation |

### Dashboard (Dash/Plotly)
| File | Purpose |
|------|---------|
| [lib/dash/integrated_dashboard.py](../lib/dash/integrated_dashboard.py) | App init, layout, callback imports |
| [lib/dash/chart_builder.py](../lib/dash/chart_builder.py) | Plotly figure factory + overlay registry |
| [lib/dash/callbacks/](../lib/dash/callbacks/) | 14 callback modules |

### Visualisation (static)
| File | Purpose |
|------|---------|
| [lib/visualization.py](../lib/visualization.py) | Matplotlib chart utilities |

---

## Configuration
| File | Purpose |
|------|---------|
| [config/strategy_config.yaml](../config/strategy_config.yaml) | Default indicator params (windows, thresholds) |
| [config/ui_presets.json](../config/ui_presets.json) | Saved dashboard UI presets |

---

## Tests
| File | What it tests |
|------|--------------|
| [lib/tests/](../lib/tests/) | pytest suite — 6 test files covering strategy, signals, data |

---

## Output Directories
| Directory | Content |
|-----------|---------|
| `results/` | Parquet backtest outputs |
| `export/` | Excel exports |

---

## Signal Naming Convention
- Buy signals: `{INDICATOR}_{CONDITION}_Buy` (e.g. `RSI_Oversold_Buy`)
- Sell signals: `{INDICATOR}_{CONDITION}_Sell` (e.g. `BB_Upper_Sell`)
- All signals are boolean columns on the DataFrame

---

## Agents Available
| Agent | Use for |
|-------|---------|
| `quant-analyst` | Backtest result analysis, metric interpretation, strategy comparison |
| `signal-engineer` | Creating/debugging technical indicator strategies |
| `dashboard-dev` | Dash UI components, callbacks, chart overlays |

## Slash Commands Available
| Command | Use for |
|---------|---------|
| `/backtest` | Quick backtest on any ticker |
| `/optimize` | Signal combination optimisation |
| `/add-signal` | Scaffold a new indicator strategy |
| `/run-tests` | Run pytest suite and diagnose failures |
| `/new-callback` | Scaffold a new Dash callback |
