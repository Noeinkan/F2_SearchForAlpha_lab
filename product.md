# SearchForAlpha Lab Product Brief

## Executive Summary

SearchForAlpha Lab is a Python algorithmic trading research platform that fetches OHLCV market data from Yahoo Finance, computes technical-indicator signals, runs event-driven backtests, performs Bayesian and combinatorial parameter optimisation, validates candidates through rolling walk-forward analysis, and (in `--mode paper`) executes the resulting strategy on an Interactive Brokers paper account behind a broker-protocol abstraction. The codebase exposes two interfaces to operators and external agents: a Dash web dashboard started via `python main.py` (default URL `http://127.0.0.1:8050/ticker/TSLA`), and a Typer console script `sfa` (entry point declared in `pyproject.toml`) that supports every workflow step (list, backtest, optimise, trials, walkforward, promote, run, status, kill, sweep-single, sample-universe, instructions) with stable JSON contracts documented in `lib/cli/contracts.py`. Persistence uses Parquet in `results/`, Excel in `export/`, YAML for indicator and bundle config, and SQLite (`state/optuna.db`) for trials, walk-forward windows, fills, and runner state. The license declared in `pyproject.toml` is MIT; the README explicitly disclaims financial advice and frames the build as educational.

## Problem it Solves

The platform addresses the recurring friction in trading-strategy research where manual, ad-hoc studies are non-reproducible and have no consistent path from idea to validated, executable strategy. Concrete needs that the code responds to:

- **Reproducibility** — indicator parameters come from `config/strategy_config.yaml` (singular loader in `lib/config_loader.py`), RNG is seeded via `lib/seeds.py`, every trial stores `seed`, `wall_seconds`, and `git_commit` in `sfa_trials` (`lib/store/trials.py`), and optuna studies resume across runs against RDB storage at `state/optuna.db`.
- **Validation against overfitting** — the platform provides rolling walk-forward (`lib/walkforward/runner.py`) and a `WindowVerdict` aggregation (`lib/walkforward/verdict.py`) with explicit robustness thresholds: an aggregate is `robust == True` iff OOS Sharpe > `1.0` in at least `0.8` (fraction) of windows AND mean per-window degradation < `0.4`.
- **Safe promotion** — `lib/promotion/gate.py` gates any update to `live_params` until a recent walk-forward record passes thresholds in `config/agent.yaml` (defaults `min_oos_sharpe_mean=1.0`, `max_degradation=0.4`, `walkforward_max_age_days=7`) and the strategy is not currently running.
- **Multi-strategy enumeration** — agent-strategy bundles in `config/strategy_config.yaml` under `agent_strategies:` pair a `(ticker, buy_signals, sell_signals, live_params, search_space, mode)` descriptor that the same CLI surfaces for backtest, optimise, walkforward, promote, and paper-run.
- **Options-flow context** — a Flow Scanner (`scripts/flow_scanner.py`, surfaced at `/flow/<ticker>` and `/flow_report.html`) ranks unusual-options contracts with Volume vs Open Interest, OTM/weekly flags, and premium tiers so signals can be enriched with sentiment.
- **Fundamental overlay** — `lib/fundamentals.py` pulls SEC EDGAR XBRL (primary, no API key) and yfinance (fallback + analyst estimates) so the UI can render a Big-Five valuation card next to the chart.

## What it Does

