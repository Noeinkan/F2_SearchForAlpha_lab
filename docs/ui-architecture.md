# Dashboard UI Architecture

How the Dash dashboard is assembled: the component tree, which file owns which
region, and the recipes for extending it (indicators, themes, shortcuts).

Entry point: `python main.py` → `run_dashboard()` builds the Dash app, sets
`app.layout = create_dashboard_layout(theme, bootstrap)`, then
`register_callbacks(app)`.

---

## Component tree

```mermaid
graph TD
    MP[dmc.MantineProvider] --> APP["#app-container (Div)"]
    APP --> STORES["dcc.Store / dcc.Interval / dcc.Location<br/>(theme, data-loaded, optimization,<br/>chart-payload, command-palette, …)"]
    APP --> SHELL["#terminal-shell (Div)"]
    APP --> FOV[".sfa-fundamentals-overlay"]
    APP --> FLOW[".sfa-flow-overlay"]
    APP --> OPTWS[".sfa-optimize-overlay"]
    APP --> PALETTE["#command-palette (modal)"]
    APP --> SYMSEARCH["#symbol-search-modal"]

    SHELL --> HEADER[".bbg-header — header.py"]
    SHELL --> MAIN["main_container (Div)"]
    SHELL --> STATUS[".bbg-status-bar — header.py"]

    MAIN --> SIDEBAR[".sfa-sidebar (Aside) — sidebar.py"]
    MAIN --> CHART["chart_container (Main) — chart_area.py"]
    MAIN --> SPLIT["#right-panel-splitter"]
    MAIN --> RIGHT[".sfa-right-panel (Aside) — right_panel.py"]

    CHART --> HOME["#chart-area-home"]
    HOME --> TOOLBAR["chart_toolbar<br/>title · #chart-bar-count · export"]
    HOME --> FRAME["#chart-frame > dcc.Loading > #financial-chart"]

    RIGHT --> TABS["Backtest · Optimizer · Data tabs"]
    RIGHT --> BT["#panel-backtest → #backtest-results"]
    RIGHT --> OPT["#panel-optimizer teaser → /optimize"]
    RIGHT --> DATA["#panel-data → #data-table-container"]
    RIGHT --> EXEC["#execution-learn-modal"]

    OPTWS --> OPTCFG["config rail + Run/Stop + opt-* mirrors"]
    OPTWS --> OPTSLOT["#optimize-chart-slot hosts #chart-area-home"]
    OPTWS --> OPTRES["#optimization-results"]

    STATUS --> ACT["#status-activity-label / #status-activity-dot"]
    STATUS --> DS["#data-status · #strategy-order-status"]
```

The whole tree is wrapped in a single `dmc.MantineProvider` so `dmc.Select`
(the searchable ticker box) has Mantine context. Everything is composed **once**
by `create_dashboard_layout` — see the note in `shell.py` about why the stores
live in one builder (avoids the dual-walk bug where two callbacks could see
different `dcc.Store` id sets).

---

## Layout file map

All under [`lib/dash/layout/`](../lib/dash/layout/):

| File | Owns |
| --- | --- |
| `shell.py` | Top-level composer. Emits every `dcc.Store` / `dcc.Interval` / hidden preload div, the four visible regions, the overlays, and the command palette. Also `wire_command_palette_is_open()`. |
| `header.py` | The Bloomberg-style header tape **and** the dense bottom status bar (`_create_header`, `_create_status_bar`). |
| `sidebar.py` | Left sidebar: Market Data, Saved Configurations, Chart Settings. |
| `chart_area.py` | Center chart region: `#chart-area-home` wraps toolbar + `#financial-chart` (reparented into `#optimize-chart-slot` on `/optimize`). |
| `right_panel.py` | Right panel shell: Backtest / Optimizer / Data tabs. |
| `backtest_panel.py` | Backtest tab accordion + execution-mode cards; emits `execution-learn-modal`; **OPEN OPTIMIZER** CTA. SoT for capital/window/costs. |
| `optimizer_panel.py` | Optimizer tab teaser — deep-links to the full-screen workspace. |
| `optimizer_workspace.py` | Full-screen `/optimize/<ticker>` overlay: `opt-*` mirrors, universe, chart slot, Run/Stop, results. |
| `overlays.py` | Fundamentals workspace and Flow scanner workspace (both hidden until opened), plus the Flow learn modal. |
| `command_palette.py` | The Ctrl+K command-palette modal. |
| `symbol_search.py` | The Ctrl+/ symbol-search modal: query box, sector / asset-class filters, watchlist rail. |

