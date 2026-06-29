Create a new Dash callback for the integrated dashboard.

Usage: /new-callback [DESCRIPTION]

Example: /new-callback "export chart as PNG when button is clicked"

Steps to follow:
1. Read `.cursor/rules/dash-callbacks.mdc` for the current register/layout architecture.
2. Read `lib/dash/integrated_dashboard.py` (app init only) and 2–3 existing callbacks in `lib/dash/callbacks/` for the `register_*_callbacks(app)` pattern.
3. Identify the correct Input(s), Output(s), and State(s) for the new callback based on the description.
4. Create `lib/dash/callbacks/{name}.py` with:
   - `def register_{name}_callbacks(app):` wrapping the `@app.callback` decorator
   - `prevent_initial_call=True` unless initial fire is required (`'initial_duplicate'` for routing-style callbacks)
   - Type hints on all parameters
   - Clear docstring explaining what triggers it and what it does
5. Register the new function in `lib/dash/callbacks/__init__.py` inside `register_callbacks()` — **do not** import in `integrated_dashboard.py`.
6. If new UI components are needed, add them to the appropriate file in `lib/dash/layout/` (not `integrated_dashboard.py`).
7. Run targeted tests: `rtk python -m pytest lib/tests/test_dashboard.py lib/tests/test_dash_routing.py -q`
8. Show the user what was created and how to test it (`python main.py`).
