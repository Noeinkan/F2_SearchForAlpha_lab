"""Symbol-search modal — the TradingView-style replacement for the sidebar Select.

Opened by any `*-symbol-search-trigger` button (sidebar, fundamentals, flow) or
Ctrl+/ (bound in the global keyboard listener in callbacks/misc_ui.py). Closed
by Esc, the backdrop, or picking a row.

Chrome deliberately mirrors the command palette (layout/command_palette.py) so
the two overlays feel like one system: same modal shell, same footer key hints,
same `.active` row convention for keyboard navigation.

Results are rendered server-side by callbacks/symbol_search.py — the universe is
~14k rows, far too large to ship into a browser store for clientside filtering
the way the palette does with its dozen commands.
"""

from dash import dcc, html
import dash_bootstrap_components as dbc

from lib.dash.dash_config import DEFAULT_TICKER


# Asset-class tabs. `None` is the "All" pseudo-class; the rest match the
# AssetClass column in config/tickers_universe.csv.
ASSET_CLASS_TABS = [
    {"id": "all", "label": "ALL"},
    {"id": "Stock", "label": "STOCKS"},
    {"id": "ETF", "label": "ETF"},
    {"id": "Index", "label": "INDICES"},
    {"id": "FX", "label": "FOREX"},
    {"id": "Future", "label": "FUTURES"},
]


def build_symbol_search_trigger(
    *,
    trigger_id: str,
    symbol_id: str,
    name_id: str,
    compact: bool = False,
) -> html.Button:
    """Open-symbol-search control used in the sidebar and overlay toolbars.

    Selection still funnels through the shared modal; these buttons only open
    it and mirror the current ``ticker-dropdown`` value.
    """
    classes = 'sfa-symbol-trigger'
    if compact:
        classes = f'{classes} sfa-symbol-trigger-compact'
    return html.Button(
        id=trigger_id,
        className=classes,
        n_clicks=0,
        title='Search symbols (Ctrl+/)',
        **{'aria-label': 'Search symbols'},
        children=[
            html.Span(
                DEFAULT_TICKER,
                id=symbol_id,
                className='sfa-symbol-trigger-sym num',
            ),
            html.Span('', id=name_id, className='sfa-symbol-trigger-name'),
            html.Span('Ctrl+/', className='sfa-status-kbd sfa-symbol-trigger-kbd'),
        ],
    )

# Badge colour class per asset class, so the list is scannable at a glance.
ASSET_CLASS_BADGE = {
    "Stock": "sfa-symsearch-badge-stock",
    "ETF": "sfa-symsearch-badge-etf",
    "Index": "sfa-symsearch-badge-index",
    "FX": "sfa-symsearch-badge-fx",
    "Future": "sfa-symsearch-badge-future",
}


def _asset_class_tabs() -> html.Div:
    return html.Div(
        [
            html.Button(
                tab["label"],
                id={'type': 'sym-class', 'index': tab["id"]},
                className=(
                    'sfa-symsearch-tab active' if tab["id"] == 'all'
                    else 'sfa-symsearch-tab'
                ),
                n_clicks=0,
            )
            for tab in ASSET_CLASS_TABS
        ],
        className='sfa-symsearch-tabs',
        role='tablist',
    )


