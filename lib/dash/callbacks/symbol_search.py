"""Symbol-search modal callbacks.

Owns the server side of the search overlay: open/close, ranked result
rendering, symbol selection, and watchlist stars. The keyboard listener that
binds Ctrl+/ and arrow navigation lives in `misc_ui.py`; the chrome lives in
`lib/dash/layout/symbol_search.py`.

Selection funnels through a single write to `ticker-dropdown.value`. That
component is hidden but is still the app's source of truth for the current
symbol, so every downstream callback (data load, chart, backtest, routing,
fundamentals, flow) reacts exactly as it did when the Select was visible.
"""

from __future__ import annotations

import json
import logging
from typing import Any

from dash import callback_context, html, no_update
from dash.dependencies import ALL, Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DEFAULT_TICKER, WATCHLIST_FILE_PATH
from lib.dash.layout.symbol_search import ASSET_CLASS_TABS, build_result_rows
from lib.dash.ticker_search import resolve_ticker_symbol, search_symbols
from lib.dash.watchlist_storage import (
    load_watchlists,
    normalize,
    save_watchlists,
    symbols_in,
    toggle_symbol,
)
from lib.ticker_universe import lookup, sectors

logger = logging.getLogger(__name__)

# Rendered rows per query. High enough that scrolling feels like a real
# universe, low enough that the DOM stays responsive.
RESULT_LIMIT = 150


def _triggered_index(prop_id: str) -> str | None:
    """Pull the `index` out of a pattern-matching callback's prop_id."""
    try:
        return json.loads(prop_id.split('.', 1)[0]).get('index')
    except (ValueError, AttributeError):
        return None


def _filters(store: dict | None) -> tuple[str | None, str | None, bool]:
    """Unpack the filter store into (asset_class, sector, fav_only)."""
    data = store or {}
    asset_class = data.get('asset_class') or 'all'
    return (
        None if asset_class == 'all' else asset_class,
        data.get('sector') or None,
        bool(data.get('fav_only')),
    )


