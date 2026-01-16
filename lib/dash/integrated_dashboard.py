"""
Professional Trading Dashboard
Bloomberg Terminal-inspired design with single-page layout.
"""

import logging
import socket
from datetime import date
from threading import Timer
import webbrowser

import dash
from dash import dcc, html
import dash_bootstrap_components as dbc

from lib.dash.dash_config import (
    DEFAULT_THEME, DEFAULT_TICKER, INITIAL_CAPITAL, START_DATE,
    START_PORT, MAX_PORT_TRIES,
    FONT_SIZES, FONT_MONO,
    PLOT_OPTIONS, CHART_ELEMENT_OPTIONS, SIGNAL_OPTIONS,
    get_theme
)
from lib.dash.state import dashboard_state  # noqa: F401 - used by callbacks
from lib.dash.styles import get_styles, CUSTOM_CSS
from lib.dash.chart_builder import create_chart
from lib.dash.callbacks import register_callbacks

logger = logging.getLogger(__name__)


def create_dashboard_layout(theme: dict) -> html.Div:
    """Create the main dashboard layout."""
    styles = get_styles(theme)

    return html.Div([
        # Hidden stores
        dcc.Store(id='theme-store', data=DEFAULT_THEME),
        dcc.Store(id='data-loaded-store', data=False),
        dcc.Store(id='layout-store', data={}),
        dcc.Store(id='optimization-running', data=False),
        dcc.Interval(id='startup-interval', interval=500, max_intervals=1),
        dcc.Interval(id='autoload-interval', interval=1000, max_intervals=1),
        dcc.Interval(id='optimization-interval', interval=500, disabled=True),

        # Keyboard shortcut listener
        html.Div(id='keyboard-listener', style={'display': 'none'}),

        # Header
        _create_header(styles, theme),

        # Main container
        html.Div([
            # Left Sidebar - Controls
            _create_sidebar(styles, theme),

            # Main Chart Area
            _create_chart_area(styles, theme),

            # Right Panel - Backtest & Results
            _create_right_panel(styles, theme),

        ], style=styles['main_container']),

        # Hidden elements
        html.Div(id='hidden-output', style={'display': 'none'}),

    ], style=styles['app'], id='app-container')


def _create_header(styles: dict, theme: dict) -> html.Header:
    """Create the dashboard header."""
    return html.Header([
        html.Div([
            html.Div("S", style=styles['logo_icon']),
            html.Span("SearchForAlpha", style=styles['logo_text']),
        ], style=styles['logo']),

        html.Div([
            # Theme toggle
            html.Button(
                id='theme-toggle',
                children=[html.Span("\u2600\ufe0f", id='theme-label')],
                style={**styles['button_outline'], 'fontSize': '16px', 'padding': '6px 12px'},
                n_clicks=0
            ),
            dbc.Tooltip("Toggle light/dark theme", target='theme-toggle', placement='bottom'),
            # Current time/status
            html.Div(id='header-status', style={
                'fontSize': FONT_SIZES['sm'],
                'color': theme['text_secondary'],
                'fontFamily': FONT_MONO,
            }),
        ], style=styles['header_controls']),
    ], style=styles['header'])