### The price chart

`#financial-chart` is a plain `<div>`, not a Dash component. It is drawn by
TradingView Lightweight Charts, vendored at
[`assets/00-lightweight-charts.standalone.production.js`](../lib/dash/assets/)
and driven by the hand-written glue in
[`assets/10-sfa-chart.js`](../lib/dash/assets/10-sfa-chart.js).

Python's only job is to keep `chart-payload-store` current;
[`chart_payload.py`](../lib/dash/chart_payload.py) turns an enriched OHLCV frame
into `{meta, theme, panes, candles, series, markers}`. Everything interactive —
pan, zoom, crosshair, autoscale, chart type, price scale — happens on the client
and never reaches the server.

Two consequences worth knowing before changing anything here:

- **There is no viewport round-trip.** Do not add a callback that rebuilds the
  chart from a zoom or pan event. That loop is what previously put two writers
  on one output in a single Dash 4 dispatch layer, which aborts the whole batch
  with "Duplicate callback outputs" and leaves every control in the app inert.
- **First paint needs a real DOM event.** The payload callback is downstream of
  `load_data`, which raises `PreventUpdate` on a bootstrapped page, and Dash
  never dispatches a callback downstream of a prevented one. The glue therefore
  clicks a hidden `chart-boot-btn` once the container exists.
- **Optimizer reparents the same host.** On `/optimize`, clientside code moves
  `#chart-area-home` into `#optimize-chart-slot` and calls `sfaChart.nudge()` so
  LWC recovers from zero size under a hidden `#terminal-shell`. Close restores
  it under the terminal `main`. Do not mount a second `#financial-chart`.

Callbacks are one file per concern in [`lib/dash/callbacks/`](../lib/dash/callbacks/),
each exposing `register_*_callbacks(app)` and wired together in
`callbacks/__init__.py` (19 registered modules). Notable ones: `data_loading`,
`chart` (the sole `chart-payload-store` writer plus the clientside renderer),
`test_window` (evaluated period + chart focus sync), `data_table` (Data tab
filters and CSV export), `backtest`, `optimization`, `execution_help` (the
Execution Type explainer), `symbol_search`, `status` (Phase 7 activity
indicator), `command_palette`, `misc_ui` (keyboard shortcuts),
`layout` (collapsible panels + splitter).

### Chart-collapse invariant (do not regress)

The chart region must keep `flex: 1 1 0`, `minWidth: 0`, `width: 100%` on both
`main_container` and `chart_container` (see `styles.py`), plus the viewport lock
in `dashboard.css`. Without `min-width: 0` a flex child refuses to shrink below
its content and the chart collapses to zero width. `test_layout.py` guards this.

---

## How to add a new indicator

Signals and chart indicators are two related extension points.

1. **Signal strategy** (buy/sell columns): follow
   [`lib/signals/indicators.py`](../lib/signals/indicators.py) — columns are
   named `{INDICATOR}_{CONDITION}_Buy` / `_Sell`. Parameters always come from
   `config/strategy_config.yaml` via `lib/config_loader.py`. The `/add-signal`
   skill scaffolds this.
