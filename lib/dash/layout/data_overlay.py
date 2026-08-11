"""
Shared Data overlay used by both the terminal and the Optimizer workspace.
"""

from dash import dcc, html

from lib.dash.dash_config import DATA_COLUMN_GROUPS, DATA_ROW_OPTIONS, FONT_SIZES


def _create_data_overlay(styles: dict, theme: dict) -> html.Div:
    """Create the singleton data overlay so table IDs are mounted only once."""
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                "DATA",
                                style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'fontWeight': '600',
                                    'letterSpacing': '1.2px',
                                },
                            ),
                            html.Div(
                                "Loaded bars, indicators, signals, and portfolio columns",
                                style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'color': theme['text_primary'],
                                    'fontWeight': '600',
                                },
                            ),
                        ],
                        style={'minWidth': 0, 'flex': '1 1 auto'},
                    ),
                    html.Button(
                        "CLOSE",
                        id='close-data-button',
                        n_clicks=0,
                        style={
                            **styles['button_outline'],
                            'color': theme['accent_red'],
                            'borderColor': theme['accent_red'],
                            'padding': '6px 12px',
                        },
                    ),
                ],
                style={
                    'minHeight': '36px',
                    'flex': '0 0 auto',
                    'padding': '8px 10px',
                    'display': 'flex',
                    'alignItems': 'center',
                    'justifyContent': 'space-between',
                    'gap': '8px',
                    'backgroundColor': theme['bg_secondary'],
                    'borderBottom': f'1px solid {theme["border_primary"]}',
                },
            ),
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                [
                                    html.Label(
                                        'Rows',
                                        style={
                                            'fontSize': FONT_SIZES['xs'],
                                            'color': theme['text_secondary'],
                                            'marginBottom': '4px',
                                            'display': 'block',
                                        },
                                    ),
                                    dcc.RadioItems(
                                        id='data-rows',
                                        options=DATA_ROW_OPTIONS,
                                        value=50,
                                        inline=True,
                                        className='bbg-radio-seg',
                                    ),
                                ],
                                style={'marginBottom': '10px'},
                            ),
                            html.Div(
                                [
                                    html.Label(
                                        'Columns',
                                        style={
                                            'fontSize': FONT_SIZES['xs'],
                                            'color': theme['text_secondary'],
                                            'marginBottom': '4px',
                                            'display': 'block',
                                        },
                                    ),
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
                                ],
                                style={'marginBottom': '10px'},
                            ),
                            html.Div(
                                [
                                    html.Div(
                                        [
                                            html.Label(
                                                'From',
                                                style={
                                                    'fontSize': FONT_SIZES['xs'],
                                                    'color': theme['text_secondary'],
                                                    'marginBottom': '4px',
                                                    'display': 'block',
                                                },
                                            ),
                                            dcc.DatePickerSingle(
                                                id='data-date-start',
                                                display_format='YYYY-MM-DD',
                                                className='dark-datepicker',
                                                style={'width': '100%'},
                                            ),
                                        ],
                                        style={'flex': 1},
                                    ),
                                    html.Div(
                                        [
                                            html.Label(
                                                'To',
                                                style={
                                                    'fontSize': FONT_SIZES['xs'],
                                                    'color': theme['text_secondary'],
                                                    'marginBottom': '4px',
                                                    'display': 'block',
                                                },
                                            ),
                                            dcc.DatePickerSingle(
                                                id='data-date-end',
                                                display_format='YYYY-MM-DD',
                                                className='dark-datepicker date-picker-end',
                                                style={'width': '100%'},
                                            ),
                                        ],
                                        style={'flex': 1},
                                    ),
                                ],
                                style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'},
                            ),
                            html.Button(
                                'EXPORT CSV',
                                id='data-export-btn',
                                style={**styles['button_outline'], 'width': '100%', 'marginBottom': '10px'},
                                n_clicks=0,
                            ),
                            dcc.Download(id='data-download'),
                        ],
                        style={
                            'padding': '10px',
                            'borderBottom': f'1px solid {theme["border_primary"]}',
                            'flex': '0 0 auto',
                        },
                    ),
                    html.Div(
                        [
                            html.Div(id='data-summary-strip'),
                            html.Div(id='data-table-container', style={'fontSize': FONT_SIZES['xs']}),
                        ],
                        style={
                            'padding': '10px',
                            'display': 'flex',
                            'flexDirection': 'column',
                            'gap': '10px',
                            'minHeight': 0,
                            'overflow': 'auto',
                            'flex': '1 1 auto',
                        },
                    ),
                ],
                style={
                    'display': 'flex',
                    'flexDirection': 'column',
                    'minHeight': 0,
                    'flex': '1 1 auto',
                },
            ),
        ],
        id='data-overlay',
        style={
            'display': 'none',
            'position': 'fixed',
            'inset': '56px 16px 36px 16px',
            'zIndex': 25,
            'backgroundColor': theme['bg_primary'],
            'border': f'1px solid {theme["border_primary"]}',
            'boxShadow': '0 18px 60px rgba(0, 0, 0, 0.45)',
            'overflow': 'hidden',
            'flexDirection': 'column',
        },
        className='sfa-data-overlay',
    )
