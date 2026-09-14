# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added
- **Quarterly fundamentals from SEC filings** (ROADMAP 7.6). For U.S. filers, the
  Fundamentals page's quarterly view now reads the same SEC company-facts file as the annual
  view, so it shows up to 40 quarters instead of the last five Yahoo returns. Income items
  are filed as three-month amounts and read directly. Cash-flow items are filed only as
  year-to-date totals, and no filing has a fourth quarter, so those quarters are the
  difference of two totals: Q4 is the full year minus the first nine months. A derived Q4
  EPS is approximate, because the share count moves during the year; the page notes this.
  On AAPL, MSFT and NVDA every quarter that overlaps Yahoo's matched within 0.5%. Yahoo
  quarters stay in use for non-U.S. symbols and when SEC has under four quarters (XOM).
  Quarter-end prices are now read at the filed period end (Apple's 27 September), not the
  calendar quarter end. The SEC code moved to `lib/fundamentals_sec.py`.
- **Fundamentals cache and refresh policy** (ROADMAP 7.9). Every visit to the Fundamentals
  page used to download the SEC file (3.8 MB for Apple) and call Yahoo up to seven times.
  Inputs are now kept in `state/fundamentals/`: SEC filings, Yahoo statements and price
  history for 24 hours (`SFA_FUNDAMENTALS_FILINGS_TTL_HOURS`), the Yahoo quote and analyst
  estimates for 15 minutes (`SFA_FUNDAMENTALS_QUOTE_TTL_MINUTES`), the SEC ticker map for
  7 days. A warm load of AAPL takes about 0.2 s instead of 5 s. **Refresh** refetches
  everything. When a refetch fails or comes back empty, the last good copy stays on screen,
  the status line says `REFETCH FAILED, SHOWING CACHED COPY`, and a note gives its date.
  `fetch_fundamentals(..., use_cache=False)` touches no cache; the demo freezer uses it.
- **Limit, stop and stop-limit orders in paper trading** (ROADMAP 8.11). The runner used to
  send a market order whatever the strategy said. It now reads `order_type`,
  `limit_offset_pct`, `stop_offset_pct`, `time_in_force` and `order_expiry_bars` from
  `live_params`, the same keys the backtest, the optimizer and `sfa promote` use.
  Prices come from the engine's own function, rounded to `runner.price_tick` (0.01) so
  that a buy limit is never rounded up and a stop never rounded nearer the market.
  Resting orders go to IB as LMT / STP / STP LMT with GTC or DAY and no longer block
  the bar loop. The runner checks them each bar, cancels an `ioc` order after one bar
  and any order after `order_expiry_bars`, as the backtest does, and replaces the
  working order when a new signal arrives on its side. `sfa_fills` gains `order_type`,
  `broker_order_id` and the statuses `working`, `partially_filled`, `cancelled` and
  `rejected`. `sfa status` shows `working_orders`, and a rejection sends an alert. The
  mock broker fills resting orders with `lib/orders.py`'s model, so the tests check
  paper fills against backtest fills. **Changed behaviour:** `sfa run` now refuses to
  start (`unsupported_live_params`, exit 2) when `live_params` sets an exit, sizing or
  signal-gating key the runner does not apply; before, it silently ignored them. No
  bundle in the repo sets one today. "Bars" are IB's 5-second bars; ROADMAP 8.15
  records that and the other paper/research differences found along the way.
- **The paper runner survives the IB Gateway daily restart** (ROADMAP 8.13). A heartbeat
  (`runner.heartbeat_seconds`, default 5) checks the connection and evaluates the guards
  whether or not bars arrive. When the connection drops it reconnects, waiting 2s, 4s,
  8s … up to 30s (`ib.reconnect`), then re-subscribes to bars. A drop inside the
  `ib.daily_restart` window (default 23:45 local, 15 minutes) does not trip
  `broker_disconnected`. A longer one still stops the runner once the window closes.
  **Match the time to IB Gateway's Auto restart setting.** Other fixes on the same path:
  - Guards used to run only when a bar arrived. A dead connection sends no bars, so
    `broker_disconnected` could never trip.
  - An exception in a bar handler used to end IB's bar stream for good.
  - An order waiting on a dropped connection used to wait forever.
  - A bar replayed with an old timestamp is now ignored.
- **Alerts** (ROADMAP 8.14). With `SFA_ALERT_WEBHOOK` set, the runner posts when a
  guard trips, when the broker refuses an order, and when the runner crashes. The
  payload suits Slack and Discord (`text` / `content`); ntfy.sh URLs get a plain-text
  push (`SFA_ALERT_FORMAT` overrides). Delivery is one attempt with a 5s timeout. It
  never raises, so an unreachable webhook cannot stop the shutdown. Setup: README,
  *Alerts on your phone*.
- **Basket backtests against one cash account** (ROADMAP 3.8.3, 3.8.4).
  `lib.portfolio.backtest_portfolio(panel, capital, sizer, params, buys, sells, **options)`
  runs every symbol of a `lib.panel` panel through one shared cash balance, taking the same
  keyword options as `backtest()`. It implements the rules in
  [docs/portfolio-semantics.md](docs/portfolio-semantics.md): orders are sized off the
  **total** portfolio value of the previous bar; each bar settles every symbol's sells
  before any symbol buys, so a same-bar sale funds a same-bar buy; buys that outrun the
  cash share it by the equal-share water-fill (`lib/engine/allocation.py`); and a bar a
  symbol did not print is valued at its last close but never traded. A stop the symbol
  reopens through after such a hole fills at the open, as it does after a weekend.
  Reversing the ticker list changes no unit, round trip or balance. In rebalancing mode
  `position_size_pct` defaults to an equal weight, `100 / number of symbols`. The result
  (`PortfolioResult`: per-symbol frames, a portfolio frame benchmarked against equal-weight
  buy-and-hold of the basket, combined ledgers) is **provisional** until 3.8.5–3.8.7, and
  nothing in the CLI or dashboard calls it yet.
- **The engine moved into `lib/engine/`** — config, account and per-symbol state, per-bar
  steps, the resting-order book, the allocation rule and the bar loop, one file each.
  `lib/strategy.py` keeps `backtest()`, `run_backtest()` and `calculate_metrics()`, and
  re-exports every name it exported before, so no import changes. **Single-symbol results
  do not change:** 603 configurations (every strategy mode × order type × exit model ×
  signal mode, on daily and hourly tapes) were compared before and after, and every
  result frame, trade and fill matched exactly; `test_strategy_snapshot` is untouched.
- **Flow Scanner reports refresh on their own** (ROADMAP 6.8). While the dashboard runs, a
  background thread rescans stale reports: the tickers in `watchlist.txt` plus every ticker
  already scanned from the page, at most 20. A report is stale after
  `SFA_FLOW_REFRESH_MINUTES` (default 15) while the US market is open, and once more after
  the close; nothing runs overnight or at weekends. There is no holiday calendar, so a
  holiday is scanned like a normal session. `SFA_FLOW_REFRESH_MINUTES=0` turns it off. An
  open `/flow/<ticker>` page swaps in the new report within a minute of it landing. Only
  `python main.py` starts the thread; the public demo does not.
- **One Flow Scanner report per ticker**, in `state/flow/<TICKER>.json` and `.html`. Before,
  every scan overwrote one `flow_report.json`, so `/flow/AAPL` showed whichever ticker had
  been scanned last. A failed scan no longer replaces a good report either: if Yahoo
  throttles a rescan, the page keeps the last good chain and the status line says
  `RATE LIMITED — kept the report from 14:05`. OPEN IN NEW TAB opens the current ticker's
  report (`/flow_report.html?ticker=AAPL`); a `flow_report.html` at the repo root, written
  by a manual CLI run, is still served at the bare URL. `lib/dash/flow_store.py`,
  `lib/dash/flow_refresh.py`.
- **The dashboard reopens where you left it** (ROADMAP 5.15). The symbol, bar interval,
  test window, capital, chart toggles, indicator settings, signal selection, trade setup,
  costs and order model are saved to `state/ui_session.json` as they change, and restored
  on the next start. Results are not saved: data is refetched and backtests are not
  replayed. A deep link to another symbol still wins; if the saved symbol no longer loads,
  the dashboard falls back to TSLA. `SFA_RESTORE_SESSION=0` turns it off, and the public
  demo has it off.
- **Error boundary** (ROADMAP 5.13). A callback that raises now shows a dismissible alert
  at the top right — which part of the page failed, and the error — and sets the status
  bar to `ERROR`. Before, it failed silently and the status bar stayed on `WORKING…`.
  Full traceback in the server log. `lib/dash/error_boundary.py`, via Dash's `on_error`.
- **Empty states** (ROADMAP 5.14) for the chart area, backtest results and signal list
  before they have content. The chart's overlay also shows why a chart came back empty,
  which the canvas never displayed.
- **Regime slicing — `sfa regimes` and the optimizer's REGIMES button** (ROADMAP 4.15).
  RESEARCH.md has always said a robust strategy should show positive Sortino in at least
  3 of its 7 market regimes, including the 2022 bear, but nothing computed it. Now a
  strategy is backtested **separately in each regime**: it starts flat with fresh capital,
  so a trade opened in one period is never scored in another. Indicators are computed
  once over the whole history before slicing, so each regime's first bars have warmed-up
  indicators. Each row shows Sortino, return, buy-and-hold return, drawdown and trade
  count, and the set gets a verdict.
- The verdict has three outcomes, not two. **Pass**: enough regimes clear the bar,
  required ones included. **Fail**: a required regime was scored and missed, or too few
  pass even if every regime without data had passed. **Inconclusive**: the regimes
  without data could still change the answer. That third state matters on
  intraday bars, where Yahoo history reaches back ~2 years and six of the seven regimes
  have no data: an hourly run cannot pass or fail the 2022 test, and says so instead of
  scoring it as a loss.
- `config/regimes.yaml` — the calendar and the rule in machine-readable form. RESEARCH.md
  stays the human reference (agents must not edit it), and
  `test_repo_calendar_matches_research_md_table` fails if the two drift. The table's one
  shared month (2020-02) is split at SPY's pre-COVID peak, 2020-02-19.
- `lib/regimes/` (calendar, slicer, bundle runner), `lib/dash/combo_regimes.py`,
  `lib/dash/regime_view.py`, `lib/dash/callbacks/optimizer_regimes.py`; 23 tests in
  `lib/tests/test_regimes.py`. Nothing is persisted and the promotion gate does not read
  the verdict yet.
- **`lib/panel.py` — many symbols on one index** (ROADMAP 3.8.2). The first piece of the
  multi-asset backtest, and pure data: `align_panel({symbol: frame})` returns a `Panel`
  where bar `i` is the same instant for every member, which is the property the portfolio
  engine (3.8.3) will be built on. Nothing calls it yet — the engine below it is still
  scalar — so no existing result moves.

  It implements [docs/portfolio-semantics.md](docs/portfolio-semantics.md) §6, whose one
  sentence is really two rules pulling opposite ways. **Valuation forward-fills**: a new
  `Mark` column carries the last close across a hole, because a halted name still belongs
  in portfolio value and §2 sizes every order off that total. **Execution does not**:
  `Open`/`High`/`Low`/`Close` stay `NaN` and a new `Tradable` column reads `False`, because
  forward-filling those would let a resting stop fill against a bar that never printed.
- Signal columns fill with `0` on a hole, not `NaN`. This is the trap the module exists to
  disarm: `{INDICATOR}_{CONDITION}_Buy` is int-coded, a reindex turns the gaps into `NaN`,
  and **`NaN` is truthy** — so a naive `df.reindex(...)` would have fired a buy on every
  bar a symbol did not trade. Boolean columns fill `False`; indicators keep their `NaN`.
- **Sessions are inferred once, on the merged index**, and written to every member as
  `Session_Start` — which `resolve_session_starts` already honours, so the engine picks up
  the basket's boundaries with no change. A hole in one symbol is no longer a session
  boundary for the basket, and `Panel.periods_per_year()` annualises at the bar count the
  *merged* tape emits rather than any one member's.
- The panel index is the **union** of its members' bars, not the intersection — an
  intersection deletes real trading in four symbols to avoid a hole in the fifth.
  `trim='common'` clips to the window every member was tradable in, for a fair-comparison
  basket. Ticker order changes nothing but `Panel.symbols`, the same commitment
  `CASH_ALLOCATION_RULE` makes in §4.
- `lib/tests/test_panel.py` — 40 tests over the hole rules, the signal-truthiness trap, the
  merged session mask, trimming, and the §8 degenerate case: a gapless one-symbol panel
  backtests to the same equity curve as the raw frame.
- `lib.sessions.bars_per_session_from_starts` — the counting half of `bars_per_session`,
  split out so a panel that already inferred its boundaries on the merged index is not
  forced to re-infer them per member.
- **`lib/orders.py` — an order model** (ROADMAP 3.7). Until now the engine had no order
  abstraction: every decision became a fill at the bar's close, and the only nod to
  intrabar reality was a bespoke branch comparing the trailing stop against `Low`. There
  is now an `Order` / `Fill` / `OrderBook` layer, and `backtest()` takes `order_type`
  (`market`, `limit`, `stop`, `stop_limit`), `limit_offset_pct`, `stop_offset_pct`,
  `time_in_force` (`gtc` / `day` / `ioc`), `order_expiry_bars`, `trailing_stop_orders`,
  `use_brackets`, `bracket_stop_pct` and `bracket_target_pct`.

  > ⚠️ **These change results, and that is the point.** Every default is chosen so that a
  > run which sets none of them reproduces the pre-3.7 numbers exactly — that equivalence
  > is what `test_strategy_snapshot` pins, and its constants are unchanged. But the moment
  > you select a limit order, entries that used to fill at the close may never fill at
  > all; the moment you select `trailing_stop_orders`, a bar whose *low* trips your stop
  > exits even though the close recovered. A strategy can look materially worse under
  > either, and the older, kinder number was the assumption, not the truth.
- Resting orders fill against the bar's High and Low: a limit fills at its level, or at
  the **open** when the bar opened through it (price improvement is real); a stop fills at
  its level, or at the **open** on a gap — the generalisation of the 3.9.4 gap rule to
  every resting order. A stop-limit that triggers past its limit does **not** fill at a
  worse price; it stays resting as a plain limit, which is exactly why a stop-limit can
  leave you holding a position a plain stop would have exited.
- **A stated rule for bars that touch more than one resting order** (3.7.3): orders
  marketable at the open fill first, then stops before limits, then nearest the open, then
  submission order. A bar that reaches both legs of a bracket is scored as the **stop** —
  ranking the profitable leg first would make every wide bracket look free.
- **OCO brackets** — an entry can carry a fixed stop and a fixed profit target hung off
  the average entry price, and whichever trades cancels the other. Two new exit reasons,
  `bracket_stop` and `bracket_target`, because a bracket's stop is not the trailing stop
  and its target is not `take_profit`: both are fixed at entry and neither moves.
- The trade ledger gained `entry_order_type` and `exit_order_type` — the *mechanism*, as
  opposed to `exit_reason`'s *cause*. A sell signal worked as a limit still reads
  `signal`.
- **`result_df.attrs['fills']` — a fill ledger.** One row per execution with the market
  price before slippage and fees, market orders included, so `attrs['trades']` (round
  trips) and `attrs['fills']` (executions) finally have a shared source.
- The order model is reachable from the **backtest toolbar** (Order Type, Order Offset,
  Time in Force, Exit Handling), from the **optimizer** whenever realistic ranking is on,
  and from the **shared execution search space**, which now sweeps `order_type` by
  default. `lib/execution_params.py` carries an opt-in `ORDER_SEARCH_SPACE` for sweeping
  the offsets, TIF and bracket distances too.
- The Execution Type sandbox tape was rebuilt with real intrabar range. Its Open, High and
  Low used to be cosmetic multiples of the close, which meant no limit or stop could ever
  be demonstrated on it — and it also hid the 3.9.4 gap fill, which is now visible in the
  ledger. The explainer gained an **Order type** and an **Exit handling** row, and the
  sandbox gained live controls for both.
- `lib/tests/test_orders.py` and `lib/tests/test_order_wiring.py` — 136 tests covering the
  fill rules, the priority rule, time in force, the bracket lifecycle, and the three
  surfaces that reach them. The invariant every order-model bug breaks first — the trade
  ledger reconciling with the equity curve — is asserted on all eleven configurations.

- **Benchmark-relative metrics** (ROADMAP 3.10.1–3.10.2). `lib/metrics/benchmark.py`
  measures the strategy against buy-and-hold on the same bars, using the `Returns`
  column the engine has always written and nothing ever read. `BacktestMetrics` gained
  `benchmark_return`, `excess_return`, `alpha`, `beta`, `information_ratio`,
  `tracking_error`, `up_capture` and `down_capture`. The Backtest tab renders them in a
  new **VS BUY & HOLD** block; the CLI prints them and the JSON contract carries them.
- **Probabilistic and Deflated Sharpe** (ROADMAP 3.10.3–3.10.4, closes 4.13).
  `lib/metrics/deflated.py` implements Bailey & López de Prado's PSR and DSR. `psr` is
  the chance the true Sharpe is above zero given the sample's length, skew and kurtosis;
  `deflated_sharpe` is the same probability measured against the Sharpe the best of *N*
  trials would reach on noise alone. `BacktestMetrics` also carries the sample the two
  were computed from — `num_bars`, `returns_skew`, `returns_kurtosis`,
  `periods_per_year`, `num_trials` — so a caller that learns the trial count later can
  redo the deflation without re-running anything (`with_deflated_sharpe`).
- The combo search deflates its whole leaderboard against the real combination count and
  the spread of the trials' Sharpes (`apply_deflated_sharpe` in `lib/dash/helpers.py`).
  Attempts that errored out or were pruned by a constraint still count: the search
  looked at them.
- `sfa optimise` deflates its winning trial against every trial in the study, read back
  from `sfa_trials` — so a **resumed** study counts the trials it already had, because
  that history is part of the search. `best.dsr` is printed and carried in the JSON.
- New leaderboard columns — `Excess_Return_%`, `Beta`, `DSR_%`, `Info_Ratio` — and new
  sort options: **DSR**, **ALPHA**, **INFO RATIO**.
- `lib/tests/test_metrics_benchmark.py` — 44 tests pinning the new formulas against
  hand-computed references, including the two distinctions that matter: a levered long
  has excess return and no alpha, and a wider search deflates the same Sharpe further.

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

- **Hover explanations on every indicator parameter.** The gear-icon settings panel
  rendered each parameter as a bare label and a number box — 38 inputs across 12
  indicators with nothing anywhere saying what "Expansion Factor" or "Squeeze Threshold"
  meant, or which way to move them. Every field in `INDICATOR_DEFINITIONS` now carries a
  `help` string explaining what it controls *and* the effect of raising or lowering it,
  surfaced as native `title=` hover copy (same idiom as the Chart Settings checklist);
  the panel header explains the indicator itself.
- **24 missing SIGNALS-panel descriptions filled in** — every SMA slope-flip, VWAP, ADX,
  ATR and OBV signal was falling through to the generic "Signal generated from …".
  `lib/tests/test_indicator_help.py` now fails if any registered signal, indicator or
  parameter ships without copy, so this cannot silently regress.
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
- **`sfa kill` stops the runner cleanly, and `--flatten` works** (ROADMAP 8.8). On Windows
  `sfa kill` used to terminate the process on the spot: no cancel, no disconnect. `--flatten`
  was refused outright. Now the command leaves a stop request in `state/running/`, and the
  runner answers at its next heartbeat. It cancels open orders and closes its own ticker's
  position with a market order when `--flatten` is given; the order-size caps do not block
  that exit. Then it disconnects and reports the orders it sent. A runner that does not
  answer is terminated. The JSON then says `"graceful": false`, and with `--flatten` the
  command exits 3, because nothing was closed. A stale PID file is cleaned up. A PID now
  used by some other process is never terminated (`pid_mismatch`). New `--wait` option,
  default 60 seconds.
- **The Flow Scanner survives a bad expiry and says when Yahoo is throttling** (ROADMAP 6.7).
  All of its Yahoo calls moved to `lib/options/chain_source.py` and now retry 429 / 5xx /
  timeouts with the same backoff as the OHLCV fetch. One expiry that still fails is left
  out and named on the ticker card ("Partial chain: 1 expiry could not be fetched…");
  before, it threw away the whole ticker. A ticker that stays throttled shows
  `RATE LIMITED` instead of looking like a bad symbol. Reports carry the two new fields
  `error_kind` and `failed_expiries`. A failed expiry-list lookup is now an error, where it
  used to pass as a ticker with no options. `--scan` builds its most-actives list with
  `yfinance.screen` instead of calling Yahoo's private screener URL, so Yahoo's login
  handshake is yfinance's to keep working. There is still no second chain source (ROADMAP
  6.9): the free candidates need an account or allow only a few requests a day.