def register_symbol_search_callbacks(app) -> None:
    """Wire the symbol-search modal."""

    # ------------------------------------------------------------------
    # Watchlists: disk -> store on boot.
    # ------------------------------------------------------------------
    @app.callback(
        [Output('watchlists-store', 'data'),
         Output('symbol-search-list', 'options'),
         Output('symbol-search-list', 'value')],
        Input('startup-interval', 'n_intervals'),
    )
    def _load_watchlists(n_intervals):
        if n_intervals is None:
            raise PreventUpdate
        data = load_watchlists(WATCHLIST_FILE_PATH)
        options = [{'label': name, 'value': name} for name in data['watchlists']]
        return data, options, data['active']

    # Sector options depend on the active asset-class tab, so "Technology"
    # only appears while stocks are in scope and the ETF categories only while
    # ETFs are. Do not read `symbol-search-filters` here — even as State.
    # That store is written from `symbol-search-sector.value`, and Dash 4's
    # client cycle detector still treats State as a graph edge, which would
    # close filters.data ↔ sector.value.
    @app.callback(
        [Output('symbol-search-sector', 'options'),
         Output('symbol-search-sector', 'value')],
        Input({'type': 'sym-class', 'index': ALL}, 'n_clicks'),
        State('symbol-search-sector', 'value'),
    )
    def _sector_options(_class_clicks, current):
        ctx = callback_context
        index = _triggered_index(ctx.triggered[0]['prop_id']) if ctx.triggered else None
        # Class comes from the click itself — `_update_filters` may not have
        # written the store yet. Initial load (no useful trigger) matches the
        # default "all" tab.
        asset_class = None if (not index or index == 'all') else index
        values = sectors(asset_class)
        options = [{'label': value, 'value': value} for value in values]
        # Drop a selection that the new asset class does not offer. Skip the
        # value Output when unchanged so we do not re-fire `_update_filters`.
        new_value = current if current in values else None
        return options, (no_update if new_value == current else new_value)

    # ------------------------------------------------------------------
    # Open / close.
    # ------------------------------------------------------------------
    @app.callback(
        Output('symbol-search-open', 'data'),
        [Input('symbol-search-trigger', 'n_clicks'),
         Input('fundamentals-symbol-search-trigger', 'n_clicks'),
         Input('flow-symbol-search-trigger', 'n_clicks')],
        prevent_initial_call=True,
    )
    def _open_modal(sidebar_clicks, fundamentals_clicks, flow_clicks):
        if not any((sidebar_clicks, fundamentals_clicks, flow_clicks)):
            raise PreventUpdate
        return True

    # Reset the query when the modal closes so the next open starts clean.
    @app.callback(
        Output('symbol-search-query', 'value', allow_duplicate=True),
        Input('symbol-search-open', 'data'),
        prevent_initial_call=True,
    )
    def _clear_query_on_close(open_state):
        if open_state:
            raise PreventUpdate
        return ''

    # ------------------------------------------------------------------
    # Filter chips.
    # ------------------------------------------------------------------
    @app.callback(
        [Output('symbol-search-filters', 'data'),
         Output({'type': 'sym-class', 'index': ALL}, 'className')],
        [Input({'type': 'sym-class', 'index': ALL}, 'n_clicks'),
         Input('symbol-search-sector', 'value'),
         Input('symbol-search-fav-only', 'n_clicks')],
        State('symbol-search-filters', 'data'),
        prevent_initial_call=True,
    )
    def _update_filters(_class_clicks, sector_value, fav_clicks, current):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        data = dict(current or {})
        data.setdefault('asset_class', 'all')
        prop_id = ctx.triggered[0]['prop_id']

        if prop_id.startswith('{'):
            index = _triggered_index(prop_id)
            if index:
                data['asset_class'] = index
                # Changing asset class invalidates the sector pick; the
                # _sector_options callback clears the visible dropdown too.
                data['sector'] = None
        elif prop_id.startswith('symbol-search-sector'):
            data['sector'] = sector_value or None
        elif prop_id.startswith('symbol-search-fav-only'):
            data['fav_only'] = not bool(data.get('fav_only'))

        active = data.get('asset_class', 'all')
        classes = [
            'sfa-symsearch-tab active' if tab['id'] == active else 'sfa-symsearch-tab'
            for tab in ASSET_CLASS_TABS
        ]
        return data, classes

    @app.callback(
        Output('symbol-search-fav-only', 'className'),
        Input('symbol-search-filters', 'data'),
    )
    def _fav_toggle_class(filters):
        _, _, fav_only = _filters(filters)
        return 'sfa-symsearch-favtoggle on' if fav_only else 'sfa-symsearch-favtoggle'

    # ------------------------------------------------------------------
    # Results.
    # ------------------------------------------------------------------
    @app.callback(
        [Output('symbol-search-results', 'children'),
         Output('symbol-search-count', 'children')],
        [Input('symbol-search-query', 'value'),
         Input('symbol-search-filters', 'data'),
         Input('symbol-search-list', 'value'),
         Input('watchlists-store', 'data'),
         Input('symbol-search-open', 'data')],
        State('ticker-dropdown', 'value'),
    )
    def _render_results(query, filters, list_name, watchlists, open_state, active):
        asset_class, sector, fav_only = _filters(filters)
        starred = set(symbols_in(watchlists, list_name))

        try:
            rows = search_symbols(
                query,
                asset_class=asset_class,
                sector=sector,
                symbols=sorted(starred) if fav_only else None,
                limit=RESULT_LIMIT,
            )
        except Exception as exc:
            logger.error("Symbol search failed for %r: %s", query, exc)
            return (
                [html.Div('Search failed — see server log.',
                          className='sfa-symsearch-empty')],
                '',
            )

        count = (
            f'{len(rows)}+ matches' if len(rows) >= RESULT_LIMIT
            else f'{len(rows)} match{"" if len(rows) == 1 else "es"}'
        )
        current = str(active or '').strip().upper()
        return build_result_rows(rows, starred, active=current), count

    # ------------------------------------------------------------------
    # Selection. Both paths write the same Output, so they live in one
    # callback — Dash forbids two callbacks racing on one non-duplicate
    # output, and splitting them would need a second allow_duplicate chain.
    # ------------------------------------------------------------------
    @app.callback(
        [Output('ticker-dropdown', 'value', allow_duplicate=True),
         Output('symbol-search-open', 'data', allow_duplicate=True)],
        [Input({'type': 'sym-row', 'index': ALL}, 'n_clicks'),
         Input('symbol-search-query', 'n_submit')],
        State('symbol-search-query', 'value'),
        prevent_initial_call=True,
    )
    def _select_symbol(row_clicks, _n_submit, query):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        prop_id = ctx.triggered[0]['prop_id']

        if prop_id.startswith('{'):
            # A row was clicked. Dash fires this callback whenever the row
            # list re-renders, with every n_clicks at 0 — ignore those.
            if not any(row_clicks or []):
                raise PreventUpdate
            symbol = _triggered_index(prop_id)
            if not symbol:
                raise PreventUpdate
            return str(symbol).upper(), False

        # Enter in the search box. Resolve free text against the whole
        # universe; unresolvable text still goes through uppercased because
        # yfinance serves plenty of symbols this universe does not list.
        text = str(query or '').strip()
        if not text:
            raise PreventUpdate
        symbol = resolve_ticker_symbol(text) or text.upper()
        return symbol, False

    # ------------------------------------------------------------------
    # Watchlist stars.
    # ------------------------------------------------------------------
    @app.callback(
        Output('watchlists-store', 'data', allow_duplicate=True),
        Input({'type': 'sym-star', 'index': ALL}, 'n_clicks'),
        [State('watchlists-store', 'data'),
         State('symbol-search-list', 'value')],
        prevent_initial_call=True,
    )
    def _toggle_star(star_clicks, watchlists, list_name):
        ctx = callback_context
        if not ctx.triggered or not any(star_clicks or []):
            raise PreventUpdate

        symbol = _triggered_index(ctx.triggered[0]['prop_id'])
        if not symbol:
            raise PreventUpdate

        updated = toggle_symbol(watchlists, list_name, symbol)
        try:
            return save_watchlists(WATCHLIST_FILE_PATH, updated)
        except OSError as exc:
            # Keep the star responsive even if the disk write fails; the
            # store still holds the change for this session.
            logger.error("Could not persist watchlists: %s", exc)
            return normalize(updated)

    # ------------------------------------------------------------------
    # Sidebar + overlay trigger labels follow the current symbol.
    # ------------------------------------------------------------------
    @app.callback(
        [Output('symbol-trigger-symbol', 'children'),
         Output('symbol-trigger-name', 'children'),
         Output('fundamentals-symbol-trigger-symbol', 'children'),
         Output('fundamentals-symbol-trigger-name', 'children'),
         Output('flow-symbol-trigger-symbol', 'children'),
         Output('flow-symbol-trigger-name', 'children')],
        Input('ticker-dropdown', 'value'),
    )
    def _update_trigger(ticker):
        symbol = str(ticker or DEFAULT_TICKER).strip().upper()
        row: dict[str, Any] | None = lookup(symbol)
        name = (row or {}).get('Security', '') or ''
        return symbol, name, symbol, name, symbol, name
