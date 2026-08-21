# SearchForAlpha Lab — Flawless UI/UX Plan (Critical Path)

> **Status at 2026-08-21.** Most of this plan has shipped. The phase text below is the original
> spec and still describes files and line numbers as they were when it was written — read it for
> intent, not as a to-do list. Live status is tracked in [ROADMAP.md](../ROADMAP.md).
>
> | Phase | State |
> |---|---|
> | 1 — chart collapse | Superseded — the Plotly chart was replaced by TradingView Lightweight Charts, rendered client-side |
> | 2 — responsive + collapsible sidebars | Shipped — `layout/shell.py`, `callbacks/layout.py`, `assets/70-forms-responsive.css` |
> | 3 — split the layout file | Shipped — `lib/dash/layout/`, twelve modules |
> | 4 — accessibility & theming | Shipped — CVD palette in `dash_config.py`, `:focus-visible` rings across the sheets |
> | 5 — command palette | Shipped — `layout/command_palette.py`, `callbacks/command_palette.py`, incl. the shortcuts help of 5.3 |
> | 6 — remove dead TradingView branch | Shipped, then reversed by design — Lightweight Charts is now *the* chart |
> | 7 — loading / empty / error states | **Partial** — status bar wired to the callback lifecycle; no global error boundary (7.3), empty states unpolished (7.2) |
> | 8 — performance | Superseded — client-side LWC handles large tapes; bar-count meta in `lib/dash/chart_meta.py` |
> | 9 — tests + docs | Shipped — `docs/ui-architecture.md`, layout tests in `lib/tests/` |

**Target:** laptop (≥1024px) and desktop. Bloomberg-style tri-pane. Backward compatible with existing callbacks and presets. No functional regression in research workflow.

---

## Phase 1 — Fix the chart collapse (root cause of the screenshot)

### 1.1 Layout chain — break the intrinsic-min-width lock

The screenshot happens because `chart_container` and `chart_area` are flex items with `min-width: auto` (the default), and the Plotly graph inside refuses to shrink below its content. Combined with absolute-positioned children (`position: absolute; inset: 0`) that depend on a sized ancestor, the entire flex row overflows the viewport and gets clipped on the left.

In [`lib/dash/styles.py`](lib/dash/styles.py):

- `chart_container` (lines 194-202): change `flex: 1` → `flex: '1 1 0'`, add `'minWidth': 0`, `'width': '100%'`, `'position': 'relative'`.
- `chart_area` (lines 214-218): change `flex: 1` → `flex: '1 1 0'`, add `'minWidth': 0`, `'position': 'relative'`.
- `main_container` (lines 75-79): add `'minWidth': 0` to the flex row itself.

In [`lib/dash/integrated_dashboard.py`](lib/dash/integrated_dashboard.py) at the resizable chart wrapper (lines 867-874):

- Add `'minWidth': 0`, `'width': '100%'`, change `'overflow': 'auto'` → `'overflow': 'hidden'` (the absolute children handle their own clipping).
- Remove the second `plotly-chart-container` div's `'position': 'absolute', 'inset': 0` (lines 840-847). Make it a normal flow child with `width: 100%; height: 100%`. Same for `tv-chart-container` (lines 855-865) — but that one dies in Phase 6.

### 1.2 Lock the body to viewport

In [`lib/dash/assets/dashboard.css`](lib/dash/assets/dashboard.css), add near the top of the file:

```css
html, body { width: 100%; max-width: 100vw; overflow-x: hidden; }
#app-container { width: 100%; max-width: 100vw; }
```

This guarantees that even if a single flex child misbehaves, nothing escapes the viewport.

### 1.3 Plotly sizing sanity

