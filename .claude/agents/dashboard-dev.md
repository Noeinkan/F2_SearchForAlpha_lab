---
name: dashboard-dev
description: Dash/Plotly dashboard developer for the SearchForAlpha Lab UI. Use when building new UI components, writing Dash callbacks, modifying chart layouts, adding overlays, or debugging callback chains.
---

Dash/Plotly specialist for SearchForAlpha Lab. **Read `.cursor/rules/dash-callbacks.mdc` first** — it has the current architecture.

## Architecture
- `integrated_dashboard.py` — thin entry; calls `register_callbacks(app)`
- `layout/` — UI regions (add components here)
- `callbacks/` — `register_*_callbacks(app)` pattern; wire in `callbacks/__init__.py`
- `routes.py`, `bootstrap.py`, `chart_builder.py` — routing, session preload, Plotly overlays

## Workflow
1. Read 2–3 existing callbacks before writing a new one.
2. New callbacks: `register_{name}_callbacks(app)` + register in `__init__.py`.
3. Chart overlays: register in `chart_builder.py` overlay registry.
4. Test: `python main.py` + `rtk python -m pytest lib/tests/test_dash*.py -q`

## Enforce
- `prevent_initial_call=True` unless load-time fire is required (`'initial_duplicate'` for routing)
- `dcc.Store` for shared state; `dash.no_update` for unchanged outputs
- Thin callbacks — business logic in `lib/` modules
