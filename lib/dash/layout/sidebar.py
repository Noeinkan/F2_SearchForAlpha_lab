"""
Left sidebar with three collapsible Bloomberg-style sections:
- Market Data (ticker, dates, capital, load + overlay entry buttons)
- Saved Configurations (presets CRUD)
- Chart Settings (indicator toggles + gear icons, overlays, signal kinds)
"""

from datetime import date

from dash import dcc, html
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc

from lib.dash.dash_config import (
    DEFAULT_TICKER, INITIAL_CAPITAL, START_DATE,
    FONT_SIZES,
    PLOT_INDICATOR_OPTIONS, CHART_ELEMENT_OPTIONS, SIGNAL_OPTIONS,
    INDICATOR_SETTING_SCHEMA,
)
from lib.dash.components import bloomberg_section, dense_input


def _create_sidebar(styles: dict, theme: dict) -> html.Aside:
    """Create the left sidebar with controls."""
    help_icon_style = styles['help_icon']

    market_section = html.Div([
        html.Div([
                html.Label("Symbol", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '4px', 'display': 'block'}),
                dmc.Select(
                    id='ticker-dropdown',
                    value=DEFAULT_TICKER,
                    placeholder="Type to search ticker or company...",
                    searchable=True,
                    clearable=False,
                    nothingFoundMessage="No matches",
                    limit=50,
                    comboboxProps={"withinPortal": True, "shadow": "md"},
                    size="xs",
                    data=[{"value": DEFAULT_TICKER, "label": DEFAULT_TICKER}],
                    style={'fontSize': FONT_SIZES['sm']},
                ),
            ], style={'marginBottom': '12px'}),

            html.Div([
                html.Div([
                    html.Label("Start Date", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '4px', 'display': 'block'}),
                    dcc.DatePickerSingle(
                        id='start-date',
                        date=START_DATE,
                        display_format='YYYY-MM-DD',
                        style={'width': '100%'}
                    ),
                ], style={'flex': 1}),
                html.Div([
                    html.Label("End Date", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '4px', 'display': 'block'}),
                    dcc.DatePickerSingle(
                        id='end-date',
                        date=date.today().isoformat(),
                        display_format='YYYY-MM-DD',
                        className='date-picker-end',
                        style={'width': '100%'}
                    ),
                ], style={'flex': 1}),
            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '12px'}),

            html.Div([
                html.Label("Initial Capital", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '4px', 'display': 'block'}),
                dense_input(
                    id='initial-capital',
                    type='number',
                    value=INITIAL_CAPITAL,
                    style={**styles['input'], 'textAlign': 'right'}
                ),
            ], style={'marginBottom': '12px'}),

            html.Button(
                [html.Span("LOAD DATA"), html.Span(" ENTER", style={'opacity': '0.65', 'marginLeft': '8px', 'fontSize': '10px'})],
                id='load-data-button',
                style={**styles['button_primary'], 'width': '100%'},
                n_clicks=0
            ),
            dbc.Tooltip("Fetch market data and calculate indicators (Ctrl+Enter)", target='load-data-button', placement='right'),
            html.Button(
                "OPEN FUNDAMENTALS",
                id='open-fundamentals-button',
                style={**styles['button_outline'], 'width': '100%', 'marginTop': '8px', 'padding': '7px 10px'},
                n_clicks=0,
            ),
            dbc.Tooltip("Open 10-year fundamentals and Rule #1 valuation for the selected symbol", target='open-fundamentals-button', placement='right'),
            html.Button(
                "OPEN FLOW",
                id='open-flow-button',
                style={
                    **styles['button_outline'],
                    'width': '100%',
                    'marginTop': '8px',
                    'padding': '7px 10px',
                    'borderColor': theme['accent_purple'],
                    'color': theme['accent_purple'],
                },
                n_clicks=0,
            ),
            dbc.Tooltip(
                "Cheddar-Flow-style unusual options activity scanner",
                target='open-flow-button',
                placement='right',
            ),
        ])

    presets_section = html.Div([
        html.Div([
            html.Label("Preset", style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_secondary'],
                'marginBottom': '4px',
                'display': 'block'
            }),
            dcc.Dropdown(
                id='preset-selector',
                options=[],
                value=None,
                placeholder="Select preset...",
                clearable=True,
                style={'fontSize': FONT_SIZES['sm']},
                className='dark-dropdown'
            ),
        ], style={'marginBottom': '10px'}),
        html.Div([
            html.Label("Name", style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_secondary'],
                'marginBottom': '4px',
                'display': 'block'
            }),
            dcc.Input(
                id='preset-name-input',
                type='text',
                value='',
                placeholder='Preset name',
                style={**styles['input'], 'width': '100%'}
            ),
        ], style={'marginBottom': '10px'}),
        html.Div([
            html.Button(
                "Save",
                id='preset-save-btn',
                style={**styles['button_primary'], 'flex': '1', 'padding': '6px 10px'},
                n_clicks=0
            ),
            html.Button(
                "Save As",
                id='preset-save-as-btn',
                style={**styles['button_outline'], 'flex': '1', 'padding': '6px 10px'},
                n_clicks=0
            ),
        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '8px'}),
        html.Div([
            html.Button(
                "Rename",
                id='preset-rename-btn',
                style={**styles['button_outline'], 'flex': '1', 'padding': '6px 10px'},
                n_clicks=0
            ),
            html.Button(
                "Delete",
                id='preset-delete-btn',
                style={
                    **styles['button_outline'],
                    'flex': '1',
                    'padding': '6px 10px',
                    'color': theme['accent_red'],
                    'borderColor': theme['accent_red']
                },
                n_clicks=0
            ),
        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '6px'}),
        html.Div(id='preset-status', style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary']}),
    ])

    chart_section = html.Div([
        html.Div([
            html.Div([
                html.Label("Indicators", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': 0, 'display': 'block'}),
                html.Span("?", id='help-chart-indicators', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '8px'}),
            html.Div(
                [
                    html.Div([
                        html.Div([
                            dcc.Checklist(
                                id={'type': 'plot-toggle', 'indicator': value},
                                options=[{'label': html.Span(label, style={'fontSize': FONT_SIZES['sm']}), 'value': value}],
                                value=[value] if value in {'candlestick', 'volume', 'rsi', 'cci', 'macd'} else [],
                                style={'flex': 1},
                                inputStyle={'cursor': 'pointer'},
                            labelStyle={
                                'display': 'flex',
                                'alignItems': 'center',
                                'gap': '8px',
                                'cursor': 'pointer',
                                'color': theme['text_primary']
                            }
                            ),
                            html.Button(
                                "\u2699",
                                id={'type': 'indicator-gear', 'indicator': value},
                                n_clicks=0,
                                n_clicks_timestamp=0,
                                type='button',
                                style=styles['indicator_gear_button'],
                                title=f"{label} settings",
                            ) if (value in INDICATOR_SETTING_SCHEMA and value not in {opt[1] for opt in CHART_ELEMENT_OPTIONS}) else html.Span(style={'width': '22px'})
                        ], style=styles['indicator_row']),
                        html.Div(
                            id={'type': 'indicator-settings-panel', 'indicator': value},
                            style=styles['indicator_settings_panel']
                        ) if (value in INDICATOR_SETTING_SCHEMA and value not in {opt[1] for opt in CHART_ELEMENT_OPTIONS}) else None
                    ])
                    for label, value in PLOT_INDICATOR_OPTIONS
                ],
                style={'display': 'flex', 'flexDirection': 'column', 'gap': '4px'}
            ),
        ], style={'marginBottom': '16px'}),
        html.Div([
            html.Div([
                html.Label("Overlays", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': 0, 'display': 'block'}),
                html.Span("?", id='help-chart-overlays', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '8px'}),
            dcc.Checklist(
                id='chart-elements-checklist',
                options=[{'label': html.Span(label, style={'marginLeft': '8px', 'fontSize': FONT_SIZES['sm']}), 'value': value}
                        for label, value in CHART_ELEMENT_OPTIONS],
                value=['candlesticks', 'signals', 'bollinger'],
                style={'display': 'flex', 'flexDirection': 'column', 'gap': '4px'},
                inputStyle={'cursor': 'pointer'},
                labelStyle={
                    'display': 'flex',
                    'alignItems': 'center',
                    'padding': '4px 0',
                    'cursor': 'pointer',
                    'color': theme['text_primary']
                }
            ),
            html.Div([
                html.Div([
                    html.Span("Bollinger Bands", style={'fontSize': FONT_SIZES['sm'], 'color': theme['text_primary']}),
                    html.Button(
                        "\u2699",
                        id={'type': 'indicator-gear', 'indicator': 'bollinger'},
                        n_clicks=0,
                        n_clicks_timestamp=0,
                        type='button',
                        style=styles['indicator_gear_button'],
                        title="Bollinger Bands settings",
                    ),
                ], style=styles['indicator_row']),
                html.Div(
                    id={'type': 'indicator-settings-panel', 'indicator': 'bollinger'},
                    style=styles['indicator_settings_panel']
                ),
                html.Div([
                    html.Span("SMA", style={'fontSize': FONT_SIZES['sm'], 'color': theme['text_primary']}),
                    html.Button(
                        "\u2699",
                        id={'type': 'indicator-gear', 'indicator': 'sma'},
                        n_clicks=0,
                        n_clicks_timestamp=0,
                        type='button',
                        style=styles['indicator_gear_button'],
                        title="SMA settings",
                    ),
                ], style=styles['indicator_row']),
                html.Div(
                    id={'type': 'indicator-settings-panel', 'indicator': 'sma'},
                    style=styles['indicator_settings_panel']
                ),
                html.Div([
                    html.Span("EMA", style={'fontSize': FONT_SIZES['sm'], 'color': theme['text_primary']}),
                    html.Button(
                        "\u2699",
                        id={'type': 'indicator-gear', 'indicator': 'ema'},
                        n_clicks=0,
                        n_clicks_timestamp=0,
                        type='button',
                        style=styles['indicator_gear_button'],
                        title="EMA settings",
                    ),
                ], style=styles['indicator_row']),
                html.Div(
                    id={'type': 'indicator-settings-panel', 'indicator': 'ema'},
                    style=styles['indicator_settings_panel']
                ),
            ], style={'display': 'flex', 'flexDirection': 'column', 'gap': '4px', 'marginTop': '6px'}),
        ], style={'marginBottom': '16px', 'marginTop': '16px'}),
        html.Div([
            html.Div([
                html.Label("Signals", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': 0, 'display': 'block'}),
                html.Span("?", id='help-chart-signals', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '8px'}),
            dcc.Checklist(
                id='signal-checklist',
                options=[{'label': html.Span(label, style={'marginLeft': '8px', 'fontSize': FONT_SIZES['sm']}), 'value': value}
                        for label, value in SIGNAL_OPTIONS],
                value=['buy', 'sell'],
                style={'display': 'flex', 'gap': '16px'},
                inputStyle={'cursor': 'pointer'},
                labelStyle={
                    'display': 'flex',
                    'alignItems': 'center',
                    'cursor': 'pointer',
                    'color': theme['text_primary']
                }
            ),
        ]),
        dbc.Tooltip(
            "Show/hide indicators and overlays on the chart.",
            target='help-chart-settings',
            placement='right',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Select price and indicator panels to plot.",
            target='help-chart-indicators',
            placement='right',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Click the gear next to an indicator to edit its settings.",
            target='help-indicator-settings',
            placement='right',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Toggle moving averages, bands, and visual overlays.",
            target='help-chart-overlays',
            placement='right',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Show buy/sell markers on the chart.",
            target='help-chart-signals',
            placement='right',
            trigger='hover focus',
        ),
    ])

    return html.Aside([
        html.Div(
            html.Button(">>", id='sidebar-toggle-btn', n_clicks=0, className='sfa-panel-toggle'),
            className='sfa-panel-toggle-wrap',
        ),
        bloomberg_section('Market Data', market_section, collapsible=True, open=True, theme=theme),
        bloomberg_section('Saved Configurations', presets_section, collapsible=True, open=True, theme=theme),
        bloomberg_section(
            html.Div([
                html.Span('Chart Settings'),
                html.Span('?', id='help-chart-settings', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'}),
            chart_section,
            collapsible=True,
            open=True,
            theme=theme,
        ),
    ], style=styles['sidebar'], className='sfa-sidebar')