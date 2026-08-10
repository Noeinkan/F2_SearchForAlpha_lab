"""
Modal-style overlays rendered on top of the chart area:
- Fundamentals workspace (10-year financials + Rule #1 valuation)
- Flow scanner workspace (iframe hosting the unusual-options HTML report)

Both overlays are hidden by default and shown via `display: 'flex'` when
their respective `open-*` button is clicked.
"""

from dash import dcc, html
import dash_bootstrap_components as dbc

from lib.dash.dash_config import (
    FONT_SIZES, FONT_FAMILY,
    FUNDAMENTALS_PERIOD_OPTIONS, DEFAULT_FUNDAMENTALS_PERIOD,
)
from lib.dash.flow_view import render_learn_modal_content
from lib.dash.layout.symbol_search import build_symbol_search_trigger


def _create_fundamentals_overlay(styles: dict, theme: dict) -> html.Div:
    """Create the on-demand fundamentals workspace."""
    return html.Div([
        html.Div([
            html.Div([
                html.Div("FUNDAMENTALS", style={
                    'fontFamily': FONT_FAMILY,
                    'fontSize': FONT_SIZES['xs'],
                    'letterSpacing': '1.6px',
                    'color': theme['text_secondary'],
                }),
                html.Div(id='fundamentals-title', children='Select a symbol', style={
                    'fontFamily': FONT_FAMILY,
                    'fontSize': FONT_SIZES['lg'],
                    'fontWeight': 700,
                    'color': theme['text_primary'],
                    'whiteSpace': 'nowrap',
                    'overflow': 'hidden',
                    'textOverflow': 'ellipsis',
                }),
            ], className='sfa-overlay-toolbar-title', style={'minWidth': 0, 'flex': '1 1 auto'}),
            html.Div([
                html.Span(id='fundamentals-status', children='READY', className='num muted', style={
                    'fontFamily': FONT_FAMILY,
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'alignSelf': 'center',
                }),
                build_symbol_search_trigger(
                    trigger_id='fundamentals-symbol-search-trigger',
                    symbol_id='fundamentals-symbol-trigger-symbol',
                    name_id='fundamentals-symbol-trigger-name',
                    compact=True,
                ),
                html.Button("REFRESH", id='refresh-fundamentals-button', n_clicks=0, style=styles['button_outline']),
                dcc.RadioItems(
                    id='fundamentals-period-toggle',
                    options=FUNDAMENTALS_PERIOD_OPTIONS,
                    value=DEFAULT_FUNDAMENTALS_PERIOD,
                    inline=True,
                    className='bbg-radio-seg',
                    inputClassName='bbg-radio-seg-input',
                    labelClassName='bbg-radio-seg-label',
                    persistence=True,
                    persistence_type='session',
                ),
                html.Button("CLOSE", id='close-fundamentals-button', n_clicks=0, style={
                    **styles['button_outline'],
                    'color': theme['accent_red'],
                    'borderColor': theme['accent_red'],
                }),
            ], className='sfa-overlay-toolbar-actions', style={
                'display': 'flex',
                'alignItems': 'center',
                'gap': '8px',
                'flex': '0 1 auto',
                'marginLeft': '8px',
                'flexWrap': 'wrap',
            }),
        ], className='sfa-overlay-toolbar', style={
            'minHeight': '36px',
            'flex': '0 0 auto',
            'padding': '4px 8px',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
            'gap': '8px',
            'flexWrap': 'wrap',
            'backgroundColor': theme['bg_secondary'],
            'borderBottom': f'1px solid {theme["border_primary"]}',
        }),
        # Scroll outside dcc.Loading — Loading wrappers break nested
        # flex/overflow chains (same fix as #flow-scroll-region).
        html.Div(
            dcc.Loading(
                id='fundamentals-loading',
                type='circle',
                color=theme['accent_blue'],
                delay_show=200,
                children=html.Div(
                    id='fundamentals-content',
                    children=[
                        html.Div("Open fundamentals after selecting a stock.", style={
                            'fontFamily': FONT_FAMILY,
                            'fontSize': FONT_SIZES['sm'],
                            'color': theme['text_secondary'],
                            'padding': '18px',
                        })
                    ],
                    style={'padding': '6px'},
                    className='sfa-fundamentals-content',
                ),
            ),
            id='fundamentals-scroll-region',
            style={
                'flex': '1 1 auto',
                'minHeight': 0,
                'overflowY': 'auto',
                'overflowX': 'hidden',
                'WebkitOverflowScrolling': 'touch',
            },
        ),
    ], id='fundamentals-overlay', style={
        'display': 'none',
        'position': 'fixed',
        'flexDirection': 'column',
        # Header is 44px tall — start the overlay flush below it so the
        # logo/tape never peeks through and creates the visual "two-headers"
        # overlap. Status bar is 24px so reserve 24px at the bottom when the
        # terminal shell (and its status bar) is still visible.
        'inset': '44px 6px 24px 6px',
        'zIndex': 20,
        'backgroundColor': theme['bg_primary'],
        'border': f'1px solid {theme["border_primary"]}',
        'boxShadow': '0 18px 60px rgba(0, 0, 0, 0.45)',
        'overflow': 'hidden',
    }, className='sfa-fundamentals-overlay')