- **Fetches OHLCV bars via `yfinance`** — `lib/data_processing.py` `fetch_data(symbol, start_date, end_date)` returns a validated DataFrame (required columns `Open`, `High`, `Low`, `Close`, `Volume`, with NaN warnings above 10%). The default landing ticker is `TSLA` (`lib/dash/dash_config.py: DEFAULT_TICKER`).
- **Discovers and computes technical indicators** — `lib/signals/indicators.py` auto-discovers strategy classes in `lib/signals/signals_*.py` (RSI, BB, MACD, EMA, SMA, CCI, VWAP) plus ADX/ATR/OBV via `ta.trend` / `ta.volatility`. Signal columns follow `{INDICATOR}_{CONDITION}_{Buy|Sell}` (e.g. `RSI_Oversold_Buy`, `BB_Upper_Sell`) and are boolean DataFrame columns.
- **Runs an event-driven backtest** — `lib/strategy.py` `backtest(df, initial_capital, …)` supports three `strategy_mode` values: `trading`, `accumulation`, `rebalancing`. `BacktestMetrics` (`lib/backtest_result.py`) is the structured output with fields `total_return, sharpe, sortino, calmar, max_drawdown, num_trades, win_rate, profit_factor, turnover`. Per-trade win rate/profit factor are computed from closed round-trips (`Units` goes `0 -> >0` and back to `0`).
- **Optimises parameters** — four flavours are wired: per-indicator sweeps (`lib/params_optimization.py`), signal-combination combinatorial search (`lib/signal_combo_optimisation.py`), indicator-weight optimisation (`lib/weights_optimization.py`), and Optuna TPE (`lib/bayesian_optimization.py`). The CLI entry `sfa optimise --name … --trials N --metric …` runs TPE; the live loop supports metrics `sortino|sharpe|calmar|composite` with composite weights in `config/agent.yaml`.
- **Validates with walk-forward** — `sfa walkforward --name … --params <trial_id>` slices OHLCV into N windows (default 5), runs in-sample then out-of-sample backtests (default 12 train months / 3 test months, non-overlapping), computes the `WindowVerdict`, and persists to `sfa_walkforward` in `state/optuna.db`.
- **Gates promotion** — `sfa promote --trial <id>` evaluates the gate, then writes promoted `live_params` back to `config/strategy_config.yaml` (via `ruamel.yaml` to preserve comments and order) and appends to `config/param_history.yaml` and `sfa_promotions`.
- **Runs paper trading** — `sfa run --name … --mode paper` connects via `ib_async` to IB Gateway on `127.0.0.1:4002` (configurable in `config/agent.yaml`). `--mode live` is always refused (`lib/cli/commands/run_cmd.py`).
- **Hosts an interactive dashboard** — `python main.py` runs Dash (`lib/dash/integrated_dashboard.py`) on `127.0.0.1:8050` (auto-opens the browser at `/ticker/TSLA`), with routes `/fundamentals/<ticker>`, `/flow/<ticker>`, `/flow_report.html`, and `/ticker/<ticker>`. The UI exposes a ticker search, date range, indicator overlays (candlestick, volume, RSI, CCI, MACD, BB), signal toggles, strategy-mode controls (Trading, Accumulation, Rebalancing), in-dashboard optimisation, presets (`config/ui_presets.json`), a Cmd+K command palette, and theme cycling (default `bloomberg`, also `cvd`, `dark`, `light`).
- **Persists artifacts** — Parquet in `results/`, Excel via `lib/utils.py` `export_to_excel()`, SQLite `state/optuna.db` for trials/walkforward/fills/runner state, PID files in `state/running/<name>.pid`.

## Target Users

The codebase identifies its users through what is wired, not through declared personas:

- **Algorithmic trading researchers** who iterate on indicator combinations and want a single command-line surface (`sfa optimise --metric sortino`, `sfa trials --top 10`) instead of bespoke notebooks; the bayesian + walkforward + gated promotion stack targets this loop.
- **Operators with an Interactive Brokers paper account** who want a locally controlled execution path without writing a TWS/IB API client themselves; the runner is gated to `127.0.0.1`, port `4002`, client `7`.
- **External autonomous agents** consuming structured JSON — `lib/cli/contracts.py` defines `StrategyEntry`, `StrategyList`, `StrategySweep`, `StrategySweepFailure`, `UniverseSamplePlan`, `UniverseSeedSample`, `CliError`, and `BacktestResult` (`lib/backtest_result.py`) with the explicit note that field names are part of a stable contract consumed by `AGENTS.md` and `docs/openclaw-research.md`. The `sfa instructions` subcommand emits a compact agent briefing.
- **Traders analysing options activity** who can run `python scripts/flow_scanner.py <ticker>` and inspect an HTML/JSON report with flag categories (`unusual`, `high_unusual`, `block_premium`, `repeat_call`, `error`).
- **Analysts doing fundamental valuation** — SEC EDGAR integration in `lib/fundamentals.py` provides annual financials for U.S. tickers without an API key.

## Inputs