def _create_symbol_search_modal(styles: dict, theme: dict) -> dbc.Modal:
    """Return the symbol-search modal mounted at the bottom of the shell."""
    body = html.Div([
        html.Div([
            dcc.Input(
                id='symbol-search-query',
                type='text',
                placeholder='Search symbol, company, or business category…',
                value='',
                debounce=False,
                autoComplete='off',
                className='bbg-input sfa-symsearch-input',
                n_submit=0,
            ),
            html.Span('esc', className='sfa-palette-foot-key sfa-symsearch-esc'),
        ], className='sfa-symsearch-search-row'),

        _asset_class_tabs(),

        html.Div([
            dcc.Dropdown(
                id='symbol-search-sector',
                options=[],
                value=None,
                placeholder='All categories',
                clearable=True,
                className='dark-dropdown sfa-symsearch-sector',
            ),
            dcc.Dropdown(
                id='symbol-search-list',
                options=[],
                value=None,
                placeholder='Watchlist',
                clearable=False,
                className='dark-dropdown sfa-symsearch-list',
            ),
            html.Button(
                [html.Span('★', className='sfa-symsearch-star-glyph'),
                 html.Span('STARRED ONLY')],
                id='symbol-search-fav-only',
                className='sfa-symsearch-favtoggle',
                n_clicks=0,
                title='Show only symbols in the selected watchlist',
            ),
            html.Div(id='symbol-search-count', className='sfa-symsearch-count'),
        ], className='sfa-symsearch-filters'),

        html.Div(
            id='symbol-search-results',
            className='sfa-symsearch-results',
            children=[],
        ),

        html.Div([
            html.Span('↑↓ navigate', className='sfa-palette-foot-key'),
            html.Span('↵ select', className='sfa-palette-foot-key'),
            html.Span('★ star', className='sfa-palette-foot-key'),
            html.Span('esc close', className='sfa-palette-foot-key'),
            html.Span('Ctrl+/', className='sfa-palette-foot-key'),
        ], className='sfa-palette-foot sfa-symsearch-foot'),
    ], className='sfa-symsearch-body')

    return dbc.Modal(
        children=[body],
        id='symbol-search-modal',
        is_open=False,
        centered=True,
        size='xl',
        backdrop=True,
        keyboard=True,
        className='sfa-symsearch-modal',
        content_class_name='sfa-symsearch-content',
        backdrop_class_name='sfa-symsearch-backdrop',
        style={'overflow': 'visible'},
    )


def build_result_rows(rows: list[dict], starred: set[str], active: str | None = None) -> list:
    """Render universe rows into the modal's result list.

    Args:
        rows: Universe row dicts from `ticker_search.search_symbols`.
        starred: Symbols in the currently selected watchlist.
        active: The currently loaded symbol, highlighted in the list.
    """
    if not rows:
        return [html.Div(
            'No symbols match. Press ↵ to load the text as a symbol anyway.',
            className='sfa-symsearch-empty',
        )]

    children = []
    for row in rows:
        symbol = str(row.get('Symbol', ''))
        asset_class = str(row.get('AssetClass', '') or 'Stock')
        sector = str(row.get('Sector', '') or '')
        industry = str(row.get('Industry', '') or '')
        # Sector is the headline category; industry is the finer one. Show both
        # when they differ so "Technology · Semiconductors" reads as a path.
        category = ' · '.join(part for part in (sector, industry) if part)
        is_starred = symbol in starred

        row_class = 'sfa-symsearch-row'
        if active and symbol == active:
            row_class += ' current'

        children.append(html.Div(
            id={'type': 'sym-row', 'index': symbol},
            className=row_class,
            n_clicks=0,
            **{'data-symbol': symbol},
            children=[
                html.Button(
                    '★' if is_starred else '☆',
                    id={'type': 'sym-star', 'index': symbol},
                    className=(
                        'sfa-symsearch-star on' if is_starred
                        else 'sfa-symsearch-star'
                    ),
                    n_clicks=0,
                    title=(
                        f'Remove {symbol} from watchlist' if is_starred
                        else f'Add {symbol} to watchlist'
                    ),
                ),
                html.Span(symbol, className='sfa-symsearch-sym num'),
                html.Span(
                    str(row.get('Security', '')),
                    className='sfa-symsearch-name',
                    title=str(row.get('Security', '')),
                ),
                html.Span(
                    asset_class.upper(),
                    className=(
                        'sfa-symsearch-badge '
                        + ASSET_CLASS_BADGE.get(asset_class, 'sfa-symsearch-badge-stock')
                    ),
                ),
                html.Span(category, className='sfa-symsearch-cat', title=category),
                html.Span(
                    str(row.get('Exchange', '') or ''),
                    className='sfa-symsearch-exch',
                ),
            ],
        ))
    return children


__all__ = [
    '_create_symbol_search_modal',
    'build_result_rows',
    'build_symbol_search_trigger',
    'ASSET_CLASS_TABS',
    'DEFAULT_TICKER',
]