def _create_flow_overlay(styles: dict, theme: dict) -> html.Div:
    """Create the options flow scanner workspace."""
    return html.Div([
        html.Div([
            html.Div([
                html.Div("FLOW SCANNER", style={
                    'fontFamily': FONT_FAMILY,
                    'fontSize': FONT_SIZES['xs'],
                    'letterSpacing': '1.6px',
                    'color': theme['text_secondary'],
                }),
                html.Div(
                    id='flow-overlay-title',
                    children='Unusual options activity',
                    style={
                        'fontFamily': FONT_FAMILY,
                        'fontSize': FONT_SIZES['lg'],
                        'fontWeight': 700,
                        'color': theme['text_primary'],
                    },
                ),
            ], className='sfa-overlay-toolbar-title', style={'minWidth': 0, 'flex': '1 1 auto'}),
            html.Div([
                html.Span(id='flow-status', children='Ready', className='num muted sfa-flow-status', style={
                    'fontFamily': FONT_FAMILY,
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'alignSelf': 'center',
                    'marginRight': '8px',
                }),
                build_symbol_search_trigger(
                    trigger_id='flow-symbol-search-trigger',
                    symbol_id='flow-symbol-trigger-symbol',
                    name_id='flow-symbol-trigger-name',
                    compact=True,
                ),
                html.Button("LEARN", id='flow-learn-button', n_clicks=0, style={
                    **styles['button_outline'],
                    'padding': '6px 12px',
                }),
                html.Button("GLOSSARY", id='flow-glossary-button', n_clicks=0, className='sfa-flow-secondary-action', style={
                    **styles['button_outline'],
                    'padding': '6px 12px',
                }),
                html.Button("COLLAPSE ALL", id='flow-collapse-all', n_clicks=0, className='sfa-flow-secondary-action', style={
                    **styles['button_outline'],
                    'padding': '6px 12px',
                }),
                html.Button("RESCAN NOW", id='flow-rescan-button', n_clicks=0, style={
                    **styles['button_primary'],
                    'padding': '6px 12px',
                }),
                html.A(
                    "OPEN IN NEW TAB",
                    href='/flow_report.html',
                    target='_blank',
                    className='sfa-flow-secondary-action',
                    style={
                        **styles['button_outline'],
                        'padding': '6px 12px',
                        'textDecoration': 'none',
                        'display': 'inline-block',
                        'marginLeft': '8px',
                    },
                ),
                html.Button("CLOSE", id='close-flow-button', n_clicks=0, style={
                    **styles['button_outline'],
                    'color': theme['accent_red'],
                    'borderColor': theme['accent_red'],
                    'marginLeft': '8px',
                }),
            ], className='sfa-overlay-toolbar-actions', style={
                'display': 'flex',
                'alignItems': 'center',
                'gap': '8px',
                'flex': '0 1 auto',
                'flexWrap': 'wrap',
            }),
        ], className='sfa-overlay-toolbar', style={
            'minHeight': '36px',
            'flex': '0 0 auto',
            'padding': '4px 8px',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
            'flexWrap': 'wrap',
            'gap': '8px',
            'backgroundColor': theme['bg_secondary'],
            'borderBottom': f'1px solid {theme["border_primary"]}',
        }),
        dbc.Modal(
            [
                dbc.ModalHeader(
                    dbc.ModalTitle("Options 101 — Flow Scanner"),
                    close_button=True,
                ),
                dbc.ModalBody(
                    render_learn_modal_content(theme),
                    id='flow-learn-modal-body',
                    className='sfa-flow-learn-modal-body',
                ),
                dbc.ModalFooter(
                    html.Button(
                        "Close",
                        id='flow-learn-close',
                        n_clicks=0,
                        style={**styles['button_outline'], 'padding': '6px 14px'},
                    ),
                ),
            ],
            id='flow-learn-modal',
            is_open=False,
            centered=True,
            size='lg',
            backdrop=True,
            keyboard=True,
            className='sfa-flow-learn-modal',
            scrollable=True,
        ),
        # Single scroll container for the whole report — the glossary lives inside
        # it so an open glossary scrolls with the content instead of stealing height.
        html.Div(
            [
                html.Div(id='flow-glossary', style={'display': 'none'}, children=[]),
                dcc.Loading(
                    id='flow-loading',
                    type='circle',
                    color=theme['accent_blue'],
                    children=html.Div(
                        id='flow-content',
                        children=html.Div(
                            "No report yet. Click RESCAN NOW.",
                            style={
                                'fontFamily': FONT_FAMILY,
                                'fontSize': FONT_SIZES['sm'],
                                'color': theme['text_secondary'],
                                'padding': '24px',
                                'textAlign': 'center',
                            },
                        ),
                        style={'backgroundColor': theme['bg_primary']},
                    ),
                ),
            ],
            id='flow-scroll-region',
            style={
                'flex': '1 1 auto',
                'minHeight': 0,
                'overflowY': 'auto',
                'overflowX': 'hidden',
                'WebkitOverflowScrolling': 'touch',
            },
        ),
    ], id='flow-overlay', style={
        'display': 'none',
        'position': 'fixed',
        'flexDirection': 'column',
        # Matches fundamentals-overlay — clear of the 44px header / 24px footer.
        'inset': '44px 6px 24px 6px',
        'zIndex': 20,
        'backgroundColor': theme['bg_primary'],
        'border': f'1px solid {theme["border_primary"]}',
        'boxShadow': '0 18px 60px rgba(0, 0, 0, 0.45)',
        'overflow': 'hidden',
    }, className='sfa-flow-overlay')
