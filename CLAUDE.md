# SearchForAlpha Lab

Python algorithmic trading research: Yahoo Finance OHLCV → indicator signals → backtest → Dash dashboard.

**Start:** `python main.py` (dev mode on, reload off by default, port 8050) · **Test:** `rtk python -m pytest lib/tests/ -q`

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
- Dash reload: `DASH_RELOAD=1` opt-in (off by default — Werkzeug reloader is unreliable on Windows; debug error pages still honour `DASH_DEV`)
- Browser landing: `run_dashboard()` opens `http://127.0.0.1:<port>/ticker/<DEFAULT_TICKER>` via `_default_browser_path()` (bootstrap-driven)
- Theme: default is `bloomberg` (dark); header button cycles bloomberg→cvd→light. Palettes in `lib/dash/dash_config.py` `THEMES` (`DEFAULT_THEME`)
- Flow Scanner: served at `/flow/<ticker>` and `/flow_report.html` (stub when `flow_report.html` absent); regenerate via `scripts/flow_scanner.py <ticker>`
- Outputs: `results/` (parquet), `export/` (Excel)

Educational/research use only. Not financial advice.
