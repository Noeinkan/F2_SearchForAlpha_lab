"""Watchlist strip in the header, and the editor it opens.

The header is the only chrome every workspace shares (chart, fundamentals,
flow, optimize), so the strip is reachable from all of them. A click is a plain
symbol change, the same as picking the symbol in the search modal: the routing
callback keeps the current workspace and swaps only the ticker in the URL.

The ✎ button at the end of the strip opens the editor: drag rows to reorder,
× to remove, type a symbol to add, up to ``MAX_WATCHLIST_SYMBOLS``. Changes
are a draft until SAVE, so CANCEL leaves the list as it was.

Callbacks: ``callbacks/header_watchlist.py``. Drag and drop:
``assets/86-watchlist-editor.js``. Styling: ``20-controls.css`` (strip) and
``86-watchlist-editor.css`` (editor).
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from lib.dash.watchlist_storage import MAX_WATCHLIST_SYMBOLS
from lib.ticker_universe import lookup


def build_header_chips(symbols: list[str], active: str | None) -> list:
    """One button per watchlist symbol; the loaded one is marked."""
    if not symbols:
        return [html.Span('Watchlist empty: ✎ to add symbols', className='sfa-hwl-empty')]
    current = str(active or '').strip().upper()
    return [
        html.Button(
            symbol,
            id={'type': 'header-wl-chip', 'index': symbol},
            n_clicks=0,
            type='button',
            className='sfa-hwl-chip active' if symbol == current else 'sfa-hwl-chip',
            title=f'Open {symbol}',
        )
        for symbol in symbols
    ]


def create_header_watchlist() -> html.Div:
    return html.Div(
        [
            html.Div(id='header-watchlist-chips', className='sfa-hwl-chips'),
            html.Button(
                '✎',
                id='header-wl-edit',
                n_clicks=0,
                type='button',
                className='sfa-hwl-edit',
                title='Edit watchlist',
                **{'aria-label': 'Edit watchlist'},
            ),
        ],
        id='header-watchlist',
        className='sfa-hwl',
        role='navigation',
        **{'aria-label': 'Watchlist'},
    )


def _company(symbol: str) -> str:
    row = lookup(symbol) or {}
    return str(row.get('Security') or '')


def build_editor_rows(symbols: list[str]) -> list:
    """Draggable rows, in list order. The JS reads the order back from data-symbol."""
    if not symbols:
        return [html.Div('No symbols yet. Add one below.', className='sfa-wle-empty')]
    return [
        html.Div(
            [
                html.Span('⠿', className='sfa-wle-grip', **{'aria-hidden': 'true'}),
                html.Span(str(position), className='sfa-wle-pos num'),
                html.Span(symbol, className='sfa-wle-symbol'),
                html.Span(_company(symbol), className='sfa-wle-name'),
                html.Button(
                    '×',
                    id={'type': 'wle-remove', 'index': symbol},
                    n_clicks=0,
                    type='button',
                    className='sfa-wle-remove',
                    title=f'Remove {symbol}',
                    **{'aria-label': f'Remove {symbol}'},
                ),
            ],
            className='sfa-wle-row',
            draggable='true',
            **{'data-symbol': symbol},
        )
        for position, symbol in enumerate(symbols, start=1)
    ]


def editor_counter(count: int) -> str:
    return f'{count}/{MAX_WATCHLIST_SYMBOLS}'


def create_watchlist_editor() -> html.Div:
    body = dbc.ModalBody(
        [
            html.Div(
                [
                    html.Span('Drag to reorder · × to remove', className='sfa-wle-hint'),
                    html.Span(editor_counter(0), id='watchlist-editor-count',
                              className='sfa-wle-count num'),
                ],
                className='sfa-wle-head',
            ),
            html.Div(id='watchlist-editor-rows', className='sfa-wle-rows'),
            html.Div(
                [
                    html.Label('Symbol to add', htmlFor='watchlist-editor-input',
                               className='visually-hidden'),
                    dcc.Input(
                        id='watchlist-editor-input',
                        type='text',
                        value='',
                        placeholder='Add symbol or company, e.g. NFLX',
                        autoComplete='off',
                        debounce=False,
                        className='bbg-input sfa-wle-input',
                    ),
                    html.Button('ADD', id='watchlist-editor-add', n_clicks=0,
                                type='button', className='sfa-wle-add'),
                ],
                className='sfa-wle-add-row',
            ),
            html.Div(id='watchlist-editor-status', className='sfa-wle-status'),
        ],
        className='sfa-wle-body',
    )
    footer = dbc.ModalFooter(
        [
            html.Button('Cancel', id='watchlist-editor-cancel', n_clicks=0, type='button',
                        className='bbg-button-ghost sfa-feedback-cancel'),
            html.Button('Save', id='watchlist-editor-save', n_clicks=0, type='button',
                        className='sfa-feedback-send'),
        ],
        className='sfa-wle-footer',
    )
    return html.Div([
        # {'list': name, 'symbols': [...]}: the edit in progress, until SAVE.
        dcc.Store(id='watchlist-editor-draft', data=None),
        # Written by the drag-and-drop script: {'symbols': [...], 'nonce': n}.
        dcc.Store(id='watchlist-editor-order', data=None),
        dbc.Modal(
            [
                dbc.ModalHeader(
                    dbc.ModalTitle('Edit watchlist', id='watchlist-editor-title'),
                    close_button=True,
                    className='sfa-feedback-header',
                ),
                body,
                footer,
            ],
            id='watchlist-editor-modal',
            is_open=False,
            centered=True,
            backdrop=True,
            keyboard=True,
            className='sfa-wle-modal',
            content_class_name='sfa-wle-content',
        ),
    ])
