# OpenClaw Research Agent — Full Operating Manual

Companion to root `AGENTS.md`. OpenClaw loads `AGENTS.md` automatically; **read this file at session start** alongside `RESEARCH.md`.

## Research sweep (autonomous multi-ticker loop)

When asked to run a full research sweep, iterate over the ticker universe
defined in `config/agent.yaml` under `research.ticker_universe`. Run the sweep
in stages, not as one flat list:

1. Start with liquid benchmark ETF sleeves first: `etf_broad`, then the most
  relevant cross-asset benchmark sleeve such as `etf_fixed_income`,
  `etf_international`, or `etf_commodity_physical`.
2. For each approved strategy × ticker pair, run backtest on the canonical
  in-sample window (2020-01-01 → 2023-12-31).
3. Run backtest on the stress window (2022-01-01 → 2022-12-31, bear market).
  Use `sfa backtest --name <strategy> --ticker <symbol> ...`; do not pass the
  ticker as `--name`.
  If the task is a single fixed ticker across all strategies, use
  `sfa sweep-single --ticker <symbol> ...` instead of issuing one backtest per strategy.
4. Expand to `etf_sector`, `etf_style_factor`, or other specialist ETF sleeves
  only if Sortino > 1.5 on at least two benchmark ETFs.
5. Treat `etf_commodity_futures` as second-pass research only. These are valid
  test targets, but their returns can be dominated by roll yield and curve
  shape rather than spot-price moves.
6. Use `sp500_*` stock baskets only after ETF robustness is established.
7. Report which ticker × period combination produces the best Sortino.
8. Propose the top 3 ticker × strategy combinations for deeper optimisation.
  Wait for human approval before running `sfa optimise`.

If `research.exploration.enabled` is true, run an additional exploratory pass
after the fixed benchmark sweep:

1. Call `sfa sample-universe --json` once to materialize the benchmark tickers
  and seeded exploratory ETF picks from `config/agent.yaml`.
2. Keep the configured `benchmark_groups` deterministic.
3. Sample extra ETFs only from `eligible_groups`, never from `excluded_groups`.
4. Run every exploratory sample across each configured seed.
5. Summarise the median and worst result across seeds; never cherry-pick the
  best seed as the headline result.
6. Treat exploration as advisory only. Any strategy that looks promising must be
  rechecked on a deterministic validation set before optimisation or promotion.

Never run more than 3 backtests without pausing to summarise findings.

## Regime-aware metric selection

| Market condition              | Preferred metric  | Rationale                        |
|-------------------------------|-------------------|----------------------------------|
| Trending (SPY > SMA200)       | `sortino`         | Rewards upside capture           |
| Ranging / sideways            | `calmar`          | Penalises drawdowns heavily      |
| High volatility (VIX-like)    | `composite`       | Balances all three               |
| Unknown / first run           | `composite`       | Safe default                     |

Use `composite` when you cannot determine the regime from available data.

## Research commentary format

After every CLI result, append a **Research note** block in your reply:

```
Research note
─────────────
Regime:      [trending | ranging | volatile | unknown]
Ticker fit:  [good | marginal | poor] — one sentence reason
Param sense: [yes | flag] — flag if any param is at a search-space boundary
Next action: [what you recommend running next and why]
Cost impact: [estimated round-trip cost using asset-class slippage × avg trade freq]
```

Keep the note concise — maximum 6 lines.

## Hard rules (full)

- Never invent a strategy name. Always call `sfa list` first.
- Never modify Python, TOML, or JSON files. Never modify YAML files other
  than `config/strategy_config.yaml`.
- In `config/strategy_config.yaml` you may directly edit `search_space`
  blocks under `agent_strategies` (parameter bounds only). All other
  sections of that file (e.g. `live_params`, `guards`) require a proposed
  diff and human approval before applying.
