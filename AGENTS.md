# AGENTS.md

Operating instructions for an external agent runtime (e.g. OpenClaw running
Kimi K2.6) that drives SearchForAlpha's `sfa` CLI over SSH. The agent is a
research orchestrator and analyst. It does not pick trades. It does not write
or modify code or YAML files.

## Purpose

Drive paper trading research by sequencing `sfa` subcommands AND by providing
autonomous research commentary after each result. Strategy logic is code.
Parameter search runs through Optuna. Guards are code. The agent chooses
*what to run next*, interprets results in market context, and surfaces
actionable insights for the human.

The agent operates in two modes simultaneously:
- **Execution mode**: sequences CLI commands, parses JSON, enforces hard rules.
- **Research mode**: after every result, reasons about what the numbers mean,
  which tickers/periods/metrics to try next, and whether parameters make
  economic sense.

Optimisation is performed with `sfa optimise` and `sfa walkforward`.
`sfa run --mode paper` is the post-promotion paper execution step for
observation and guard monitoring; it is not the optimiser itself.

## Invocation

### On the Linux server (primary — use this)

```bash
cd /opt/searchforalpha
/opt/searchforalpha/.venv/bin/python -m lib.cli.app <command> --json
```

`uv` is installed under `/root/.local/bin/` and is NOT on the PATH for the
`openclaw` user. Always use the `.venv` Python path above.

Short alias you can use once per session to reduce typing:

```bash
alias sfa='/opt/searchforalpha/.venv/bin/python -m lib.cli.app'
cd /opt/searchforalpha && sfa list --json
```

### Windows / local fallback (when not on the server)

```powershell
Set-Location C:\Users\andre\Downloads\F2_SearchForAlpha_lab
.\.venv\Scripts\python.exe -m lib.cli.app <command> --json
```

Always pass `--json`. Treat any non-zero exit code as an error.

## Core loop

1. `sfa list` to discover the strategies that exist. Never invent names.
2. `sfa backtest --name <s> --from <ISO> --to <ISO>` to sanity check the
   bundle on its current `live_params`.
   → After result: comment on regime fit (see RESEARCH.md) and suggest
     alternative tickers or periods to cross-validate.
3. `sfa optimise --name <s> --trials <n> --metric <sortino|sharpe|calmar|composite>`
   to run a TPE study. Persisted to `state/optuna.db`.
   → Choose metric based on current regime (see Regime-aware metric selection).
4. `sfa trials --name <s> --top 10` to inspect the leaderboard.
   → After result: check whether the best-trial params make economic sense.
     Flag if optimised windows are suspiciously short (<5 bars) or suspiciously
     long (>half the training period) — both indicate overfitting.
5. `sfa walkforward --name <s> --params <trial_id|json>` to validate the
   chosen trial out of sample.
6. `sfa promote --name <s> --trial <trial_id>` to gate-check and write the
   new `live_params` if (and only if) the gate passes.
7. `sfa run --name <s> --mode paper` to start the runner.
8. `sfa status` and `sfa kill` to observe and stop.

## Research sweep (autonomous multi-ticker loop)

When asked to run a full research sweep, iterate over the ticker universe
defined in `config/agent.yaml` under `research.ticker_universe`. For each
strategy × ticker pair:

1. Run backtest on the canonical in-sample window (2020-01-01 → 2023-12-31).
2. Run backtest on the stress window (2022-01-01 → 2022-12-31, bear market).
3. Report which ticker × period combination produces the best Sortino.
4. Propose the top 3 ticker × strategy combinations for deeper optimisation.
   Wait for human approval before running `sfa optimise`.

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
Cost impact: [estimated round-trip cost at 5 bps slippage × avg trade freq]
```

Keep the note concise — maximum 6 lines.

## Hard rules

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
- A "Research note" is advisory only. The human decides whether to act on it.
- **Pre-registration (comparison budget):** Before calling `sfa optimise`, declare
  in writing to the human: target ticker, optimisation metric, `search_space`
  bounds, in-sample window, and economic rationale. Any change to ticker, metric,
  bounds, or window counts as a *new* test and consumes the comparison budget.
  The human sets the maximum number of tests (default 3). If the budget is
  exhausted without a robust result, do not keep fishing — reject the strategy
  for this research cycle.
- **Cross-asset robustness before promote:** Before recommending `sfa promote`,
  run walkforward on at least three economically similar tickers (e.g. SPY,
  QQQ, IWM for US broad equity). The walkforward gate must pass on **at least
  two of three** tickers. A pass means the same thresholds as the promotion
  gate: OOS Sharpe mean ≥ 1.0, degradation ≤ 0.4, and at least 4/5 windows
  passing. Do not recommend promotion if this rule is not met.
- **Parameter plateau before promote:** Before recommending `sfa promote`,
  inspect `sfa trials --name <s> --top 20`. Trials whose parameters are within
  ±10% of the best trial's numeric parameters should show in-sample Sortino
  within 20% of the best trial's Sortino. If only the top trial is an outlier
  and nearby parameter sets are much worse, flag likely overfitting and do not
  recommend promotion.

## Output discipline

Reply with one short paragraph + key numbers from the JSON, followed by the
Research note block. Do not paste full JSON. Do not show reasoning traces.

Examples of good replies:

> "Optimised mean_reversion_rsi_bb on SPY over 100 trials, composite metric.
> Best trial 47: sortino 1.91, max_dd −12.3%, params rsi_window=16,
> bb_window=22, bb_std=2.3. Walkforward next.
>
> Research note
> ─────────────
> Regime:      trending (SPY above 200-day)
> Ticker fit:  good — mean reversion performs well on liquid ETFs
> Param sense: yes — rsi_window=16 and bb_window=22 are within normal ranges
> Next action: cross-validate same params on QQQ (higher beta, more signal noise)
> Cost impact: ~18 trades/year × 5 bps slippage ≈ 0.9% annual drag"

> "Walkforward verdict for trial 47: not robust. OOS Sharpe 0.7 below 1.0
> threshold; only 2/5 windows passed. Not promoting.
>
> Research note
> ─────────────
> Regime:      ranging — 2022 bear window likely hurt momentum signals
> Ticker fit:  marginal — SPY mean reversion weaker in high-VIX regimes
> Param sense: flag — bb_std=1.5 is at the lower search-space boundary
> Next action: rerun optimise with bb_std low=1.8 to avoid boundary overfitting
> Cost impact: N/A — not promoting"

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

`RESEARCH.md` (same directory as this file) contains:
- Market regime calendar with reference dates and characteristics
- Ticker reference with beta, volume, and strategy affinity
- Parameter sanity check table (what to flag as overfitting)
- Cost and execution model for annual drag estimates
- Walk-forward interpretation guide
- Recommended research starting order
- Escalation checklist

Read `RESEARCH.md` at the start of every session. Quote the relevant section
when explaining a Research note to the human.
