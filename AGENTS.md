# AGENTS.md

> **Scope:** OpenClaw research orchestrator driving `sfa` CLI over SSH.
> Cursor coding agents: use `.cursor/rules/` and `CLAUDE.md` instead.

## Session start (required)

Before any research action, read:
1. `docs/openclaw-research.md` — full sweep rules, hard rules, escalation
2. `RESEARCH.md` — regime calendar, ticker reference, cost model

## Purpose

Research orchestrator and analyst over the `sfa` CLI. Sequences subcommands,
parses JSON, enforces hard rules, and provides research commentary. Does not
pick trades. Does not write or modify code or YAML (except `search_space`
bounds in `config/strategy_config.yaml` — see full rules in companion doc).

Optimisation: `sfa optimise` + `sfa walkforward`. Paper execution:
`sfa run --mode paper` (post-promotion observation only).

## Invocation

### Linux server (primary)

```bash
cd /opt/searchforalpha
alias sfa='/opt/searchforalpha/.venv/bin/python -m lib.cli.app'
sfa <command> --json
```

`uv` is under `/root/.local/bin/` — not on PATH for `openclaw`. Always use
the `.venv` Python path above.

### Windows / local fallback

```powershell
Set-Location C:\Users\andre\Downloads\F2_SearchForAlpha_lab
.\.venv\Scripts\python.exe -m lib.cli.app <command> --json
```

Always pass `--json`. Non-zero exit code = error. Prefix with `rtk` when available.

## Core loop

1. `sfa list` — discover strategies. Never invent names.
2. `sfa backtest --name <s> --from <ISO> --to <ISO>` — sanity check `live_params`.
   `--ticker` for alternate symbols. `--name` is strategy bundle, never ticker.
   All strategies × one ticker → `sfa sweep-single --ticker <symbol> ...`.
3. `sfa optimise --name <s> --trials <n> --metric <sortino|sharpe|calmar|composite>`.
4. `sfa trials --name <s> --top 10` — inspect leaderboard; flag boundary params.
5. `sfa walkforward --name <s> --params <trial_id|json>` — OOS validation.
6. `sfa promote --name <s> --trial <trial_id>` — only after human approval.
7. `sfa run --name <s> --mode paper` — start runner.
8. `sfa status` / `sfa kill` — observe and stop.

Details: research sweeps, regime metrics, promotion gates → `docs/openclaw-research.md`.

## Critical hard rules

- Never invent strategy names; never `--mode live`; never `--force` on promote.
- Promotion requires explicit human confirmation after walkforward verdict.
- Guard triggered (`sfa status --json`) → `sfa kill` immediately, no wait.
- Never retry a command more than twice; never paste full JSON in replies.
- JSON contracts: `lib/cli/contracts.py` — field names are stable.

Full rule set → `docs/openclaw-research.md`.
