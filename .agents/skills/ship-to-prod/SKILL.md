---
name: ship-to-prod
description: >-
  Generate a commit message, commit, push to origin, and deploy to the Hetzner
  production server with .\deploy.ps1. Use when the user says ship, commit and
  deploy, publish to prod, /ship, or asks to push changes live.
disable-model-invocation: true
---

# Ship to prod

Commit → push → `.\deploy.ps1` for SearchForAlpha Lab.

## When invoked

1. Inspect with `rtk git status`, `rtk git diff` (+ staged), `rtk git log -10 --oneline`.
2. Draft a conventional-commit message matching recent history (`feat|fix|refactor(scope): …`). Why over what; ≤72-char subject.
3. **Confirm once** — show files, message, and deploy command. Wait for approval before any write/push/deploy.
4. Commit (no force, no hook skip, no secrets). PowerShell message:

```powershell
git commit -m @'
<message>
'@
```

5. `git push -u origin HEAD` — stop on failure; do not deploy a divergent local-only state unless the user overrides.
6. `.\deploy.ps1` with any flags the user passed (`-DryRun`, `-PushConfig`, `-SkipPipInstall`, `-File …`).
7. Report: commit hash, push result, deploy outcome, prod URL `http://77.42.70.26:8060/`.

## Deploy facts

- Script: `.\deploy.ps1` (repo root). Target: `root@77.42.70.26` → `/opt/searchforalpha`.
- Syncs `lib/`, selected `config/`, `scripts/` (excludes `*.ps1`, `strategy_config.yaml` unless `-PushConfig`).
- Default: may pip-install on `requirements.txt` change and restart the dashboard.
- Clean tree + nothing to push → stop unless user asks to deploy anyway.

## Hard rules

- Never `git push --force`, never amend unless user rules allow, never update git config.
- Never commit `.env` / credentials / private keys.
- One confirmation gate for the whole pipeline unless the user asks for step-by-step confirms.
- Prefer `rtk` for git inspection commands.
