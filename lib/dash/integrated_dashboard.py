"""
Professional Trading Dashboard
Bloomberg Terminal-inspired design with single-page layout.
"""

import logging
import os
import socket
from datetime import date, datetime
from threading import Timer
import webbrowser

import dash
from dash import dcc, html
import dash_bootstrap_components as dbc
import dash_mantine_components as dmc
from flask import Response, send_file

# Optional TradingView lightweight chart wrapper. Not all environments will
# have `dash_tvlwc` installed (it's an optional dependency). Provide a safe
# fallback so the app can run without the package.
try:
    from dash_tvlwc import Tvlwc  # type: ignore[reportMissingImports]
except Exception:
    def Tvlwc(*args, **kwargs):
        # Return a minimal placeholder component. The caller often places this
        # inside a hidden element (preload) or expects an html.Component
        # returned from callbacks, so return a Div that makes failure visible
        # but does not crash the app.
        return html.Div("TradingView component not installed (dash_tvlwc).", style={'display': 'none'})

from lib.dash.dash_config import (
    DEFAULT_THEME, DEFAULT_TICKER, INITIAL_CAPITAL, START_DATE,
    START_PORT, MAX_PORT_TRIES,
    FONT_SIZES, FONT_FAMILY, BORDER_RADIUS,
    DEFAULT_SIGNAL_WINDOW,
    PLOT_OPTIONS, PLOT_INDICATOR_OPTIONS, CHART_ELEMENT_OPTIONS, SIGNAL_OPTIONS,
    DEFAULT_INDICATOR_SETTINGS, INDICATOR_SETTING_SCHEMA,
    FUNDAMENTALS_PERIOD_OPTIONS, DEFAULT_FUNDAMENTALS_PERIOD,
    get_theme
)
from lib.dash.state import dashboard_state  # noqa: F401 - used by callbacks
from lib.dash.styles import get_styles, CUSTOM_CSS
from lib.dash.components import bloomberg_section, dense_input, ticker_pill
from lib.dash.chart_builder import create_chart
from lib.dash.callbacks import register_callbacks
from lib.signals.indicators import get_signal_categories

logger = logging.getLogger(__name__)

DEFAULT_FLOW_REPORT = os.path.join(os.getcwd(), "flow_report.html")

_FLOW_STUB_HTML = """<!DOCTYPE html>
<html><head><meta charset="utf-8"><title>Flow Scanner</title>
<style>body{background:#0d1117;color:#c9d1d9;font-family:system-ui;padding:24px;}</style>
</head><body><h1>No flow report yet</h1>
<p>Click <strong>RESCAN NOW</strong> on the Flow Scanner page, or run:</p>
<pre>python scripts/flow_scanner.py AAPL</pre>
</body></html>"""


