# SearchForAlpha Lab — Project Index

Navigation hub for agents. **Don't load the full module catalog every turn** — use this hub, then jump to [PROJECT_INDEX_MODULES.md](PROJECT_INDEX_MODULES.md) for tables.

## Instruction tiers (token efficiency)

| Layer | File | When loaded |
|-------|------|-------------|
| Always-on | `.cursor/rules/token-efficiency.mdc` | Every Cursor session — rtk + context discipline |
| Always-on | `CLAUDE.md` | Every session — essentials only (~20 lines) |
| On-demand | `.cursor/rules/sfa-python.mdc` | Editing `lib/**/*.py` (excludes dash, cli) |
| On-demand | `.cursor/rules/dash-callbacks.mdc` | Editing `lib/dash/**` |
| On-demand | `.cursor/rules/sfa-cli-research.mdc` | Editing `lib/cli/**` |
| Research only | `docs/openclaw-research.md` | sfa CLI research in Cursor (`@`-mention; `AGENTS.md` in `.cursorignore`) |
| Shell hook | `.cursor/hooks.json` | Auto-prefixes `rtk` on Shell tool calls |

Shell commands: prefix with `rtk` (see `.github/copilot-instructions.md`).

Full rationale (IT): [docs/token-efficiency.md](../docs/token-efficiency.md)

---

## Entry Points

| File | Purpose |
|------|---------|
| [main.py](../main.py) | Launch Dash app at http://127.0.0.1:8050 (`DASH_DEV=1` default, auto-reload) |
| `python -m lib.cli.app` | **sfa CLI** — backtest, optimise, walkforward, paper trade |
| `rtk python -m pytest lib/tests/ -q` | Run test suite (26 test files) |

---

## Module catalog

Detailed tables (data, signals, CLI, dashboard layout/callbacks, tests, config): **[PROJECT_INDEX_MODULES.md](PROJECT_INDEX_MODULES.md)**

Dashboard quick map: `integrated_dashboard.py` (thin entry) · `layout/` (UI regions) · `callbacks/` (15 registered modules + `shared.py`) · `routes.py` · `bootstrap.py`

---

## Agents & commands

| Agent / Command | Use for |
|-----------------|---------|
| `dashboard-dev` | Dash UI, callbacks, chart overlays |
| `signal-engineer` | Indicator strategies |
| `quant-analyst` | Backtest metrics, strategy comparison |
| `/new-callback` | Scaffold a Dash callback (register pattern) |
| `/add-signal` | Scaffold a new indicator |
| `/run-tests` | pytest suite |
