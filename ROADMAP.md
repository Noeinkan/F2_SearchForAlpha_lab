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

The open headlines below were each one line until 2026-08-21. They are broken out here
in the order they should be built. The metrics foundation came first, because all three
either add metrics or change what existing metrics mean; it and the session model are now
shipped.

### 3.11 Metrics foundation — one metrics engine ✅

Every metric now has exactly one implementation, in [lib/metrics/](lib/metrics/).
Before this, Sharpe existed four times with two different risk-free defaults (three of the
four in modules nothing imported), `num_trades` meant "fills" in one module and "closed
round-trips" in another, and the Backtest tab rendered a dict whose mixed units made its
drawdown and win-rate tiles wrong on screen.

- [x] 3.11.1 One implementation of Sharpe, Sortino, Calmar and max drawdown, with a single risk-free convention (`0.0`, set by `metrics.risk_free_rate` in `config/agent.yaml`) — [lib/metrics/core.py](lib/metrics/core.py) <!-- size: M -->
- [x] 3.11.2 Round-trip statistics read from the engine ledger everywhere; the `Units`-scan reconstruction is gone — [lib/metrics/ledger.py](lib/metrics/ledger.py) <!-- size: M -->
- [x] 3.11.3 `num_trades` settled as closed round-trips; the fill count survives as `num_fills` <!-- size: S -->
- [x] 3.11.4 `interval` threaded into the combo-search metrics call, so 1h/4h results stop annualising at 252 <!-- size: S -->
- [x] 3.11.5 Shared metric-name registry replacing the `Title_Case_%` literals — [lib/metrics/names.py](lib/metrics/names.py) <!-- size: M -->
- [x] 3.11.6 Backtest tab and optimizer read the same metrics object; `create_backtest_results` retired <!-- size: M -->

### 3.9 Intraday session-gap handling ✅

The engine was positionally indexed and knew nothing about sessions; the 4h resample bucketed on
the wall clock, so bars straddled the overnight boundary. Session boundaries now come from
[lib/sessions.py](lib/sessions.py), inferred from the bar timestamps with no exchange calendar.

- [x] 3.9.1 Anchor the 4h resample to the session open instead of the wall clock, so no bar straddles the overnight boundary — `resample_ohlcv(session_anchored=True)` in [lib/timeframes.py](lib/timeframes.py) <!-- size: M -->
- [x] 3.9.2 Reconcile `PERIODS_PER_YEAR` with the bar count the tape actually emits — `BARS_PER_SESSION`; 1h is 1764 (was 1638), 4h is 504 (was 410) <!-- size: S -->
- [x] 3.9.3 Mark session boundaries on the frame so the engine can tell an overnight gap from an intrabar move — `Session_Start`, overridable by the caller <!-- size: M -->
- [x] 3.9.4 Trailing stop honours overnight gaps — a gap-down through the stop fills at the open, not at the close (`gap_fills`, default on) <!-- size: M -->
- [x] 3.9.5 Holding period measured in session time, so a five-bar hold cannot silently span a weekend — `Holding_Sessions`, `holding_sessions`, `avg_holding_sessions` <!-- size: S -->
- [x] 3.9.6 Session model documented in the execution-model docstring and the backtest toolbar guide, both languages <!-- size: S -->

### 3.10 Deflated Sharpe and benchmark-relative metrics — also closes 4.13

Alpha % exists only in the combo-search path and is a naive arithmetic difference. The benchmark
series is already on every result frame and never rendered.

- [ ] 3.10.1 Benchmark return series promoted from an unrendered column into the metrics object <!-- size: S -->
- [ ] 3.10.2 Benchmark-relative metrics — alpha, beta, information ratio, tracking error, up/down capture — available to CLI, optimizer and Backtest tab alike <!-- size: M -->
- [ ] 3.10.3 Probabilistic Sharpe Ratio, skew- and kurtosis-aware, replacing the assumption that returns are normal <!-- size: M -->
- [ ] 3.10.4 Deflated Sharpe Ratio with the trial count folded in, wired to the combo count and the trials store <!-- size: M -->
- [ ] 3.10.5 New metrics exposed through the JSON contract, the leaderboard columns and the sort options <!-- size: M -->
- [ ] 3.10.6 Computed overfitting number replaces the prose honesty caption, in the app and in the optimizer guide <!-- size: S -->