In [`lib/dash/integrated_dashboard.py`](lib/dash/integrated_dashboard.py) (lines 811-827), the `dcc.Graph` already has `responsive: True` and `style={'height': '100%', 'width': '100%'}` — keep that, but also drop the explicit `'toImageButtonOptions'` `height: 800 / width: 1200` (use `'height': None, 'width': None` so the export uses the chart's actual rendered size, not a hardcoded 1200×800 that fights the responsive container).

---

## Phase 2 — Responsive layout, laptop to 4K

### 2.1 Breakpoints in `dashboard.css`

Add media queries:

```css
@media (max-width: 1180px) {
    aside.sfa-right-panel { position: fixed; right: 0; top: 44px; bottom: 24px;
        transform: translateX(100%); transition: transform 200ms ease; z-index: 5; }
    aside.sfa-right-panel.open { transform: translateX(0); }
    aside.sfa-sidebar { width: 220px; min-width: 220px; }
}
@media (min-width: 1800px) {
    aside.sfa-right-panel { width: 360px; min-width: 360px; }
}
```

### 2.2 Collapsible sidebars

- **Left sidebar**: thin `<<` / `>>` toggle button pinned to its top-right edge. State stored in `dcc.Store(id='sidebar-collapsed', storage_type='session')`. When collapsed, sidebar collapses to 40px showing only icons (use existing `bbg-section-header` icons).
- **Right panel**: same pattern, opposite side. Default open on desktop, closed by default on `<1180px`.

These are pure CSS + a tiny clientside callback. No server roundtrip.

### 2.3 Splitter handles (replace `resize: vertical`)

The current chart uses CSS `resize: vertical` (browser-native, ugly). Replace with a small custom splitter component (8px column between right panel and chart) that drags to resize. Reuse the same session-store pattern.

---

## Phase 3 — Split the 1946-line layout file

The single biggest UX risk is that [`lib/dash/integrated_dashboard.py`](lib/dash/integrated_dashboard.py) is 1946 lines. Every layout change touches everything.

Create a new package `lib/dash/layout/` mirroring the `callbacks/` pattern:

```
lib/dash/layout/
    __init__.py
    header.py          # _create_header + status_bar
    sidebar.py         # _create_sidebar + sections
    chart_area.py      # _create_chart_area + toolbar + signal_count_bar
    right_panel.py     # _create_right_panel + tabs
    shell.py           # _create_app_shell composing the above
    overlays.py        # fundamentals + flow overlays
```

Each file owns its builder(s). `integrated_dashboard.py` becomes a thin entry point: import from `layout.shell`, expose `create_dashboard_layout(theme)`.

Mechanical refactor, no behavior change. Keep public function names identical so existing imports keep working.

---

## Phase 4 — Accessibility & theming

### 4.1 Color-blind safe palette (CVD mode)

Bloomberg-style apps must default to CVD-safe colors for ~8% of male users. In [`lib/dash/dash_config.py`](lib/dash/dash_config.py) (lines 134-138), add a fourth theme `'cvd'` mirroring `'bloomberg'` but with:

- `accent_green` → `#0091EA` (blue, "up")
- `accent_red` → `#FF6F00` (orange, "down")

This matches Bloomberg's own CVD research ([Bloomberg UX: Designing the Terminal for color accessibility](https://www.bloomberg.com/ux/2021/10/14/designing-the-terminal-for-color-accessibility/)). The theme toggle button becomes `[ DARK ]` / `[ CVD ]` / `[ LIGHT ]` cycling through three states.

### 4.2 Contrast audit

Walk every CSS variable in `dashboard.css` and verify WCAG 2.2 AA contrast ratios (4.5:1 text, 3:1 UI). Known offenders:

- `text_tertiary: #6E6E6E` on `bg_primary: #0A0A0A` — borderline; bump to `#8A8A8A`.
- `text_secondary: #A8A8A8` on `bg_panel: #0E0E0E` — fine, but check all panel combos.

### 4.3 Don't rely on color alone for P&L

Every place that colors a value green/red (KPI cells, header tape delta, backtest results) must also include a sign or arrow. Audit and patch in [`lib/dash/components.py`](lib/dash/components.py) (`build_metric_card`) and [`lib/dash/integrated_dashboard.py`](lib/dash/integrated_dashboard.py) (header tape, status bar).

### 4.4 Focus rings

`dashboard.css` currently hides outline on inputs. Add a visible `outline: 2px solid var(--border_focus)` on `:focus-visible` for every interactive element (buttons, gear icons, tabs, dropdown triggers). Color-only focus is an accessibility failure.

---

## Phase 5 — Command palette + keyboard shortcuts

The single biggest workflow win for power users ([Superhuman command palette](https://blog.superhuman.com/how-to-build-a-remarkable-command-palette/), [Thrive docs](https://docs.thrive.fi/docs/keyboard-shortcuts)).

### 5.1 Command palette modal

Add a `dbc.Modal(id='command-palette', centered=True, size='lg')` mounted in the shell:

- Large `dcc.Input` autofocus, placeholder "Type a command or search…".
- Result list: scrolling `dbc.ListGroup` of `{label, shortcut, action_id}` rows.
- Fuzzy filter via `difflib.SequenceMatcher` or substring + recency ranking.

Seed commands:

| Command | Shortcut | Action |
|---|---|---|
| Load data | `Ctrl+Enter` (existing) | click load-data-button |
| Run backtest | `Ctrl+B` (existing) | click run-backtest-btn |
| Toggle theme | `Ctrl+J` | cycle theme |
| Toggle right panel | `Ctrl+.` | toggle session-store |
| Toggle sidebar | `Ctrl+,` | toggle session-store |
| Open fundamentals | `G F` | navigate to /fundamentals/<current ticker> |
| Open flow | `G O` | navigate to /flow |
| Reset zoom | `R` | plotly resetZoom on chart |
| Export CSV | `E C` | click export-csv-btn |
| Export PNG | `E P` | plotly downloadImage |
| Switch ticker | type `AAPL` (no slash) | set ticker input |

### 5.2 Wire global shortcut

Extend the existing clientside callback in [`lib/dash/callbacks/misc_ui.py`](lib/dash/callbacks/misc_ui.py) (lines 123-154):

- Add `Ctrl+K` (and `Cmd+K` on Mac) → open command palette.
- Escape inside palette → close it (preserve focus return).
- Arrow keys + Enter to navigate results.

Keep the existing `Ctrl+Enter` and `Ctrl+B` working.

---

### 5.3 Add a help in the UI button that shows the user these shortcuts

## Phase 6 — Remove dead TradingView branch

The TradingView radio option is `disabled=True` ([`integrated_dashboard.py:790`](lib/dash/integrated_dashboard.py)) and the entire TV branch is unreachable. Remove:

- `lib/dash/tv_chart_builder.py` (180 lines)
- `lib/dash/callbacks/chart_tv.py` (94 lines)
- The `Tvlwc` preload div ([`integrated_dashboard.py:124-134`](lib/dash/integrated_dashboard.py))
- The hidden `tv-chart-container` div in `_create_chart_area` ([`integrated_dashboard.py:849-866`](lib/dash/integrated_dashboard.py))
- `dash_tvlwc` import and the try/except wrapper ([`integrated_dashboard.py:22-30`](lib/dash/integrated_dashboard.py))
- `chart-library-toggle` RadioItems (or keep toggle but make Plotly the only option)
- Any `chart-library` reference in `dash_config.PLOT_OPTIONS`

If TradingView is wanted later, gate behind a config flag rather than re-enabling this dead code. Net: ~300 lines removed.

---

## Phase 7 — Loading / empty / error states

The dashboard currently has **one** `dcc.Loading` wrapping the chart and no other loading indicators.

### 7.1 Loading states

- Wrap each major button (Load Data, Run Backtest, Run Optimization, Open Flow) in `dcc.Loading(type='circle', color=theme['accent_blue'])`.
- Add a `dcc.Loading` skeleton placeholder for the chart area when no data is loaded.
- Wire the status bar to actual callback lifecycle: `WAITING` → `LOADING…` → `READY` / `ERROR`.

### 7.2 Empty states

- Chart area before first data load: centered placeholder (Bloomberg-amber logo + "Enter a ticker and click Load Data, or press Ctrl+K").
- Backtest results panel before first run: "Run a backtest to see results".
- Signal list: "No signals match. Try a wider window or different indicators."

### 7.3 Error states

- All callbacks should return user-friendly errors via the existing `build_alert` helper ([`lib/dash/components.py`](lib/dash/components.py)).
- Add a global `error-boundary` div that catches unhandled callback exceptions and renders a dismissible `build_alert(variant='error')`.
- Network errors (Yahoo Finance 429/5xx) get a retry button; validation errors get a hint pointing at the offending field.

---

## Phase 8 — Performance for large datasets

Plotly candlesticks become sluggish past ~2-5k bars ([Plotly community: candlestick performance](https://community.plotly.com/t/candlestick-plot-performance/28851)).

### 8.1 Bar-count indicator

Tiny text in the chart toolbar: `1,247 bars · 1D · 2018-01-02 → 2024-12-31`.

### 8.2 Smart pre-aggregation (no new dependency)

In [`lib/dash/chart_builder.py`](lib/dash/chart_builder.py) (`create_chart`):

- If `len(df) > 5000` and current range shows ≤1500 bars of detail, downsample using `df.resample(...).agg({'Open':'first','High':'max','Low':'min','Close':'last','Volume':'sum'})`.
- Detect zoom range from a `dcc.Store` populated by a `relayout` callback.

This avoids the `plotly-resampler` dependency.

### 8.3 Indicator compute offload

When indicator parameters change via the gear icon ([`lib/dash/callbacks/signals.py`](lib/dash/callbacks/signals.py)), the entire DataFrame is re-enriched. Add a `dcc.Loading` wrapping the signal list and a "Computing…" pill in the status bar.

---

## Phase 9 — Tests + docs

### 9.1 Layout tests

- Snapshot test of `create_dashboard_layout` asserting top-level component IDs match expected tree (`terminal-shell`, `app-container`, `sidebar`, `chart-container`, `right-panel`, `status-bar`).
- CSS unit test: `chart_container` style includes `min-width: 0`.

### 9.2 Document the architecture

Add a new `docs/ui-architecture.md`:

- Component tree diagram (mermaid)
- Layout file map (which file owns which region)
- How to add a new indicator (extend `.cursor/rules/sfa-python.mdc`)
- How to add a new theme / palette
- Keyboard shortcut catalog

---

## Phase ordering (recommended PRs)

1. **PR 1**: Phase 1 (chart collapse fix) — fixes the screenshot bug.
2. **PR 2**: Phase 6 (remove dead TradingView branch) — pure deletion.
3. **PR 3**: Phase 3 (split `integrated_dashboard.py` into `layout/` package) — mechanical refactor.
4. **PR 4**: Phase 2 (responsive breakpoints + collapsible sidebars) — first user-visible polish.
5. **PR 5**: Phase 4 (CVD palette + contrast + focus rings) — accessibility.
6. **PR 6**: Phase 7 (loading/empty/error states) — UX completeness.
7. **PR 7**: Phase 5 (command palette) — biggest power-user win.
8. **PR 8**: Phase 8 (performance) — only matters when intraday data lands.
9. **PR 9**: Phase 9 (tests + docs) — last.

---

## Out of scope

- Mobile (<1024px) — separate project; the Bloomberg-style density doesn't translate.
- Multi-chart layouts / linked charts — Phase 8 in original ideas, not critical path.
- Replacing Plotly with TradingView Lightweight Charts — different architecture; revisit only if perf budget exceeded.
- Live data streaming — functional, not UX; separate track.
- Internationalization — Bloomberg's English-only convention is fine for now.

---

## URL routing (deep links)

Supported browser URLs for ticker preselection:

| URL | Effect |
|---|---|
| `/` | Terminal, default ticker (TSLA) |
| `/ticker/AAPL` | Terminal with AAPL pre-selected |
| `/fundamentals` | Fundamentals workspace, cold-load fallback ticker |
| `/fundamentals/TSLA` | Fundamentals for TSLA |
| `/fundamentals?ticker=AAPL` | Fundamentals for AAPL (flow-scanner legacy link) |
| `/flow` | Flow scanner workspace |
| `/flow/AAPL` | Flow scanner with AAPL pre-selected |

Implementation: `lib/dash/routes.py` parses path segments; `route-ticker-store` syncs the ticker for callbacks.
