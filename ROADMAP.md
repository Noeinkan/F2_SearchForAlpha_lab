# SearchForAlpha Lab — Roadmap

Where the project stands, in one page. `[x]` is shipped and in the repo today; `[ ]` is open work.
Details behind the ticks live in [CHANGELOG.md](CHANGELOG.md) (what changed) and
[product.md](product.md) (what the platform does).

**Last reviewed:** 2026-08-21

---

## 📡 Data & Market Access

- [x] Validated Yahoo OHLCV fetch with NaN warnings above 10% — [lib/data_processing.py](lib/data_processing.py)
- [x] 1d / 1h / 4h intervals, per-interval annualisation, Yahoo's 728-day intraday clamp — [lib/timeframes.py](lib/timeframes.py)
- [x] On-disk OHLCV cache — [lib/dash/ohlcv_disk_cache.py](lib/dash/ohlcv_disk_cache.py)
- [x] ~13k-symbol committed universe with sector / industry / asset class — [lib/ticker_universe.py](lib/ticker_universe.py), `config/tickers_universe.csv`
- [x] Hand-maintained non-equity sleeve merged from `config/tickers_curated.csv`
- [x] Symbol-search modal (`Ctrl + /`) with named watchlists persisted to disk — [lib/dash/watchlist_storage.py](lib/dash/watchlist_storage.py)
- [x] Live quote snapshots for the visible page of search results — [lib/dash/symbol_quotes.py](lib/dash/symbol_quotes.py)
- [ ] A second data vendor behind the `fetch_data(ticker, start, end)` shape — yfinance is the only wired source
- [ ] Intraday history beyond Yahoo's 730-day cap (needs a vendor that keeps deeper 1h bars)
- [ ] Surface Yahoo 429 / 5xx as a retryable UI error instead of an empty frame
- [ ] Audit corporate actions and dividend adjustment across the fetch path

## 📐 Signals & Indicators

- [x] Seven auto-discovered strategy classes — RSI, BB, MACD, EMA, SMA, CCI, VWAP — [lib/signals/](lib/signals/)
- [x] ADX / ATR / OBV regime indicators
- [x] Regime-gated strategy variants
- [x] `{INDICATOR}_{CONDITION}_{Buy|Sell}` column convention, enforced across UI, optimizer and CLI
- [x] Flat param keys mapped to nested indicator settings via `PARAM_KEY_MAP` — [lib/agent_strategy.py](lib/agent_strategy.py)
- [ ] Decide the fate of [lib/WIP/](lib/WIP/) — `ML_strategy.py`, `WIP_Stochastic_oscillator.py`, `WIP_Market_Analysis_Trader.py`: promote to real strategies or delete
- [ ] ML-built signals (nothing in the shipped indicator set is learned)
- [ ] Order-book microstructure and sentiment inputs

## 🧮 Backtest Engine

- [x] Event-driven engine with `trading` / `accumulation` / `rebalancing` modes — [lib/strategy.py](lib/strategy.py)
- [x] Trailing stop, take profit, position sizing, commission, slippage, FX fee
- [x] Nine-metric `BacktestMetrics` computed from closed round-trips — [lib/backtest_result.py](lib/backtest_result.py)
- [x] Rebalancing sizes off portfolio value on **both** sides (was cash on buy, units on sell)
- [x] Execution Type explainer driven by the real engine over a fixed 24-bar tape — [lib/dash/execution_sim.py](lib/dash/execution_sim.py)
- [x] Portfolio column group in the data table — units, cash/stock/portfolio value, holding period, trailing stop, accepted vs rejected triggers
- [ ] Limit / stop / bracket order simulation — the engine is market-only
- [ ] Multi-asset portfolio backtests — one ticker per run today
- [ ] Intraday session-gap handling (overnight gaps on 1h/4h tapes)
- [ ] Deflated Sharpe and benchmark-relative metrics beyond the optimizer's Alpha %

## 🎯 Optimizer & Validation

