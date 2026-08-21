# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **`lib/sessions.py` — the session model** (ROADMAP 3.9). One place decides where a
  trading session ends and the next begins, inferred from the bar timestamps alone so no
  exchange calendar is needed: every bar on a daily tape, and on an intraday tape any
  step more than 1.5× the tape's own bar spacing. That threshold is deliberately narrow —
  Tokyo's 90-minute lunch break is exactly 1.5 steps and stays *inside* the session,
  CME's hour-long maintenance break is 2 steps and does not.
- `backtest()` gained `gap_fills` (default **on**), and its result frame gained
  `Session_Start` and `Holding_Sessions`. A caller holding a real exchange calendar can
  put a `Session_Start` column on the input frame and the inference is skipped.
- The trade ledger gained `holding_sessions`, and `BacktestMetrics` gained
  `avg_holding_sessions`: `holding_bars` counts bars of tape and so cannot tell you
  whether a position was held overnight. This one can.
- `resample_ohlcv(..., session_anchored=False)` for the pre-3.9 wall-clock bucketing.

- **`lib/signals/signals_STOCH.py` — the Stochastic oscillator, eighth indicator**
  (ROADMAP 2.6, 2.9). `STOCH_K` / `STOCH_D` plus six signals: `STOCH_Oversold_Buy`,
  `STOCH_Overbought_Sell`, `STOCH_Cross_{Buy,Sell}` and `STOCH_Reversal_{Buy,Sell}`.
  The reversal pair is the plain %K/%D cross *qualified* by having just left an extreme
  zone — the same exit-the-zone framing as `CCI_Reversal_*`, because a cross while still
  sinking deeper into the zone is a falling knife. Wired end to end: YAML defaults, the
  runtime settings mappers, `stoch_*` keys in `PARAM_KEY_MAP` for the optimizers, an
  indicator pane in the chart payload, and SIGNALS-panel descriptions.
  **Registered default-off** (`DEFAULT_OFF_SIGNAL_CATEGORIES`), so no existing default
  run changes its results — the default-on set is still BB / MACD / RSI / CCI.
- **`lib/metrics/` — one metrics engine** (ROADMAP 3.11). Every performance metric in the
  project now has exactly one implementation: `core.py` holds the primitives, `engine.py`
  holds `BacktestMetrics` and `compute_metrics`, `ledger.py` owns the trade-ledger shape,
  and `names.py` is a registry mapping each metric's canonical name to its UI name, unit
  and formatter. `lib/tests/test_metrics.py` pins Sharpe, Sortino and Calmar against
  hand-computed references — nothing anywhere did that before, which is how four
  implementations managed to drift apart.
- `BacktestMetrics` gained `cagr`, `num_fills`, `open_trades`, `avg_win`, `avg_loss`,
  `expectancy`, `avg_holding_bars`, `total_fees` and `exposure`. The nine existing fields
  keep their names, so the `sfa` JSON contract is a superset of what it was.
- `metrics.risk_free_rate` in `config/agent.yaml`.

### Changed
- **⚠️ Backtest results move: the trailing stop now honours overnight gaps**
  (ROADMAP 3.9.4). On a session's first bar, a market that reopens at or below the
  trailing stop has *gapped through* it — the stop could not be worked while the exchange
  was shut, so it fills at the **open**, not at the close. This applies in both stop
  modes and on daily tapes, where every bar opens a session. On the pinned engine
  snapshot eight of twenty-one round trips changed exit price (the trade count did not
  move); `gap_fills=False` reproduces the old numbers exactly.
- **⚠️ Intraday annualisation moves** (ROADMAP 3.9.2). `PERIODS_PER_YEAR` is now
  252 sessions × the bars a session actually emits, not a session duration divided by a
  bar size. Yahoo returns **seven** 1h bars for a 6.5-hour US session (09:30 … 15:30, the
  last a 30-minute stub), so `1h` is `1764` (was `1638`) and `4h` is `504` (was `410`).
  Every Sharpe, Sortino and CAGR on a 1h or 4h run rises by the square root of the ratio;
  daily is untouched. `lib/tests/test_sessions.py` checks the map against a synthetic
  tape rather than trusting the arithmetic.