- **Market data** — Yahoo Finance via `yfinance` (`lib/data_processing.py`); ticker universe loaded from `config/tickers_universe.csv` with a GitHub/Wikipedia/local fallback that resolves S&P 500, NASDAQ-100, Russell 2000, and watchlist entries (`scripts/generate_ticker_universe.py`).
- **Configuration** — `config/strategy_config.yaml` (per-indicator params `strategies.sma / ema / rsi / bollinger_bands / cci / macd / vwap`, `signal_registry` controls, `backtest.{initial_capital, percent_of_portfolio, delay}`, `ml_strategy.*`, and the `agent_strategies:` block with 14 named bundles).
- **Agent runtime config** — `config/agent.yaml` (`ib.{host, port, client_id}`, `guards.{max_daily_loss_pct=0.02, max_position_pct=0.25, max_disconnect_seconds=60, max_clock_drift_seconds=5, max_order_quantity, max_order_notional}`, `promotion.{min_oos_sharpe_mean, max_degradation, walkforward_max_age_days}`, `optimiser.{composite_weights, tpe_seed, n_warmup_steps}`, `research.{single_target_mode, ticker_universe.{etf_broad, etf_sector, etf_style_factor, etf_international, etf_fixed_income, etf_commodity_physical, etf_commodity_futures, etf_commodity_equity_linked}, exploration, cost_model, backtest_windows.{in_sample, stress, recent}, regime_signals, strategy_affinity}`).
- **UI state** — `config/ui_presets.json` for saved chart configurations, `config/param_history.yaml` for promotion audit, `watchlist.txt`.
- **CLI invocation parameters** — see `lib/cli/commands/*.py` for option lists (e.g. `sfa backtest --name … --from YYYY-MM-DD --to YYYY-MM-DD --capital 10000 --seed 42 --json`).
- **Environment variables** — `DASH_DEV` (default `1`), `DASH_RELOAD` (default `0`), `DASH_PORT` (default `8050`), `DASH_HOST` (default `127.0.0.1`).

## Outputs

- **Backtest contract (JSON)** — produced by `lib/backtest_result.py` `BacktestResult.to_contract()`:
  ```
  {strategy, ticker, window:{from,to}, params, metrics:{total_return,sharpe,sortino,calmar,max_drawdown,num_trades,win_rate,profit_factor,turnover}, seed, duration_seconds}
  ```
- **Backtest DataFrame** — produced by `lib/strategy.py` `backtest()` with columns including `Units`, `Units_to_buy`, `Units_to_sell`, `Portfolio_Value`, `Strategy_Returns`, `Buy_Signal`, `Sell_Signal`.
- **Try-list and sweep results** — `StrategyList.strategies` and `StrategySweep.{strategy_count, success_count, failure_count, results, failures}` (`lib/cli/contracts.py`).
- **Optuna studies** — RDB storage in `state/optuna.db` with namespace `study_*` plus mirrored rows in `sfa_trials` and `sfa_walkforward`.
- **Promotion record** — appended to `sfa_promotions` (SQLite), `config/param_history.yaml` (audit log), and overwritten into `config/strategy_config.yaml` (active `live_params`).
- **Paper-trade ledger** — every fill persisted via `lib/store/fills.py`; runner heartbeat in `lib/store/state.py` writes `sfa_runner_state` with equity, positions, and guard status each bar.
- **Dashboard routes** — `/` (default ticker terminal), `/ticker/<ticker>`, `/fundamentals/<ticker>`, `/flow/<ticker>`, `/flow_report.html` (serves `flow_report.html` from the repo root, or a stub when missing).
- **Static artifacts** — Parquet (`results/`), Excel (`export/`), `flow_report.html` + `flow_report.json`, `Signal_Combination.pbix`.

## Benefits & Value Proposition

- **One CLI for the full research loop** — `list → backtest → (sweep-single / optimise) → trials → walkforward → promote → run → status/kill`, with `--json` on every command, returning the contract shapes in `lib/cli/contracts.py`.
- **Reproducible parameter search** — Optuna TPE studies resume across runs against `state/optuna.db`, every trial carries `seed`, `wall_seconds`, `params_json`, `metrics_json`, `git_commit`, `created_at`.
- **Out-of-sample validation** by default — `sfa walkforward` produces an aggregate `WindowVerdict` and a `robust` flag; `sfa promote` refuses unless `robust=True`, `oos_sharpe_mean >= min_oos_sharpe_mean`, `degradation <= max_degradation`, the walk-forward record is younger than `walkforward_max_age_days`, and the strategy is not currently running.
- **Risk-bounded paper execution** — `lib/live/guards.py` evaluates four guards each bar (`daily_loss`, `position_size`, `broker_disconnected`, `clock_drift`) and the runner cancels open orders and disconnects on the first trigger; order-size caps `max_order_quantity` and `max_order_notional` are configurable in `config/agent.yaml`.
- **Bundle-level parameter portability** — the same `(ticker, signals, params)` descriptor that you backtest is the descriptor you promote and run; `lib/agent_strategy.py` `PARAM_KEY_MAP` translates flat param keys (`rsi_window`, `bb_std`, …) into the nested `indicator_settings` shape used by `add_indicators`.
- **Live UI without rediscovering ticks** — Dash bootstrap (`lib/dash/bootstrap.py`) preloads `TSLA` and warm indicator caches before the first paint; `eager_loading=True` embeds `plotly.min.js` to avoid the lazy-load race that previously left the chart container blank.
- **Free data + fundamentals integration** — no API key required for either Yahoo market data or SEC EDGAR XBRL (`lib/fundamentals.py`); yfinance supplies supplemental analyst estimates and non-U.S. fallback.
- **Educational scope for the research assistant** — `sfa instructions --json` emits a mode-aware briefing (sweep vs single-target), rules (e.g. `promote gate: oos_sharpe_mean>=1.0, degradation<=0.4, walkforward_age<=7d`), and a numbered `loop` for external agents.

