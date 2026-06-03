# SearchForAlpha Lab

Python algorithmic trading research: Yahoo Finance OHLCV → indicator signals → backtest → Dash dashboard.

**Start:** `python main.py` · **Test:** `rtk python -m pytest lib/tests/ -q`

## Navigation
- Module index: [.claude/PROJECT_INDEX.md](.claude/PROJECT_INDEX.md)
- Scoped rules: [.cursor/rules/](.cursor/rules/) (load on demand by file path)
- Token efficiency rationale: [docs/token-efficiency.md](docs/token-efficiency.md)
- OpenClaw research agent: [AGENTS.md](AGENTS.md) + [docs/openclaw-research.md](docs/openclaw-research.md)

## Non-obvious essentials
- Signal columns: `{INDICATOR}_{CONDITION}_Buy` / `_Sell` — see `lib/signals/indicators.py`
- Indicator params: always from `config/strategy_config.yaml` via `lib/config_loader.py`
- Dash callbacks: one file per concern in `lib/dash/callbacks/`, imported by `integrated_dashboard.py`
- Outputs: `results/` (parquet), `export/` (Excel)

Educational/research use only. Not financial advice.
