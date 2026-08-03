# SearchForAlpha Lab — Module Index

On-demand module catalog. Read specific sections only — do not load the entire file unless exploring broadly.

Hub: [PROJECT_INDEX.md](PROJECT_INDEX.md)

---

## Core Modules

### Data & Config
| File | Key Functions |
|------|--------------|
| [lib/data_processing.py](../lib/data_processing.py) | `fetch_data(ticker, start, end)`, `calculate_metrics(trades_df)`, `calculate_performance_stats()` |
| [lib/config_loader.py](../lib/config_loader.py) | `load_config()` → reads `config/strategy_config.yaml` |
| [lib/fundamentals.py](../lib/fundamentals.py) | `fetch_fundamentals()`, `build_fundamentals_result()` — SEC + yfinance financials |
| [lib/utils.py](../lib/utils.py) | `export_to_excel()`, input validation helpers |
| [lib/seeds.py](../lib/seeds.py) | Deterministic RNG seed helpers |

### Backtesting Engine
| File | Key Functions |
|------|--------------|
| [lib/strategy.py](../lib/strategy.py) | `backtest()`, `run_backtest()` — 3 strategy modes |
| [lib/backtest_result.py](../lib/backtest_result.py) | `BacktestMetrics`, `BacktestResult`, `run_backtest_result()`, Sortino/Calmar |

**Strategy modes** (`strategy_mode`): `trading`, `accumulation`, `rebalancing`. (Swing/Position/Trend are separate UI quick-presets — `strategy-preset` values `swing`/`position`/`trend` in `right_panel.py`, not engine modes.)

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
| [lib/bayesian_optimization.py](../lib/bayesian_optimization.py) | `run_study()`, `run_optimise_cli()`, Optuna trials |

### Walk-forward & Promotion
| File | Key Functions |
|------|--------------|
| [lib/walkforward/runner.py](../lib/walkforward/runner.py) | `run_walkforward()`, `run_walkforward_cli()` |
| [lib/walkforward/verdict.py](../lib/walkforward/verdict.py) | `WindowVerdict`, `aggregate()` — OOS degradation gates |
| [lib/walkforward/spaces.py](../lib/walkforward/spaces.py) | `suggest_from_space()`, `validate_space()` |
| [lib/promotion/gate.py](../lib/promotion/gate.py) | `evaluate_gate()`, `promote()`, `run_promote_cli()` |
| [lib/promotion/registry.py](../lib/promotion/registry.py) | `update_live_params()`, `record_promotion()`, `diff_params()` |

### Live / Paper Trading
| File | Key Functions |
|------|--------------|
| [lib/live/runner.py](../lib/live/runner.py) | `PaperRunner`, `run_paper_cli()`, `status_cli()`, `kill_cli()` |
| [lib/live/broker.py](../lib/live/broker.py) | `Broker` protocol, `MockBroker`, `IBBroker` |
| [lib/live/guards.py](../lib/live/guards.py) | `evaluate()` — daily loss, position size, broker disconnect guards |

### Store (SQLite persistence)
| File | Key Functions |
|------|--------------|
| [lib/store/trials.py](../lib/store/trials.py) | `save_trial()`, `list_trials()`, `get_trial()` |
| [lib/store/state.py](../lib/store/state.py) | `upsert_state()`, `read_state()`, PID file helpers |
| [lib/store/fills.py](../lib/store/fills.py) | `record_intent()`, `mark_filled()`, `list_fills()` |

