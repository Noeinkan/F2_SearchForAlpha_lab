# SearchForAlpha Lab — Roadmap

Where the project stands, in one page. `[x]` is shipped and in the repo today; `[ ]` is open work.
Details behind the ticks live in [CHANGELOG.md](CHANGELOG.md) (what changed) and
[product.md](product.md) (what the platform does).

**Last reviewed:** 2026-08-21

---

## 1. 📡 Data & Market Access

- [x] 1.1 Validated Yahoo OHLCV fetch with NaN warnings above 10% — [lib/data_processing.py](lib/data_processing.py) <!-- size: M -->
- [x] 1.2 1d / 1h / 4h intervals, per-interval annualisation, Yahoo's 728-day intraday clamp — [lib/timeframes.py](lib/timeframes.py) <!-- size: M -->
- [x] 1.3 On-disk OHLCV cache — [lib/dash/ohlcv_disk_cache.py](lib/dash/ohlcv_disk_cache.py) <!-- size: M -->
- [x] 1.4 ~13k-symbol committed universe with sector / industry / asset class — [lib/ticker_universe.py](lib/ticker_universe.py), `config/tickers_universe.csv` <!-- size: L -->
- [x] 1.5 Hand-maintained non-equity sleeve merged from `config/tickers_curated.csv` <!-- size: S -->
- [x] 1.6 Symbol-search modal (`Ctrl + /`) with named watchlists persisted to disk — [lib/dash/watchlist_storage.py](lib/dash/watchlist_storage.py) <!-- size: L -->
- [x] 1.7 Live quote snapshots for the visible page of search results — [lib/dash/symbol_quotes.py](lib/dash/symbol_quotes.py) <!-- size: M -->
- [x] 1.10 Yahoo 429 / 5xx retried with backoff, then surfaced as a distinct `RATE LIMITED` state rather than a generic error — [lib/fetch_errors.py](lib/fetch_errors.py) <!-- size: S -->
- [x] 1.11 Corporate actions audited — adjustment stated explicitly, action columns kept out of the pipeline, 4h resample no longer drops dividends — [docs/data-adjustment.md](docs/data-adjustment.md) <!-- size: M -->
- [x] 1.12 Vendor seam extracted (`_yahoo_history`), so a second source only has to return an OHLCV frame <!-- size: S -->
- [ ] 1.8 A second data vendor behind the seam — **no free option found**: Stooq's keyless endpoint is now behind a JS browser challenge, and every alternative needs an API key. Survey: [docs/data-vendors.md](docs/data-vendors.md) <!-- size: L -->
- [ ] 1.9 Intraday history beyond Yahoo's 728-day cap — **no free option found**: Alpha Vantage's 20-year intraday is premium-gated, Tiingo reaches 2016 but on IEX-only volume which breaks VWAP/OBV. Reopens if a consolidated-volume intraday source appears <!-- size: M -->

## 2. 📐 Signals & Indicators

- [x] 2.1 Seven auto-discovered strategy classes — RSI, BB, MACD, EMA, SMA, CCI, VWAP — [lib/signals/](lib/signals/) <!-- size: L -->
- [x] 2.2 ADX / ATR / OBV regime indicators <!-- size: M -->
- [x] 2.3 Regime-gated strategy variants <!-- size: M -->
- [x] 2.4 `{INDICATOR}_{CONDITION}_{Buy|Sell}` column convention, enforced across UI, optimizer and CLI <!-- size: M -->
- [x] 2.5 Flat param keys mapped to nested indicator settings via `PARAM_KEY_MAP` — [lib/agent_strategy.py](lib/agent_strategy.py) <!-- size: S -->
- [ ] 2.6 Decide the fate of [lib/WIP/](lib/WIP/) — `ML_strategy.py`, `WIP_Stochastic_oscillator.py`, `WIP_Market_Analysis_Trader.py`: promote to real strategies or delete <!-- size: M -->
- [ ] 2.7 ML-built signals (nothing in the shipped indicator set is learned) <!-- size: XL -->
- [ ] 2.8 Order-book microstructure and sentiment inputs <!-- size: XL -->

## 3. 🧮 Backtest Engine