- [x] Per-indicator parameter sweeps — [lib/params_optimization.py](lib/params_optimization.py)
- [x] Signal-combination combinatorial search — [lib/signal_combo_optimisation.py](lib/signal_combo_optimisation.py)
- [x] Indicator-weight optimisation — [lib/weights_optimization.py](lib/weights_optimization.py)
- [x] Optuna TPE Bayesian search, resumable against `state/optuna.db` — [lib/bayesian_optimization.py](lib/bayesian_optimization.py)
- [x] Grid search — [lib/grid_search.py](lib/grid_search.py)
- [x] Full-screen optimizer workspace: landscape, search-space viz, run history, glossary — [lib/dash/layout/optimizer_workspace.py](lib/dash/layout/optimizer_workspace.py)
- [x] Scoring through the shared metrics engine — Sortino, Calmar, win rate, profit factor, turnover
- [x] Buy-and-hold benchmark and Alpha % per combination
- [x] Min-Trades reliability floor and robustness-weighted default ranking
- [x] Rolling walk-forward with a `WindowVerdict` robustness flag — [lib/walkforward/](lib/walkforward/)
- [x] Walk-forward validation launched from the optimizer panel — [lib/dash/combo_walkforward.py](lib/dash/combo_walkforward.py)
- [x] Gated promotion with an audit trail — [lib/promotion/gate.py](lib/promotion/gate.py), `config/param_history.yaml`
- [ ] Compute the multiple-testing correction (deflated Sharpe), not just the honesty caption
- [ ] Multi-ticker sweep from the UI — CLI-only today via `sfa sweep-single`
- [ ] Automated regime slicing against the [RESEARCH.md](RESEARCH.md) regime calendar
- [ ] Persist and compare optimizer runs across sessions

## 🖥️ Dashboard & UX