- **4h bars are bucketed from each session's open, not the wall clock**
  (ROADMAP 3.9.1). A 4h bar can no longer contain the tail of one session and the head of
  the next — on an overnight futures tape the old wall-clock 16:00 bucket held both. Bar
  labels are now real bar timestamps: a US 1h tape resamples to 09:30 and 13:30, where it
  used to be labelled 08:00 and 12:00, times at which the exchange was shut.
- **⚠️ Metric values move.** Three deliberate changes, each altering numbers you have
  already seen:
  1. **One risk-free convention, now `0.0`** (was `0.02` on the production path,
     `0.0` in `lib/strategy.calculate_metrics`). Every Sharpe and Sortino rises slightly.
     The promotion gate's `min_oos_sharpe_mean: 1.0` therefore becomes easier to clear,
     and trials already in `state/optuna.db` are no longer comparable with new ones.
  2. **`num_trades` now counts closed round trips, not fills.** It is read from the
     engine's trade ledger instead of reconstructed by scanning the `Units` column. Counts
     drop sharply for anything that scales in — a real SPY run went from 69 to 15 — so the
     optimizer's Min-Trades floor of `10` is now a genuine ten-round-trip floor. The fill
     count survives as `num_fills`. Accumulation mode reports `num_trades == 0`, because
     nothing closes; `open_trades` carries the information there.
  3. **Calmar's numerator is now the geometric CAGR** off the equity curve, rather than
     the arithmetic mean compounded (`(1 + mean) ** ppy - 1`).
  Win rate and profit factor also shift wherever a scale-in or partial exit made the old
  `Units` scan disagree with the ledger.
- The Backtest tab and the optimizer now read the same metrics object.
  `create_backtest_results` and its divergent mixed-unit dict are gone.
- The combinatorial optimizer threads the bar interval into its metrics call, so 1h and
  4h searches stop annualising at 252 (ROADMAP 3.11.4).
- `Total_Return_%`, `Sharpe_Ratio` and the rest of the `Title_Case` UI vocabulary now come
  from `lib/metrics/names.py` instead of being retyped in seven modules. **The strings
  themselves are unchanged**, so persisted optimizer run history keeps working.
- The optimizer's initial sort key is `Robustness_Score` everywhere.
  `lib/dash/layout/shell.py` defaulted its store to `Total_Return_%` while the callback
  fell back to `Robustness_Score`.

### Fixed
- **The Backtest tab was showing three metrics wrong.** `create_backtest_results` returned
  drawdown and win rate as fractions while the tab formatted and thresholded them as
  percents: a 6.7% drawdown rendered as `-0.07%` and its badge read **CONTROLLED** for
  every backtest ever run, a 64% win rate rendered as `0.6%` and read **BELOW 50%** always,
  and **Trade Count was permanently 0** because the dict never contained the
  `num_trades` key the tab read. All three now show real values.
- `lib/dash/callbacks/optimizer_grid.py` and `optimizer_phase3.py` labelled a fraction
  read off `BacktestMetrics` as a percentage in three places, so a +20% return displayed
  as `+0.2%`.

### Removed
- **`lib/WIP/`** — `ML_strategy.py`, `WIP_Stochastic_oscillator.py`,
  `WIP_Market_Analysis_Trader.py` and `ML_tester.ipynb` (ROADMAP 2.6). Only the
  Stochastic oscillator was worth keeping, and it was promoted (above). The rest did not
  survive review: both ML files trained on a `Close.shift(-1)` target through a shuffled
  `train_test_split` — look-ahead in the label *and* in the split — and one of them
  derived its target from the very rule-based Buy/Sell columns it was meant to replace.
  `ML_strategy.py` could not have run in any case: `sklearn` is not a dependency and its
  `backtest()` call predated the current signature by two required arguments.
  `WIP_Market_Analysis_Trader.py` took a `List[float]`, fabricated a 2023 date index, and
  scored itself with its own return calculation. Also removed: the orphaned `ml_strategy`
  block in `config/strategy_config.yaml` and `ConfigLoader.get_ml_config`, which had no
  callers left, and the `lib.WIP*` mypy exclusion.
- `lib/params_optimization.py`, `lib/weights_optimization.py` and
  `lib/signal_combo_optimisation.py` — three modules with **zero importers** between them
  (the last was reached only by its own test, with every metric mocked). They held three
  of the four disagreeing Sharpe implementations. The live combinatorial search is, and
  was, `lib/dash/helpers.py:evaluate_signal_combination`.
