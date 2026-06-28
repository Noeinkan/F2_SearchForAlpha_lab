"""
Modal-style overlays rendered on top of the chart area:
- Fundamentals workspace (10-year financials + Rule #1 valuation)
- Flow scanner workspace (iframe hosting the unusual-options HTML report)

Both overlays are hidden by default and shown via `display: 'flex'` when
their respective `open-*` button is clicked.
"""

from dash import dcc, html

from lib.dash.dash_config import (
    DEFAULT_TICKER,
    FONT_SIZES, FONT_FAMILY,
    FUNDAMENTALS_PERIOD_OPTIONS, DEFAULT_FUNDAMENTALS_PERIOD,
)


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
            ], style={'minWidth': 0, 'flex': '1 1 auto'}),
            html.Div([
                html.Span(id='fundamentals-global-symbol', children=f'GLOBAL {DEFAULT_TICKER}', className='num muted', style={
                    'fontFamily': FONT_FAMILY,
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'alignSelf': 'center',
                    'marginRight': '6px',
                }),
                html.Span(id='fundamentals-status', children='READY', className='num muted', style={
                    'fontFamily': FONT_FAMILY,
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'alignSelf': 'center',
                }),
                dcc.Input(
                    id='fundamentals-ticker-input',
                    type='text',
                    value=DEFAULT_TICKER,
                    placeholder='Ticker',
                    debounce=True,
                    persistence=True,
                    persistence_type='session',
                    style={
                        **styles['input'],
                        'width': '88px',
                        'textTransform': 'uppercase',
                    },
                ),
                html.Button("LOAD", id='load-fundamentals-ticker-button', n_clicks=0, style=styles['button_outline']),
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
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'gap': '8px',
                'flex': '0 0 auto',
                'marginLeft': '8px',
            }),
        ], style={
            'height': '36px',
            'padding': '0 8px',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
            'gap': '8px',
            'backgroundColor': theme['bg_secondary'],
            'borderBottom': f'1px solid {theme["border_primary"]}',
        }),
        html.Div(id='fundamentals-content', children=[
            html.Div("Open fundamentals after selecting a stock.", style={
                'fontFamily': FONT_FAMILY,
                'fontSize': FONT_SIZES['sm'],
                'color': theme['text_secondary'],
                'padding': '18px',
            })
        ], style={
            'height': 'calc(100% - 36px)',
            'overflow': 'auto',
            'padding': '6px',
        }, className='sfa-fundamentals-content'),
    ], id='fundamentals-overlay', style={
        'display': 'none',
        'position': 'fixed',
        'inset': '42px 6px 24px 6px',
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
            ], style={'minWidth': 0, 'flex': '1 1 auto'}),
            html.Div([
                html.Span(id='flow-status', children='Ready', className='num muted', style={
                    'fontFamily': FONT_FAMILY,
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'alignSelf': 'center',
                    'marginRight': '8px',
                }),
                html.Button("RESCAN NOW", id='flow-rescan-button', n_clicks=0, style={
                    **styles['button_primary'],
                    'padding': '6px 12px',
                }),
                html.A(
                    "OPEN IN NEW TAB",
                    href='/flow_report.html',
                    target='_blank',
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
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'gap': '8px',
                'flex': '0 0 auto',
            }),
        ], style={
            'height': '36px',
            'padding': '0 8px',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
            'gap': '8px',
            'backgroundColor': theme['bg_secondary'],
            'borderBottom': f'1px solid {theme["border_primary"]}',
        }),
        html.Iframe(
            id='flow-iframe',
            src='',
            className='sfa-flow-iframe',
            style={
                'width': '100%',
                'height': 'calc(100vh - 36px)',
                'border': 'none',
                'backgroundColor': theme['bg_primary'],
            },
        ),
    ], id='flow-overlay', style={
        'display': 'none',
        'position': 'fixed',
        'inset': '42px 6px 24px 6px',
        'zIndex': 20,
        'backgroundColor': theme['bg_primary'],
        'border': f'1px solid {theme["border_primary"]}',
        'boxShadow': '0 18px 60px rgba(0, 0, 0, 0.45)',
        'overflow': 'hidden',
    }, className='sfa-flow-overlay')