## Typical Workflow

1. **Discover** — `sfa list --json` reads `config/strategy_config.yaml:agent_strategies` and returns 14 bundles with `status` (`running` if `state/running/<name>.pid` exists else `idle`).
2. **Sanity-check** — `sfa backtest --name mean_reversion_rsi_bb --from 2024-01-01 --to 2024-06-30 --json` loads the bundle, fetches OHLCV, applies indicator settings, runs the engine, returns the metrics contract.
3. **Sweep or optimise**:
   - Cross-strategy on one ticker: `sfa sweep-single --ticker SPY --from … --to … --json` runs every bundle against one symbol.
   - Per-strategy: `sfa optimise --name <bundle> --trials 100 --metric sortino --from … --to … --json` runs Optuna TPE.
4. **Inspect trials** — `sfa trials --name <bundle> --top 10 --json` lists trials sorted by objective value descending (dwell in `sfa_trials`).
5. **Validate OOS** — `sfa walkforward --name <bundle> --params <trial_id> --windows 5 --train-months 12 --test-months 3 --json` produces `WindowVerdict` and persists to `sfa_walkforward`.
6. **Promote** — `sfa promote --name <bundle> --trial <id> --json` evaluates the gate; on pass, writes `live_params` back to the YAML and records the promotion.
7. **Run paper** — `sfa run --name <bundle> --mode paper --json` starts the runner; `sfa status --json` and `sfa kill --name <bundle> [--flatten]` respectively observe and stop it. `--mode live` is hard-rejected.
8. **Dashboard exploration** — `python main.py` opens `http://127.0.0.1:8050/ticker/TSLA`, with overlays for Fundamentals, Flow Scanner, and Indicator panels plus the Cmd+K palette.

## Technical Foundation

