# Indicator Roadmap — Implemented vs Remaining

_Analysis date: 2026-08-02 · branch `main` · based on working tree (includes uncommitted work)_

## 0. Correction to the starting premise

The research brief assumed **ADX, ATR and OBV are "unwired"** — i.e. computed in
`add_indicators` but with no strategy attached. That is no longer true. The working
tree contains a complete, tested Tier 1 implementation that is **untracked / uncommitted**:

```
?? lib/signals/signals_ADX.py
?? lib/signals/signals_ATR.py
?? lib/signals/signals_OBV.py
?? lib/tests/test_signals_regime.py
 M config/strategy_config.yaml   (+116 lines)
 M lib/agent_strategy.py         (+11 lines)
 M lib/signals/indicators.py     (+41 lines)
 M lib/dash/dash_config.py, layout/right_panel.py
```

So Tier 1 is ~80% done, not 0%. The remaining Tier 1 work is narrower and more
specific than "wire up the indicators" — it is listed in §2.

---

## 1. What IS implemented

### 1.1 Signal strategies (Tier 1) — done

| Module | Key | Priority | Columns |
|---|---|---|---|
| [signals_ADX.py](lib/signals/signals_ADX.py) | `adx` | 80 | `ADX_TrendRegime_*`, `ADX_RangeRegime_*`, `ADX_DICross_*`, `ADX_Rising_*` |
| [signals_ATR.py](lib/signals/signals_ATR.py) | `atr` | 90 | `ATR_Expansion_*`, `ATR_Compression_*`, `ATR_Breakout_*` (+ `ATR_Stop_Long/Short` levels) |
| [signals_OBV.py](lib/signals/signals_OBV.py) | `obv` | 100 | `OBV_MACross_*`, `OBV_Divergence_*`, `OBV_Confirmation_*` |

Quality notes — these are genuinely well built, not stubs:

