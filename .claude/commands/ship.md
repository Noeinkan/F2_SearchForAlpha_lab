Commit current changes, push to the remote, and deploy to production via `.\deploy.ps1`.

Usage: /ship [optional: deploy flags or "dry-run"]

Examples:
- /ship
- /ship dry-run
- /ship -PushConfig
- /ship -SkipPipInstall
- /ship message: fix symbol search on prod

Steps to follow:

## 0. Preconditions
- Work from the repo root.
- If the working tree is clean and there is nothing to push, say so and stop (do not redeploy unless the user explicitly asks to deploy anyway).
- Never update git config. Never `--force` push. Never skip hooks. Never commit secrets (`.env`, credentials, private keys).

## 1. Inspect changes (parallel)
Run with `rtk`:
- `rtk git status`
- `rtk git diff` and `rtk git diff --staged`
- `rtk git log -10 --oneline`
- `rtk git status -sb` (confirm branch tracks `origin/<branch>`)

## 2. Draft commit message
- Style: conventional commits matching recent history (`feat(scope): …`, `fix(scope): …`, `refactor(scope): …`).
- Focus on **why**, 1–2 sentences max. Subject ≤72 chars.
- If the user passed `message: …`, use that (lightly tidy only).
- Do **not** commit yet.

## 3. Confirm once
Show:
1. Branch + tracking status
2. Files that will be committed (exclude junk: `__pycache__/`, `*.pyc`, local secrets)
3. Proposed commit message
4. Deploy command that will run (default `.\deploy.ps1`, or flags from the invocation; `dry-run` → `.\deploy.ps1 -DryRun`)

Ask: proceed with **commit → push → deploy**?

Stop if the user declines. If they want only commit, or only deploy, honour that.

## 4. Commit
```powershell
git add <relevant paths>
git commit -m "$(cat <<'EOF'
<message>

EOF
)"
```
On Windows PowerShell without HEREDOC, use:
```powershell
git commit -m @'
<message>
'@
```
If a hook fails, fix the issue and create a **new** commit (do not amend unless the user asks and amend rules are met).

## 5. Publish (push)
```powershell
git push -u origin HEAD
```
If push fails (auth/network/non-fast-forward), stop and report — do **not** deploy a divergent local-only state unless the user explicitly overrides.

## 6. Deploy
```powershell
.\deploy.ps1
```
Pass through any flags from the command (`-PushConfig`, `-SkipPipInstall`, `-DryRun`, `-File …`, etc.).

Notes:
- Prod is Hetzner `root@77.42.70.26` → `/opt/searchforalpha` (see `deploy.ps1` / prod-parity rule).
- Default deploy restarts the dashboard and may pip-install when `requirements.txt` changed.
- `strategy_config.yaml` is **not** uploaded unless `-PushConfig`.
- Deploy can take a few minutes — set a generous wait; do not background unless it clearly hangs.

## 7. Report
Return:
- Commit hash + subject
- Push result (remote branch)
- Deploy summary (ok / failures from `deploy.ps1` output)
- Prod URL reminder: http://77.42.70.26:8060/