- `lib/dash/helpers.py:calculate_performance_metrics` — dead, and broken: it read a
  `Position` column the engine has never emitted.
- The metric functions in `lib/data_processing.py` (`calculate_sharpe_ratio`,
  `calculate_max_drawdown`, `calculate_win_rate`, `calculate_profit_factor`,
  `calculate_average_trade_duration`) and `lib/strategy.py:calculate_max_drawdown`.
  `lib/strategy.py:calculate_metrics` remains as a thin adapter over the engine.

### Changed
- **`lib/dash/assets/dashboard.css` (4,183 lines) split into ten per-concern stylesheets**
  — `10-tokens.css`, `20-controls.css`, `30-vendor-widgets.css`, `40-chart.css`,
  `50-fundamentals.css`, `55-theme-light.css`, `60-execution.css`,
  `70-forms-responsive.css`, `80-command-palette.css`, `90-symbol-search.css`. The split
  is strictly sequential: concatenating the files in Dash's load order reproduces the old
  file byte for byte, so nothing about rendering changed. Vendored Bootstrap was renamed
  to `00-bootstrap.min.css` because Dash injects assets in sorted filename order and
  digits sort before letters — without the prefix the project sheets would have loaded
  *before* Bootstrap and lost every override. A new regression test pins that ordering.
  See [docs/ui-architecture.md](docs/ui-architecture.md) for the file map.

### Fixed
- The symbol-search sector dropdown now refills from the asset-class tab click itself
  rather than the `symbol-search-filters` store, which is written downstream of the
  dropdown and so still held the *previous* class when the options were rebuilt. Picking
  an asset class now immediately offers that class's sectors (and clears a selection the
  new class does not have) instead of lagging one click behind.
- **Rebalancing mode now sizes off portfolio value on both sides** (`lib/strategy.py`
  `_execute_buy` / `_execute_sell`). It previously bought a percentage of *remaining cash*
  — so consecutive buys decayed geometrically (25%, 18.75%, 14.1%…) — and sold a
  percentage of *units held*. Neither matched the mode's name, its UI label or its own
  docstring. **This changes results for every rebalancing backtest**; runs saved to
  `results/` before this change will not reproduce. Saved presets keep working.
- Execution Type mode cards no longer carry an inline style dict that overrode
  `.strategy-mode-card` in `dashboard.css`, which had silently disabled the card `:hover`
  and `:checked` states.
- The Trading mode `Scale-in` default is now 100% (was 25%), so one buy signal opens a
  full Kelly-sized entry instead of quietly quartering it.

### Added
- **Portfolio column group in the data table.** A fourth "Portfolio" toggle (on by
  default, alongside OHLCV / Indicators / Signals) exposes the execution columns the
  backtest engine writes — units held and traded, cash/stock/portfolio value, per-bar and
  cumulative returns, holding period, trailing stop, average entry price and cost basis,
  and the accepted/rejected trigger flags. The table now colours these to make a run
  readable at a glance: accepted buy and sell triggers are tinted green and red, rejected
  triggers orange, `Close` is coloured against `Open`, and `Returns` / `Strategy_Returns`
  outliers outside the 2.5–97.5 percentile band are highlighted (skipped when there are
  fewer than 20 finite values to measure).
- **Execution Type explainer.** Each mode card now shows a live preview of what the first
  buy signal actually does in dollars, plus an equity-curve fingerprint; a new
  "HOW EXECUTION WORKS" modal adds a three-column mechanics matrix and an interactive
  sandbox with predict-then-reveal and per-mode progress. Every figure is produced by
  `lib/dash/execution_sim.py`, which runs the real `backtest()` over a fixed 24-bar tape,
  so the explanations cannot drift from the engine. New modules:
  `lib/dash/execution_glossary.py`, `execution_sim.py`, `execution_view.py`,
  `lib/dash/callbacks/execution_help.py`.
