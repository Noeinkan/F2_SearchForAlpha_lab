Create a new Dash callback for the integrated dashboard.

Usage: /new-callback [DESCRIPTION]

Example: /new-callback "export chart as PNG when button is clicked"

Steps to follow:
1. Read `lib/dash/integrated_dashboard.py` to understand the app instance and layout structure.
2. Read 2-3 existing callbacks in `lib/dash/callbacks/` to understand the naming and pattern conventions.
3. Identify the correct Input(s), Output(s), and State(s) for the new callback based on the description.
4. Create a new file `lib/dash/callbacks/callback_{snake_case_name}.py` with:
   - The `@app.callback` decorator
   - `prevent_initial_call=True` unless initial call is needed
   - Type hints on all parameters
   - Clear docstring explaining what triggers it and what it does
5. Import the new callback module in `lib/dash/integrated_dashboard.py`.
6. If new UI components (buttons, dropdowns) are needed, add them to the layout in `integrated_dashboard.py`.
7. Show the user what was created and how to test it.