- **Warmup handled correctly.** `ta` back-fills its warmup period with `0.0`, not `NaN`.
  Both ADX ([signals_ADX.py:70-81](lib/signals/signals_ADX.py#L70-L81)) and ATR
  ([signals_ATR.py:81](lib/signals/signals_ATR.py#L81)) mask that out, so the
  range-regime / compression gates cannot fire on an uninitialised window. This is
  the single most common bug in this kind of code and it was avoided.
- **ATR is normalised** to `ATR_Pct = ATR / Close` before comparison, so the volatility
  regime is comparable across tickers and across long ranges where price level drifts.
- **Regime columns are deliberately symmetric** (`ADX_RangeRegime_Buy == _Sell`,
  `ATR_Compression_Buy == _Sell`) so the same mask ANDs onto either side. Documented
  in the module docstrings.
- Auto-discovery via `_discover_strategy_classes()` picks them up with no registration edit.

### 1.2 Config surface — done

- `config/strategy_config.yaml` has `adx` / `atr` / `obv` blocks under `strategies:`
  ([strategy_config.yaml:60-90](config/strategy_config.yaml#L60-L90)) with a comment
  explaining they are filters, not entries.
- `_build_default_indicator_settings()` and `_build_strategy_config_mappers()` in
  [indicators.py:240-404](lib/signals/indicators.py#L240-L404) map all three.
- `longest_lookback()` `_WINDOWED_PARAM_KEYS` was extended with `ma_period`,
  `expansion_lookback`, `divergence_lookback`, `confirmation_lookback` — so warmup
  sizing accounts for the new windows.
- `PARAM_KEY_MAP` in [agent_strategy.py:50-60](lib/agent_strategy.py#L50-L60) exposes
  11 new flat params for optimisation (`adx_trend_threshold`, `atr_breakout_multiplier`, …).

### 1.3 Regime-gated agent bundles — partially done

Four **additive** bundles were added (originals left untouched so results stay comparable):

| Bundle | Logic | What it does |
|---|---|---|
| `trend_macd_ema_adx_gated` | `and`, window 3 | MACD cross **only while ADX confirms trend** |
| `mean_reversion_rsi_range_gated` | `and`, window 2 | RSI mean reversion **only while ADX says ranging** |
| `bb_squeeze_vol_confirmed` | `and`, window 3 | BB squeeze **confirmed by ATR thrust** |
| `trend_ema_obv_confirmed` | `and`, window 3 | EMA cross **confirmed by OBV flow** |

Total: 19 bundles (15 original + 4 gated). Each has a `search_space` covering the new params.

### 1.4 Dashboard — done

- Indicator settings panel: ADX gained `range_threshold`; ATR gained all four
  expansion/compression/breakout fields; OBV gained both lookbacks
  ([dash_config.py:431-475](lib/dash/dash_config.py#L431-L475)).
- `DEFAULT_OFF_SIGNAL_CATEGORIES = {'ADX','ATR','OBV'}` — these start **unticked** in
  the SIGNALS panel, matching the fact that their chart panes are absent from
  `DEFAULT_SELECTED_PLOTS`. Correct call: they'd otherwise flood the signal list with
  gate columns that fire on most bars.
- Chart panes `_add_adx` / `_add_atr` / `_add_obv` exist in
  [chart_builder.py:560-613](lib/dash/chart_builder.py#L560-L613) (pre-existing, see §2.2).

### 1.5 Tests — done and passing

[test_signals_regime.py](lib/tests/test_signals_regime.py) — 29 tests covering all three
strategies plus registry integration. Verified:

```
python -m pytest lib/tests/test_signals_regime.py lib/tests/test_indicators.py -q
→ 45 passed
```

Coverage includes the non-obvious cases: warmup emits no signals, regimes are mutually
exclusive, stops sit on the correct side of price, thresholds are config-driven,
zero-price and zero-volume rows don't raise.

---

## 2. What is LEFT to implement

### 2.1 Tier 1 gap — ATR stops and sizing never reach the backtest ⚠️ **highest value remaining**

This is the one item from the brief's Tier 1 that is genuinely not done. The signal
module computes `ATR_Stop_Long` / `ATR_Stop_Short`
([signals_ATR.py:89-90](lib/signals/signals_ATR.py#L89-L90)), but grep confirms
**nothing reads them except the test.** The backtest still uses:

- `trailing_stop_loss: float = 0.05` — a **fixed 5% trailing stop**
  ([strategy.py:86](lib/strategy.py#L86)), applied identically to a low-vol utility
  and to TSLA.
- `risk_based()` sizing keyed off `stop_loss_percent`, again a fixed percentage
  ([strategy.py:609-620](lib/strategy.py#L609-L620)).

**Work required:**

1. Add a `stop_mode: 'percent' | 'atr'` parameter to `backtest()`; when `'atr'`, drive
   `trailing_stop[i]` from `df['ATR_Stop_Long']` instead of `close * (1 - pct)`.
   Touches the ~8 assignment sites at [strategy.py:317-377](lib/strategy.py#L317-L377).
2. Add an `atr_risk_based` position-sizing strategy alongside the existing five in the
   dict at [strategy.py:541-557](lib/strategy.py#L541-L557), using ATR rather than a
   percentage as the risk denominator.
3. Guard for the ATR column being absent (bundles that don't include ATR params) —
   fall back to percent mode with a logged warning rather than raising.
4. Surface `stop_mode` in the backtest panel and in `backtest_result.py` extras so
   runs are distinguishable in results.

**Why it matters:** the brief's own conclusion was that these indicators are
risk-management tools, not return generators. Right now the risk-management half is
the only half that isn't hooked up.

### 2.2 Chart panes recompute instead of reading the strategy columns

`_add_adx`, `_add_atr`, `_add_obv` each recompute their indicator locally rather than
reading the columns the strategies already wrote. Three concrete consequences:

- **ATR pane is misleading.** It plots `ATR` and a rolling mean of *raw* ATR over
  `period` ([chart_builder.py:574-592](lib/dash/chart_builder.py#L574-L592)). The
  strategy compares `ATR_Pct` to `ATR_Pct_MA` over `expansion_lookback`. So the
  visible "ATR crosses ATR MA" moment does **not** correspond to `ATR_Expansion_*`
  firing. A user tuning `expansion_factor` sees no change on the chart.
- **+DI / −DI are never plotted** even though `ADX_DICross_*` is built entirely from
  them, and the `range_threshold` hline is missing — only the trend threshold is drawn.
- **OBV MA warmup mismatch:** chart uses `min_periods=1`, strategy uses
  `min_periods=ma_period`. The chart shows an MA during warmup where the strategy has none.

**Work required:** switch the three renderers to read `df['ADX_Pos_DI']`,
`df['ATR_Pct']`/`df['ATR_Pct_MA']`, `df['OBV_MA']` when present, recompute only as
fallback. Add the second ADX hline and the DI lines.

### 2.3 Redundant computation in `add_indicators`

[indicators.py:475-486](lib/signals/indicators.py#L475-L486) still computes ADX, ATR and
OBV globally; the strategies then overwrite those columns with their own (correctly
warmup-masked) versions. Harmless today because strategies run after and win, but it's a
trap: anything reading `df['ADX']` between the two calls gets the unmasked variant.
Either drop the three blocks or add a comment stating they exist only for bare-frame
callers.

### 2.4 No empirical validation of the gated bundles

The four gated bundles exist but have **not been backtested against their ungated
baselines**. The entire thesis — "gating on ADX regime helps more than any new entry
signal" — is currently untested in this repo.

**Work required:** run each pair (`trend_macd_ema` vs `trend_macd_ema_adx_gated`, etc.)
over a common window via `/backtest` or the `sfa` CLI, and record Sharpe / max drawdown /
trade count side by side. If the gated variants don't improve risk-adjusted metrics,
that finding should change the priority of everything below.

### 2.5 Missing bundles for the strategies the brief flagged as bleeding

The brief specifically named `connors_rsi2`, `cci_oversold_meanrev` and
`golden_cross_sma` as bleeding in the wrong regime — none of them got a gated variant.
Also unbundled: `ADX_DICross_*`, `OBV_Divergence_*`, and the
`ATR_Compression → breakout` pre-squeeze setup, all of which have signal columns but no
bundle exercising them.

### 2.6 Work is uncommitted

Four new files are untracked and eight are modified. A single `git clean` loses the
entire Tier 1 implementation. **Commit before starting Tier 2.**

---

## 3. Tier 2 / Tier 3 — not started

Grep confirms zero occurrences of Keltner, Supertrend, MFI, CMF, Donchian, Volume
Profile, or anchored VWAP anywhere in `lib/` or `config/`. Stochastic exists only as
[lib/WIP/WIP_Stochastic_oscillator.py](lib/WIP/WIP_Stochastic_oscillator.py), outside the
registry (it isn't named `signals_*` so auto-discovery skips it).

| Tier | Item | Effort | Notes |
|---|---|---|---|
| 2 | **Keltner + TTM Squeeze** | M | Highest-value new math. KC is ATR-based where BB is stdev-based — genuinely new information. BB-inside-KC is a better squeeze detector than the current bandwidth-threshold `BB_Squeeze`. Reuses the ATR already computed. |
| 2 | **Supertrend** (10/3) | S | ATR-based trailing stop; pairs naturally with §2.1. Cleanest chart overlay of the set. |
| 2 | **MFI** | S | Volume-weighted RSI — the one momentum flavour the current oscillators lack. |
| 2 | **Anchored VWAP** | M | Needs a UI anchor-point picker, which is the bulk of the work. More useful than the rolling 20-bar VWAP now that 1H/4H views exist. |
| 3 | Donchian | S | Turtle breakouts; pairs with ADX. |
| 3 | Stochastic %K/%D | S | Promote the WIP file. Correlated with RSI — low marginal value. |
| 3 | Volume Profile | L | Awkward as a horizontal histogram in Plotly subplots. |
| 3 | Relative strength vs SPY | M | Needs a second data fetch; not a classic indicator but often carries more signal than any oscillator. |

**Redundancy check before adding anything:** momentum is already saturated (RSI, CCI,
MACD). Per the brief's own framing, do not add a fourth momentum oscillator. MFI is the
exception because it carries volume.

---

## 4. Recommended order

1. **Commit the existing Tier 1 work** (§2.6) — it's complete and passing; don't risk it.
2. **ATR stops + sizing into the backtest** (§2.1) — the only real Tier 1 gap, and the
   item the brief's own conclusion ranks highest.
3. **Backtest the gated bundles vs baselines** (§2.4) — cheap, and the result determines
   whether steps 4–6 are worth doing at all.
4. **Fix the chart panes** (§2.2) — small, and currently the ATR pane actively misleads
   anyone tuning the parameters.
5. **Fill the missing gated bundles** (§2.5) — config-only, no new code.
6. **Keltner + TTM Squeeze** (§3) — first genuinely new math, once the above is validated.

Steps 1–5 are all small-to-medium and build on work already done. Step 6 is where new
indicator development actually starts.

---

## 5. Standing caveat

The brief's own honest note is worth keeping in view: the arXiv HFT random-forest study
found indicator-augmented models improved risk-adjusted metrics but **underperformed
buy-and-hold on raw returns**. Treat everything here as regime and risk-management
tooling. That is exactly why §2.1 (ATR stops) outranks every new entry oscillator in §3.

_Educational/research use only. Not financial advice._
