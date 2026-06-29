# SearchForAlpha Lab

Python algorithmic trading research: Yahoo Finance OHLCV → indicator signals → backtest → Dash dashboard.

**Start:** `python main.py` (dev reload on by default, port 8050) · **Test:** `rtk python -m pytest lib/tests/ -q`

## Navigation
- Module index: [.claude/PROJECT_INDEX.md](.claude/PROJECT_INDEX.md) (detail: [PROJECT_INDEX_MODULES.md](.claude/PROJECT_INDEX_MODULES.md))
- Scoped rules: [.cursor/rules/](.cursor/rules/) (load on demand by file path)
- Token efficiency rationale: [docs/token-efficiency.md](docs/token-efficiency.md)
- **sfa research in Cursor:** read [docs/openclaw-research.md](docs/openclaw-research.md) first (`@`-mention it)

## Non-obvious essentials
- Signal columns: `{INDICATOR}_{CONDITION}_Buy` / `_Sell` — see `lib/signals/indicators.py`
- Indicator params: always from `config/strategy_config.yaml` via `lib/config_loader.py`
- Dash callbacks: one file per concern in `lib/dash/callbacks/`; register via `register_*_callbacks(app)` in `callbacks/__init__.py`
- Dash dev: `DASH_DEV=1` default; bump `UI_STORAGE_VERSION` in `dash_config.py` when persisted store shape changes
- Outputs: `results/` (parquet), `export/` (Excel)

Educational/research use only. Not financial advice.
