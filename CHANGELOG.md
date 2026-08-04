# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Fixed
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
