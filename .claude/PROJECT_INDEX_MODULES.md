# SearchForAlpha Lab — Module Index

On-demand module catalog. Read specific sections only — do not load the entire file unless exploring broadly.

Hub: [PROJECT_INDEX.md](PROJECT_INDEX.md)

---

## Core Modules

### Data & Config
| File | Key Functions |
|------|--------------|
| [lib/data_processing.py](../lib/data_processing.py) | `fetch_data(ticker, start, end)`, `get_all_tickers()`, `validate_symbol()`, `create_backtest_results()`, `calculate_max_drawdown/sharpe_ratio/win_rate/profit_factor()` |
| [lib/config_loader.py](../lib/config_loader.py) | `load_config()` → reads `config/strategy_config.yaml` |
| [lib/fundamentals.py](../lib/fundamentals.py) | `fetch_fundamentals()`, `build_fundamentals_result()` — SEC + yfinance financials |
| [lib/utils.py](../lib/utils.py) | `export_priceaction_to_excel()`, `get_user_input()`, `TradingStrategyInput` |
| [lib/seeds.py](../lib/seeds.py) | Deterministic RNG seed helpers |
| [lib/ticker_universe.py](../lib/ticker_universe.py) | Loads `config/tickers_universe.csv` — symbol lookup, sector / asset-class facets |
| [lib/timeframes.py](../lib/timeframes.py) | Interval metadata + `clamp_window()` (Yahoo's 728d intraday lookback limit, stale-range relocation) |
| [lib/agent_strategy.py](../lib/agent_strategy.py) | Resolves agent strategy bundles (`config/agent.yaml`) to executable backtests |

### Backtesting Engine
| File | Key Functions |
|------|--------------|
| [lib/strategy.py](../lib/strategy.py) | `backtest()`, `run_backtest()` — 3 strategy modes |
| [lib/backtest_result.py](../lib/backtest_result.py) | `BacktestMetrics`, `BacktestResult`, `run_backtest_result()`, Sortino/Calmar |

**Strategy modes** (`strategy_mode`), sized in `_execute_buy` / `_execute_sell`:
- `trading` — Kelly size × `position_scaling`; scaling ramps each *order* and stacks, with no target cap
- `accumulation` — fixed `amount_per_buy`; sell signals discarded, trailing stop pinned to `inf`
- `rebalancing` — `position_size_pct` of **portfolio value** on both sides (not of cash / units held)

(Swing/Position/Trend are separate UI quick-presets — `strategy-preset` values `swing`/`position`/`trend` in `backtest_panel.py`, not engine modes.)

**Execution Type explainer** — user-facing copy in [lib/dash/execution_glossary.py](../lib/dash/execution_glossary.py); every number it shows is produced by [lib/dash/execution_sim.py](../lib/dash/execution_sim.py), which runs the real `backtest()` over a fixed 24-bar tape. Explanatory UI must never recompute sizing itself.

### Signals & Indicators
| File | Class / Function |
|------|-----------------|
| [lib/signals/base_strategy.py](../lib/signals/base_strategy.py) | `BaseTradingStrategy` ABC |
| [lib/signals/indicators.py](../lib/signals/indicators.py) | `add_indicators(df)`, `generate_signals(df)` |
| [lib/signals/signals_RSI.py](../lib/signals/signals_RSI.py) | `RSI_TradingStrategy` |
| [lib/signals/signals_BB.py](../lib/signals/signals_BB.py) | `BB_TradingStrategy` (Bollinger Bands) |
| [lib/signals/signals_MACD.py](../lib/signals/signals_MACD.py) | `MACD_TradingStrategy` |
| [lib/signals/signals_EMA.py](../lib/signals/signals_EMA.py) | `EMA_TradingStrategy` |
| [lib/signals/signals_SMA.py](../lib/signals/signals_SMA.py) | `SMA_TradingStrategy` |
| [lib/signals/signals_CCI.py](../lib/signals/signals_CCI.py) | `CCI_TradingStrategy` |
| [lib/signals/signals_VWAP.py](../lib/signals/signals_VWAP.py) | `VWAP_TradingStrategy` |
| [lib/signals/signals_ADX.py](../lib/signals/signals_ADX.py) | `ADX_TradingStrategy` — trend/range regime filter |
| [lib/signals/signals_ATR.py](../lib/signals/signals_ATR.py) | `ATR_TradingStrategy` — volatility regime + ATR risk sizing |
| [lib/signals/signals_OBV.py](../lib/signals/signals_OBV.py) | `OBV_TradingStrategy` — volume confirmation |

ADX/ATR/OBV also back the **regime-gated variants** in `config/strategy_config.yaml` (trend-gated and mean-reversion-gated bundles). Guarded by `test_signals_regime.py`.

### Optimisation
| File | Key Functions |
|------|--------------|
| [lib/signal_combo_optimisation.py](../lib/signal_combo_optimisation.py) | `test_all_combinations(df, ...)` |
| [lib/params_optimization.py](../lib/params_optimization.py) | Per-indicator parameter sweeps |
| [lib/weights_optimization.py](../lib/weights_optimization.py) | Indicator weight optimisation |
| [lib/bayesian_optimization.py](../lib/bayesian_optimization.py) | `run_study()`, `run_optimise_cli()`, Optuna trials |
| [lib/execution_params.py](../lib/execution_params.py) | `partition_params()`, shared execution search-space keys |
| [lib/grid_search.py](../lib/grid_search.py) | `run_grid_search()` — capped cartesian grid over unified space |
| [lib/dash/optimizer_space_viz.py](../lib/dash/optimizer_space_viz.py) | Combo estimate card, param range bars, param landscape figures |

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
| `grid_search_cmd` | `grid-search` |
| `trials_cmd` | `trials` |
| `walkforward_cmd` | `walkforward` |
| `promote_cmd` | `promote` |
| `run_cmd` | `run --mode paper` |
| `status_cmd` | `status` |
| `kill_cmd` | `kill` |
| `sweep_single_cmd` | `sweep-single` |
| `sample_universe_cmd` | `sample-universe` |
| `instructions_cmd` | `instructions` |

### Dashboard (Dash + TradingView Lightweight Charts)
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
| [lib/dash/execution_glossary.py](../lib/dash/execution_glossary.py) | Execution Type copy — `MODE_SPECS`, `MECHANICS_ROWS`, `PREDICT_QUESTIONS` (pure data) |
| [lib/dash/execution_sim.py](../lib/dash/execution_sim.py) | `simulate()`, `first_entry_summary()` — runs the real `backtest()` on a fixed tape so explainer figures cannot drift |
| [lib/dash/execution_view.py](../lib/dash/execution_view.py) | Pure render — `render_execution_learn_content()`, `render_mechanics_matrix()`, `render_fingerprint()` |
| [lib/dash/ticker_search.py](../lib/dash/ticker_search.py) | Ticker autocomplete + symbol-search query/filter resolution |
| [lib/dash/watchlist_storage.py](../lib/dash/watchlist_storage.py) | `config/watchlists.json` read/write — disk is the source of truth, `watchlists-store` mirrors it |
| [lib/dash/overlay_registry.py](../lib/dash/overlay_registry.py) | Shared overlay metadata — `get_tv_overlay_specs()`, `build_overlay_visibility()` |
| [lib/dash/components.py](../lib/dash/components.py) | Reusable component builders shared across `layout/` regions |
| [lib/dash/helpers.py](../lib/dash/helpers.py) | Callback-side data prep and optimisation utilities |
| [lib/dash/combo_walkforward.py](../lib/dash/combo_walkforward.py) | `ComboSpec`, `run_combo_walkforward()` — signal-combo walk-forward for Optimizer OOS |
| [lib/dash/optimizer_history.py](../lib/dash/optimizer_history.py) | `summarize_run`, `append_history`, `history_for_ticker` — compact run history |
| [lib/dash/optimizer_landscape.py](../lib/dash/optimizer_landscape.py) | `build_return_sharpe_figure()` — Return vs Sharpe scatter |
| [lib/dash/styles.py](../lib/dash/styles.py) | `get_styles(theme)` — theme-derived inline style dicts |
| [lib/dash/preset_storage.py](../lib/dash/preset_storage.py) | `config/ui_presets.json` atomic load/save |

**Layout** (`lib/dash/layout/` — one file per UI region):
| File | Region |
|------|--------|
| `shell.py` | Top-level composer — stores, intervals, wires all regions |
| `header.py` | Header bar + status bar |
| `sidebar.py` | Left sidebar (ticker, date range, toggles) |
| `chart_area.py` | Main chart + controls |
| `right_panel.py` | Right panel shell (Backtest / Optimizer / Data tabs) |
| `backtest_panel.py` | Backtest tab accordion + execution-mode cards + learn modal |
| `optimizer_panel.py` | Optimizer tab teaser → full-screen `/optimize` |
| `optimizer_workspace.py` | Full-screen Optimizer overlay (mirrors, universe, chart slot, results) |
| `overlays.py` | Fundamentals + Flow Scanner overlays (incl. Flow learn modal) |
| `command_palette.py` | Ctrl+K command palette |
| `symbol_search.py` | Ctrl+/ (or bare `/`) symbol-search modal — search, sector/asset filters, watchlists |

The Execution Type explainer modal (`execution-learn-modal`) is emitted by `backtest_panel.py`, not by `shell.py`.

**Callbacks** (`lib/dash/callbacks/` — 20 registered modules via `register_callbacks()`):
| File | Concern |
|------|---------|
| `startup.py` | Initial load, bootstrap wiring |
| `presets.py` | UI preset save/load |
| `data_loading.py` | Ticker fetch (always max history), indicator compute |
| `test_window.py` | Evaluated period — window defaults/presets, chart focus sync |
| `data_table.py` | Data tab — row/column-group filters, date slice, CSV export |
| `strategy_ui.py` | Strategy mode / param controls |
| `execution_help.py` | Execution Type explainer — mode previews, sandbox, predict-then-reveal modal |
| `signals.py` | Signal toggle callbacks |
| `chart.py` | Sole `chart-payload-store` writer + the clientside renderer |
| `backtest.py` | Run backtest from UI |
| `optimization.py` | In-dashboard optimisation (thread pool, cost estimate) |
| `optimizer_phase3.py` | Landscape, run history, OOS validation, Bayesian sweep (Optimizer Phase 3) |
| `optimizer_sync.py` | Bidirectional sync of `opt-*` mirrors ↔ Backtest SoT controls |
| `optimize_workspace.py` | `/optimize` navigate, overlay visibility, chart reparent |
| `routing.py` | URL-based page routing |
| `fundamentals.py` | Fundamentals overlay — register + re-exports |
| `fundamentals_formulas.py` | Valuation formulas + explainability helpers |
| `fundamentals_render.py` | Fundamentals tables / charts / `_render_payload` |
| `flow.py` | Flow Scanner overlay — rescan subprocess, JSON load, native `#flow-content` render |
| `misc_ui.py` | Keyboard shortcuts, palette dispatch bridge, misc UI hooks |
| `layout.py` | Panel collapse, splitter, theme |
| `command_palette.py` | Command palette actions |
| `symbol_search.py` | Symbol-search modal — query, sector/asset options, watchlist mutations |
| `status.py` | Status-bar activity indicator (WORKING…/READY/ERROR) |
| `shared.py` | Re-export hub for shared helpers (not registered) |
| `shared_enrichment.py` | Test-window slice + indicator enrichment cache |
| `shared_signals.py` | Signal labels / option rows / plot toggles |
| `shared_data_display.py` | Data-tab classify / filter / style / table builders |
| `shared_presets.py` | UI preset payload helpers |
| `shared_optimization_ui.py` | Optimizer result tables + best-strategy card |

**Data tab column groups** — `DATA_COLUMN_GROUPS` in `dash_config.py`: `ohlcv`, `indicators`, `signals`, `portfolio`. Classification and the conditional styling rules (signal triggers, portfolio outliers) live in `callbacks/shared_data_display.py`; `test_data_table.py` guards both.

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
| [config/tickers_universe.csv](../config/tickers_universe.csv) | Ticker universe for search / sweeps (~13k rows: symbol, name, sector, industry, asset class) |
| [config/tickers_curated.csv](../config/tickers_curated.csv) | Hand-maintained non-equities (FX, futures, crypto, indices) merged into the universe |
| [config/watchlists.json](../config/watchlists.json) | Named watchlists for the symbol-search modal |
| [config/param_history.yaml](../config/param_history.yaml) | Promotion history (YAML fallback) |
| [config/agent.yaml](../config/agent.yaml) | OpenClaw agent config |

---

## Scripts
| File | Purpose |
|------|---------|
| [scripts/run_dashboard_latest.ps1](../scripts/run_dashboard_latest.ps1) | Windows dashboard launcher (port cleanup) |
| [scripts/flow_scanner.py](../scripts/flow_scanner.py) | Flow Scanner — yfinance options scan, `write_html_report()`, `write_json_report()` |
| [scripts/flow_runner.py](../scripts/flow_runner.py) | Subprocess wrapper — `run_flow_scan()` writes HTML + JSON for Dash |
| [scripts/build_universe.py](../scripts/build_universe.py) | Rebuild `config/tickers_universe.csv` — current builder (equities + `tickers_curated.csv`, sector/industry/asset class) |
| [scripts/generate_ticker_universe.py](../scripts/generate_ticker_universe.py) | Legacy S&P500/NASDAQ-only builder, superseded by `build_universe.py` |

---

## Tests (46 files)
| Area | Files |
|------|-------|
| Strategy & signals | `test_strategy`, `test_strategy_engine`, `test_strategy_snapshot`, `test_indicators`, `test_signals_regime`, `test_atr_risk`, `test_signal_combination`, `test_param_propagation`, `test_determinism` |
| Backtest & optimisation | `test_bayesian_optimizer`, `test_bayes_holdout`, `test_walkforward`, `test_promotion_gate` |
| CLI contracts | `test_cli_contracts` |
| Live runner | `test_runner_safety`, `test_guards`, `test_broker_mock` |
| Dashboard | `test_dashboard`, `test_dashboard_startup`, `test_bootstrap`, `test_data_loading`, `test_data_table`, `test_test_window`, `test_layout`, `test_dash_routing`, `test_dash_no_writeback`, `test_dash_enriched_cache`, `test_command_palette`, `test_ticker_search`, `test_symbol_search`, `test_watchlist_storage`, `test_radio_seg_css` |
| Chart (Lightweight Charts) | `test_chart_payload`, `test_chart_meta`, `test_chart_assets`, `test_chart_regime_panes` |
| Execution explainer | `test_execution_sim`, `test_execution_view` |
| Flow Scanner | `test_flow_scanner_json`, `test_flow_view` |
| Fundamentals | `test_fundamentals`, `test_fundamentals_explainability`, `test_fundamentals_formula_rendering` |
| Data | `test_data_processing`, `test_ticker_universe`, `test_timeframes` |

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
