"""
Right panel shell: Backtest / Optimizer / Data tabs.

Tab bodies live in ``backtest_panel`` and ``optimizer_panel``; the Data tab
filter chrome stays here (table body is filled by callbacks).
"""

from dash import dcc, html

from lib.dash.dash_config import FONT_SIZES, DATA_ROW_OPTIONS, DATA_COLUMN_GROUPS
from lib.dash.bootstrap import BootstrapSnapshot
from .backtest_panel import _create_backtest_panel
from .optimizer_panel import _create_optimizer_panel


def _create_right_panel(styles: dict, theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Aside:
    """Create the right panel with backtest controls and results."""
    return html.Aside([
        html.Div(
            # Glyph is re-set per state by the layout clientside callback; this
            # is just the expanded-by-default first paint.
            html.Button(">>", id='right-panel-toggle-btn', n_clicks=0, className='sfa-panel-toggle',
                        title='Collapse panel', **{'aria-label': 'Toggle backtest panel'}),
            className='sfa-panel-toggle-wrap',
        ),
        html.Div([
            # Tabs
            html.Div([
                html.Button("Backtest", id='tab-backtest', n_clicks=0,
                           style=styles['tab'], className='panel-tab'),
                html.Span('│', className='num', style={'color': theme['border_primary'], 'alignSelf': 'center'}),
                html.Button("Optimizer", id='tab-optimizer', n_clicks=0,
                           style=styles['tab'], className='panel-tab'),
                html.Span('│', className='num', style={'color': theme['border_primary'], 'alignSelf': 'center'}),
                html.Button("Data", id='tab-data', n_clicks=0,
                           style=styles['tab'], className='panel-tab'),
            ], style=styles['panel_header']),

            # Panel Content
            html.Div([
                # Backtest Panel
                _create_backtest_panel(styles, theme, bootstrap=bootstrap),

                # Optimizer Panel
                _create_optimizer_panel(styles, theme),

                # Data Panel
                html.Div(id='panel-data', children=[
                    html.Div([
                        html.Div([
                            html.Label('Rows', style={
                                'fontSize': FONT_SIZES['xs'],
                                'color': theme['text_secondary'],
                                'marginBottom': '4px',
                                'display': 'block',
                            }),
                            dcc.RadioItems(
                                id='data-rows',
                                options=DATA_ROW_OPTIONS,
                                value=50,
                                inline=True,
                                className='bbg-radio-seg',
                            ),
                        ], style={'marginBottom': '10px'}),
                        html.Div([
                            html.Label('Columns', style={
                                'fontSize': FONT_SIZES['xs'],
                                'color': theme['text_secondary'],
                                'marginBottom': '4px',
                                'display': 'block',
                            }),
                            dcc.Checklist(
                                id='data-col-groups',
                                options=DATA_COLUMN_GROUPS,
                                value=['ohlcv', 'indicators', 'signals', 'portfolio'],
                                inline=True,
                                inputStyle={'marginRight': '4px'},
                                labelStyle={
                                    'fontSize': FONT_SIZES['xs'],
                                    'marginRight': '10px',
                                    'color': theme['text_primary'],
                                },
                            ),
                        ], style={'marginBottom': '10px'}),
                        html.Div([
                            html.Div([
                                html.Label('From', style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'marginBottom': '4px',
                                    'display': 'block',
                                }),
                                dcc.DatePickerSingle(
                                    id='data-date-start',
                                    display_format='YYYY-MM-DD',
                                    className='dark-datepicker',
                                    style={'width': '100%'},
                                ),
                            ], style={'flex': 1}),
                            html.Div([
                                html.Label('To', style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'marginBottom': '4px',
                                    'display': 'block',
                                }),
                                dcc.DatePickerSingle(
                                    id='data-date-end',
                                    display_format='YYYY-MM-DD',
                                    className='dark-datepicker date-picker-end',
                                    style={'width': '100%'},
                                ),
                            ], style={'flex': 1}),
                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                        html.Button(
                            'EXPORT CSV',
                            id='data-export-btn',
                            style={**styles['button_outline'], 'width': '100%', 'marginBottom': '10px'},
                            n_clicks=0,
                        ),
                        dcc.Download(id='data-download'),
                    ]),
                    html.Div(id='data-summary-strip'),
                    html.Div(id='data-table-container', style={'fontSize': FONT_SIZES['xs']}),
                ], style={'display': 'none'}),

            ], style=styles['panel_content']),
        ], className='sfa-right-panel-inner'),
    ], style=styles['right_panel'], className='sfa-right-panel')