2. **Chart pane** (like RSI/MACD): in `chart_payload.py`
   - add the key to `INDICATOR_PANES` (this also fixes its stacking order),
   - write a `_<name>_series(df, times, config, theme)` returning series specs,
   - register it in `_PANE_BUILDERS`,
   - add it to `PLOT_INDICATOR_OPTIONS` in `dash_config.py` so it appears in the
     sidebar toggle list,
   - if it has tunable params, add an `INDICATOR_SETTING_SCHEMA` entry (gear icon
     + settings panel are generated from the schema).

   Read the strategy's own columns when they exist (`ATR_Pct`, `ADX_Pos_DI`,
   `OBV_MA`, …) instead of recomputing, so the plotted line is the series the
   signal actually fired from; keep a local computation only as the fallback for
   bare OHLCV frames. `_strategy_column()` handles the "present but all-NaN"
   case.
3. Keep the deeper conventions in
   [`.cursor/rules/sfa-python.mdc`](../.cursor/rules/sfa-python.mdc) in sync.

There is no downsampling to think about: Lightweight Charts renders the full
series, so the old `DOWNSAMPLE_THRESHOLD` / `MAX_RENDER_BARS` machinery is gone
along with the zoom round-trip that needed it.

---

## How to add a new theme / palette

Themes are palette dicts in `THEMES` in
[`lib/dash/dash_config.py`](../lib/dash/dash_config.py).

1. Add a new key to `THEMES` with the full colour set (copy an existing entry —
   `bloomberg` is the reference — and change values). Required keys include
   `bg_primary/secondary/tertiary`, `text_primary/secondary/tertiary`,
   `border_primary`, `accent_*`, and the `chart_*` colours.
2. Add the key to `THEME_CYCLE` (currently `('bloomberg', 'cvd', 'light')`) in
   the order the header button should cycle through.
3. `DEFAULT_THEME` selects the initial theme.
4. If the theme needs CSS overrides beyond inline styles (e.g. the CVD focus
   ring), add a `:root[data-theme="<name>"]` block in
   [`lib/dash/assets/dashboard.css`](../lib/dash/assets/dashboard.css). The theme
   toggle stamps `data-theme` on the root element.

When you change the shape of any persisted `dcc.Store`, bump
`UI_STORAGE_VERSION` in `dash_config.py` so stale browser storage is discarded.
Phase 3 adds `optimizer-run-history-store` (localStorage, capped summaries).

The full-screen Optimizer (`/optimize`) adds a Plotly **Return vs Sharpe**
landscape (`optimizer-landscape-graph`), OOS validation strip, run-history list,
and a **Bayesian Sweep** rail section — callbacks in `optimizer_phase3.py`.

---

## Keyboard shortcuts

Registered clientside in
[`lib/dash/callbacks/misc_ui.py`](../lib/dash/callbacks/misc_ui.py) (global
`keydown` listener) and the palette handler in `command_palette`.

| Shortcut | Action |
| --- | --- |
| `Ctrl/Cmd + K` | Open the command palette |
| `Ctrl/Cmd + /` or bare `/` | Open the symbol search modal |
| `Ctrl + Enter` | Load / refresh market data |
| `Ctrl + B` | Run backtest |
| `G` then `F` | Open Fundamentals for the current ticker |
| `Esc` | Close the palette / symbol search / dismiss alerts & overlays |
| `↑` / `↓` | Move selection within the palette or symbol search |
| `Enter` | Run the highlighted palette command / pick the highlighted symbol |
| `Tab` | Cycle focus within the open palette |

Bare `/` only opens symbol search when focus is not in a text field, and the
binding is deliberately **not** `Ctrl+K` — the palette and symbol search must
never fight over one key.

The header `?` button and the status-bar **COMMANDS** button both open the same
palette; every palette action maps to a DOM side-effect via the dispatch bridge
in `misc_ui.py` (no server round-trip).

---

## Status & loading feedback (Phase 7)

- Action outputs are wrapped in `dcc.Loading` (chart, `backtest-results`,
  fundamentals content, flow content, signal list) with a `delay_show` so fast
  sidebar-driven redraws don't flash a spinner.
- The status-bar activity segment (`#status-activity-label` / `-dot`) is driven
  by `callbacks/status.py`: a clientside handler flips it to **WORKING…** the
  instant an action starts, and resolvers settle it to **READY** / **ERROR**
  from the callback outputs. Optimization mirrors its interval's `disabled` flag.