def create_dashboard_layout(theme: dict) -> html.Div:
    """Create the main dashboard layout."""
    styles = get_styles(theme)

    content = html.Div([
        dcc.Location(id='app-url', refresh=False),
        # Hidden stores
        dcc.Store(id='theme-store', data=DEFAULT_THEME, storage_type='local'),
        dcc.Store(id='data-loaded-store', data=False),
        dcc.Store(id='layout-store', data={}),
        dcc.Store(id='presets-store', data={'presets': {}}),
        dcc.Store(id='active-preset-name', data=None),
        dcc.Store(id='preset-apply-store', data=None),
        dcc.Store(id='active-tab-store', data='backtest', storage_type='local'),
        dcc.Store(id='optimization-running', data=False),
        dcc.Store(id='optimization-state', data={
            'running': False,
            'current_index': 0,
            'total_combinations': 0,
            'completed': False,
            'sort_by': 'Total_Return_%',
            'sort_ascending': False
        }),
        dcc.Store(id='optimization-results-store', data=[]),
        dcc.Store(id='signals-unified-store', data=[]),
        dcc.Store(id='indicator-settings-store', data=DEFAULT_INDICATOR_SETTINGS),
        dcc.Store(id='active-indicator-store', data=None),
        dcc.Store(id='export-img-store', data=None),
        dcc.Store(id='fundamentals-store', data=None, storage_type='session'),
        dcc.Store(id='fundamentals-period-store', data=DEFAULT_FUNDAMENTALS_PERIOD, storage_type='session'),
        # Tracks tickers the user has explicitly selected. Stays None until
        # the user changes the dropdown, so the fundamentals callback can
        # distinguish a cold direct load (no selection yet) from a
        # genuine user choice.
        dcc.Store(id='user-ticker-store', data=None, storage_type='session'),
        dcc.Input(id='fundamentals-esc-signal', type='text', value='', style={'display': 'none'}),
        dcc.Download(id='download-csv'),
        dcc.Interval(id='startup-interval', interval=500, max_intervals=1),
        dcc.Interval(id='autoload-interval', interval=1000, max_intervals=1),
        dcc.Interval(id='optimization-interval', interval=500, disabled=True, n_intervals=0),
        dcc.Store(id='flow-state-store', data={'last_scan_at': None, 'tickers': []}, storage_type='session'),
        dcc.Interval(id='flow-rescan-interval', interval=2000, max_intervals=1, disabled=True),

        # Keyboard shortcut listener
        html.Div(id='keyboard-listener', style={'display': 'none'}),
        html.Div(id='theme-class-sync', style={'display': 'none'}),

        html.Div([
            _create_header(styles, theme),
            html.Div([
                _create_sidebar(styles, theme),
                _create_chart_area(styles, theme),
                _create_right_panel(styles, theme),
            ], style=styles['main_container']),
            _create_status_bar(styles, theme),
        ], id='terminal-shell'),

        _create_fundamentals_overlay(styles, theme),
        _create_flow_overlay(styles, theme),

        # Hidden elements
        html.Div(id='hidden-output', style={'display': 'none'}),
        html.Div(
            Tvlwc(
                id='tv-preload',
                seriesData=[[]],
                seriesTypes=['candlestick'],
                seriesOptions=[{}],
                seriesMarkers=[[]],
                width=1,
                height=1
            ),
            style={'display': 'none'}
        ),

    ], style=styles['app'], id='app-container')

    # Wrap with MantineProvider so dmc.Select renders with our Bloomberg-amber theme.
    # dmc.MantineProvider must wrap the entire layout tree for Mantine context to be
    # available to all dmc.* components (in particular dmc.Select used for ticker search).
    return dmc.MantineProvider(
        content,
        theme={
            "primaryColor": "orange",
            "fontFamily": 'Source Sans 3, system-ui, sans-serif',
            "defaultRadius": "xs",
            "colors": {
                # Override orange scale with Bloomberg amber (#FFA726) accents.
                "orange": [
                    "#FFF3E0", "#FFE0B2", "#FFCC80", "#FFB74D", "#FFA726",
                    "#FB8C00", "#F57C00", "#EF6C00", "#E65100", "#B87420",
                ],
            },
        },
        forceColorScheme="dark",
    )


def _create_header(styles: dict, theme: dict) -> html.Header:
    """Create the dashboard header."""
    return html.Header([
        html.Div([
            html.Div("SFA", style=styles['logo_icon'], className='bbg-wordmark'),
            html.Span("Terminal", style=styles['logo_text'], className='bbg-wordmark-sub'),
        ], style=styles['logo']),

        html.Div([
            html.Span(DEFAULT_TICKER, id='header-ticker-symbol', className='bbg-tape-symbol'),
            html.Span('$--', id='header-ticker-price', className='bbg-tape-price num'),
            html.Span('READY', id='header-ticker-change', className='bbg-tape-delta muted'),
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
            # Theme toggle
            html.Button(
                id='theme-toggle',
                children=[html.Span('[ DARK ]', id='theme-label')],
                style=styles['button_outline'],
                className='bbg-button-ghost',
                n_clicks=0
            ),
            dbc.Tooltip("Toggle light/dark theme", target='theme-toggle', placement='bottom'),
        ], style=styles['header_controls']),
    ], style=styles['header'], className='bbg-header')


def _create_status_bar(styles: dict, theme: dict) -> html.Div:
    """Create the dense bottom status bar."""
    return html.Div([
        html.Div([
            html.Span(className='dot dot-up'),
            html.Span('READY'),
        ], style=styles['status_segment'], className='bbg-status-segment'),
        html.Div([
            html.Span('DATA:'),
            html.Span('WAITING', id='data-status', className='num', style={'marginLeft': '6px'}),
        ], style=styles['status_segment'], className='bbg-status-segment'),
        html.Div([
            html.Span('STRATEGY:'),
            html.Span('--', id='strategy-order-status', className='num', style={'marginLeft': '6px'}),
        ], style={**styles['status_segment'], 'flex': 1, 'minWidth': 0}, className='bbg-status-segment flex-grow'),
        html.Div([
            html.Span(id='status-clock', className='num'),
        ], style={**styles['status_segment'], 'borderRight': 'none'}, className='bbg-status-segment'),
    ], style=styles['status_bar'], className='bbg-status-bar')


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
                    clearable=True,
                    nothingFoundMessage="No matches",
                    limit=20,
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
    ], style=styles['sidebar'])


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
                        children=[
                            dcc.Graph(
                                id='financial-chart',
                                style={'height': '100%', 'width': '100%'},
                                config={
                                    'responsive': True,
                                    'displayModeBar': True,
                                    'displaylogo': False,
                                    'modeBarButtonsToRemove': ['lasso2d', 'select2d'],
                                    'toImageButtonOptions': {
                                        'format': 'png',
                                        'filename': 'chart',
                                        'height': 800,
                                        'width': 1200,
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
                    'position': 'absolute',
                    'inset': 0,
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
                    'position': 'absolute',
                    'inset': 0,
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
            'overflow': 'auto',
            'position': 'relative'
        }, className='resizable-chart'),
    ], style=styles['chart_container'])