- [x] 3.1 Event-driven engine with `trading` / `accumulation` / `rebalancing` modes — [lib/strategy.py](lib/strategy.py) <!-- size: XL -->
- [x] 3.2 Trailing stop, take profit, position sizing, commission, slippage, FX fee <!-- size: L -->
- [x] 3.3 Nine-metric `BacktestMetrics` computed from closed round-trips — [lib/backtest_result.py](lib/backtest_result.py) <!-- size: M -->
- [x] 3.4 Rebalancing sizes off portfolio value on **both** sides (was cash on buy, units on sell) <!-- size: S -->
- [x] 3.5 Execution Type explainer driven by the real engine over a fixed 24-bar tape — [lib/dash/execution_sim.py](lib/dash/execution_sim.py) <!-- size: M -->
- [x] 3.6 Portfolio column group in the data table — units, cash/stock/portfolio value, holding period, trailing stop, accepted vs rejected triggers <!-- size: M -->
- [ ] 3.7 Limit / stop / bracket order simulation — the engine is market-only <!-- size: L -->
- [ ] 3.8 Multi-asset portfolio backtests — one ticker per run today <!-- size: XL -->
- [ ] 3.9 Intraday session-gap handling (overnight gaps on 1h/4h tapes) <!-- size: M -->
- [ ] 3.10 Deflated Sharpe and benchmark-relative metrics beyond the optimizer's Alpha % <!-- size: M -->

## 4. 🎯 Optimizer & Validation

- [x] 4.1 Per-indicator parameter sweeps — [lib/params_optimization.py](lib/params_optimization.py) <!-- size: M -->
- [x] 4.2 Signal-combination combinatorial search — [lib/signal_combo_optimisation.py](lib/signal_combo_optimisation.py) <!-- size: L -->
- [x] 4.3 Indicator-weight optimisation — [lib/weights_optimization.py](lib/weights_optimization.py) <!-- size: M -->
- [x] 4.4 Optuna TPE Bayesian search, resumable against `state/optuna.db` — [lib/bayesian_optimization.py](lib/bayesian_optimization.py) <!-- size: L -->
- [x] 4.5 Grid search — [lib/grid_search.py](lib/grid_search.py) <!-- size: M -->
- [x] 4.6 Full-screen optimizer workspace: landscape, search-space viz, run history, glossary — [lib/dash/layout/optimizer_workspace.py](lib/dash/layout/optimizer_workspace.py) <!-- size: XL -->
- [x] 4.7 Scoring through the shared metrics engine — Sortino, Calmar, win rate, profit factor, turnover <!-- size: M -->
- [x] 4.8 Buy-and-hold benchmark and Alpha % per combination <!-- size: S -->
- [x] 4.9 Min-Trades reliability floor and robustness-weighted default ranking <!-- size: M -->
- [x] 4.10 Rolling walk-forward with a `WindowVerdict` robustness flag — [lib/walkforward/](lib/walkforward/) <!-- size: L -->
- [x] 4.11 Walk-forward validation launched from the optimizer panel — [lib/dash/combo_walkforward.py](lib/dash/combo_walkforward.py) <!-- size: M -->
- [x] 4.12 Gated promotion with an audit trail — [lib/promotion/gate.py](lib/promotion/gate.py), `config/param_history.yaml` <!-- size: L -->
- [ ] 4.13 Compute the multiple-testing correction (deflated Sharpe), not just the honesty caption <!-- size: M -->
- [ ] 4.14 Multi-ticker sweep from the UI — CLI-only today via `sfa sweep-single` <!-- size: L -->
- [ ] 4.15 Automated regime slicing against the [RESEARCH.md](RESEARCH.md) regime calendar <!-- size: L -->
- [ ] 4.16 Persist and compare optimizer runs across sessions <!-- size: M -->

## 5. 🖥️ Dashboard & UX

