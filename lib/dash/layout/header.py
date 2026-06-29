"""
Top-of-window chrome: the Bloomberg-style header tape and the dense
bottom status bar. Both are tiny enough to share a file.
"""

from dash import dcc, html
import dash_bootstrap_components as dbc

from lib.dash.dash_config import DEFAULT_TICKER, FONT_SIZES, FONT_FAMILY
from lib.dash.bootstrap import BootstrapSnapshot


def _create_header(styles: dict, theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Header:
    """Create the dashboard header."""
    return html.Header([
        html.Div([
            html.Div("SFA", style=styles['logo_icon'], className='bbg-wordmark'),
            html.Span("Terminal", style=styles['logo_text'], className='bbg-wordmark-sub'),
        ], style=styles['logo']),

        html.Div([
            html.Span(
                bootstrap.header_symbol if bootstrap else DEFAULT_TICKER,
                id='header-ticker-symbol',
                className='bbg-tape-symbol',
            ),
            html.Span(
                bootstrap.header_price if bootstrap else '$--',
                id='header-ticker-price',
                className='bbg-tape-price num',
            ),
            html.Span(
                bootstrap.header_change if bootstrap else 'READY',
                id='header-ticker-change',
                className='bbg-tape-delta muted' if not bootstrap else 'bbg-tape-delta',
            ),
        ], style=styles['header_tape'], className='bbg-tape'),

        html.Div([
            html.Span(className='dot dot-up'),
            html.Span('CONNECTED', style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_secondary'],
                'fontFamily': FONT_FAMILY,
                'letterSpacing': '1px',
            }),
            html.Span('│', style={'color': theme['border_primary'], 'fontFamily': FONT_FAMILY}),
            html.Div(id='header-status', style={
                'fontSize': FONT_SIZES['sm'],
                'color': theme['text_secondary'],
                'fontFamily': FONT_FAMILY,
            }, className='num'),
            # Theme toggle — Phase 4: cycle DARK → CVD → LIGHT.
            html.Button(
                id='theme-toggle',
                children=[html.Span('[ DARK ]', id='theme-label')],
                style=styles['button_outline'],
                className='bbg-button-ghost',
                n_clicks=0,
                **{'aria-label': 'Cycle theme (Dark, CVD-safe, Light)'},
            ),
            dbc.Tooltip(
                "Cycle theme: Dark → CVD-safe → Light",
                target='theme-toggle', placement='bottom',
            ),
            # Phase 5 — keyboard-shortcut catalog button. Same chrome as
            # the theme toggle so the header rhythm stays consistent.
            html.Button(
                id='help-shortcuts-btn',
                children=[html.Span('[ ? ]', id='help-shortcuts-label')],
                style=styles['button_outline'],
                className='bbg-button-ghost',
                n_clicks=0,
                **{'aria-label': 'Show keyboard shortcuts (Ctrl+/)'},
            ),
            dbc.Tooltip(
                "Show keyboard shortcuts (Ctrl+K)",
                target='help-shortcuts-btn', placement='bottom',
            ),
        ], style=styles['header_controls']),
    ], style=styles['header'], className='bbg-header')


def _create_status_bar(styles: dict, theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Div:
    """Create the dense bottom status bar."""
    return html.Div([
        html.Div([
            html.Span(className='dot dot-up'),
            html.Span('READY'),
        ], style=styles['status_segment'], className='bbg-status-segment'),
        html.Div([
            html.Span('DATA:'),
            html.Span(
                bootstrap.data_status if bootstrap else 'WAITING',
                id='data-status',
                className='num',
                style={'marginLeft': '6px'},
            ),
        ], style=styles['status_segment'], className='bbg-status-segment'),
        html.Div([
            html.Span('STRATEGY:'),
            html.Span(
                bootstrap.strategy_order if bootstrap else '--',
                id='strategy-order-status',
                className='num',
                style={'marginLeft': '6px'},
            ),
        ], style={**styles['status_segment'], 'flex': 1, 'minWidth': 0}, className='bbg-status-segment flex-grow'),
        # Command palette launcher. The palette no longer auto-opens, so this
        # button (plus Ctrl+K and the header `[ ? ]` button) is how it is
        # reached. Wired to `command-palette-open` in callbacks/command_palette.py.
        html.Div([
            html.Button(
                id='palette-open-btn',
                children=[
                    html.Span('⌘', className='sfa-status-kbd'),
                    html.Span('COMMANDS', style={'marginLeft': '6px'}),
                ],
                style=styles['button_outline'],
                className='bbg-button-ghost bbg-status-btn',
                n_clicks=0,
                **{'aria-label': 'Open command palette (Ctrl+K)'},
            ),
            dbc.Tooltip(
                "Open command palette (Ctrl+K)",
                target='palette-open-btn', placement='top',
            ),
        ], style=styles['status_segment'], className='bbg-status-segment'),
        html.Div([
            html.Span(id='status-clock', className='num'),
        ], style={**styles['status_segment'], 'borderRight': 'none'}, className='bbg-status-segment'),
    ], style=styles['status_bar'], className='bbg-status-bar')