def _create_right_panel(styles: dict, theme: dict) -> html.Aside:
    """Create the right panel with backtest controls and results."""
    return html.Aside([
        # Tabs
        html.Div([
            html.Button("Backtest", id='tab-backtest', n_clicks=0,
                       style={**styles['tab'], **styles['tab_active']}, className='panel-tab active'),
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
            _create_backtest_panel(styles, theme),

            # Optimizer Panel
            _create_optimizer_panel(styles, theme),

            # Data Panel
            html.Div(id='panel-data', children=[
                html.Div(id='data-table-container', style={'fontSize': FONT_SIZES['xs']}),
            ], style={'display': 'none'}),

        ], style=styles['panel_content']),
    ], style=styles['right_panel'])


def _create_backtest_panel(styles: dict, theme: dict) -> html.Div:
    """Create the backtest panel content."""

    # Strategy mode card style
    mode_card_base = {
        'padding': '8px 10px',
        'borderRadius': BORDER_RADIUS['sm'],
        'border': f'1px solid {theme["border_primary"]}',
        'backgroundColor': theme['bg_secondary'],
        'cursor': 'pointer',
        'transition': 'all 0.1s ease',
        'marginBottom': '4px',
    }
    help_icon_style = styles['help_icon']

    signal_categories = get_signal_categories()

    return html.Div(id='panel-backtest', children=[
        dbc.Accordion(
            [
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Div([
                                html.Span("Execution Type", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'fontWeight': '600',
                                }),
                                html.Span("?", id='help-strategy-mode', style=help_icon_style),
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'space-between',
                                'marginBottom': '8px',
                            }),
                            dcc.RadioItems(
                                id='strategy-mode',
                                options=[
                                    {
                                        'label': html.Div([
                                            html.Div([
                                                html.Div([
                                                    html.Span("Trading", style={
                                                        'fontWeight': '600',
                                                        'fontSize': FONT_SIZES['sm'],
                                                        'color': theme['text_primary'],
                                                    }),
                                                    html.Span(" - Full Buy/Sell", style={
                                                        'fontSize': FONT_SIZES['xs'],
                                                        'color': theme['text_secondary'],
                                                        'marginLeft': '4px',
                                                    }),
                                                ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap'}),
                                                html.Span("?", id='help-strategy-trading', style=help_icon_style),
                                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'}),
                                            html.Div("Buy 100%, then sell 100%", style={
                                                'fontSize': '10px',
                                                'color': theme['text_tertiary'],
                                                'marginTop': '2px',
                                            }),
                                        ], className='strategy-mode-card', style=mode_card_base),
                                        'value': 'trading'
                                    },
                                    {
                                        'label': html.Div([
                                            html.Div([
                                                html.Div([
                                                    html.Span("Accumulation", style={
                                                        'fontWeight': '600',
                                                        'fontSize': FONT_SIZES['sm'],
                                                        'color': theme['accent_green'],
                                                    }),
                                                    html.Span(" - DCA", style={
                                                        'fontSize': FONT_SIZES['xs'],
                                                        'color': theme['text_secondary'],
                                                        'marginLeft': '4px',
                                                    }),
                                                ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap'}),
                                                html.Span("?", id='help-strategy-accumulation', style=help_icon_style),
                                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'}),
                                            html.Div("Fixed $ amount per buy signal", style={
                                                'fontSize': '10px',
                                                'color': theme['text_tertiary'],
                                                'marginTop': '2px',
                                            }),
                                        ], className='strategy-mode-card', style=mode_card_base),
                                        'value': 'accumulation'
                                    },
                                    {
                                        'label': html.Div([
                                            html.Div([
                                                html.Div([
                                                    html.Span("Rebalancing", style={
                                                        'fontWeight': '600',
                                                        'fontSize': FONT_SIZES['sm'],
                                                        'color': theme['accent_blue'],
                                                    }),
                                                    html.Span(" - Partial", style={
                                                        'fontSize': FONT_SIZES['xs'],
                                                        'color': theme['text_secondary'],
                                                        'marginLeft': '4px',
                                                    }),
                                                ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap'}),
                                                html.Span("?", id='help-strategy-rebalancing', style=help_icon_style),
                                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'}),
                                            html.Div("Trade % of portfolio per signal", style={
                                                'fontSize': '10px',
                                                'color': theme['text_tertiary'],
                                                'marginTop': '2px',
                                            }),
                                        ], className='strategy-mode-card', style=mode_card_base),
                                        'value': 'rebalancing'
                                    },
                                ],
                                value='trading',
                                className='strategy-mode-radio',
                                inputStyle={'display': 'none'},
                                labelStyle={'display': 'block', 'margin': 0, 'padding': 0},
                            ),
                            dbc.Tooltip(
                                "Choose how signals are executed in the backtest.",
                                target='help-strategy-mode',
                                placement='left',
                                trigger='hover focus',
                            ),
                            dbc.Tooltip(
                                "Full buy on signal, full sell on exit.",
                                target='help-strategy-trading',
                                placement='left',
                                trigger='hover focus',
                            ),
                            dbc.Tooltip(
                                "Fixed dollar-cost averaging on each buy signal.",
                                target='help-strategy-accumulation',
                                placement='left',
                                trigger='hover focus',
                            ),
                            dbc.Tooltip(
                                "Trade a percentage of portfolio each signal.",
                                target='help-strategy-rebalancing',
                                placement='left',
                                trigger='hover focus',
                            ),
                        ])
                    ],
                    title=html.Div([
                        html.Span("Execution Type"),
                        html.Span(
                            id='summary-strategy-mode',
                            className='accordion-title-summary'
                        )
                    ], className='accordion-title-row'),
                    item_id='backtest-strategy',
                ),
                dbc.AccordionItem(
                    [
                        html.Div(id='preset-options', children=[
                            html.Div([
                                html.Span("Strategy Preset", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_purple'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Dropdown(
                                id='strategy-preset',
                                options=[
                                    {'label': 'Custom', 'value': 'custom'},
                                    {'label': 'Swing', 'value': 'swing'},
                                    {'label': 'Position', 'value': 'position'},
                                    {'label': 'Trend', 'value': 'trend'},
                                ],
                                value='custom',
                                clearable=False,
                                style={'fontSize': FONT_SIZES['sm']},
                                className='dark-dropdown',
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_purple"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_purple"]}40',
                        }),
                        dbc.Tooltip(
                            "Quick presets for longer-hold strategies (swing/position/trend).",
                            target='strategy-preset',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='holding-period-options', children=[
                            html.Div([
                                html.Span("Min Holding Period", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_orange'],
                                }),
                                html.Span(" bars", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='min-holding-period',
                                type='number',
                                value=5,
                                min=0,
                                step=1,
                                placeholder='bars to hold',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_orange'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_orange"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_orange"]}40',
                        }),
                        dbc.Tooltip(
                            "Minimum number of bars to hold before a sell/exit.",
                            target='min-holding-period',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='trailing-stop-options', children=[
                            html.Div([
                                html.Span("Trailing Stop", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_red'],
                                }),
                                html.Span(" %", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='trailing-stop-pct',
                                type='number',
                                value=5,
                                min=0,
                                max=100,
                                step=0.5,
                                placeholder='% trail',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_red'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_red"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_red"]}40',
                        }),
                        dbc.Tooltip(
                            "Trailing stop percentage applied after entry.",
                            target='trailing-stop-pct',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='position-scaling-options', children=[
                            html.Div([
                                html.Span("Position Scaling", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_cyan'],
                                }),
                                html.Span(" %", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='position-scaling-pct',
                                type='number',
                                value=25,
                                min=0,
                                max=100,
                                step=1,
                                placeholder='% scale per signal',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_cyan'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_cyan"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_cyan"]}40',
                        }),
                        dbc.Tooltip(
                            "Increase position size by this % on repeated buys.",
                            target='position-scaling-pct',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='consecutive-signal-options', children=[
                            html.Div([
                                html.Span("Consecutive Signals", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_purple'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Dropdown(
                                id='consecutive-signal-mode',
                                options=[
                                    {'label': 'Scale-in (default behavior)', 'value': 'scale_in'},
                                    {'label': 'Edge trigger (0→1 only)', 'value': 'edge'},
                                    {'label': 'Cooldown between triggers', 'value': 'cooldown'},
                                    {'label': 'Reset + Cooldown (stricter)', 'value': 'reset_cooldown'},
                                ],
                                value='scale_in',
                                clearable=False,
                                style={'fontSize': FONT_SIZES['sm']},
                                className='dark-dropdown',
                            ),
                            html.Div(
                                id='consecutive-signal-help',
                                children="Controls repeated triggers for BUY and SELL signals.",
                                style={
                                    'fontSize': '10px',
                                    'color': theme['text_tertiary'],
                                    'marginTop': '6px'
                                }
                            ),
                            html.Div(id='signal-cooldown-container', children=[
                                html.Div([
                                    html.Span("Cooldown", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_secondary'],
                                    }),
                                    html.Span(" bars", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_primary'],
                                    }),
                                ], style={'marginTop': '8px', 'marginBottom': '4px'}),
                                dcc.Input(
                                    id='signal-cooldown-bars',
                                    type='number',
                                    value=5,
                                    min=0,
                                    step=1,
                                    placeholder='bars between triggers',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                        'borderColor': theme['accent_purple'],
                                    }
                                ),
                                html.Div("Applies to BUY and SELL signals.", style={
                                    'fontSize': '10px',
                                    'color': theme['text_tertiary'],
                                    'marginTop': '4px'
                                })
                            ], style={'display': 'block'})
                        ], style={
                            'marginBottom': '12px',
                            'display': 'block',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_purple"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_purple"]}40',
                        }),
                        dbc.Tooltip(
                            "Edge = only on 0→1. Cooldown = wait N bars. Reset+Cooldown = wait for reset plus N bars.",
                            target='consecutive-signal-mode',
                            placement='right',
                            trigger='hover focus',
                        ),
                        dbc.Tooltip(
                            "Best practice defaults: edge=0, cooldown=5, reset+cooldown=5.",
                            target='signal-cooldown-bars',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='take-profit-options', children=[
                            html.Div([
                                html.Span("Take Profit", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_green'],
                                }),
                                html.Span(" %", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='take-profit-pct',
                                type='number',
                                value=0,
                                min=0,
                                max=100,
                                step=0.5,
                                placeholder='% target',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_green'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_green"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_green"]}40',
                        }),
                        dbc.Tooltip(
                            "Exit full position when profit target is reached.",
                            target='take-profit-pct',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='accumulation-options', children=[
                            html.Div([
                                html.Span("Amount Per Buy", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_green'],
                                }),
                                html.Span(" $", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='amount-per-buy',
                                type='number',
                                value=1000,
                                min=100,
                                placeholder='$ per buy signal',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_green'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_green"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_green"]}40',
                        }),
                        dbc.Tooltip(
                            "Dollar amount used for each buy signal in Accumulation mode.",
                            target='amount-per-buy',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='rebalancing-options', children=[
                            html.Div([
                                html.Span("Position Size", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_blue'],
                                }),
                                html.Span(" %", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='position-size-pct',
                                type='number',
                                value=25,
                                min=1,
                                max=100,
                                placeholder='% per trade',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_blue'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_blue"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_blue"]}40',
                        }),
                        dbc.Tooltip(
                            "Percentage of portfolio to trade per signal in Rebalancing mode.",
                            target='position-size-pct',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='kelly-options', children=[
                            html.Div([
                                html.Span("Kelly Criterion", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_purple'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            html.Div([
                                html.Div([
                                    html.Span("Win Rate", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_secondary'],
                                    }),
                                ], style={'marginBottom': '4px'}),
                                dcc.Input(
                                    id='kelly-win-rate',
                                    type='number',
                                    value=0.5,
                                    min=0,
                                    max=1,
                                    step=0.01,
                                    placeholder='0.50',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                        'borderColor': theme['accent_purple'],
                                    }
                                ),
                            ], style={'marginBottom': '10px'}),
                            html.Div([
                                html.Div([
                                    html.Span("Win/Loss Ratio", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_secondary'],
                                    }),
                                ], style={'marginBottom': '4px'}),
                                dcc.Input(
                                    id='kelly-win-loss-ratio',
                                    type='number',
                                    value=1.5,
                                    min=0.1,
                                    step=0.1,
                                    placeholder='1.50',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                        'borderColor': theme['accent_purple'],
                                    }
                                ),
                            ]),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_purple"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_purple"]}40',
                        }),
                        dbc.Tooltip(
                            "Probability of a winning trade (0-1).",
                            target='kelly-win-rate',
                            placement='right',
                            trigger='hover focus',
                        ),
                        dbc.Tooltip(
                            "Average win/loss ratio used by Kelly sizing.",
                            target='kelly-win-loss-ratio',
                            placement='right',
                            trigger='hover focus',
                        ),
                    ],
                    title=html.Div([
                        html.Span("Trade Setup"),
                        html.Span(
                            id='summary-position-sizing',
                            className='accordion-title-summary'
                        )
                    ], className='accordion-title-row'),
                    item_id='backtest-sizing',
                ),
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Div([
                                html.Div([
                                    html.Span("SIGNALS", style=styles['card_header']),
                                    html.Span("?", id='help-signal-section', style=help_icon_style),
                                ], style={'display': 'flex', 'alignItems': 'center'}),
                                # AND/OR Toggle
                                html.Div([
                                    dcc.RadioItems(
                                        id='signal-logic-mode',
                                        options=[
                                            {'label': 'OR', 'value': 'or'},
                                            {'label': 'AND', 'value': 'and'},
                                        ],
                                        value='or',
                                        inline=True,
                                        inputStyle={'marginRight': '4px'},
                                        labelStyle={
                                            'fontSize': FONT_SIZES['xs'],
                                            'padding': '2px 8px',
                                            'cursor': 'pointer',
                                            'marginRight': '4px',
                                        },
                                        className='signal-logic-toggle'
                                    ),
                                ], style={
                                    'backgroundColor': theme['bg_tertiary'],
                                    'borderRadius': '4px',
                                    'padding': '2px 4px',
                                }),
                            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '6px'}),
                            html.Div([
                                html.Div([
                                    html.Label("AND Window", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_secondary'],
                                        'marginBottom': 0,
                                        'display': 'block'
                                    }),
                                    html.Span("?", id='help-signal-window', style=help_icon_style),
                                ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '4px'}),
                                dcc.Slider(
                                    id='signal-window',
                                    min=0,
                                    max=10,
                                    step=1,
                                    value=DEFAULT_SIGNAL_WINDOW,
                                    marks={
                                        0: {'label': '0', 'style': {'color': theme['text_secondary']}},
                                        2: {'label': '2', 'style': {'color': theme['text_secondary']}},
                                        4: {'label': '4', 'style': {'color': theme['text_secondary']}},
                                        6: {'label': '6', 'style': {'color': theme['text_secondary']}},
                                        8: {'label': '8', 'style': {'color': theme['text_secondary']}},
                                        10: {'label': '10', 'style': {'color': theme['text_secondary']}}
                                    }
                                ),
                                html.Div("Signals must occur within this window for AND logic.", style={
                                    'fontSize': '10px',
                                    'color': theme['text_tertiary'],
                                    'marginTop': '4px'
                                })
                            ], id='signal-window-container', style={'marginBottom': '10px'}),
                            html.Div([
                                html.Div([
                                    html.Div("Filters", className='signals-filter-label'),
                                    dcc.Input(
                                        id='signals-search',
                                        type='text',
                                        placeholder='Search signals...',
                                        style=styles['input'],
                                    ),
                                    html.Div("Categories", className='signals-filter-label'),
                                    dcc.Checklist(
                                        id='signals-category-filter',
                                        options=[{'label': cat, 'value': cat} for cat in signal_categories],
                                        value=signal_categories,
                                        inline=True,
                                        className='signals-category-filter'
                                    ),
                                ], className='signals-unified-controls'),
                                html.Div(
                                    id='signals-unified-list',
                                    className='signals-unified-list'
                                ),
                                dcc.Checklist(id='buy-signals', options=[], value=[], style={'display': 'none'}),
                                dcc.Checklist(id='sell-signals', options=[], value=[], style={'display': 'none'}),
                            ], style={'marginTop': '6px'}),
                            dbc.Tooltip(
                                "Configure how multiple signals combine to create entries.",
                                target='help-signal-section',
                                placement='left',
                                trigger='hover focus',
                            ),
                            dbc.Tooltip(
                                "When using AND, signals must occur within this window.",
                                target='help-signal-window',
                                placement='left',
                                trigger='hover focus',
                            ),
                        ], style=styles['card'])
                    ],
                    title=html.Div([
                        html.Span("Signals"),
                        html.Span(
                            id='summary-signal-settings',
                            className='accordion-title-summary accordion-title-summary--signals'
                        )
                    ], className='accordion-title-row'),
                    item_id='backtest-signals',
                ),
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Div([
                                html.Span("TRANSACTION COSTS", style=styles['card_header']),
                                html.Span("?", id='help-transaction-costs', style=help_icon_style),
                            ], style={'display': 'flex', 'alignItems': 'center'}),
                            html.Div([
                                html.Label("FX Fee (%)", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'marginBottom': '4px',
                                    'display': 'block'
                                }),
                                dcc.Input(
                                    id='fx-fee-pct',
                                    type='number',
                                    value=0.15,
                                    min=0,
                                    step=0.01,
                                    placeholder='0.15',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                    }
                                ),
                            ], style={'marginBottom': '10px'}),
                            html.Div([
                                html.Label("Slippage (%)", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'marginBottom': '4px',
                                    'display': 'block'
                                }),
                                dcc.Input(
                                    id='slippage-pct',
                                    type='number',
                                    value=0.05,
                                    min=0,
                                    step=0.01,
                                    placeholder='0.05',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                    }
                                ),
                            ], style={'marginBottom': '10px'}),
                            html.Div([
                                html.Label("Commission (%)", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'marginBottom': '4px',
                                    'display': 'block'
                                }),
                                dcc.Input(
                                    id='commission-pct',
                                    type='number',
                                    value=0.0,
                                    min=0,
                                    step=0.01,
                                    placeholder='0.00',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                    }
                                ),
                            ], style={'marginBottom': '4px'}),
                            html.Div("Trading 212 UK: 0% commission, 0.15% FX fee.", style={
                                'fontSize': '10px',
                                'color': theme['text_tertiary'],
                                'marginTop': '2px'
                            }),
                            dbc.Tooltip(
                                "Applied on every trade. FX fee assumes cross-currency.",
                                target='help-transaction-costs',
                                placement='left',
                                trigger='hover focus',
                            ),
                        ], style=styles['card'])
                    ],
                    title=html.Div([
                        html.Span("Transaction Costs"),
                        html.Span(
                            id='summary-transaction-costs',
                            className='accordion-title-summary'
                        )
                    ], className='accordion-title-row'),
                    item_id='backtest-costs',
                ),
            ],
            className='compact-accordion',
            always_open=True,
            active_item=['backtest-strategy', 'backtest-signals'],
            flush=True,
        ),

        html.Button(
            "RUN BACKTEST",
            id='run-backtest-btn',
            style={**styles['button_primary'], 'width': '100%', 'padding': '10px 14px'},
            n_clicks=0
        ),
        dbc.Tooltip("Simulate trading with selected buy/sell signals", target='run-backtest-btn', placement='top'),

        html.Div(id='backtest-results', style={'marginTop': '10px'}),
    ])