def _create_sidebar(styles: dict, theme: dict) -> html.Aside:
    """Create the left sidebar with controls."""
    return html.Aside([
        # Data Input Section
        html.Div([
            html.Div("MARKET DATA", style=styles['sidebar_title']),

            html.Div([
                html.Label("Symbol", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '4px', 'display': 'block'}),
                dcc.Dropdown(
                    id='ticker-dropdown',
                    value=DEFAULT_TICKER,
                    placeholder="Type to search...",
                    style={'fontSize': FONT_SIZES['sm']},
                    className='dark-dropdown',
                    searchable=True,
                    search_value='',
                ),
            ], style={'marginBottom': '12px'}),

            html.Div([
                html.Div([
                    html.Label("Start Date", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '4px', 'display': 'block'}),
                    dcc.DatePickerSingle(
                        id='start-date',
                        date=date.fromisoformat(START_DATE),
                        display_format='YYYY-MM-DD',
                        style={'width': '100%'}
                    ),
                ], style={'flex': 1}),
                html.Div([
                    html.Label("End Date", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '4px', 'display': 'block'}),
                    dcc.DatePickerSingle(
                        id='end-date',
                        date=date.today(),
                        display_format='YYYY-MM-DD',
                        style={'width': '100%'}
                    ),
                ], style={'flex': 1}),
            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '12px'}),

            html.Div([
                html.Label("Initial Capital", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '4px', 'display': 'block'}),
                dcc.Input(
                    id='initial-capital',
                    type='number',
                    value=INITIAL_CAPITAL,
                    style={**styles['input'], 'fontFamily': FONT_MONO}
                ),
            ], style={'marginBottom': '12px'}),

            html.Button(
                [html.Span("Load Data"), html.Span(" \u2318\u21b5", style={'opacity': '0.5', 'marginLeft': '8px', 'fontSize': '10px'})],
                id='load-data-button',
                style={**styles['button_primary'], 'width': '100%'},
                n_clicks=0
            ),
            dbc.Tooltip("Fetch market data and calculate indicators (Ctrl+Enter)", target='load-data-button', placement='right'),

            dcc.Loading(
                id='loading-data',
                type='dot',
                color=theme['accent_blue'],
                children=[html.Div(id='data-status', style={'marginTop': '8px', 'fontSize': FONT_SIZES['xs']})]
            ),
        ], style=styles['sidebar_section']),

        # Chart Settings Section
        html.Div([
            html.Div("CHART SETTINGS", style=styles['sidebar_title']),

            html.Div([
                html.Label("Indicators", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '8px', 'display': 'block'}),
                dcc.Checklist(
                    id='plot-checklist',
                    options=[{'label': html.Span(label, style={'marginLeft': '8px', 'fontSize': FONT_SIZES['sm']}), 'value': value}
                            for label, value in PLOT_OPTIONS],
                    value=['candlestick', 'volume'],
                    style={'display': 'flex', 'flexDirection': 'column', 'gap': '4px'},
                    inputStyle={'cursor': 'pointer'},
                    labelStyle={'display': 'flex', 'alignItems': 'center', 'padding': '4px 0', 'cursor': 'pointer'}
                ),
            ], style={'marginBottom': '16px'}),

            html.Div([
                html.Label("Overlays", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '8px', 'display': 'block'}),
                dcc.Checklist(
                    id='chart-elements-checklist',
                    options=[{'label': html.Span(label, style={'marginLeft': '8px', 'fontSize': FONT_SIZES['sm']}), 'value': value}
                            for label, value in CHART_ELEMENT_OPTIONS],
                    value=['candlesticks', 'signals'],
                    style={'display': 'flex', 'flexDirection': 'column', 'gap': '4px'},
                    inputStyle={'cursor': 'pointer'},
                    labelStyle={'display': 'flex', 'alignItems': 'center', 'padding': '4px 0', 'cursor': 'pointer'}
                ),
            ], style={'marginBottom': '16px'}),

            html.Div([
                html.Label("Signals", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '8px', 'display': 'block'}),
                dcc.Checklist(
                    id='signal-checklist',
                    options=[{'label': html.Span(label, style={'marginLeft': '8px', 'fontSize': FONT_SIZES['sm']}), 'value': value}
                            for label, value in SIGNAL_OPTIONS],
                    value=['buy', 'sell'],
                    style={'display': 'flex', 'gap': '16px'},
                    inputStyle={'cursor': 'pointer'},
                    labelStyle={'display': 'flex', 'alignItems': 'center', 'cursor': 'pointer'}
                ),
            ]),
        ], style={**styles['sidebar_section'], 'flex': 1, 'overflowY': 'auto'}),
    ], style=styles['sidebar'])


def _create_chart_area(styles: dict, theme: dict) -> html.Main:
    """Create the main chart area."""
    return html.Main([
        # Chart Toolbar
        html.Div([
            html.Div([
                html.H2(id='chart-title', children="Select a symbol to begin", style={
                    'fontSize': FONT_SIZES['lg'],
                    'fontWeight': '600',
                    'color': theme['text_primary'],
                    'margin': 0,
                }),
                html.Span(id='chart-subtitle', style={
                    'fontSize': FONT_SIZES['sm'],
                    'color': theme['text_secondary'],
                    'marginLeft': '12px',
                }),
            ], style={'display': 'flex', 'alignItems': 'baseline'}),

            html.Div([
                html.Button("Export CSV", id='export-csv-btn', style=styles['button_outline'], n_clicks=0),
                html.Button("Export Image", id='export-img-btn', style=styles['button_outline'], n_clicks=0),
            ], style={'display': 'flex', 'gap': '8px'}),
        ], style=styles['chart_toolbar']),

        # Chart - resizable container
        html.Div([
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
            )
        ], style={
            **styles['chart_area'],
            'height': 'calc(100vh - 56px - 60px)',
            'minHeight': '400px',
            'resize': 'vertical',
            'overflow': 'auto',
        }, className='resizable-chart'),
    ], style=styles['chart_container'])


