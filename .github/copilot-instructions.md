# SearchForAlpha — Token-Optimized CLI

**rtk** filters and compresses command outputs (~60–90% token savings). Prefix shell commands with `rtk`.

## Rule

```bash
# Instead of:                              Use:
git status                                 rtk git status
git log                                    rtk git log -10
python -m pytest lib/tests/ -v             rtk python -m pytest lib/tests/ -q
python -m lib.cli.app list --json          rtk python -m lib.cli.app list --json
python -m lib.cli.app backtest --name ...    rtk python -m lib.cli.app backtest --name ...
```

Prefer `-q`, `--tb=short`, and `-10` limits even with rtk.

## Meta commands

```bash
rtk gain              # Token savings dashboard
rtk gain --history    # Per-command savings history
rtk discover          # Find missed rtk opportunities
rtk proxy <cmd>       # Run raw (no filtering) but track usage
```

## Context

Module index: `.claude/PROJECT_INDEX.md` — navigate by path instead of re-exploring the tree.