- **Python** ≥3.11 (`pyproject.toml`); published package name `searchforalpha`, version `0.2.0`, MIT license.
- **Dependencies** (`pyproject.toml`): `pandas>=2.0`, `numpy>=1.24`, `yfinance>=0.2`, `ta>=0.11`, `PyYAML>=6.0`, `ruamel.yaml>=0.18`, `plotly>=5.18`, `dash>=2.14`, `dash-bootstrap-components>=1.5`, `openpyxl>=3.1`, `scipy>=1.10`, `tqdm>=4.65`, `psutil>=5.9`, `typer>=0.12`, `optuna>=3.5`, `structlog>=24.0`, `pydantic>=2.5`, `ib_async>=1.0`. Dev: `pytest>=8.0`, `pytest-asyncio>=0.23`, `hypothesis>=6.100`, `ruff>=0.5`, `mypy>=1.10`.
- **Console entry points** — `sfa = lib.cli.app:app` (Typer), `python main.py` (Dash).
- **Architecture** — `lib/signals/`: auto-discovered strategy classes inheriting `BaseTradingStrategy` (`base_strategy.py`); `lib/strategy.py`: event-driven backtest engine with `trailing_stop_loss`, `take_profit`, `position_sizing_strategy`, `commission_per_trade`, `slippage_pct`, `fx_fee_pct`; `lib/backtest_result.py`: structured wrapper with `BacktestMetrics` and `BacktestResult` dataclasses; `lib/walkforward/`: rolling OOS runner (`runner.py`), verdict aggregator (`verdict.py`), search-space helpers (`spaces.py`); `lib/promotion/`: gate evaluation (`gate.py`) and registry (`registry.py`) using `ruamel.yaml` round-trip; `lib/live/`: async `PaperRunner` (`runner.py`), Broker `Protocol` with `MockBroker` and `IBBroker` (`broker.py`), guards (`guards.py`); `lib/store/`: SQLite persistence (`trials.py`, `state.py`, `fills.py`); `lib/cli/`: Typer app + `commands/*` (12 subcommands); `lib/dash/`: dashboard entry (`integrated_dashboard.py`), callbacks (`callbacks/` 14 modules), layout regions (`layout/` 7 modules), chart payload builder (`chart_payload.py`) rendered client-side by TradingView Lightweight Charts (`assets/10-sfa-chart.js`), config (`dash_config.py`), state (`state.py`), routes (`routes.py`), bootstrap (`bootstrap.py`).
- **Persistence** — `state/optuna.db` (Optuna RDB + mirrored `sfa_trials`, `sfa_walkforward`, `sfa_promotions`, `sfa_runner_state`, `sfa_fills` tables), `state/running/<name>.pid`, `config/strategy_config.yaml`, `config/param_history.yaml`, `config/agent.yaml`, `config/ui_presets.json`, `config/tickers_universe.csv`, `results/*.parquet`, `export/*.xlsx`.
- **Concurrency model** — async runner with `asyncio.Event` cancellation; bar-by-bar re-computation of indicators on a rolling buffer (`rolling_buffer_bars` default 250); `bar_lock` guards state mutation per bar.
- **Determinism** — `lib/seeds.py: set_global_seed`, default seed `42` (CLI `--seed` and config `tpe_seed`); tests in `lib/tests/` cover strategies, signals, optimisation, walk-forward, promotion gate, runner safety, broker mock, dashboard startup, routing, command palette, ticker search, fundamentals, and flow scanner.
- **Deployment** — `scripts/run_dashboard_latest.ps1` (Windows launcher with `KillAll`/`NoOpen`/`Foreground`), `deploy.ps1` (server deploy with `SkipPipInstall` / `SkipRestartDashboard` deploy parameters and a rollback path), `sfa.cmd` and `run_dashboard_latest.cmd`, `justfile`. README explicitly warns that the Werkzeug reloader is unreliable on Windows and defaults it off.

## Current Limitations & Boundaries

- **Live trading is hard-disabled** — `sfa run` rejects `--mode live` unconditionally (`lib/cli/commands/run_cmd.py`); the IB broker only targets paper port `4002` and refuses `4001`. Any production deployment must lift this at the code level rather than via config.
- **Backend is single-process per runner** — `lib/live/runner.py` documents "one strategy per process, one ticker per strategy, market orders only"; no multi-symbol, multi-strategy runner.
- **Market orders only** — `lib/live/broker.py` `Order` defaults to `order_type="MKT"`; limit/stop/bracket orders are not implemented in the live path even though the dataclass carries `limit_price`.
- **Data vendor lock-in** — only `yfinance` is wired for OHLCV; no Polygon/Alpaca/IB historical bar source.
- **Backtest engine is event-driven but only daily by default** — `lib/data_processing.fetch_data` returns EOD bars; `lib/live/runner.py` consumes `real time bars` from IB Gateway, but the backtest fixtures use EOD signals.
- **Fundamentals cover only U.S. SEC** — non-U.S. tickers fall back to yfinance annual statements; no quarterly XBRL coverage in this release. Quarterly statements are yfinance-only.
- **Indicator set is fixed** — exactly seven indicators (RSI, BB, MACD, EMA, SMA, CCI, VWAP) plus ADX/ATR/OBV indicators; no ML-built signals, no order-book microstructure, no sentiment NLP.
- **Rust/Core extensions are absent** — heavy work is pure Python; no Numba/Cython/Polars acceleration noted in code.
- **Dash reload is off by default** — `DASH_RELOAD=1` is opt-in; rapid edit/dev-loop on Windows is not the default.
- **Strategy mode names diverge from UI presets** — engine modes are `trading|accumulation|rebalancing` while UI quick-presets are `swing|position|trend` (configured in `lib/dash/layout/right_panel.py`, not engine modes).
- **Portuguese/Italian documentation only partially translates** — `docs/` contains both EN and `.it.md` variants for backtest/optimiser guides; CLI contract is English-only.
- **Dashboard does not write back to disk** — UI presets flow through `config/ui_presets.json`, but most panel state is in-memory (`lib/dash/state.py` `dashboard_state`).
- **Options-flow scan is HTTP-best-effort** — `scripts/flow_scanner.py` queries the Yahoo screener (`YAHOO_SCREENER_URL`); when the report is absent `flow_report.html` serves a stub.