- [x] 5.1 `integrated_dashboard.py` split into a twelve-module `layout/` package — [lib/dash/layout/](lib/dash/layout/) <!-- size: L -->
- [x] 5.2 Collapsible sidebars and a keyboard-resizable splitter — [lib/dash/layout/shell.py](lib/dash/layout/shell.py), [lib/dash/callbacks/layout.py](lib/dash/callbacks/layout.py) <!-- size: M -->
- [x] 5.3 Command palette (`Ctrl + K`) with a keyboard-shortcut help view — [lib/dash/layout/command_palette.py](lib/dash/layout/command_palette.py) <!-- size: M -->
- [x] 5.4 Three themes — `bloomberg` (default), CVD-safe, light — cycled from the header — [lib/dash/dash_config.py](lib/dash/dash_config.py) <!-- size: M -->
- [x] 5.5 `:focus-visible` rings across every interactive control <!-- size: S -->
- [x] 5.6 Ten numbered stylesheets replacing the 4,183-line `dashboard.css`, with a load-order regression test — [docs/ui-architecture.md](docs/ui-architecture.md#stylesheet-layout) <!-- size: L -->
- [x] 5.7 TradingView Lightweight Charts rendered client-side from `chart-payload-store` — [lib/dash/chart_payload.py](lib/dash/chart_payload.py), `assets/10-sfa-chart.js` <!-- size: XL -->
- [x] 5.8 Crosshair legend with overlay and pane values <!-- size: M -->
- [x] 5.9 Status bar wired to the real callback lifecycle instead of a static `READY` — [lib/dash/callbacks/status.py](lib/dash/callbacks/status.py) <!-- size: M -->
- [x] 5.10 Deep-link routes: `/`, `/ticker/<t>`, `/fundamentals/<t>`, `/flow/<t>`, `/flow_report.html` — [lib/dash/routes.py](lib/dash/routes.py) <!-- size: M -->
- [x] 5.11 UI presets saved to `config/ui_presets.json` <!-- size: S -->
- [x] 5.12 Data table with OHLCV / Indicators / Signals / Portfolio column groups and outlier highlighting <!-- size: L -->
- [ ] 5.13 Global `error-boundary` for unhandled callback exceptions — planned in the UI overhaul, never built <!-- size: M -->
- [ ] 5.14 Empty-state polish for the chart area, results panel and signal list before first load <!-- size: S -->
- [ ] 5.15 Persist panel state to disk — [lib/dash/state.py](lib/dash/state.py) is in-memory; only presets and watchlists survive a restart <!-- size: M -->
- [ ] 5.16 Options pricing tab (see below) <!-- size: S -->

## 6. 🧊 Options & Flow

- [x] 6.1 Flow Scanner ranking unusual contracts by volume vs open interest, OTM / weekly flags, premium tiers — [scripts/flow_scanner.py](scripts/flow_scanner.py) <!-- size: L -->
- [x] 6.2 `/flow/<ticker>` route, dashboard overlay and standalone `flow_report.html` <!-- size: M -->
- [x] 6.3 Gamma-exposure and Vanna ladders — [lib/options/greeks.py](lib/options/greeks.py), [lib/dash/flow_gex.py](lib/dash/flow_gex.py), [lib/dash/flow_vanna.py](lib/dash/flow_vanna.py) <!-- size: L -->
- [x] 6.4 Chain panel with filtering, contract inventory and a fullscreen diagram <!-- size: M -->
- [x] 6.5 Flow glossary and an educational modal (calls vs puts, strikes, volume vs OI, how the unusual score works) <!-- size: M -->
- [ ] 6.6 The Options pricing tab from [docs/OPTIONS_INTEGRATION.md](docs/OPTIONS_INTEGRATION.md) — payoff and greeks surface, `lib/dash/callbacks/options_pricing.py`, the `sfa options` command. Only the shared greeks module exists today, and it serves the flow panels <!-- size: XL -->
- [ ] 6.7 Replace the best-effort Yahoo-screener scrape with a resilient chain source <!-- size: M -->
- [ ] 6.8 Schedule [scripts/flow_runner.py](scripts/flow_runner.py) so reports refresh without a manual run <!-- size: S -->

## 7. 📊 Fundamentals

- [x] 7.1 SEC EDGAR XBRL as primary source, yfinance as fallback — no API key needed — [lib/fundamentals.py](lib/fundamentals.py) <!-- size: L -->
- [x] 7.2 Big-Five valuation card with a live price snapshot <!-- size: M -->
- [x] 7.3 Analyst targets with conditional styling <!-- size: S -->
- [x] 7.4 Discounted cash flow analysis — [lib/dcf.py](lib/dcf.py) <!-- size: M -->
- [x] 7.5 Metric explainability: detailed tooltips, dependency chips, formula breakdowns <!-- size: M -->
- [ ] 7.6 Quarterly statements from XBRL — quarterly data is yfinance-only <!-- size: M -->
- [ ] 7.7 First-class non-US coverage (currently fallback quality) <!-- size: L -->
- [ ] 7.8 Peer / sector comparison alongside the single-ticker card <!-- size: L -->
- [ ] 7.9 An explicit cache and refresh policy for fundamentals fetches <!-- size: S -->

## 8. 🤖 Research CLI & Paper Trading

- [x] 8.1 Thirteen `sfa` subcommands, every one with `--json` — [lib/cli/commands/](lib/cli/commands/) <!-- size: XL -->
- [x] 8.2 Stable JSON contracts for external agents — [lib/cli/contracts.py](lib/cli/contracts.py) <!-- size: M -->
- [x] 8.3 `sfa instructions` agent briefing (mode-aware, with rules and a numbered loop) <!-- size: M -->
- [x] 8.4 Seeded determinism — every trial records seed, wall time and git commit — [lib/seeds.py](lib/seeds.py) <!-- size: M -->
- [x] 8.5 SQLite store for trials, walk-forward windows, promotions, fills and runner state — [lib/store/](lib/store/) <!-- size: L -->
- [x] 8.6 Broker protocol with Mock and IB implementations — [lib/live/broker.py](lib/live/broker.py) <!-- size: L -->
- [x] 8.7 Four live guards — daily loss, position size, broker disconnect, clock drift — [lib/live/guards.py](lib/live/guards.py) <!-- size: M -->
- [x] 8.8 Paper runner with PID-file lifecycle, `sfa status` and `sfa kill --flatten` <!-- size: L -->
- [x] 8.9 `--mode live` refused unconditionally; the IB broker rejects the live port <!-- size: S -->
- [ ] 8.10 Decide whether live mode is ever unlocked, and what evidence would justify it — today it is a hard code-level refusal <!-- size: M -->
- [ ] 8.11 Limit orders in the live path — `Order` carries `limit_price` but only `MKT` is sent <!-- size: M -->
- [ ] 8.12 Multi-symbol / multi-strategy runner — one strategy and one ticker per process <!-- size: L -->
- [ ] 8.13 Reconnect and resume across the IB Gateway daily restart <!-- size: M -->
- [ ] 8.14 Alerting when a guard trips (the runner exits silently apart from the state row) <!-- size: S -->

## 9. 🧪 Docs, Testing & Infra

- [x] 9.1 60+ test files covering engine, signals, optimisation, walk-forward, promotion gate, runner safety, dashboard startup and routing, chart payload, symbol search, fundamentals and flow — [lib/tests/](lib/tests/) <!-- size: XL -->
- [x] 9.2 Ruff and mypy configured in `pyproject.toml`, wrapped in `just lint` / `just fmt` / `just mypy` <!-- size: M -->
- [x] 9.3 Architecture and usage docs — [docs/ui-architecture.md](docs/ui-architecture.md), [docs/backtest-toolbar-guide.md](docs/backtest-toolbar-guide.md), [docs/optimizer-panel-guide.md](docs/optimizer-panel-guide.md) (EN + IT) <!-- size: L -->
- [x] 9.4 Agent context tiering — [.claude/PROJECT_INDEX.md](.claude/PROJECT_INDEX.md), scoped `.cursor/rules/`, [AGENTS.md](AGENTS.md), [RESEARCH.md](RESEARCH.md) <!-- size: M -->
- [x] 9.5 Deployment tooling — `deploy.ps1` with rollback, nginx vhost, TLS and Windows service scripts under [scripts/](scripts/) <!-- size: L -->
- [ ] 9.6 **CI** — `.github/` has no `workflows/`, so pytest, ruff and mypy only run when someone remembers <!-- size: M -->
- [ ] 9.7 Widen mypy beyond `cli` / `walkforward` / `promotion` / `live` / `store` to `lib/dash`, `lib/signals` and `lib/strategy.py` <!-- size: L -->
- [ ] 9.8 Cut a tagged release — the entire changelog is still `[Unreleased]` against version `0.2.0` <!-- size: S -->
- [ ] 9.9 Coverage reporting <!-- size: S -->
- [ ] 9.10 Translate the remaining guides (only the toolbar and optimizer guides have `.it.md` versions) <!-- size: M -->

---

Educational and research use only. Not financial advice.