- **`Alpha_%` changed meaning.** It was the arithmetic difference between the strategy's
  return and buy-and-hold's, computed by hand in the combo-search path only. It is now
  annualised **Jensen's alpha**, from the metrics engine, available everywhere. The old
  figure survives under the name it always deserved, `Excess_Return_%`, and the captions
  that reconcile two headline returns ("+12.4% vs buy & hold") use that one — a levered
  long earns excess return with no alpha, and the two columns now say so side by side.
  Persisted optimizer history written before this release keeps the old numbers under
  the old key; nothing re-labels them.
- The optimizer's completion caption is a measured number rather than a general warning.
  It read "the more you test, the more likely the top result is luck" after every run,
  which is true of every search and therefore said nothing about that one. It now reports
  the winner's Deflated Sharpe, colour-coded against the 95% and 50% thresholds, and both
  optimizer guides explain how to read it (§7).
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
- **SEC EPS was not adjusted for stock splits, so older fundamentals were wrong.** Filings
  report EPS on the share count of their day, while Yahoo's prices are split-adjusted.
  Apple's annual EPS fell from 9.21 (2017) to 2.98 (2018) at the 2020 four-for-one split,
  which pushed down the 10-year EPS growth, the P/E and the Rule #1 price. Each per-share
  figure is now divided by the splits that took effect after its filing date, before any
  quarter is derived; the split history comes from the Yahoo price history the page
  already reads. AAPL, NVDA, TSLA and AMZN now match their published split-adjusted EPS,
  and a note on the page lists the splits applied. Cached price history from before this
  fix is refetched once, because it did not keep the splits.
- **The Fundamentals page showed the day's change 100 times too large** (+34.6% for a
  +0.35% day). Yahoo's `regularMarketChangePercent` is in percent points and was read as a
  fraction. The change is now calculated from the price and the previous close.
- **Refresh on the Fundamentals page reloaded the terminal chart behind it.** It re-sent
  the ticker the terminal already had, which re-ran the price, indicator and signal
  callbacks; Refresh took 13 to 60 seconds. The ticker is now sent only when it differs,
  and Refresh takes about 4 seconds.
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