## Extensibility & Integration Points

- **Adding an indicator strategy** — drop a `signals_<NAME>.py` file under `lib/signals/` with a class subclassing `BaseTradingStrategy` (`lib/signals/base_strategy.py`); `lib/signals/indicators.py` auto-discovers via `_discover_strategy_classes()`. Standard naming for the resulting columns: `{INDICATOR}_{CONDITION}_{Buy|Sell}`. Flat param keys can be added to `PARAM_KEY_MAP` in `lib/agent_strategy.py` so they propagate from YAML `live_params` to `indicator_settings`.
- **Adding an agent strategy bundle** — append a new entry under `agent_strategies:` in `config/strategy_config.yaml` with the standard keys (`description`, `ticker`, `buy_signals`, `sell_signals`, `mode`, `live_params`, `search_space`, optional `signal_logic`, `signal_window`); `sfa list` will surface it and every downstream command will accept it.
- **Adding a CLI subcommand** — create a `lib/cli/commands/<name>_cmd.py` that exposes `register(app: typer.Typer)` and import it in `lib/cli/app.py:build_app`; emit a stable JSON contract via the dataclasses in `lib/cli/contracts.py`. All subcommands should support `--json`.
- **Adding a Dash callback** — drop a module under `lib/dash/callbacks/`, expose `register_<concern>_callbacks(app)`, and invoke it from `lib/dash/callbacks/__init__.py`. Layout regions live under `lib/dash/layout/`, one file per UI region. Shared helpers go in `callbacks/shared.py`.
- **Adding a dashboard route** — extend `_shell_routes` in `lib/dash/integrated_dashboard.py` to wrap the same `app.index()` shell, and bind URL → load via `lib/dash/routes.py`. New HTML overlays can be served through `app.server.route(...)` like the `/flow_report.html` hook.
- **Swapping the broker** — implement the `Broker` protocol in `lib/live/broker.py` (with `subscribe_bars`, `place_order`, `cancel_order`, `account`, `positions`, `server_time`) and pass an instance into `PaperRunner`. `MockBroker` and `IBBroker` are reference implementations; tests ship with `lib/tests/test_broker_mock.py`.
- **Adding a guard** — implement `def <name>_guard(snapshot, config) -> GuardResult` in `lib/live/guards.py`; thresholds are read from `config/agent.yaml:guards.*`.
- **Adding a metric for optimisation** — extend `lib/bayesian_optimization.py` and `lib/backtest_result.metrics_from_result_df` together, then expose the new name through `sfa optimise --metric`. Composite weighting lives in `config/agent.yaml:optimiser.composite_weights`.
- **Extending walk-forward** — additional aggregation rules go in `lib/walkforward/verdict.py` (`aggregate()`); additional space specifications go in `lib/walkforward/spaces.py`. New gate checks extend `evaluate_gate()` in `lib/promotion/gate.py`.
- **Switching data source** — wrap the new client behind a function with the `fetch_data(ticker, start, end) -> DataFrame` shape used by `lib/data_processing.py` and `lib/agent_strategy.prepare_dataframe`.
- **Ticker universe** — regenerate via `scripts/build_universe.py` writing to `config/tickers_universe.csv` (hand-maintained non-equities are merged in from `config/tickers_curated.csv`); read through `lib/ticker_universe.py`. The loader falls back to a minimal bootstrap list and `resolve_universe_ticker()` in `lib/data_processing.py` if the CSV is absent.
- **Theming** — palettes are declared under `THEMES` in `lib/dash/dash_config.py`; `DEFAULT_THEME` is `bloomberg` and `THEME_CYCLE` (`bloomberg` → `cvd` → `light`) is the order the header button walks. There is no YAML override.
- **Test surface** — `lib/tests/` holds 46 test files grouped by area (strategy engine, signals and regime gating, backtest, optimisation, walkforward, promotion, CLI contracts, runner safety, broker mock, dashboard startup/routing/data/layout, chart payload, execution explainer, symbol search and watchlists, fundamentals, flow scanner). Run with `rtk python -m pytest lib/tests/ -q`.