- When editing `config/strategy_config.yaml`, **do not use `sed -i`** — it
  requires directory write permission which the `openclaw` user does not have.
  Use this Python pattern instead (overwrites the file in-place without a
  temp-file rename):

  ```bash
  python3 -c "
  content = open('/opt/searchforalpha/config/strategy_config.yaml').read()
  content = content.replace('old_value', 'new_value')
  open('/opt/searchforalpha/config/strategy_config.yaml', 'w').write(content)
  "
  ```

  Always `grep` the file after writing to verify the change was applied.
- Never pass `--mode live`. Only `--mode paper` is supported.
- Never pass `--force` to `sfa promote`. The flag bypasses the "strategy is
  running" guard and is never permitted.
- Promotion requires explicit human confirmation: show walkforward verdict,
  wait for approval, then call `sfa promote`. No exceptions.
- Never retry a command more than twice. Report stderr verbatim and stop.
- On any JSON parse failure, stop and report. Do not guess the shape.
- Never share secrets, credentials, broker account numbers, or `.env` contents.
- Never recommend a position size larger than `guards.max_position_pct` (25%).
- Never suggest disabling or relaxing guards — propose tightening them instead.
- Treat futures-based commodity ETFs (e.g. `DBC`, `PDBC`, `DBA`, `USO`, `UNG`)
  as exposure sleeves, not spot proxies. Mention roll yield / curve-shape risk
  in the Research note whenever it is materially relevant.
- If seeded exploration is enabled, always report the seed list and sampled
  tickers. Never present one seed's outcome as sufficient evidence on its own.
- A "Research note" is advisory only. The human decides whether to act on it.
- **Pre-registration (comparison budget):** Before calling `sfa optimise`, declare
  in writing to the human: target ticker, optimisation metric, `search_space`
  bounds, in-sample window, and economic rationale. Any change to ticker, metric,
  bounds, or window counts as a *new* test and consumes the comparison budget.
  The human sets the maximum number of tests (default 3). If the budget is
  exhausted without a robust result, do not keep fishing — reject the strategy
  for this research cycle.
- **Cross-asset robustness before promote:** Before recommending `sfa promote`,
  run walkforward on at least three economically similar tickers from the same
  sleeve (e.g. SPY, QQQ, IWM for US broad equity; AGG, IEF, TLT for duration;
  GLD, IAU, SLV for precious metals). The walkforward gate must pass on **at
  least two of three** tickers. A pass means the same thresholds as the
  promotion gate: OOS Sharpe mean ≥ 1.0, degradation ≤ 0.4, and at least 4/5
  windows passing. Do not recommend promotion if this rule is not met.
- **Parameter plateau before promote:** Before recommending `sfa promote`,
  inspect `sfa trials --name <s> --top 20`. Trials whose parameters are within
  ±10% of the best trial's numeric parameters should show in-sample Sortino
  within 20% of the best trial's Sortino. If only the top trial is an outlier
  and nearby parameter sets are much worse, flag likely overfitting and do not
  recommend promotion.

## Output discipline

Reply with one short paragraph + key numbers from the JSON, followed by the
Research note block. Do not paste full JSON. Do not show reasoning traces.
See `RESEARCH.md` for reply examples.

## Escalation

If `sfa status --json` shows any element of `guard_state` with
`"triggered": true`, immediately call `sfa kill --name <s>` and report. Do
not wait for human confirmation on guard triggered kills. Examples of
guards: `daily_loss`, `position_size`, `broker_disconnected`, `clock_drift`.

If a kill itself fails, report the stderr and stop. Do not loop.

## JSON contract reference

Authoritative dataclasses live in `lib/cli/contracts.py` and the modules
they call into. Field names are stable; if a field is missing, treat it
as the agent's parsing error rather than a CLI bug, and stop.

## Knowledge base

`RESEARCH.md` (repo root) contains:
- Market regime calendar with reference dates and characteristics
- Ticker reference with beta, volume, and strategy affinity
- Parameter sanity check table (what to flag as overfitting)
- Cost and execution model for annual drag estimates
- Walk-forward interpretation guide
- Recommended research starting order
- Escalation checklist

Read `RESEARCH.md` at the start of every session. Quote the relevant section
when explaining a Research note to the human.
