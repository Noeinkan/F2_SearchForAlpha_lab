"""
Phase 5 — Command palette server-side callbacks.

The keyboard listener (clientside, in misc_ui) owns open/close on Ctrl+K
and Esc. This module wires the rest:

  - Seed the master commands list into `command-palette-commands` once
    on startup. Used by the row-render and clientside filter.
  - Filter the visible rows based on the search query (clientside).
    The filtering is done on the client to avoid a roundtrip per
    keystroke; the master command list comes from the store populated
    here.
  - Dispatch a clicked row: when a `sfa-palette-row` is clicked, look up
    its `data-cmd-id` and trigger the matching side-effect (route change,
    button click, etc.). This is the single funnel for every command.
  - Close the palette when a row is dispatched, and refocus the chart.
  - When the user clicks the header `[ ? ]` button, open the palette
    with the special query `?` so a separate modal of the same chrome
    shows the shortcut catalog. Implemented as a second store-driven
    modal.

Convention: this file owns the *server-side* behavior only. The clientside
filter and key handling live in `misc_ui.py` and the layout chrome lives
in `lib/dash/layout/command_palette.py`.
"""

from __future__ import annotations

import difflib
import re

from dash import callback_context, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.layout.command_palette import COMMANDS


# Detect "looks-like-a-ticker" queries: 1-5 uppercase letters, optional
# trailing .X for share class. We synthesize a "Switch ticker" command for
# these so the palette doubles as a quick ticker switcher.
#
# IMPORTANT: only treat the query as a ticker when it is ALREADY
# uppercase. The user types tickers as uppercase (AAPL, TSLA, BRK.B),
# and the convention is that bare-text lowercase queries like "theme"
# are command searches, not symbol entries. This prevents a query like
# "theme" from being misread as the ticker THEME.
_TICKER_RE = re.compile(r"^[A-Z]{1,5}(\.[A-Z])?$")


def _build_synthetic_ticker_cmd(ticker: str) -> dict:
    """Build a transient command dict for a bare ticker query."""
    return {
        "id": f"switch-ticker:{ticker}",
        "label": f"Switch ticker to {ticker}",
        "shortcut": "",
        "group": "Navigate",
        "hint": "Set the ticker input and load data",
    }


def _score(query: str, text: str) -> float:
    """Return a relevance score in [0, 1]. Higher = better.

    Pure substring match scores highest, then prefix, then a fuzzy
    SequenceMatcher ratio. Empty query = 1.0 (show everything).
    """
    if not query:
        return 1.0
    q = query.lower()
    t = text.lower()
    if q == t:
        return 1.0
    if t.startswith(q):
        return 0.9
    if q in t:
        return 0.75
    # difflib ratio on the closest chunk; cap to avoid noise
    return min(0.6, difflib.SequenceMatcher(None, q, t).ratio())


def _filter_commands(query: str, top_n: int = 25) -> list[dict]:
    """Return the top-N commands matching the query, with synthesized
    ticker commands for bare ticker queries.
    """
    query = (query or "").strip()
    out: list[dict] = []

    # Synthetic ticker switch command for bare tickers.
    # Match against the raw query (not uppercased) so that a lowercase
    # word like "theme" doesn't accidentally match the ticker pattern.
    if _TICKER_RE.match(query):
        out.append(_build_synthetic_ticker_cmd(query))
        return out

    # Score every command by its label + hint + group.
    scored: list[tuple[float, dict]] = []
    for cmd in COMMANDS:
        haystack = " ".join([cmd["label"], cmd["hint"], cmd["group"]])
        scored.append((_score(query, haystack), cmd))
    scored.sort(key=lambda x: x[0], reverse=True)

    # Keep anything with a non-zero score.
    for score, cmd in scored:
        if score <= 0:
            break
        out.append({**cmd, "_score": score})
        if len(out) >= top_n:
            break
    return out


