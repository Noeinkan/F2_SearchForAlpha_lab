# AGENTS.md

Operating instructions for an external agent runtime (e.g. OpenClaw running
Kimi K2.6) that drives SearchForAlpha's `sfa` CLI over SSH. The agent is a
tool orchestrator. It does not pick trades. It does not write code.

## Purpose

Drive paper trading research by sequencing `sfa` subcommands. Strategy logic
is code. Parameter search runs through Optuna. Guards are code. The agent
chooses *what to run next*, parses JSON, and reports concise results to the
human. Anything beyond that is out of scope.

Optimisation is performed with `sfa optimise` and `sfa walkforward`.
`sfa run --mode paper` is the post-promotion paper execution step for
observation and guard monitoring; it is not the optimiser itself.

## Invocation

Every call uses one of these shapes (adjust paths if your install differs):

```
cd /opt/searchforalpha && uv run sfa <command> --json
```

Windows / local virtualenv fallback when `sfa` is not on PATH:

```powershell
Set-Location C:\Users\andre\Downloads\F2_SearchForAlpha_lab
.\.venv\Scripts\python.exe -m lib.cli.app <command> --json
```

If `sfa` is unavailable on PATH, use the interpreter form above instead of
guessing another launcher.

Always pass `--json`. Treat any non-zero exit code as an error.

## Core loop

1. `sfa list` to discover the strategies that exist. Never invent names.
2. `sfa backtest --name <s> --from <ISO> --to <ISO>` to sanity check the
   bundle on its current `live_params`.
3. `sfa optimise --name <s> --trials <n> --metric <sortino|sharpe|calmar|composite>`
   to run a TPE study. Persisted to `state/optuna.db`.
4. `sfa trials --name <s> --top 10` to inspect the leaderboard.
5. `sfa walkforward --name <s> --params <trial_id|json>` to validate the
   chosen trial out of sample.
6. `sfa promote --name <s> --trial <trial_id>` to gate-check and write the
   new `live_params` if (and only if) the gate passes.
7. `sfa run --name <s> --mode paper` to start the runner.
8. `sfa status` and `sfa kill` to observe and stop.

## Hard rules

- Never invent a strategy name. Always call `sfa list` first.
- Never modify repository files. If something needs to change in YAML or
  Python, propose the edit in chat and ask the human to apply it.
- Never pass `--mode live`. Only `--mode paper` is supported. The CLI will
  refuse anyway, but do not even attempt it.
- Promotion is two steps with explicit human confirmation between them:
  show the walkforward verdict, wait for approval, then call `sfa promote`.
- Never retry a command more than twice. If it fails twice, report stderr
  verbatim and stop.
- On any JSON parse failure, stop and report. Do not guess the shape.
- Never share secrets, credentials, broker account numbers, or `.env`
  contents in chat or in tickets.

## Output discipline

Reply to the user with one short paragraph plus the key numbers from the
JSON. Do not paste full JSON back. Do not show reasoning traces in the
final reply. Examples of good summaries:

> "Optimised mean_reversion_rsi_bb over 100 trials, sortino objective.
> Best trial 47 with sortino 1.91, params rsi_window=16, bb_window=22,
> bb_std=2.3. Walkforward next."

> "Walkforward verdict for trial 47: not robust. OOS Sharpe 0.7 below
> threshold 1.0; only 2/5 windows passed. Not promoting."

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
