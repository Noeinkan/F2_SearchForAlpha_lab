"""
Central chart region: toolbar (title, export) and a single Plotly graph.
"""

from dash import dcc, html

from lib.dash.dash_config import FONT_SIZES, FONT_FAMILY
from lib.dash.components import ticker_pill
from lib.dash.chart_builder import create_empty_chart
from lib.dash.bootstrap import BootstrapSnapshot


def _create_chart_area(styles: dict, theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Main:
    """Create the main chart area."""
    return html.Main([
        html.Div([
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
                # Phase 8: bar-count / interval / span readout. Driven by
                # callbacks/chart_view.py; reflects the zoomed window when the
                # relayout store is active.
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
            ], style={'display': 'flex', 'gap': '12px', 'alignItems': 'baseline', 'flex': '1 1 auto', 'minWidth': 0}),

            html.Div([
                html.Button("Export CSV", id='export-csv-btn', style=styles['button_outline'], n_clicks=0),
                html.Button("Export Image", id='export-img-btn', style=styles['button_outline'], n_clicks=0),
            ], style={'display': 'flex', 'gap': '12px', 'alignItems': 'center', 'flexShrink': 0}),
        ], style={**styles['chart_toolbar'], 'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'gap': '12px'}),

        html.Div(
            # `delay_show` keeps the spinner from flashing on the many fast,
            # sidebar-driven chart rebuilds (toggle an overlay \u2192 sub-100ms
            # redraw). It only appears when a redraw genuinely stalls \u2014 a data
            # (re)load or a slow enrichment pass.
            dcc.Loading(
                id='chart-loading',
                type='circle',
                color=theme['accent_blue'],
                delay_show=350,
                parent_style={'height': '100%', 'width': '100%'},
                children=dcc.Graph(
                    id='financial-chart',
                    figure=(
                        bootstrap.chart_figure
                        if bootstrap
                        else create_empty_chart(theme, "Loading TSLA\u2026")
                    ),
                    style={'height': '100%', 'width': '100%'},
                    # height/width None = size the PNG export to the on-screen
                    # chart. Dash's Config TypedDict doesn't model the None, so
                    # the literal trips Pylance — harmless at runtime.
                    config={  # type: ignore[reportArgumentType]
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
                ),
            ),
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
