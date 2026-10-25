"""Header watchlist strip and its editor.

The strip reads the same list the Backtest quick-swap strip shows (the one
selected in the search modal), so the two never disagree. The editor works on
a draft store and touches ``watchlists-store`` and the disk only on SAVE.

Output ownership:

  header-watchlist-chips.children   <- render_header_chips (only writer)
  ticker-dropdown.value             <- select_header_symbol (allow_duplicate)
  watchlist-editor-modal.is_open    <- open_editor, close_editor (allow_duplicate)
  watchlist-editor-draft.data       <- open_editor, edit_draft (allow_duplicate)
  watchlist-editor-order.data       <- assets/86-watchlist-editor.js (set_props)
  watchlists-store.data             <- close_editor on SAVE (allow_duplicate)
"""

from __future__ import annotations

import json
import logging

from dash import callback_context, no_update
from dash.dependencies import ALL, Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import WATCHLIST_FILE_PATH
from lib.dash.layout.header_watchlist import (
    build_editor_rows,
    build_header_chips,
    editor_counter,
)
from lib.dash.ticker_search import resolve_ticker_symbol
from lib.dash.watchlist_storage import (
    MAX_WATCHLIST_SYMBOLS,
    normalize,
    save_watchlists,
    set_symbols,
)
from .quick_swap import _active_list

logger = logging.getLogger(__name__)


def clicked_index(triggered: dict) -> str | None:
    """The ``index`` of a really clicked pattern-matched button, or None.

    Buttons are re-rendered with n_clicks at 0 and Dash fires the callback for
    each re-render; only a non-zero value is a click.
    """
    if not triggered.get('value'):
        return None
    prop_id = triggered.get('prop_id', '')
    if not prop_id.startswith('{'):
        return None
    try:
        component = json.loads(prop_id.rsplit('.', 1)[0])
    except ValueError:
        return None
    return str(component.get('index') or '').strip().upper() or None


def add_to_draft(symbols: list[str], text: str) -> tuple[list[str], str]:
    """Add the typed symbol to the draft. Returns (symbols, status message)."""
    query = str(text or '').strip()
    if not query:
        return symbols, ''
    if len(symbols) >= MAX_WATCHLIST_SYMBOLS:
        return symbols, (f'The list is full ({MAX_WATCHLIST_SYMBOLS}). '
                         'Remove a symbol to add another.')
    # Unresolvable text still goes through uppercased, as in the search modal:
    # yfinance serves plenty of symbols the universe file does not list.
    symbol = (resolve_ticker_symbol(query) or query).strip().upper()
    if symbol in symbols:
        return symbols, f'{symbol} is already in the list.'
    return [*symbols, symbol], ''