### 3.7 Limit / stop / bracket order simulation — unblocks 8.11

Every fill is at the close of the bar; realism comes only from the signal lag. There is no order
abstraction at all — the closest precedent is the low-based trailing-stop check.

- [ ] 3.7.1 Order and Fill types with a resting-order book, market-only at first — a pure refactor that must leave the pinned engine snapshot unchanged <!-- size: L -->
- [ ] 3.7.2 Intrabar touch-and-fill against High and Low, generalising the existing low-based stop check <!-- size: M -->
- [ ] 3.7.3 A documented rule for bars where more than one resting order is touched <!-- size: S -->
- [ ] 3.7.4 Limit orders with a time-in-force knob <!-- size: M -->
- [ ] 3.7.5 Stop and stop-limit orders, with the bespoke trailing-stop branch expressed as a resting stop <!-- size: M -->
- [ ] 3.7.6 Bracket and OCO orders, extending the exit reasons and the trade ledger <!-- size: M -->
- [ ] 3.7.7 Order type reachable from the optimizers, the shared execution search space and the backtest toolbar <!-- size: M -->
- [ ] 3.7.8 Execution sandbox tape given real intrabar range so limit and stop fills can be demonstrated, plus an order-type mechanics row <!-- size: M -->
- [ ] 3.7.9 Order model documented in the execution-model docstring and both toolbar guides, with a results-change warning in the changelog <!-- size: S -->

### 3.8 Multi-asset portfolio backtests — converges with 4.14

The engine is scalar top to bottom: single `units`, single `cash`, 1-D price arrays, one ticker
per bundle. The live side is already multi-symbol; the backtest side is not.

- [ ] 3.8.1 Portfolio semantics decided and written down — shared cash or per-sleeve, rebalance cadence, and what happens when two symbols signal on one bar and cash is short <!-- size: S -->
- [ ] 3.8.2 Aligned multi-symbol panel on a common session-aware index <!-- size: M -->
- [ ] 3.8.3 Engine state generalised from scalars to per-symbol maps, with the single-symbol path preserved as the one-symbol case <!-- size: L -->
- [ ] 3.8.4 Portfolio-level cash, sizing and affordability across competing orders on the same bar <!-- size: L -->
- [ ] 3.8.5 Multi-symbol trade ledger and result frame <!-- size: M -->
- [ ] 3.8.6 Contract decision for a result that names many tickers instead of one, since external agents parse the current shape <!-- size: M -->
- [ ] 3.8.7 Portfolio-level metrics — contribution by symbol, correlation, concentration <!-- size: M -->
- [ ] 3.8.8 Ticker lists accepted by the CLI and the bundle schema, reusing the existing benchmark-group registry <!-- size: M -->
- [ ] 3.8.9 Multi-symbol selection and portfolio results in the dashboard <!-- size: L -->

## 4. 🎯 Optimizer & Validation

- [x] 4.1 Per-indicator parameter sweeps — via Optuna (4.4) and grid search (4.5); the standalone `lib/params_optimization.py` was deleted on 2026-08-21, unimported and holding a stale Sharpe <!-- size: M -->
- [x] 4.2 Signal-combination combinatorial search — `evaluate_signal_combination` in [lib/dash/helpers.py](lib/dash/helpers.py), driven by [lib/dash/callbacks/optimization.py](lib/dash/callbacks/optimization.py). The older Dask module `lib/signal_combo_optimisation.py` it superseded was deleted on 2026-08-21 <!-- size: L -->
- [ ] 4.3 Indicator-weight optimisation — `lib/weights_optimization.py` was deleted on 2026-08-21: nothing imported it, and it optimised signal-return correlation rather than any backtest metric. Reopen only with a stated objective <!-- size: M -->
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