### sfa CLI
| File | Purpose |
|------|---------|
| [lib/cli/app.py](../lib/cli/app.py) | Typer app entry — `build_app()` |
| [lib/cli/contracts.py](../lib/cli/contracts.py) | Stable JSON contract dataclasses (don't rename fields) |
| [lib/cli/commands/](../lib/cli/commands/) | 12 subcommands — see table below |

| Command module | sfa subcommand |
|----------------|----------------|
| `list_cmd` | `list` |
| `backtest_cmd` | `backtest` |
| `optimise_cmd` | `optimise` |
| `trials_cmd` | `trials` |
| `walkforward_cmd` | `walkforward` |
| `promote_cmd` | `promote` |
| `run_cmd` | `run --mode paper` |
| `status_cmd` | `status` |
| `kill_cmd` | `kill` |
| `sweep_single_cmd` | `sweep-single` |
| `sample_universe_cmd` | `sample-universe` |
| `instructions_cmd` | `instructions` |

### Dashboard (Dash/Plotly)
| File | Purpose |
|------|---------|
| [lib/dash/integrated_dashboard.py](../lib/dash/integrated_dashboard.py) | App init, server boot, `register_callbacks(app)`, `_schedule_browser_open` (lands on `/ticker/<DEFAULT_TICKER>`), `/flow_report.html` route |
| [lib/dash/bootstrap.py](../lib/dash/bootstrap.py) | `try_bootstrap_default_session()` — preload default ticker on startup |
| [lib/dash/chart_payload.py](../lib/dash/chart_payload.py) | Builds the JSON payload the client chart renders (candles, panes, series, markers) |
| [lib/dash/chart_meta.py](../lib/dash/chart_meta.py) | Bar-interval inference + toolbar bar-count summary |
| [lib/dash/signal_markers.py](../lib/dash/signal_markers.py) | Buy/sell trigger resolution shared by the chart markers and the TRIG/REJ counters |
| [lib/dash/assets/10-sfa-chart.js](../lib/dash/assets/10-sfa-chart.js) | TradingView Lightweight Charts glue — owns pan/zoom/crosshair client-side |
| [lib/dash/dash_config.py](../lib/dash/dash_config.py) | Theme, defaults, indicator settings |
| [lib/dash/state.py](../lib/dash/state.py) | `dashboard_state` — in-memory session cache |
| [lib/dash/routes.py](../lib/dash/routes.py) | URL route parsing — terminal, fundamentals, flow, ticker_terminal |
| [lib/dash/flow_glossary.py](../lib/dash/flow_glossary.py) | Shared term/flag definitions, `score_breakdown()`, `interpretive_banner()` for Flow Scanner |
| [lib/dash/flow_view.py](../lib/dash/flow_view.py) | Pure render — `render_flow_reports()`, `render_ticker_card()`, native Dash DataTable |
| [lib/dash/ticker_search.py](../lib/dash/ticker_search.py) | Ticker autocomplete options |

**Layout** (`lib/dash/layout/` — one file per UI region):
| File | Region |
|------|--------|
| `shell.py` | Top-level composer — stores, intervals, wires all regions |
| `header.py` | Header bar + status bar |
| `sidebar.py` | Left sidebar (ticker, date range, toggles) |
| `chart_area.py` | Main chart + controls |
| `right_panel.py` | Right panel (metrics, backtest results) |
| `overlays.py` | Fundamentals + Flow Scanner overlays |
| `command_palette.py` | Cmd+K command palette |

**Callbacks** (`lib/dash/callbacks/` — 14 registered modules via `register_callbacks()`):
| File | Concern |
|------|---------|
| `startup.py` | Initial load, bootstrap wiring |
| `data_loading.py` | Ticker fetch, indicator compute |
| `strategy_ui.py` | Strategy mode / param controls |
| `signals.py` | Signal toggle callbacks |
| `chart_plotly.py` | Plotly chart updates |
| `backtest.py` | Run backtest from UI |
| `optimization.py` | In-dashboard optimisation |
| `fundamentals.py` | Fundamentals overlay |
| `flow.py` | Flow Scanner overlay — rescan subprocess, JSON load, native `#flow-content` render |
| `routing.py` | URL-based page routing |
| `presets.py` | UI preset save/load |
| `layout.py` | Panel collapse, theme |
| `misc_ui.py` | Miscellaneous UI hooks |
| `command_palette.py` | Command palette actions |
| `shared.py` | Shared callback helpers (not registered) |

### Visualisation (static)
| File | Purpose |
|------|---------|
| _(removed)_ | `lib/visualization.py` (matplotlib) was deleted — nothing imported it, and it was the sole reason matplotlib/mplfinance were pinned |

---

## Configuration
| File | Purpose |
|------|---------|
| [config/strategy_config.yaml](../config/strategy_config.yaml) | Default indicator params, `live_params`, `search_space` |
| [config/ui_presets.json](../config/ui_presets.json) | Saved dashboard UI presets |
| [config/tickers_universe.csv](../config/tickers_universe.csv) | Ticker universe for search / sweeps |
| [config/param_history.yaml](../config/param_history.yaml) | Promotion history (YAML fallback) |
| [config/agent.yaml](../config/agent.yaml) | OpenClaw agent config |

---

## Scripts
| File | Purpose |
|------|---------|
| [scripts/run_dashboard_latest.ps1](../scripts/run_dashboard_latest.ps1) | Windows dashboard launcher (port cleanup) |
| [scripts/flow_scanner.py](../scripts/flow_scanner.py) | Flow Scanner — yfinance options scan, `write_html_report()`, `write_json_report()` |
| [scripts/flow_runner.py](../scripts/flow_runner.py) | Subprocess wrapper — `run_flow_scan()` writes HTML + JSON for Dash |
| [scripts/generate_ticker_universe.py](../scripts/generate_ticker_universe.py) | Rebuild `config/tickers_universe.csv` |

---

## Tests (29 files)
| Area | Files |
|------|-------|
| Strategy & signals | `test_strategy`, `test_indicators`, `test_signal_combination`, `test_param_propagation`, `test_determinism` |
| Backtest & optimisation | `test_bayesian_optimizer`, `test_bayes_holdout`, `test_walkforward`, `test_promotion_gate` |
| CLI contracts | `test_cli_contracts` |
| Live runner | `test_runner_safety`, `test_guards`, `test_broker_mock` |
| Dashboard | `test_dashboard`, `test_dashboard_startup`, `test_bootstrap`, `test_data_loading`, `test_dash_routing`, `test_dash_no_writeback`, `test_dash_enriched_cache`, `test_command_palette`, `test_ticker_search` |
| Flow Scanner | `test_flow_scanner_json`, `test_flow_view` |
| Fundamentals | `test_fundamentals`, `test_fundamentals_explainability`, `test_fundamentals_formula_rendering` |
| Data | `test_data_processing`, `test_ticker_universe` |

Run: `rtk python -m pytest lib/tests/ -q`

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

## Research Docs
| File | Purpose |
|------|---------|
| [docs/openclaw-research.md](../docs/openclaw-research.md) | OpenClaw sweep rules, promotion gates, hard rules — `@`-mention for Cursor research |
| [RESEARCH.md](../RESEARCH.md) | Regime calendar, ticker reference, cost model (OpenClaw; in `.cursorignore`) |
| [AGENTS.md](../AGENTS.md) | OpenClaw orchestrator on server deploy (in `.cursorignore` for Cursor coding) |