def _create_optimizer_panel(styles: dict, theme: dict) -> html.Div:
    """Create the optimizer panel content with progress and enhanced controls."""
    card_style = {
        'backgroundColor': theme['bg_tertiary'],
        'borderRadius': BORDER_RADIUS['sm'],
        'padding': '8px 10px',
        'marginBottom': '10px',
        'border': f'1px solid {theme["border_primary"]}'
    }
    help_icon_style = styles['help_icon']

    return html.Div(id='panel-optimizer', children=[
        # Signal Preview Card
        html.Div([
            html.Div([
                html.Div("SIGNAL PREVIEW", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_tertiary'],
                    'fontWeight': '600',
                    'letterSpacing': '0.5px'
                }),
                html.Span("?", id='help-signal-preview', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '8px'}),
            html.Div(id='signal-preview', children=[
                html.Div([
                    ticker_pill('BUY', '0', color='up', value_id='preview-buy-count'),
                    html.Span('│', className='num', style={'color': theme['border_primary']}),
                    ticker_pill('SELL', '0', color='down', value_id='preview-sell-count'),
                    html.Span('│', className='num', style={'color': theme['border_primary']}),
                    ticker_pill('COMBOS', '0', color='amber', value_id='preview-combo-count'),
                ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px', 'flexWrap': 'wrap'}),
            ]),
        ], style=card_style),

        # Optimization Settings
        html.Div([
            html.Div([
                html.Label("Max Signals per Side", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'marginBottom': 0,
                    'display': 'block'
                }),
                html.Span("?", id='help-max-signals', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '8px'}),
            dcc.Slider(
                id='max-signals-slider',
                min=1, max=5, value=2, step=1,
                marks={i: {'label': str(i), 'style': {'color': theme['text_secondary']}} for i in range(1, 6)},
            ),
        ], style={'marginBottom': '20px'}),

        html.Div([
            html.Div([
                html.Label("Max Combinations", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'marginBottom': 0,
                    'display': 'block'
                }),
                html.Span("?", id='help-max-combos', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '4px'}),
            dense_input(
                id='max-combos-input',
                type='number',
                value=100,
                min=10, max=1000,
                style=styles['input']
            ),
        ], style={'marginBottom': '16px'}),

        # Sort Options
        html.Div([
            html.Div([
                html.Label("Sort Results By", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'marginBottom': 0,
                    'display': 'block'
                }),
                html.Span("?", id='help-sort-metric', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '4px'}),
            dcc.RadioItems(
                id='sort-metric-dropdown',
                options=[
                    {'label': 'RET', 'value': 'Total_Return_%'},
                    {'label': 'SHARPE', 'value': 'Sharpe_Ratio'},
                    {'label': 'DD', 'value': 'Max_Drawdown_%'},
                    {'label': 'TRADES', 'value': 'Trades'},
                ],
                value='Total_Return_%',
                inline=True,
                className='bbg-radio-seg'
            ),
        ], style={'marginBottom': '16px'}),
        dbc.Tooltip(
            "Counts selected signals and estimated combinations.",
            target='help-signal-preview',
            placement='left',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Limit how many signals can be chosen per side.",
            target='help-max-signals',
            placement='left',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Cap the total combinations to test for speed.",
            target='help-max-combos',
            placement='left',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Choose the metric used to rank results.",
            target='help-sort-metric',
            placement='left',
            trigger='hover focus',
        ),

        # Run Button
        html.Button(
            "RUN OPTIMIZER",
            id='run-optimization-btn',
            style={**styles['button_primary'], 'width': '100%'},
            n_clicks=0
        ),
        dbc.Tooltip("Test all signal combinations to find the best strategy", target='run-optimization-btn', placement='top'),

        # Progress Section
        html.Div(id='optimization-progress', style={'marginTop': '12px'}),

        # Results Section
        html.Div(id='optimization-results', style={'marginTop': '16px'}),

        # Apply Strategy Button (hidden initially)
        html.Div(id='apply-strategy-container', children=[
            html.Button(
                "Apply Best Strategy",
                id='apply-strategy-btn',
                style={
                    **styles['button_primary'],
                    'width': '100%',
                    'marginTop': '12px',
                    'backgroundColor': theme['accent_green']
                },
                n_clicks=0,
            ),
            dbc.Tooltip("Apply the best strategy to the Backtest panel", target='apply-strategy-btn', placement='top'),
        ], style={'display': 'none'}),

    ], style={'display': 'none'})


def find_available_port(start_port: int = START_PORT, max_tries: int = MAX_PORT_TRIES) -> int:
    """Find an available port."""
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    raise RuntimeError("No available ports found")


def _get_env_port(default_port: int) -> int:
    """Read DASH_PORT from env with safe integer fallback."""
    raw_port = os.getenv("DASH_PORT", str(default_port)).strip()
    try:
        return int(raw_port)
    except (TypeError, ValueError):
        logger.warning("Invalid DASH_PORT=%r; falling back to %d", raw_port, default_port)
        return default_port


def run_dashboard(dev_mode: bool = False) -> None:
    """Run the professional trading dashboard."""
    theme = get_theme(DEFAULT_THEME)

    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        suppress_callback_exceptions=True,
        meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}]
    )

    app.index_string = f'''
    <!DOCTYPE html>
    <html>
        <head>
            {{%metas%}}
            <title>SearchForAlpha - Trading Dashboard</title>
            {{%favicon%}}
            {{%css%}}
            <style>{CUSTOM_CSS}</style>
        </head>
        <body>
            {{%app_entry%}}
            <footer>
                {{%config%}}
                {{%scripts%}}
                {{%renderer%}}
            </footer>
        </body>
    </html>
    '''

    app.layout = create_dashboard_layout(theme)

    # Register all callbacks
    register_callbacks(app)

    @app.server.route("/flow_report.html")
    def serve_flow_report():
        if os.path.exists(DEFAULT_FLOW_REPORT):
            resp = send_file(DEFAULT_FLOW_REPORT, mimetype="text/html")
            resp.headers["Cache-Control"] = "no-store"
            return resp
        return Response(_FLOW_STUB_HTML, mimetype="text/html")

    def _serve_dash_shell():
        return app.index()

    for idx, route in enumerate(("/fundamentals", "/fundamentals/", "/flow", "/flow/")):
        endpoint = f"sfa_shell_{idx}"
        app.server.add_url_rule(route, endpoint=endpoint, view_func=_serve_dash_shell)

    # Start server
    def open_browser():
        webbrowser.open_new(f"http://127.0.0.1:{port}/")

    # In dev mode the reloader spawns two processes; keep a fixed port to
    # avoid the second process auto-selecting the next free port.
    # For production/deploy, prefer explicit env-based binding.
    host = "127.0.0.1" if dev_mode else os.getenv("DASH_HOST", "127.0.0.1").strip()
    port = _get_env_port(START_PORT if dev_mode else 8060)
    should_open_browser = (not dev_mode) or (os.environ.get("WERKZEUG_RUN_MAIN") == "true")
    if should_open_browser:
        Timer(1, open_browser).start()
    logger.info("Starting dashboard on %s:%s", host, port)
    app.run(debug=dev_mode, use_reloader=dev_mode, host=host, port=port)


# =============================================================================
# LEGACY SUPPORT
# =============================================================================

def create_dash_app(df, ticker: str, backtest_results: dict) -> dash.Dash:
    """Legacy function for backwards compatibility."""
    theme = get_theme()
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

    config = {
        'selected_plots': ['candlestick', 'volume', 'rsi'],
        'show_candlesticks': True,
        'show_bollinger': True,
        'show_sma': True,
        'show_ema': False,
        'show_buy_sell_signals': True,
        'show_legend': True,
        'selected_signals': ['buy', 'sell'],
        'title': f'{ticker} Analysis',
    }

    fig = create_chart(df, config, theme)

    app.layout = html.Div([
        dcc.Graph(figure=fig, style={'height': '90vh'}),
    ], style={'backgroundColor': theme['bg_primary'], 'height': '100vh'})

    return app


def plot_financial_chart_dash(df, ticker: str, backtest_results: dict) -> None:
    """Legacy function for backwards compatibility."""
    app = create_dash_app(df, ticker, backtest_results)
    port = find_available_port()
    Timer(1, lambda: webbrowser.open_new(f"http://127.0.0.1:{port}/")).start()
    app.run(debug=False, use_reloader=False, port=port)


if __name__ == '__main__':
    run_dashboard()