def _create_right_panel(styles: dict, theme: dict) -> html.Aside:
    """Create the right panel with backtest controls and results."""
    return html.Aside([
        # Tabs
        html.Div([
            html.Button("Backtest", id='tab-backtest', n_clicks=0,
                       style={**styles['tab'], **styles['tab_active']}, className='panel-tab active'),
            html.Button("Optimizer", id='tab-optimizer', n_clicks=0,
                       style=styles['tab'], className='panel-tab'),
            html.Button("Data", id='tab-data', n_clicks=0,
                       style=styles['tab'], className='panel-tab'),
        ], style=styles['tab_container']),

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


def _create_backtest_panel(styles: dict, _theme: dict) -> html.Div:
    """Create the backtest panel content."""
    return html.Div(id='panel-backtest', children=[
        # Strategy Mode Selector
        html.Div([
            html.Div("STRATEGY MODE", style={**styles['sidebar_title'], 'marginBottom': '8px'}),
            dcc.Dropdown(
                id='strategy-mode',
                options=[
                    {'label': 'Trading (Buy/Sell Cycles)', 'value': 'trading'},
                    {'label': 'Accumulation (DCA)', 'value': 'accumulation'},
                    {'label': 'Rebalancing (Partial)', 'value': 'rebalancing'}
                ],
                value='trading',
                clearable=False,
                style={'fontSize': FONT_SIZES['xs']}
            ),
        ], style={'marginBottom': '16px'}),

        # Amount Per Buy (for Accumulation mode)
        html.Div(id='accumulation-options', children=[
            html.Div("AMOUNT PER BUY ($)", style={**styles['sidebar_title'], 'marginBottom': '8px'}),
            dcc.Input(
                id='amount-per-buy',
                type='number',
                value=1000,
                min=100,
                placeholder='$ per buy signal',
                style={**styles['input'], 'width': '100%', 'fontFamily': FONT_MONO}
            ),
        ], style={'marginBottom': '16px', 'display': 'none'}),

        # Position Size % (for Rebalancing mode)
        html.Div(id='rebalancing-options', children=[
            html.Div("POSITION SIZE (%)", style={**styles['sidebar_title'], 'marginBottom': '8px'}),
            dcc.Input(
                id='position-size-pct',
                type='number',
                value=25,
                min=1,
                max=100,
                placeholder='% per trade',
                style={**styles['input'], 'width': '100%', 'fontFamily': FONT_MONO}
            ),
        ], style={'marginBottom': '16px', 'display': 'none'}),

        html.Div([
            html.Div("BUY SIGNALS", style={**styles['sidebar_title'], 'marginBottom': '8px'}),
            dcc.Checklist(
                id='buy-signals',
                options=[],
                value=[],
                style={'display': 'flex', 'flexDirection': 'column', 'gap': '2px', 'maxHeight': '120px', 'overflowY': 'auto'},
                inputStyle={'cursor': 'pointer'},
                labelStyle={'display': 'flex', 'alignItems': 'center', 'fontSize': FONT_SIZES['xs'], 'padding': '2px 0', 'cursor': 'pointer'}
            ),
        ], style={'marginBottom': '16px'}),

        html.Div([
            html.Div("SELL SIGNALS", style={**styles['sidebar_title'], 'marginBottom': '8px'}),
            dcc.Checklist(
                id='sell-signals',
                options=[],
                value=[],
                style={'display': 'flex', 'flexDirection': 'column', 'gap': '2px', 'maxHeight': '120px', 'overflowY': 'auto'},
                inputStyle={'cursor': 'pointer'},
                labelStyle={'display': 'flex', 'alignItems': 'center', 'fontSize': FONT_SIZES['xs'], 'padding': '2px 0', 'cursor': 'pointer'}
            ),
        ], style={'marginBottom': '16px'}),

        html.Button(
            "Run Backtest",
            id='run-backtest-btn',
            style={**styles['button_success'], 'width': '100%'},
            n_clicks=0
        ),
        dbc.Tooltip("Simulate trading with selected buy/sell signals", target='run-backtest-btn', placement='top'),

        html.Div(id='backtest-results', style={'marginTop': '16px'}),
    ])


def _create_optimizer_panel(styles: dict, theme: dict) -> html.Div:
    """Create the optimizer panel content."""
    return html.Div(id='panel-optimizer', children=[
        html.Div([
            html.Label("Max Signals per Side", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '8px', 'display': 'block'}),
            dcc.Slider(
                id='max-signals-slider',
                min=1, max=5, value=2, step=1,
                marks={i: {'label': str(i), 'style': {'color': theme['text_secondary']}} for i in range(1, 6)},
            ),
        ], style={'marginBottom': '20px'}),

        html.Div([
            html.Label("Max Combinations", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '4px', 'display': 'block'}),
            dcc.Input(
                id='max-combos-input',
                type='number',
                value=100,
                min=10, max=1000,
                style={**styles['input'], 'fontFamily': FONT_MONO}
            ),
        ], style={'marginBottom': '16px'}),

        html.Button(
            "Run Optimization",
            id='run-optimization-btn',
            style={**styles['button_primary'], 'width': '100%', 'backgroundColor': theme['accent_orange']},
            n_clicks=0
        ),
        dbc.Tooltip("Test all signal combinations to find the best strategy", target='run-optimization-btn', placement='top'),

        # Progress indicator for optimization
        html.Div(id='optimization-progress', style={'marginTop': '12px'}),

        dcc.Loading(
            type='dot',
            color=theme['accent_orange'],
            children=[html.Div(id='optimization-results', style={'marginTop': '16px'})]
        ),
    ], style={'display': 'none'})


def find_available_port(start_port: int = START_PORT, max_tries: int = MAX_PORT_TRIES) -> int:
    """Find an available port."""
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    raise RuntimeError("No available ports found")


def run_dashboard():
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

    # Start server
    def open_browser():
        webbrowser.open_new(f"http://127.0.0.1:{port}/")

    port = find_available_port()
    Timer(1, open_browser).start()
    logger.info(f"Starting dashboard on port {port}")
    app.run(debug=False, use_reloader=False, port=port)


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
