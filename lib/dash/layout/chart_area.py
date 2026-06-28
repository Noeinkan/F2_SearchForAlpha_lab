"""
Central chart region: toolbar (title, library toggle, export), the
Plotly financial-chart container with loading + signal-count overlay,
and the dead TradingView branch kept here until Phase 6 deletes it.
"""

from dash import dcc, html

from lib.dash.dash_config import FONT_SIZES, FONT_FAMILY
from lib.dash.components import ticker_pill


def _create_chart_area(styles: dict, theme: dict) -> html.Main:
    """Create the main chart area."""
    return html.Main([
        # Chart Toolbar
        html.Div([
            html.Div([
                html.H2(id='chart-title', children="Select a symbol to begin", style={
                    'fontSize': FONT_SIZES['sm'],
                    'fontWeight': '600',
                    'color': theme['text_primary'],
                    'margin': 0,
                    'fontFamily': FONT_FAMILY,
                    'letterSpacing': '1.5px',
                    'textTransform': 'uppercase',
                }),
                html.Span(id='chart-subtitle', style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'marginLeft': '12px',
                    'fontFamily': FONT_FAMILY,
                }),
            ], style={'display': 'flex', 'alignItems': 'baseline'}),

            html.Div([
                dcc.RadioItems(
                    id='chart-library-toggle',
                    options=[
                        {'label': 'Plotly', 'value': 'plotly'},
                        {'label': 'TradingView', 'value': 'tradingview', 'disabled': True}
                    ],
                    value='plotly',
                    inline=True,
                    className='bbg-radio-seg'
                ),
                html.Button("Export CSV", id='export-csv-btn', style=styles['button_outline'], n_clicks=0),
                html.Button("Export Image", id='export-img-btn', style=styles['button_outline'], n_clicks=0),
            ], style={'display': 'flex', 'gap': '12px', 'alignItems': 'center'}),
        ], style=styles['chart_toolbar']),

        # Chart - resizable container
        html.Div([
            html.Div(
                id='plotly-chart-container',
                children=[
                    dcc.Loading(
                        id='loading-chart',
                        type='circle',
                        color=theme['accent_blue'],
                        # dcc.Loading >= 1.9.1 ignores the `style` prop on its
                        # outer wrapper and applies it to the spinner instead,
                        # so the chart's `height: 100%` chain collapses to
                        # auto-sized content. `parent_style` is the documented
                        # way to size the Loading wrapper itself.
                        parent_style={
                            'width': '100%',
                            'height': '100%',
                            'minWidth': 0,
                            'minHeight': 0,
                        },
                        children=[
                            dcc.Graph(
                                id='financial-chart',
                                style={'height': '100%', 'width': '100%', 'minWidth': 0, 'minHeight': 0},
                                config={
                                    'responsive': True,
                                    'displayModeBar': True,
                                    'displaylogo': False,
                                    'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                                    'toImageButtonOptions': {
                                        'format': 'png',
                                        'filename': 'chart',
                                        'height': None,
                                        'width': None,
                                        'scale': 2
                                    }
                                }
                            )
                        ]
                    ),
                    html.Div(
                        id='signal-count-bar',
                        children=html.Div([
                            ticker_pill('TRIG', '--', color='amber'),
                            html.Span('|', className='num', style={'color': theme['border_primary']}),
                            ticker_pill('REJ', '--', color='down'),
                        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'}),
                        style=styles['signal_count_bar']
                    )
                ],
                style={
                    'height': '100%',
                    'width': '100%',
                    'visibility': 'visible',
                    'opacity': 1
                }
            ),
            html.Div(
                id='tv-chart-container',
                children=[
                    html.Div(id='tv-main-chart', style={'height': '75%', 'minHeight': '320px'}),
                    html.Div(id='tv-volume-chart', style={'height': '25%', 'minHeight': '120px'}),
                ],
                style={
                    'height': '100%',
                    'width': '100%',
                    'display': 'flex',
                    'flexDirection': 'column',
                    'visibility': 'hidden',
                    'opacity': 0,
                    'pointerEvents': 'none'
                }
            )
        ], style={
            **styles['chart_area'],
            'height': 'calc(100vh - 44px - 24px - 32px)',
            'minHeight': '400px',
            'resize': 'vertical',
            'overflow': 'hidden',
            'position': 'relative',
            'minWidth': 0,
            'width': '100%',
        }, className='resizable-chart'),
    ], style=styles['chart_container'])