- A warning when sell signals are selected in Accumulation mode, which discards them.
- **Signal Optimizer overhaul**: the optimizer now scores each combination with the shared, tested metrics engine (`metrics_from_result_df`), surfacing Sortino, Calmar, win rate, profit factor and turnover alongside return/Sharpe/drawdown. Added a per-combo **buy-and-hold benchmark and Alpha %**, a **Min Trades** reliability floor that flags and deprioritises "low sample" combos, a **robustness-weighted default ranking** (with new SCORE and CALMAR sort options), a multiple-testing honesty caption on completion, and richer Best Strategy card + results table.
- **Flow Scanner** for options flow analysis: a new `/flow/<ticker>` route and dashboard overlay, with educational insights, sentiment categorization, and per-contract signals surfaced in the flow glossary and contract table.
- **Fundamentals module**: fundamental analysis helpers with unit tests, a dedicated page with ticker input, quarterly financial data handling, a live price snapshot attached to financial results, and valuation/metric explainability (detailed explanations, big-five metric highlighting, ESC signal input).
- **`sfa` research CLI**: a command skeleton built around a `BacktestResult` dataclass, an Optuna-based Bayesian optimiser (a fourth optimisation flavour), walk-forward validation with gated promotion, and a paper-trading layer (Broker protocol with an async runner).
- **Research sweep workflows**: `sweep-single` and single-target modes, seeded exploration mode, a sample-universe command, a ticker override for the optimise command, and ETF categorization in sweep instructions.
- **New trading strategies** and expanded strategy configuration, with enhanced backtest metrics calculation.
- Color-vision-deficiency (CVD) safe theme as the default palette, overridable via `config/strategy_config.yaml`, plus refreshed dashboard theming and CSS.
- Default dashboard landing page that opens `http://127.0.0.1:<port>/ticker/<DEFAULT_TICKER>` on launch, an opt-in dashboard reload option, and clientside Y-axis auto-ranging for financial charts.
- Expanded ticker search universe (adds Rocket Lab, MicroStrategy, Rivian, SoFi, Snowflake, plus NASDAQ-100 and Russell 2000 constituents) and a script to generate a comprehensive ticker universe.
- Deployment and startup tooling: `run_dashboard_latest.ps1` launcher with `KillAll`/`NoOpen`/`Foreground` options; `SkipPipInstall` and `SkipRestartDashboard` deploy parameters; server permission-fix scripting; and a rollback mechanism for promotion-history write failures.
- Project scaffolding: `AGENTS.md`, agent configuration, environment example, and a `justfile`.

### Changed
- Execution Type labels rewritten to match the engine: "Trading — Full Buy/Sell"
  (which never bought 100%) is now "Trading — Signal In/Out", and "Rebalancing — Partial"
  is now "Rebalancing — Target Weight". The `Position Scaling` control is renamed
  `Scale-in` and `Position Size` is renamed `Portfolio Weight`.
- `UI_STORAGE_VERSION` bumped to `5` for the new `execution-explored-store`.
- Development mode is now enabled by default at the main entry point.
- Chart hover tooltips are unified across subplots for consistent readability.
- Fundamentals growth-estimation logic reworked for more reliable calculations.
- Deployment hardened: improved SSH option and connection handling, POSIX-ACL-based permission management for non-root deploys, and safer SCP path handling/quoting.
- Raised the minimum Python version and added determinism/seed helpers for reproducible research runs.
- Streamlined `AGENTS.md`, `CLAUDE.md`, and `README.md`, and improved tooltip, table, and layout styling across the fundamentals page.

### Fixed
- **Optimizer showed a fake "+0.0% return" winner**: `evaluate_signal_combination` read a non-existent `Position` column, so every combination silently threw `KeyError: 'Position'` and was swallowed by a bare `except`. Because the "all failed" guard only checked for an empty results list (not one full of error rows), the panel rendered the first error as a 0% strategy. The optimizer now computes trade counts and metrics from real result columns and reports honest failures ("All combinations failed") when every combo errors.
- Date handling in the integrated dashboard and yearly close-price calculation in fundamentals.
- Callback initialization behavior in fundamentals and routing (`initial_duplicate`) for more predictable overlay and tab handling.
- Trade-count calculation in signal-combination evaluation, which now counts actual buy/sell executions (`Units_to_buy` / `Units_to_sell`) instead of dividing position-change deltas by two.
- Chart container sizing so the `dcc.Loading` wrapper is full-height, preventing the chart from collapsing when its `height:100%` had nothing to resolve against.

### Removed
- TradingView chart integration, to streamline the dashboard.
- Obsolete Cursor rules file.
