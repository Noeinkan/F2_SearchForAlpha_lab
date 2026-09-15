"""Quick-swap block in the Backtest panel: symbol chips and the comparison table.

Sits directly above RUN BACKTEST. The chips are the active watchlist; clicking
one, or pressing , / . for previous / next, swaps the symbol with the test held
still and re-runs the backtest (``callbacks/quick_swap.py``). Every run adds a
row to the table below, so the same test can be read across symbols.

Styling lives in ``65-quick-swap.css``; the stores live in ``shell.py`` with
every other store.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import html

from lib.dash.quick_swap import condition_tags
from lib.metrics import format_canonical
from .empty_states import empty_state

CHIPS_EMPTY_TITLE = "Watchlist is empty"
CHIPS_EMPTY_HINT = "Star symbols in the search (Ctrl + /) to swap between them here."

COMPARE_EMPTY_TITLE = "No runs to compare yet"
COMPARE_EMPTY_HINT = "Run a backtest, then swap symbols: each run adds a row under the same test."

# (column label, canonical metric key) in display order.
COMPARE_COLUMNS = (
    ('Return', 'total_return'),
    ('B&H', 'benchmark_return'),
    ('Sharpe', 'sharpe'),
    ('Max DD', 'max_drawdown'),
    ('Trades', 'num_trades'),
)


def build_chips(symbols: list[str], active: str | None) -> list:
    """One button per watchlist symbol; the loaded one is marked."""
    if not symbols:
        return [empty_state(CHIPS_EMPTY_TITLE, CHIPS_EMPTY_HINT, compact=True)]
    current = str(active or '').strip().upper()
    return [
        html.Button(
            symbol,
            id={'type': 'quick-swap-chip', 'index': symbol},
            n_clicks=0,
            type='button',
            className='sfa-qswap-chip active' if symbol == current else 'sfa-qswap-chip',
            title=f"Run the same test on {symbol}",
        )
        for symbol in symbols
    ]


def _cell(key: str, value) -> html.Td:
    text = '—' if value is None else format_canonical(key, value)
    return html.Td(text, className='num')


def build_compare_table(rows: list | None, active: str | None = None):
    """The comparison table, newest run first. A row click swaps back to that symbol."""
    if not rows:
        return empty_state(COMPARE_EMPTY_TITLE, COMPARE_EMPTY_HINT, compact=True)

    tags = condition_tags(rows)
    current = str(active or '').strip().upper()
    header = html.Tr(
        [html.Th('Test', title='Rows with the same letter ran under identical settings'),
         html.Th('Symbol')]
        + [html.Th(label) for label, _ in COMPARE_COLUMNS]
    )
    body = []
    for row in rows:
        symbol = row.get('symbol') or ''
        window_note = f"{row.get('interval', '').upper()} · {row.get('window', '')} · {row.get('bars', 0):,} bars"
        symbol_cell = [symbol]
        if row.get('short'):
            symbol_cell.append(html.Span(' ⚠', className='sfa-qswap-short'))
            window_note += " · history does not cover the whole window"
        classes = ['sfa-qswap-row']
        if symbol == current:
            classes.append('active')
        body.append(html.Tr(
            [html.Td(tags.get(row.get('key'), '?'), className='sfa-qswap-tag'),
             html.Td(symbol_cell, className='sfa-qswap-symbol')]
            + [_cell(key, row.get(key)) for _, key in COMPARE_COLUMNS],
            # The same symbol can hold several rows (another test, another
            # interval), and Dash rejects duplicate ids; the swap reads the
            # symbol back off the front.
            id={'type': 'quick-swap-row', 'index': f"{symbol}|{row.get('interval')}|{row.get('key')}"},
            n_clicks=0,
            className=' '.join(classes),
            title=window_note,
        ))
    return html.Div(
        html.Table([html.Thead(header), html.Tbody(body)], className='sfa-qswap-table'),
        className='sfa-qswap-table-wrap',
    )


def create_quick_swap_block(styles: dict, theme: dict) -> html.Div:
    """Chips strip, keyboard hint and comparison table."""
    return html.Div(
        [
            html.Div([
                html.Span("Quick Swap", className='sfa-qswap-title'),
                html.Span(id='quick-swap-list-name', className='sfa-qswap-list'),
                html.Span("?", id='help-quick-swap', style=styles['help_icon']),
            ], className='sfa-qswap-head'),
            html.Div([
                html.Button('‹', id='quick-swap-prev', n_clicks=0, type='button',
                            className='sfa-qswap-step', title='Previous symbol ( , )'),
                html.Div(id='quick-swap-chips', className='sfa-qswap-chips'),
                html.Button('›', id='quick-swap-next', n_clicks=0, type='button',
                            className='sfa-qswap-step', title='Next symbol ( . )'),
            ], className='sfa-qswap-strip'),
            html.Div([
                html.Span("Same test, other symbols", className='sfa-qswap-subtitle'),
                html.Button("CLEAR", id='quick-swap-clear', n_clicks=0, type='button',
                            className='sfa-qswap-clear'),
            ], className='sfa-qswap-head sfa-qswap-head--table'),
            html.Div(build_compare_table([]), id='quick-swap-compare'),
            dbc.Tooltip(
                "Swap the symbol without touching the test. The window, signals, "
                "sizing, costs and order model stay as they are, and the backtest "
                "re-runs by itself once the new data has loaded. Keys: , previous, "
                ". next (outside text fields). Symbols come from the active "
                "watchlist in the search (Ctrl + /).",
                target='help-quick-swap',
                placement='left',
                trigger='hover focus',
            ),
        ],
        id='quick-swap-block',
        className='sfa-qswap',
    )
