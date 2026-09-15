"""Quick-swap callbacks — change the symbol, keep the test, re-run, compare.

The chain one swap sets off, in order:

  1. ``swap_symbol`` writes the new symbol to ``ticker-dropdown`` (which loads
     its data as any symbol change does), parks the current test window in
     ``test-window-pending-store`` with ``hold=True``, and names the symbol it
     is waiting on in ``quick-swap-autorun``.
  2. ``sync_test_window`` (test_window.py) picks the held window up once the new
     series has loaded and keeps its dates, instead of resetting to the full
     range as a plain symbol change does.
  3. The clientside ``autorun_after_swap`` sees ``test-window-series-store``
     move to that symbol and clicks RUN BACKTEST. Waiting for the series store
     rather than the data store matters: it is written in the same response as
     the window dates, so the backtest can never read the old window.
  4. ``run_backtest_callback`` (backtest.py) adds the run to
     ``quick-swap-compare-store``, which ``render_compare_table`` draws.

A load that fails (rate limit, bad symbol) never moves the series store, so
nothing runs against the previous symbol's data under the new symbol's name.

Output ownership:

  ticker-dropdown.value            <- swap_symbol (allow_duplicate)
  test-window-pending-store.data   <- swap_symbol (allow_duplicate)
  quick-swap-autorun.data          <- swap_symbol (only writer)
  quick-swap-autorun-sink.data     <- autorun_after_swap (only writer)
  quick-swap-compare-store.data    <- run_backtest_callback + clear_compare (allow_duplicate)
"""

from __future__ import annotations

import json
import time

from dash import callback_context
from dash.dependencies import ALL, Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.layout.quick_swap import build_chips, build_compare_table
from lib.dash.quick_swap import neighbour_symbol
from lib.dash.watchlist_storage import normalize, symbols_in


def _active_list(watchlists, list_name) -> tuple[str, list[str]]:
    """The watchlist the search modal has selected, and its symbols."""
    payload = normalize(watchlists)
    name = list_name if list_name in payload['watchlists'] else payload['active']
    return name, symbols_in(payload, name)


def _swap_target(triggered: dict, watchlists, list_name, current) -> str | None:
    """Which symbol a click or key asked for, or None when nothing was really clicked."""
    prop_id = triggered.get('prop_id', '')
    # Chips and rows are re-rendered after every swap with n_clicks at 0, and
    # Dash fires this callback for each re-render. Only a real click counts.
    if not triggered.get('value'):
        return None
    if prop_id.startswith('{'):
        try:
            component = json.loads(prop_id.split('.', 1)[0])
        except ValueError:
            return None
        index = str(component.get('index') or '')
        return index.split('|', 1)[0].upper() or None
    _, symbols = _active_list(watchlists, list_name)
    if prop_id.startswith('quick-swap-prev'):
        return neighbour_symbol(symbols, current, -1)
    if prop_id.startswith('quick-swap-next'):
        return neighbour_symbol(symbols, current, 1)
    return None


def register_quick_swap_callbacks(app) -> None:
    @app.callback(
        [Output('quick-swap-chips', 'children'),
         Output('quick-swap-list-name', 'children')],
        [Input('watchlists-store', 'data'),
         Input('symbol-search-list', 'value'),
         Input('ticker-dropdown', 'value')],
    )
    def render_chips(watchlists, list_name, ticker):
        name, symbols = _active_list(watchlists, list_name)
        return build_chips(symbols, ticker), name

    @app.callback(
        [Output('ticker-dropdown', 'value', allow_duplicate=True),
         Output('test-window-pending-store', 'data', allow_duplicate=True),
         Output('quick-swap-autorun', 'data')],
        [Input({'type': 'quick-swap-chip', 'index': ALL}, 'n_clicks'),
         Input({'type': 'quick-swap-row', 'index': ALL}, 'n_clicks'),
         Input('quick-swap-prev', 'n_clicks'),
         Input('quick-swap-next', 'n_clicks')],
        [State('watchlists-store', 'data'),
         State('symbol-search-list', 'value'),
         State('ticker-dropdown', 'value'),
         State('test-window-start', 'date'),
         State('test-window-end', 'date')],
        prevent_initial_call=True,
    )
    def swap_symbol(_chips, _rows, _prev, _next, watchlists, list_name, ticker,
                    window_start, window_end):
        """Change the symbol and nothing else about the test."""
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        current = str(ticker or '').strip().upper()
        target = _swap_target(ctx.triggered[0], watchlists, list_name, current)
        # Swapping to the symbol already loaded would load nothing, so the
        # held window and the autorun would sit waiting for the *next*
        # unrelated symbol change and fire there.
        if not target or target == current:
            raise PreventUpdate

        pending = (
            {'start': window_start, 'end': window_end, 'hold': True}
            if window_start and window_end else None
        )
        return target, pending, {'ticker': target, 'nonce': time.time()}

    app.clientside_callback(
        """
        function(seriesKey, autorun) {
            var noUpdate = window.dash_clientside.no_update;
            if (!seriesKey || !autorun || !autorun.ticker) { return noUpdate; }
            if (String(seriesKey).indexOf(autorun.ticker + '|') !== 0) { return noUpdate; }
            if (window.__sfaQuickSwapRan === autorun.nonce) { return noUpdate; }
            // A swap whose load failed is abandoned: reaching that symbol
            // minutes later by another route must not run a backtest.
            if (Date.now() / 1000 - autorun.nonce > 120) { return noUpdate; }
            window.__sfaQuickSwapRan = autorun.nonce;
            var btn = document.getElementById('run-backtest-btn');
            if (btn) { btn.click(); }
            return autorun.nonce;
        }
        """,
        Output('quick-swap-autorun-sink', 'data'),
        Input('test-window-series-store', 'data'),
        State('quick-swap-autorun', 'data'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('quick-swap-compare', 'children'),
        [Input('quick-swap-compare-store', 'data'),
         Input('ticker-dropdown', 'value')],
    )
    def render_compare_table(rows, ticker):
        return build_compare_table(rows, ticker)

    @app.callback(
        Output('quick-swap-compare-store', 'data', allow_duplicate=True),
        Input('quick-swap-clear', 'n_clicks'),
        prevent_initial_call=True,
    )
    def clear_compare(n_clicks):
        if not n_clicks:
            raise PreventUpdate
        return []
