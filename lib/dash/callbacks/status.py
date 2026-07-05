"""
Status-bar activity indicator callbacks (Phase 7).

The footer's first segment (``status-activity-label`` + ``status-activity-dot``)
reflects the real callback lifecycle instead of a static "READY" placeholder:

* A clientside *initiator* flips it to ``WORKING…`` the instant an action
  button is clicked (or the symbol is changed) — this fires in the browser
  before the server round-trip, so the user gets immediate feedback.
* Clientside *resolvers* flip it back to ``READY`` (or ``ERROR`` on a failed
  data load) once the corresponding output lands.

All handlers are clientside so they add zero server-callback latency. The
initiator is the canonical writer; every other handler targets the same two
props with ``allow_duplicate=True``.

Optimization is handled off its interval's ``disabled`` flag (False while a
run is in flight, True when idle/finished) rather than its per-tick result
output, so the indicator does not prematurely settle on ``READY`` while
partial results stream in.
"""

from dash.dependencies import Input, Output


def register_status_callbacks(app) -> None:
    # Initiator — flip to WORKING… the moment an action starts. Canonical
    # writer (no allow_duplicate).
    app.clientside_callback(
        """
        function(_loadClicks, _backtestClicks, _tickerValue) {
            return ['WORKING\\u2026', 'dot dot-warn dot-pulse'];
        }
        """,
        Output('status-activity-label', 'children'),
        Output('status-activity-dot', 'className'),
        Input('load-data-button', 'n_clicks'),
        Input('run-backtest-btn', 'n_clicks'),
        Input('ticker-dropdown', 'value'),
        prevent_initial_call=True,
    )

    # Optimization lifecycle — mirror the interval's disabled flag.
    app.clientside_callback(
        """
        function(intervalDisabled) {
            if (intervalDisabled === false) {
                return ['WORKING\\u2026', 'dot dot-warn dot-pulse'];
            }
            return ['READY', 'dot dot-up'];
        }
        """,
        Output('status-activity-label', 'children', allow_duplicate=True),
        Output('status-activity-dot', 'className', allow_duplicate=True),
        Input('optimization-interval', 'disabled'),
        prevent_initial_call=True,
    )

    # Resolver — settle back to READY, or ERROR when a data load failed.
    app.clientside_callback(
        """
        function(dataStatus, _backtestChildren) {
            var s = (dataStatus == null ? '' : String(dataStatus)).toUpperCase();
            if (s.indexOf('ERROR') !== -1) {
                return ['ERROR', 'dot dot-down'];
            }
            return ['READY', 'dot dot-up'];
        }
        """,
        Output('status-activity-label', 'children', allow_duplicate=True),
        Output('status-activity-dot', 'className', allow_duplicate=True),
        Input('data-status', 'children'),
        Input('backtest-results', 'children'),
        prevent_initial_call=True,
    )
