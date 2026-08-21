"""
Top-of-window chrome: the Bloomberg-style header tape and the dense
bottom status bar. Both are tiny enough to share a file.

Tooltips on header chrome use the native `title` attribute rather than
`dbc.Tooltip`. Popper-based tooltips occasionally render their text
inline (top-left of viewport) before they have computed a target
position — on small overlays like the fundamentals/flow header this
shows up as ghost text bleeding over the chart toolbar. Native title
tooltips have none of those positioning issues and keep the header DOM
small.
"""

from dash import html

from lib.dash.dash_config import DEFAULT_TICKER, KOFI_URL
from lib.dash.bootstrap import BootstrapSnapshot


def _create_header(styles: dict, theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Header:
    """Create the dashboard header."""
    return html.Header([
        html.Button(
            id='mobile-menu-btn',
            children='☰',
            n_clicks=0,
            className='bbg-icon-button sfa-mobile-menu-btn',
            title='Open navigation (Flow, Fundamentals, controls)',
            **{'aria-label': 'Open navigation menu', 'aria-expanded': 'false'},
        ),
        html.Button(
            id='mobile-backtest-btn',
            children='BT',
            n_clicks=0,
            className='bbg-icon-button sfa-mobile-backtest-btn',
            title='Open Backtest panel',
            **{'aria-label': 'Open Backtest panel', 'aria-expanded': 'false'},
        ),
        html.Div([
            html.Div(
                [
                    html.Button(
                        'SFA',
                        id='nav-workspace-sfa',
                        n_clicks=0,
                        className='sfa-workspace-nav-btn is-active',
                        title='Trading terminal',
                        **{'aria-label': 'Open trading terminal', 'aria-current': 'page'},
                    ),
                    html.Button(
                        'FUNDAMENTALS',
                        id='nav-workspace-fundamentals',
                        n_clicks=0,
                        className='sfa-workspace-nav-btn',
                        title='10-year fundamentals and Rule #1 valuation',
                        **{'aria-label': 'Open fundamentals workspace'},
                    ),
                    html.Button(
                        'FLOW',
                        id='nav-workspace-flow',
                        n_clicks=0,
                        className='sfa-workspace-nav-btn',
                        title='Unusual options flow scanner',
                        **{'aria-label': 'Open flow scanner'},
                    ),
                ],
                className='sfa-workspace-nav',
                role='navigation',
                **{'aria-label': 'Workspace'},
            ),
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
            html.Span('CONNECTED', className='bbg-header-status-label'),
            html.Span('│', className='bbg-header-divider'),
            html.Div(id='header-status', className='num bbg-header-clock'),
            # Manual re-fetch. Symbol and bar-interval changes load on their own
            # and the test window needs no fetch at all, so this is only for
            # pulling bars that appeared since the page loaded — hence an icon
            # rather than the full-width sidebar button it used to be. The id is
            # load-data-button because Ctrl+Enter (callbacks/misc_ui.py), the
            # command palette's load-data action, and the status activity
            # indicator all click it by that name.
            html.Button(
                id='load-data-button',
                children=[html.Span('⟳', id='load-data-label')],
                className='bbg-icon-button',
                n_clicks=0,
                title='Re-fetch the current symbol (Ctrl+Enter)',
                **{'aria-label': 'Refresh market data'},
            ),
            # Feedback — the whole point of publishing the repo is to hear
            # back, so this sits in the header rather than a footer. The glyph
            # and the word are both rendered; CSS drops the word on narrow
            # viewports (85-feedback.css) so the header cluster never wraps.
            html.Button(
                id='feedback-open-btn',
                children=[
                    html.Span('✉', className='sfa-feedback-open-glyph',
                              **{'aria-hidden': 'true'}),
                    html.Span('FEEDBACK', className='sfa-feedback-open-text'),
                ],
                className='bbg-icon-button sfa-feedback-open-btn',
                n_clicks=0,
                title='Send feedback — bugs, ideas, first impressions',
                **{'aria-label': 'Send feedback', 'aria-haspopup': 'dialog'},
            ),
            # Support link — warm CTA distinct from neutral header icon buttons.
            # Wording must stay "Support" (not "Donate"): Ko-fi reserves donation
            # wording for registered non-profits.
            html.A(
                'Support',
                href=KOFI_URL,
                target='_blank',
                rel='noopener noreferrer',
                className='bbg-donate-button',
                title='Support this project on Ko-fi',
                **{'aria-label': 'Support this project on Ko-fi'},
            ),
            # Theme toggle — Phase 4: cycle DARK → CVD → LIGHT.
            html.Button(
                id='theme-toggle',
                children=[html.Span('DARK', id='theme-label')],
                className='bbg-icon-button',
                n_clicks=0,
                title='Cycle theme: Dark → CVD-safe → Light',
                **{'aria-label': 'Cycle theme (Dark, CVD-safe, Light)'},
            ),
            # Phase 5 — keyboard-shortcut catalog button.
            html.Button(
                id='help-shortcuts-btn',
                children=[html.Span('?', id='help-shortcuts-label')],
                className='bbg-icon-button',
                n_clicks=0,
                title='Show keyboard shortcuts (Ctrl+K)',
                **{'aria-label': 'Show keyboard shortcuts (Ctrl+K)'},
            ),
        ], style=styles['header_controls']),
    ], style=styles['header'], className='bbg-header')


def _create_status_bar(styles: dict, theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Div:
    """Create the dense bottom status bar."""
    return html.Div([
        # Activity segment — driven by the callback lifecycle in
        # callbacks/status.py: a clientside handler flips it to WORKING… the
        # instant an action button is clicked, and server-side resolvers flip
        # it back to READY (or ERROR on a failed data load).
        html.Div([
            html.Span(id='status-activity-dot', className='dot dot-up'),
            html.Span('READY', id='status-activity-label'),
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
        # button (plus Ctrl+K and the header `?` button) is how it is reached.
        # Wired to `command-palette-open` in callbacks/command_palette.py.
        html.Div([
            html.Button(
                id='palette-open-btn',
                children=[
                    html.Span('Ctrl+K', className='sfa-status-kbd'),
                    html.Span('COMMANDS', style={'marginLeft': '6px'}),
                ],
                style=styles['button_outline'],
                className='bbg-button-ghost bbg-status-btn',
                n_clicks=0,
                title='Open command palette (Ctrl+K)',
                **{'aria-label': 'Open command palette (Ctrl+K)'},
            ),
        ], style=styles['status_segment'], className='bbg-status-segment'),
        html.Div([
            html.Span(id='status-clock', className='num'),
        ], style={**styles['status_segment'], 'borderRight': 'none'}, className='bbg-status-segment'),
    ], style=styles['status_bar'], className='bbg-status-bar')