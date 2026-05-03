# RESEARCH.md — OpenClaw Trading Research Knowledge Base

Reference document for the OpenClaw agent. Read this to inform Research notes,
ticker selection, period choice, and parameter sanity checks.
Do NOT modify this file. Propose changes in chat; human applies them.

---

## Market Regime Calendar (reference periods)

Use these when interpreting backtest results across different windows.

| Period              | Regime        | Key characteristic                         |
|---------------------|---------------|--------------------------------------------|
| 2019-01 → 2020-02   | Bull / low vol | Pre-COVID trend, tight spreads            |
| 2020-02 → 2020-04   | Crash + recover| COVID crash −34%, fastest recovery ever  |
| 2020-05 → 2021-12   | Bull / momentum| Fed QE, growth stocks outperform          |
| 2022-01 → 2022-10   | Bear / rates   | Fed hikes, SPY −25%, QQQ −35%            |
| 2022-11 → 2023-12   | Recovery       | Mean reversion bounce, rate-peak pivot    |
| 2024-01 → 2025-06   | AI bull run    | NVDA/tech concentration, low breadth      |
| 2025-07 → present   | Mixed          | Rate cuts priced in, earnings-driven      |

**Rule of thumb**: A robust strategy should show positive Sortino in at least
3 of the 7 regimes above, including the 2022 bear.

---

## Ticker Reference

### ETFs (preferred for initial research)

| Ticker | Full name              | Avg daily vol | Beta vs SPY | Best strategy type     |
|--------|------------------------|---------------|-------------|------------------------|
| SPY    | S&P 500 ETF            | ~80M shares   | 1.00        | All strategies, baseline |
| QQQ    | Nasdaq 100 ETF         | ~50M shares   | 1.18        | Trend following, MACD  |
| IWM    | Russell 2000 ETF       | ~30M shares   | 1.15        | Mean reversion, RSI    |
| XLK    | Technology sector ETF  | ~12M shares   | 1.30        | EMA crossover, BB      |
| XLF    | Financials sector ETF  | ~25M shares   | 1.05        | CCI, regime-sensitive  |
| XLE    | Energy sector ETF      | ~15M shares   | 0.90        | BB squeeze, CCI extreme|

### Single stocks (use only after ETF validation)

| Ticker | Characteristics                     | Caution                              |
|--------|-------------------------------------|--------------------------------------|
| AAPL   | Liquid, mean-reverting, tight spread| Earnings vol 4×/year                 |
| MSFT   | Stable trend, good EMA signals      | Less volatile than QQQ constituents  |
| NVDA   | High vol, strong momentum           | Can gap ±15% on earnings/AI news     |

---

## Strategy × Regime affinity

Use this table to assess whether a backtest result is in a favourable or
unfavourable regime before concluding a strategy "works" or "fails".

| Strategy family    | Works in       | Struggles in   | Key warning sign                   |
|--------------------|----------------|----------------|------------------------------------|
| Mean reversion     | Ranging, low-vol| Strong trend  | Sortino collapses if SPY >SMA200   |
| Trend following    | Trending       | Ranging, choppy| Many small losses, whipsaw         |
| Momentum           | Bull / breakout| Bear, choppy   | Win rate drops below 40%           |
| BB squeeze         | Pre-breakout   | Already-trended| Few signals generated (<10/year)   |
| VWAP cross (daily) | Any            | Low-volume days| Signal quality degrades on thin days|
| RSI(2) Connors     | Ranging + vol  | Strong trend   | Avg hold < 2 days, high turnover   |

---

## Parameter sanity checks

Flag any of the following in the Research note as **"param sense: flag"**:

| Parameter          | Suspicious if…                              | Likely cause            |
|--------------------|---------------------------------------------|-------------------------|
| `rsi_window`       | < 5 or > 30                                 | Overfitting to noise    |
| `bb_window`        | < 8 or > 60                                 | Too noisy or too slow   |
| `bb_std`           | < 1.5 or > 3.5                              | Boundary overfitting    |
| `macd_fast`        | > `macd_slow - 3`                           | Fast ≥ slow is invalid  |
| `sma_short`        | > `sma_medium / 2`                          | Crossover rarely fires  |
| Any window param   | = search_space boundary (low or high)       | Needs wider search space|
| `cci_extreme`      | < 100                                       | Too many false signals  |

---

## Cost and execution model

### Estimated costs (paper trading context, IB)

- Commission: $0 (IB paper account)
- Slippage estimate: 5 bps per side for liquid ETFs (SPY, QQQ, IWM)
- Slippage estimate: 10 bps per side for sector ETFs and single stocks
- Round-trip cost: 10 bps (ETF) or 20 bps (stock) per trade

### Annual drag formula (for Research notes)

```
annual_drag_pct = avg_trades_per_year × round_trip_bps / 10000 × 100
```

Example: 36 trades/year on SPY → 36 × 10 / 10000 × 100 = 0.36% drag

**Flag** any strategy where annual drag > 2% of capital.

### Trade frequency guidelines

| Strategy type    | Expected trades/year | Flag if…              |
|------------------|---------------------|-----------------------|
| Trend following  | 4 – 15              | > 30 (over-trading)   |
| Mean reversion   | 15 – 60             | > 100 (too reactive)  |
| Momentum         | 10 – 40             | > 80                  |
| RSI(2) Connors   | 40 – 120            | > 200                 |
| VWAP cross       | 20 – 80             | > 150                 |

---

## Walk-forward interpretation guide

The CLI runs 5 OOS windows by default. Interpret results as:

| Windows passed | Verdict      | Action                                      |
|----------------|--------------|---------------------------------------------|
| 5/5            | Very robust  | Promote, consider tighter guard thresholds  |
| 4/5            | Robust       | Promote                                     |
| 3/5            | Marginal     | Rerun with more trials, check param sense   |
| 2/5            | Not robust   | Do not promote, investigate regime mismatch |
| 0-1/5          | Overfitted   | Discard trial, widen search space           |

A window "passes" when OOS Sharpe ≥ `promotion.min_oos_sharpe_mean` (1.0)
and degradation ≤ `promotion.max_degradation` (40%) vs in-sample.

---

## Recommended research starting order

Run strategies in this order for the first full sweep (most likely to produce
robust results first, based on community benchmarks):

1. `mean_reversion_rsi_bb` — well-studied, many reference results to compare
2. `macd_rsi_combo` — cited ~73% win rate; good calibration reference
3. `connors_rsi2` — Larry Connors published params; known to work on SPY
4. `trend_macd_ema` — trend confirmation, good for 2024-2025 regime
5. `golden_cross_sma` — slow but robust; low turnover, low cost drag
6. All others — once you have a Sortino baseline from the above five

---

## Escalation checklist (research flags for human review)

Immediately pause and report to the human if:

- Any promoted strategy shows OOS Sharpe decay > 50% in paper trading
- Two consecutive optimisation runs produce the same boundary-hugging params
- A strategy shows Sortino > 3.0 in-sample (likely overfitted — run deflated Sharpe check)
- Walk-forward passes on stress window (2022) but fails on recent window (2023+) — regime decay
- Trade frequency in paper mode is 3× the backtest estimate — slippage will be much worse