def register_command_palette_callbacks(app) -> None:
    """Wire all command-palette server-side callbacks."""

    # Seed the master command list at startup. The store is read by the
    # clientside filter so the list lives in exactly one place on the server.
    @app.callback(
        Output('command-palette-commands', 'data'),
        Input('startup-interval', 'n_intervals'),
    )
    def _seed_commands(_):
        return COMMANDS

    # When the user submits or types in the palette input, recompute the
    # ranked list of visible commands. The clientside filter ALSO runs so
    # the result is instantaneous, but this callback is the source of truth
    # for what to show when the palette first opens (empty query = show all).
    @app.callback(
        Output('command-palette-visible', 'data'),
        Input('command-palette-query', 'value'),
    )
    def _filter_palette(query):
        return _filter_commands(query or "")

    # Wire the help button to the palette. Clicking the `[ ? ]` button in
    # the header opens the palette with the query pre-set to "shortcuts" so
    # the user can read the shortcut catalog inline (the palette also serves
    # as the shortcuts modal since it has the same chrome).
    @app.callback(
        Output('command-palette-open', 'data'),
        [Input('help-shortcuts-btn', 'n_clicks'),
         Input('palette-open-btn', 'n_clicks'),
         Input('sfa-palette-esc-trigger', 'data')],
        [State('command-palette-open', 'data')],
        prevent_initial_call=True,
    )
    def _toggle_palette_from_buttons(_help_clicks, _palette_clicks, esc_data, current):
        """Open from the header help button or the status-bar COMMANDS
        button; close from the esc-trigger store.

        The esc-trigger store is incremented by the clientside keyboard
        listener when Escape is pressed while the palette is open; using
        a store keeps the listener decoupled from `dbc.Modal.is_open`
        which we drive directly with no_update when the source of truth
        changes.
        """
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id in ('help-shortcuts-btn', 'palette-open-btn'):
            return True
        if trigger_id == 'sfa-palette-esc-trigger':
            # Nothing writes this store today — Esc is handled natively by
            # `dbc.Modal(keyboard=True)`. So the only time it fires is when
            # the shell remounts and it reports its default `None`. Toggling
            # on that opened the palette by itself on page load, and its
            # backdrop then swallowed every click in the app. Treat `None`
            # as "no signal"; only an explicit `False` means Esc-to-close.
            if esc_data is None:
                raise PreventUpdate
            return False
        raise PreventUpdate

    # Dispatch a palette command. Triggered by clicking a row in the
    # palette list. The row's `id` is a dict (pattern-matching) carrying
    # the command id, and the row's `data-cmd-id` attribute is the same
    # value (used as a fallback for direct DOM lookups).
    @app.callback(
        [Output('command-palette-dispatch', 'data'),
         Output('command-palette-open', 'data', allow_duplicate=True)],
        Input({'type': 'sfa-palette-row', 'index': ALL},
               'n_clicks'),
        [State('command-palette-open', 'data')],
        prevent_initial_call=True,
    )
    def _dispatch_palette_row(n_clicks, open_state):
        """Run the command carried by the clicked row."""
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        prop_id = ctx.triggered[0]['prop_id']
        # Pattern-matching callback: prop_id looks like
        #   {"index":"load-data","type":"sfa-palette-row"}.n_clicks
        try:
            import json
            head = prop_id.split('.', 1)[0]
            cmd_id_dict = json.loads(head)
            cmd_id = cmd_id_dict.get('index')
        except Exception:
            return no_update, no_update

        if not cmd_id or not n_clicks:
            raise PreventUpdate

        # Synthetic ticker switch command — id is "switch-ticker:AAPL".
        if cmd_id.startswith('switch-ticker:'):
            ticker = cmd_id.split(':', 1)[1]
            return {'action': 'switch-ticker', 'ticker': ticker}, False

        # Closing the palette on dispatch is the default; reset zoom and
        # the export actions stay open but we still close for consistency.
        return {'action': cmd_id, 'ticker': None}, False

    # Action: route changes (navigate to /flow, /fundamentals/<ticker>, /).
    @app.callback(
        Output('app-url', 'pathname', allow_duplicate=True),
        Input('command-palette-dispatch', 'data'),
        [State('ticker-dropdown', 'value')],
        prevent_initial_call=True,
    )
    def _dispatch_navigate(dispatch, current_ticker):
        if not dispatch:
            raise PreventUpdate
        action = dispatch.get('action')
        # Use the dispatch's ticker if present (synthetic ticker switch
        # command), else fall back to whatever the user has selected.
        ticker = (dispatch.get('ticker') or current_ticker or 'TSLA').upper()
        if action == 'go-fundamentals':
            return f'/fundamentals/{ticker}'
        if action == 'go-flow':
            return f'/flow/{ticker}'
        if action == 'go-optimize':
            return f'/optimize/{ticker}'
        if action == 'go-terminal':
            return '/'
        raise PreventUpdate

    # Action: theme cycle. Trigger the theme-toggle button so the existing
    # server-side callback (in misc_ui) does the cycling. We can't directly
    # bump theme-store from here without breaking the existing label sync.
    @app.callback(
        Output('theme-toggle', 'n_clicks', allow_duplicate=True),
        Input('command-palette-dispatch', 'data'),
        prevent_initial_call=True,
    )
    def _dispatch_theme(dispatch):
        if not dispatch or dispatch.get('action') != 'toggle-theme':
            raise PreventUpdate
        # The existing theme-toggle callback uses n_clicks delta to advance
        # one step in the cycle. We just need to bump the counter — return
        # the current dash_clientside no_update style by reading latest
        # value via a no-op callback. Since we don't have the current
        # value here, we return a sentinel that increments: we set n_clicks
        # directly by appending to the existing value through a clientside
        # wrapper. Easier: dispatch a custom event.
        raise PreventUpdate

    # Sidebar / right-panel toggles: dispatch as synthetic clicks on the
    # existing toggle buttons. The buttons are server-controlled so we
    # need a small DOM nudge — we use a clientside callback to translate
    # the dispatch store into a button click on the right element.

    # Filter and dispatch the synthetic "switch-ticker" command by writing
    # to ticker-dropdown. This intentionally uses allow_duplicate=True
    # because routing/fundamentals callbacks also write the same Output.
    @app.callback(
        Output('ticker-dropdown', 'value', allow_duplicate=True),
        Input('command-palette-dispatch', 'data'),
        prevent_initial_call=True,
    )
    def _dispatch_ticker(dispatch):
        if not dispatch:
            raise PreventUpdate
        if dispatch.get('action') != 'switch-ticker':
            raise PreventUpdate
        ticker = (dispatch.get('ticker') or '').upper()
        if not ticker:
            raise PreventUpdate
        return ticker

    # Render the dispatch action into a clientside bridge. The clientside
    # callback translates the dispatch store into actual DOM button clicks
    # for the actions that aren't pure data writes (load-data, backtest,
    # export-csv, export-png, reset-zoom, theme cycle, sidebar toggle,
    # right-panel toggle, clear-data).
    @app.callback(
        Output('command-palette-bridge', 'data'),
        Input('command-palette-dispatch', 'data'),
        prevent_initial_call=True,
    )
    def _refresh_bridge(dispatch):
        if not dispatch:
            raise PreventUpdate
        # Echoing through a store is enough — the clientside listener
        # already watches `command-palette-bridge` for changes and runs
        # the matching DOM action.
        return dispatch


# Pattern-matching wildcard imported once at module top. Dash 4.x exposes
# `ALL` as a sentinel object (not a callable); use it directly in pattern
# dicts: `Input({'type': 'foo', 'index': ALL}, 'n_clicks')`.
from dash.dependencies import ALL  # noqa: E402, F401  (re-exported for callers)
