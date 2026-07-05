Check the AI context/instruction files against the actual code and report or fix drift.

Usage: /sync-claude-context [optional: --fix]

Examples:
- /sync-claude-context          (report drift only)
- /sync-claude-context --fix    (apply corrections after showing them)

Context files to audit (each targets a different tool, keep them consistent, not identical):
- `CLAUDE.md` — Claude Code project instructions
- `.github/copilot-instructions.md` — GitHub Copilot (rtk + CLI focus)
- `.claude/PROJECT_INDEX.md` and `.claude/PROJECT_INDEX_MODULES.md` — module navigation
- `.cursor/rules/*.mdc` — Cursor scoped rules

Steps to follow:
1. Read every context file listed above.
2. For each factual claim, verify it against the repo:
   - Referenced paths exist (`lib/cli/app.py`, `config/strategy_config.yaml`, `main.py`, etc.).
   - Commands/entry points still work as described (`python main.py`, `python -m lib.cli.app <cmd>`).
   - Defaults and flags match the code (`DASH_DEV`, `DASH_RELOAD`, `UI_STORAGE_VERSION`, ports, default ticker).
   - The skills listed match the files in `.claude/commands/`.
3. Cross-check the files against each other for contradictions (e.g. a default stated one way in CLAUDE.md and another in copilot-instructions.md).
4. Report findings as a table: file · line · claim · status (ok / stale / wrong / missing).
5. If `--fix` was passed, apply the corrections (edit the smallest span; preserve each file's tone and audience). Otherwise, list the proposed edits and ask before changing anything.
6. Never invent conventions — only assert what the code actually does. If something is ambiguous, flag it rather than guessing.
