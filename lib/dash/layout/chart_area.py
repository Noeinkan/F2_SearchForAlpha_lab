"""Central chart region: toolbar and the Lightweight Charts render target.

``#financial-chart`` is a plain div, not a Dash component — the chart is drawn
into it by ``assets/10-sfa-chart.js`` from the payload in
``chart-payload-store``. Keeping the id stable matters: the command palette
refocuses it and ``test_layout`` asserts on it.
"""

from dash import dcc, html

from lib.dash.dash_config import FONT_SIZES, FONT_FAMILY
from lib.dash.components import ticker_pill
from lib.dash.bootstrap import BootstrapSnapshot

CHART_TYPES = [
    {'label': 'Candles', 'value': 'candles'},
    {'label': 'Hollow', 'value': 'hollow'},
    {'label': 'Bars', 'value': 'bars'},
    {'label': 'Line', 'value': 'line'},
    {'label': 'Area', 'value': 'area'},
    {'label': 'Baseline', 'value': 'baseline'},
]

SCALE_MODES = [
    {'label': 'LIN', 'value': 'normal'},
    {'label': 'LOG', 'value': 'log'},
    {'label': '%', 'value': 'percent'},
]


def _tool_button(label: str, btn_id: str, title: str) -> html.Button:
    return html.Button(
        label,
        id=btn_id,
        title=title,
        className='bbg-button-ghost',
        n_clicks=0,
    )


def _create_chart_area(styles: dict, theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Main:
    """Create the main chart area."""
    return html.Main([
        html.Div([
            # Left: title / subtitle / signal pills / bar-count
            html.Div([
                html.H2(id='chart-title', children=bootstrap.chart_title if bootstrap else "Select a symbol to begin", style={
                    'fontSize': FONT_SIZES['sm'],
                    'fontWeight': '600',
                    'color': theme['text_primary'],
                    'margin': 0,
                    'fontFamily': FONT_FAMILY,
                    'letterSpacing': '1.5px',
                    'textTransform': 'uppercase',
                }),
                html.Span(
                    id='chart-subtitle',
                    children=bootstrap.chart_subtitle if bootstrap else None,
                    style={
                        'fontSize': FONT_SIZES['xs'],
                        'color': theme['text_secondary'],
                        'marginLeft': '12px',
                        'fontFamily': FONT_FAMILY,
                    },
                ),
                html.Div(
                    id='signal-count-bar',
                    children=html.Div([
                        ticker_pill('TRIG', '--', color='amber'),
                        html.Span('|', className='num', style={'color': theme['border_primary']}),
                        ticker_pill('REJ', '--', color='down'),
                    ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'}),
                    style=styles['signal_count_bar'],
                ),
                html.Span(
                    id='chart-bar-count',
                    children='',
                    className='num',
                    style={
                        'fontSize': FONT_SIZES['xs'],
                        'color': theme['text_tertiary'],
                        'whiteSpace': 'nowrap',
                    },
                ),
            ], style={
                'display': 'flex',
                'gap': '12px',
                'alignItems': 'center',
                'flex': '1 1 auto',
                'minWidth': 0,
                'flexWrap': 'wrap',
            }),

            # Right: interval, chart type, price scale, view + export tools.
            html.Div([
                dcc.RadioItems(
                    id='bar-interval',
                    options=[
                        {'label': 'D', 'value': '1d'},
                        {'label': '1H', 'value': '1h'},
                        {'label': '4H', 'value': '4h'},
                    ],
                    value='1d',
                    inline=True,
                    className='bbg-radio-seg sfa-bar-interval',
                ),
                dcc.Dropdown(
                    id='chart-type-select',
                    options=CHART_TYPES,
                    value='candles',
                    clearable=False,
                    searchable=False,
                    className='dark-dropdown sfa-chart-type',
                    style={'width': '112px'},
                ),
                dcc.RadioItems(
                    id='price-scale-select',
                    options=SCALE_MODES,
                    value='normal',
                    inline=True,
                    className='bbg-radio-seg sfa-scale-seg',
                ),
                _tool_button('FIT', 'chart-fit-btn', 'Fit all bars to the viewport (R)'),
                _tool_button('IMG', 'export-img-btn', 'Save the chart as a PNG'),
                _tool_button('CSV', 'export-csv-btn', 'Export the chart data as CSV'),
                _tool_button('⛶', 'chart-fullscreen-btn', 'Toggle fullscreen chart'),
            ], className='sfa-chart-tools'),
        ], style={
            **styles['chart_toolbar'],
            'display': 'flex',
            'justifyContent': 'space-between',
            'alignItems': 'center',
            'gap': '12px',
        }),

        # The glue owns everything inside #financial-chart.
        html.Div(
            [
                html.Div(id='financial-chart', tabIndex='0'),
                # dcc.Loading tracks the loading state of Dash components
                # *inside* it. #financial-chart is mutated by JS and never
                # enters one, so the spinner is bound to the payload sink
                # instead — that is the thing the user is actually waiting on.
                # Absolutely positioned and click-through so it overlays the
                # canvas without taking part in layout.
                html.Div(
                    dcc.Loading(
                        id='chart-loading',
                        type='circle',
                        color=theme['accent_blue'],
                        delay_show=350,
                        children=html.Div(id='chart-render-target'),
                    ),
                    className='sfa-chart-loading',
                ),
            ],
            id='chart-frame',
            style={
                'flex': '1 1 0',
                'minHeight': '720px',
                'width': '100%',
                'position': 'relative',
                'minWidth': 0,
            },
        ),
    ], style=styles['chart_container'])