def register_header_watchlist_callbacks(app) -> None:
    @app.callback(
        Output('header-watchlist-chips', 'children'),
        [Input('watchlists-store', 'data'),
         Input('symbol-search-list', 'value'),
         Input('ticker-dropdown', 'value')],
    )
    def render_header_chips(watchlists, list_name, ticker):
        _, symbols = _active_list(watchlists, list_name)
        return build_header_chips(symbols, ticker)

    @app.callback(
        Output('ticker-dropdown', 'value', allow_duplicate=True),
        Input({'type': 'header-wl-chip', 'index': ALL}, 'n_clicks'),
        State('ticker-dropdown', 'value'),
        prevent_initial_call=True,
    )
    def select_header_symbol(_clicks, ticker):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        target = clicked_index(ctx.triggered[0])
        if not target or target == str(ticker or '').strip().upper():
            raise PreventUpdate
        return target

    # ------------------------------------------------------------------
    # Editor.
    # ------------------------------------------------------------------
    @app.callback(
        [Output('watchlist-editor-modal', 'is_open'),
         Output('watchlist-editor-draft', 'data'),
         Output('watchlist-editor-input', 'value'),
         Output('watchlist-editor-status', 'children'),
         Output('watchlist-editor-title', 'children')],
        Input('header-wl-edit', 'n_clicks'),
        [State('watchlists-store', 'data'),
         State('symbol-search-list', 'value')],
        prevent_initial_call=True,
    )
    def open_editor(n_clicks, watchlists, list_name):
        if not n_clicks:
            raise PreventUpdate
        name, symbols = _active_list(watchlists, list_name)
        return True, {'list': name, 'symbols': symbols}, '', '', f'Edit watchlist · {name}'

    @app.callback(
        [Output('watchlist-editor-modal', 'is_open', allow_duplicate=True),
         Output('watchlists-store', 'data', allow_duplicate=True)],
        [Input('watchlist-editor-cancel', 'n_clicks'),
         Input('watchlist-editor-save', 'n_clicks')],
        [State('watchlist-editor-draft', 'data'),
         State('watchlists-store', 'data')],
        prevent_initial_call=True,
    )
    def close_editor(_cancel, _save, draft, watchlists):
        ctx = callback_context
        if not ctx.triggered or not ctx.triggered[0].get('value'):
            raise PreventUpdate
        if not ctx.triggered[0]['prop_id'].startswith('watchlist-editor-save') or not draft:
            return False, no_update
        updated = set_symbols(watchlists, draft.get('list'), draft.get('symbols') or [])
        try:
            return False, save_watchlists(WATCHLIST_FILE_PATH, updated)
        except OSError as exc:
            # The edit still holds for this session; only the disk copy is stale.
            logger.error('Could not persist watchlists: %s', exc)
            return False, normalize(updated)

    @app.callback(
        [Output('watchlist-editor-draft', 'data', allow_duplicate=True),
         Output('watchlist-editor-input', 'value', allow_duplicate=True),
         Output('watchlist-editor-status', 'children', allow_duplicate=True)],
        [Input({'type': 'wle-remove', 'index': ALL}, 'n_clicks'),
         Input('watchlist-editor-add', 'n_clicks'),
         Input('watchlist-editor-input', 'n_submit'),
         Input('watchlist-editor-order', 'data')],
        [State('watchlist-editor-input', 'value'),
         State('watchlist-editor-draft', 'data')],
        prevent_initial_call=True,
    )
    def edit_draft(_removes, _add, _submit, order, text, draft):
        ctx = callback_context
        if not ctx.triggered or not draft:
            raise PreventUpdate
        triggered = ctx.triggered[0]
        prop_id = triggered.get('prop_id', '')
        symbols = list(draft.get('symbols') or [])

        if prop_id.startswith('{'):
            target = clicked_index(triggered)
            if not target or target not in symbols:
                raise PreventUpdate
            symbols.remove(target)
            return {**draft, 'symbols': symbols}, no_update, ''

        if prop_id.startswith('watchlist-editor-order'):
            # Same symbols, new order. Anything else is a stale drag from a
            # list that has changed since, and is ignored.
            new_order = [str(s).upper() for s in (order or {}).get('symbols') or []]
            if sorted(new_order) != sorted(symbols) or new_order == symbols:
                raise PreventUpdate
            return {**draft, 'symbols': new_order}, no_update, no_update

        if not triggered.get('value'):
            raise PreventUpdate
        updated, message = add_to_draft(symbols, text)
        if updated == symbols:
            return no_update, no_update, message
        return {**draft, 'symbols': updated}, '', message

    @app.callback(
        [Output('watchlist-editor-rows', 'children'),
         Output('watchlist-editor-count', 'children'),
         Output('watchlist-editor-add', 'disabled')],
        Input('watchlist-editor-draft', 'data'),
        prevent_initial_call=True,
    )
    def render_editor(draft):
        symbols = list((draft or {}).get('symbols') or [])
        full = len(symbols) >= MAX_WATCHLIST_SYMBOLS
        return build_editor_rows(symbols), editor_counter(len(symbols)), full
