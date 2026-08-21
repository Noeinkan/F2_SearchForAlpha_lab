# SearchForAlpha Lab

Python algorithmic trading research: Yahoo Finance OHLCV → indicator signals → backtest → Dash dashboard.

**Start:** `python main.py` (dev mode on, reload off by default, port 8050) · **Test:** `rtk python -m pytest lib/tests/ -q`

## Navigation
- Shipped vs open work: [ROADMAP.md](ROADMAP.md)
- Module index: [.claude/PROJECT_INDEX.md](.claude/PROJECT_INDEX.md) (detail: [PROJECT_INDEX_MODULES.md](.claude/PROJECT_INDEX_MODULES.md))
- Scoped rules: [.cursor/rules/](.cursor/rules/) (load on demand by file path)
- Token efficiency rationale: [docs/token-efficiency.md](docs/token-efficiency.md)
- **sfa research in Cursor:** read [docs/openclaw-research.md](docs/openclaw-research.md) first (`@`-mention it)

## Non-obvious essentials
- OHLCV is split- and dividend-adjusted, and corporate-action columns are stripped — [docs/data-adjustment.md](docs/data-adjustment.md). Yahoo is the only wired vendor; the seam for adding another is `_yahoo_history` in `lib/data_processing.py`, and [docs/data-vendors.md](docs/data-vendors.md) records why no free second source exists today
- Transient fetch failures (429/5xx/timeout) are retried then raised as `TransientFetchError` (`lib/fetch_errors.py`); the dashboard renders them as `RATE LIMITED`, distinct from a bad ticker
- Signal columns: `{INDICATOR}_{CONDITION}_Buy` / `_Sell` — see `lib/signals/indicators.py`
- Indicator params: always from `config/strategy_config.yaml` via `lib/config_loader.py`
- Dash callbacks: one file per concern in `lib/dash/callbacks/`; register via `register_*_callbacks(app)` in `callbacks/__init__.py`
- Price chart is TradingView Lightweight Charts, **not Plotly**: Python only writes `chart-payload-store` (`lib/dash/chart_payload.py`), the client renders it (`assets/10-sfa-chart.js`). Never add a callback that rebuilds the chart from a pan/zoom event — see [docs/ui-architecture.md](docs/ui-architecture.md)
- Dash dev: `DASH_DEV=1` default; bump `UI_STORAGE_VERSION` in `dash_config.py` when persisted store shape changes
- Dash reload: `DASH_RELOAD=1` opt-in (off by default — Werkzeug reloader is unreliable on Windows; debug error pages still honour `DASH_DEV`)
- Browser landing: `run_dashboard()` opens `http://127.0.0.1:<port>/ticker/<DEFAULT_TICKER>` via `_default_browser_path()` (bootstrap-driven)
- Theme: default is `bloomberg` (dark); header button cycles bloomberg→cvd→light. Palettes in `lib/dash/dash_config.py` `THEMES` (`DEFAULT_THEME`)
- CSS: eleven numbered sheets in `lib/dash/assets/` (`10-tokens.css` … `90-symbol-search.css`), no build step. **Dash injects assets in sorted filename order, so the prefixes are the cascade** — vendored Bootstrap must stay `00-bootstrap.min.css` or every override breaks. File map + editing rules: [docs/ui-architecture.md](docs/ui-architecture.md#stylesheet-layout)
- Flow Scanner: served at `/flow/<ticker>` and `/flow_report.html` (stub when `flow_report.html` absent); regenerate via `scripts/flow_scanner.py <ticker>`
- Symbol search: modal at `lib/dash/layout/symbol_search.py` (Ctrl+/). **`ticker-dropdown` is still the current-symbol source of truth for ~15 callbacks** — it is mounted but `display:none` in the sidebar; never delete or re-type it, write to `.value` with `allow_duplicate=True`
- Symbol universe: committed `config/tickers_universe.csv` (~13k rows, sector/industry/asset class), read via `lib/ticker_universe.py`. Regenerate with `python scripts/build_universe.py`; hand-maintained non-equities live in `config/tickers_curated.csv`
- Feedback button: header ✉ → modal (`lib/dash/layout/feedback.py`), delivery in `lib/dash/feedback.py`. Falls back to a pre-filled `mailto:` unless `SFA_FEEDBACK_ENDPOINT` points at a JSON form relay; destination is `FEEDBACK_EMAIL` in `dash_config.py`
- Watchlists: `config/watchlists.json` via `lib/dash/watchlist_storage.py` (disk is source of truth; `watchlists-store` is a mirror). Separate from the flow scanner's `watchlist.txt`
- Outputs: `results/` (parquet), `export/` (Excel)

Educational/research use only. Not financial advice.