- [x] `integrated_dashboard.py` split into a twelve-module `layout/` package — [lib/dash/layout/](lib/dash/layout/)
- [x] Collapsible sidebars and a keyboard-resizable splitter — [lib/dash/layout/shell.py](lib/dash/layout/shell.py), [lib/dash/callbacks/layout.py](lib/dash/callbacks/layout.py)
- [x] Command palette (`Ctrl + K`) with a keyboard-shortcut help view — [lib/dash/layout/command_palette.py](lib/dash/layout/command_palette.py)
- [x] Three themes — `bloomberg` (default), CVD-safe, light — cycled from the header — [lib/dash/dash_config.py](lib/dash/dash_config.py)
- [x] `:focus-visible` rings across every interactive control
- [x] Ten numbered stylesheets replacing the 4,183-line `dashboard.css`, with a load-order regression test — [docs/ui-architecture.md](docs/ui-architecture.md#stylesheet-layout)
- [x] TradingView Lightweight Charts rendered client-side from `chart-payload-store` — [lib/dash/chart_payload.py](lib/dash/chart_payload.py), `assets/10-sfa-chart.js`
- [x] Crosshair legend with overlay and pane values
- [x] Status bar wired to the real callback lifecycle instead of a static `READY` — [lib/dash/callbacks/status.py](lib/dash/callbacks/status.py)
- [x] Deep-link routes: `/`, `/ticker/<t>`, `/fundamentals/<t>`, `/flow/<t>`, `/flow_report.html` — [lib/dash/routes.py](lib/dash/routes.py)
- [x] UI presets saved to `config/ui_presets.json`
- [x] Data table with OHLCV / Indicators / Signals / Portfolio column groups and outlier highlighting
- [ ] Global `error-boundary` for unhandled callback exceptions — planned in the UI overhaul, never built
- [ ] Empty-state polish for the chart area, results panel and signal list before first load
- [ ] Persist panel state to disk — [lib/dash/state.py](lib/dash/state.py) is in-memory; only presets and watchlists survive a restart
- [ ] Options pricing tab (see below)

## 🧊 Options & Flow

- [x] Flow Scanner ranking unusual contracts by volume vs open interest, OTM / weekly flags, premium tiers — [scripts/flow_scanner.py](scripts/flow_scanner.py)
- [x] `/flow/<ticker>` route, dashboard overlay and standalone `flow_report.html`
- [x] Gamma-exposure and Vanna ladders — [lib/options/greeks.py](lib/options/greeks.py), [lib/dash/flow_gex.py](lib/dash/flow_gex.py), [lib/dash/flow_vanna.py](lib/dash/flow_vanna.py)
- [x] Chain panel with filtering, contract inventory and a fullscreen diagram
- [x] Flow glossary and an educational modal (calls vs puts, strikes, volume vs OI, how the unusual score works)
- [ ] The Options pricing tab from [docs/OPTIONS_INTEGRATION.md](docs/OPTIONS_INTEGRATION.md) — payoff and greeks surface, `lib/dash/callbacks/options_pricing.py`, the `sfa options` command. Only the shared greeks module exists today, and it serves the flow panels
- [ ] Replace the best-effort Yahoo-screener scrape with a resilient chain source
- [ ] Schedule [scripts/flow_runner.py](scripts/flow_runner.py) so reports refresh without a manual run

## 📊 Fundamentals

- [x] SEC EDGAR XBRL as primary source, yfinance as fallback — no API key needed — [lib/fundamentals.py](lib/fundamentals.py)
- [x] Big-Five valuation card with a live price snapshot
- [x] Analyst targets with conditional styling
- [x] Discounted cash flow analysis — [lib/dcf.py](lib/dcf.py)
- [x] Metric explainability: detailed tooltips, dependency chips, formula breakdowns
- [ ] Quarterly statements from XBRL — quarterly data is yfinance-only
- [ ] First-class non-US coverage (currently fallback quality)
- [ ] Peer / sector comparison alongside the single-ticker card
- [ ] An explicit cache and refresh policy for fundamentals fetches

## 🤖 Research CLI & Paper Trading

- [x] Thirteen `sfa` subcommands, every one with `--json` — [lib/cli/commands/](lib/cli/commands/)
- [x] Stable JSON contracts for external agents — [lib/cli/contracts.py](lib/cli/contracts.py)
- [x] `sfa instructions` agent briefing (mode-aware, with rules and a numbered loop)
- [x] Seeded determinism — every trial records seed, wall time and git commit — [lib/seeds.py](lib/seeds.py)
- [x] SQLite store for trials, walk-forward windows, promotions, fills and runner state — [lib/store/](lib/store/)
- [x] Broker protocol with Mock and IB implementations — [lib/live/broker.py](lib/live/broker.py)
- [x] Four live guards — daily loss, position size, broker disconnect, clock drift — [lib/live/guards.py](lib/live/guards.py)
- [x] Paper runner with PID-file lifecycle, `sfa status` and `sfa kill --flatten`
- [x] `--mode live` refused unconditionally; the IB broker rejects the live port
- [ ] Decide whether live mode is ever unlocked, and what evidence would justify it — today it is a hard code-level refusal
- [ ] Limit orders in the live path — `Order` carries `limit_price` but only `MKT` is sent
- [ ] Multi-symbol / multi-strategy runner — one strategy and one ticker per process
- [ ] Reconnect and resume across the IB Gateway daily restart
- [ ] Alerting when a guard trips (the runner exits silently apart from the state row)

## 🧪 Docs, Testing & Infra

- [x] 60+ test files covering engine, signals, optimisation, walk-forward, promotion gate, runner safety, dashboard startup and routing, chart payload, symbol search, fundamentals and flow — [lib/tests/](lib/tests/)
- [x] Ruff and mypy configured in `pyproject.toml`, wrapped in `just lint` / `just fmt` / `just mypy`
- [x] Architecture and usage docs — [docs/ui-architecture.md](docs/ui-architecture.md), [docs/backtest-toolbar-guide.md](docs/backtest-toolbar-guide.md), [docs/optimizer-panel-guide.md](docs/optimizer-panel-guide.md) (EN + IT)
- [x] Agent context tiering — [.claude/PROJECT_INDEX.md](.claude/PROJECT_INDEX.md), scoped `.cursor/rules/`, [AGENTS.md](AGENTS.md), [RESEARCH.md](RESEARCH.md)
- [x] Deployment tooling — `deploy.ps1` with rollback, nginx vhost, TLS and Windows service scripts under [scripts/](scripts/)
- [ ] **CI** — `.github/` has no `workflows/`, so pytest, ruff and mypy only run when someone remembers
- [ ] Widen mypy beyond `cli` / `walkforward` / `promotion` / `live` / `store` to `lib/dash`, `lib/signals` and `lib/strategy.py`
- [ ] Cut a tagged release — the entire changelog is still `[Unreleased]` against version `0.2.0`
- [ ] Coverage reporting
- [ ] Translate the remaining guides (only the toolbar and optimizer guides have `.it.md` versions)

---

Educational and research use only. Not financial advice.
