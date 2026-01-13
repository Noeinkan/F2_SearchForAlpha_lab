import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go
import pandas as pd
from datetime import date
import yfinance as yf
from threading import Timer
import socket
from typing import Dict, Any, Tuple, List
from dash.exceptions import PreventUpdate
import webbrowser
import sys
import os
from datetime import datetime
import dash_bootstrap_components as dbc

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from lib.strategy import backtest, run_backtest, percentage_of_portfolio
from lib.weights_optimasation import walk_forward_optimisation
from lib.data_processing import get_all_tickers, create_backtest_results
from lib.signals.indicators import add_indicators, generate_signals
from lib.dash.chart_utils import create_chart, create_legend_div
from lib.dash.dash_config import *  
from lib.utils import export_priceaction_to_excel

# Global variables
df = None
all_tickers_df = None
backtest_results = None

def format_df_for_display(df):
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == 'float64':
            df[col] = df[col].round(2)
    return df

def create_dash_app(df: pd.DataFrame, ticker: str, backtest_results: Dict) -> dash.Dash:
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
    
    ticker = ticker or 'SPY'
    
    app.layout = html.Div([
        dbc.Tabs([
            dbc.Tab(label="Chart", children=[
                html.Div([
                    html.Div([
                        html.H1(f"{ticker} Financial Dashboard", id='dashboard-title', style={'textAlign': 'center', 'color': TEXT_COLOR}),
                        html.Button('View as Spreadsheet', id='view-spreadsheet-button', n_clicks=0),
                        dcc.Graph(id='financial-chart', style={'height': CHART_HEIGHT})
                    ], style={'width': MAIN_CONTENT_WIDTH, 'float': 'left', 'overflowY': 'auto', 'height': '100vh', 'backgroundColor': BACKGROUND_COLOR}),
                    
                    html.Div([
                        html.Div([
                            html.H3("Controls", style={'textAlign': 'center', 'color': TEXT_COLOR}),
                            create_checklist('Show Buy/Sell Signals:', 'signal-checklist', SIGNAL_OPTIONS),
                            create_checklist('Select Plots to Display:', 'plot-checklist', PLOT_OPTIONS),
                            create_checklist('Show Chart Elements:', 'chart-elements-checklist', CHART_ELEMENT_OPTIONS)
                        ], style={'padding': '10px', 'border': f'1px solid {BORDER_COLOR}', 'borderRadius': '5px', 'backgroundColor': CHART_BACKGROUND_COLOR, 'marginBottom': '20px'}),
                        html.Div(id='legend-container', style={'overflowY': 'auto', 'maxHeight': '30vh', 'marginTop': '20px', 'color': TEXT_COLOR}),
                        create_backtest_results_div(backtest_results)
                    ], style={'width': SIDEBAR_WIDTH, 'float': 'right', 'position': 'fixed', 'right': '0', 'top': '0', 'height': '100vh', 'overflowY': 'auto', 'padding': '20px', 'boxSizing': 'border-box', 'backgroundColor': BACKGROUND_COLOR, 'color': TEXT_COLOR})
                ], style={'display': 'flex', 'backgroundColor': BACKGROUND_COLOR})
            ]),
            dbc.Tab(label="Data Table", children=[
                html.Div([
                    dash_table.DataTable(
                        id='data-table',
                        columns=[{"name": i, "id": i} for i in format_df_for_display(df).reset_index().columns],
                        data=format_df_for_display(df).reset_index().to_dict('records'),
                        style_table={
                            'height': 'calc(100vh - 130px)',
                            'overflowY': 'auto',
                            'overflowX': 'auto',
                            'border': f'1px solid {BORDER_COLOR}',
                        },
                        style_cell={
                            'minWidth': '100px',
                            'maxWidth': '300px',
                            'width': 'auto',
                            'overflow': 'hidden',
                            'textOverflow': 'ellipsis',
                            'padding': '10px',
                            'textAlign': 'left',
                            'backgroundColor': CHART_BACKGROUND_COLOR,
                            'color': TEXT_COLOR,
                            'border': f'1px solid {BORDER_COLOR}',
                            'height': '40px',
                        },
                        style_header={
                            'backgroundColor': BORDER_COLOR,
                            'color': TEXT_COLOR,
                            'fontWeight': 'bold',
                            'position': 'sticky',
                            'top': 0,
                            'zIndex': 1000,
                            'textAlign': 'center',
                            'height': 'auto',
                            'whiteSpace': 'normal',
                            'overflow': 'hidden',
                            'textOverflow': 'ellipsis',
                            'padding': '10px 5px',
                        },
                        style_data={
                            'whiteSpace': 'normal',
                            'height': 'auto',
                        },
                        fixed_rows={'headers': True},
                        page_action='none',
                        virtualization=True,
                        style_data_conditional=[
                            {
                                'if': {'row_index': 'odd'},
                                'backgroundColor': 'rgba(0, 0, 0, 0.05)'
                            }
                        ],
                        css=[{
                            'selector': '.dash-header',
                            'rule': 'text-align: center; padding: 5px !important;'
                        }],
                        style_cell_conditional=[
                            {'if': {'column_id': c}, 'textAlign': 'left'} for c in ['Date', 'Ticker']
                        ] + [
                            {'if': {'column_id': c}, 'textAlign': 'right'} for c in df.select_dtypes(include=['float64', 'int64']).columns
                        ],
                    )
                ], style={'height': 'calc(100vh - 130px)', 'width': '100%', 'padding': '20px'})
            ]),
        ], style={'height': '50px'}),
        html.Div(id='dummy-output', style={'display': 'none'})
    ], style={'height': '100vh', 'width': '100vw', 'margin': '0', 'padding': '0'})

    @app.callback(
        Output('financial-chart', 'figure'),
        [Input('signal-checklist', 'value'),
         Input('plot-checklist', 'value'),
         Input('chart-elements-checklist', 'value')]
    )
    def update_chart(selected_signals, selected_plots, chart_elements):
        config = {
            'selected_signals': selected_signals,
            'selected_plots': selected_plots,
            'show_candlesticks': 'candlesticks' in chart_elements,
            'show_bollinger': 'bollinger' in chart_elements,
            'show_sma': 'sma' in chart_elements,
            'show_ema': 'ema' in chart_elements,
            'show_buy_sell_signals': 'signals' in chart_elements,
            'show_legend': 'legend' in chart_elements
        }
        fig = create_chart(df, config)
        fig.update_layout(title=f"{ticker} Financial Chart")
        return fig

    @app.callback(
        Output('legend-container', 'children'),
        [Input('financial-chart', 'figure')]
    )
    def update_legend(figure):
        return create_legend_div(figure) if figure['layout']['showlegend'] else None

    @app.callback(
        Output('dummy-output', 'children'),
        [Input('view-spreadsheet-button', 'n_clicks')]
    )
    def view_as_spreadsheet(n_clicks):
        if n_clicks > 0:
            export_folder = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'export')
            os.makedirs(export_folder, exist_ok=True)
            file_path = export_priceaction_to_excel(ticker, df, 'spreadsheet_view', export_folder)
            webbrowser.open('file://' + os.path.realpath(file_path))
        return ''

    return app
def create_checklist(label: str, id: str, options: List[Tuple[str, str]]) -> html.Div:
    return html.Div([
        html.Label(label, style={'color': TEXT_COLOR}),
        dcc.Checklist(
            id=id,
            options=[{'label': label, 'value': value} for label, value in options],
            value=[value for _, value in options],
            inline=True,
            style={'color': TEXT_COLOR}
        )
    ], style={'marginTop': '10px'})

def create_backtest_results_div(backtest_results: Dict) -> html.Div:
    formatted_results = {
        'Initial Capital': f"${backtest_results['initial_capital']:,.2f}",
        'Final Portfolio Value': f"${backtest_results['final_portfolio_value']:,.2f}",
        'Total Return': f"{backtest_results['total_return']:.2f}%",
        'Market Return': f"{backtest_results['market_return']:.2f}%",
        'Max Drawdown': f"{backtest_results['max_drawdown']:.2f}%",
        'Sharpe Ratio': f"{backtest_results['sharpe_ratio']:.2f}",
        'Win Rate': f"{backtest_results['win_rate']:.2f}%",
        'Profit Factor': f"{backtest_results['profit_factor']:.2f}",
        'Avg Trade Duration': f"{backtest_results['avg_trade_duration']:.1f} days"
    }

    table_data = [{'Metric': k, 'Value': v} for k, v in formatted_results.items()]
    
    return html.Div([
        html.H3("Backtest Results", style={'textAlign': 'center', 'color': TEXT_COLOR, 'marginBottom': '20px'}),
        dash_table.DataTable(
            data=table_data,
            columns=[{'name': i, 'id': i} for i in ['Metric', 'Value']],
            style_cell={'textAlign': 'left', 'padding': '10px', 'backgroundColor': CHART_BACKGROUND_COLOR, 'color': TEXT_COLOR},
            style_header={'fontWeight': 'bold', 'backgroundColor': BORDER_COLOR},
            style_table={'overflowX': 'auto'}
        ),
        html.Div([
            html.P("Buy Strategy:", style={'fontWeight': 'bold', 'marginTop': '20px', 'color': TEXT_COLOR}),
            html.Ul([html.Li(signal, style={'color': TEXT_COLOR}) for signal in backtest_results['buy_strategy']]),
            html.P("Sell Strategy:", style={'fontWeight': 'bold', 'marginTop': '10px', 'color': TEXT_COLOR}),
            html.Ul([html.Li(signal, style={'color': TEXT_COLOR}) for signal in backtest_results['sell_strategy']])
        ])
    ], style={'padding': '20px', 'border': f'1px solid {BORDER_COLOR}', 'borderRadius': '5px', 'backgroundColor': CHART_BACKGROUND_COLOR, 'marginTop': '20px'})

def plot_financial_chart_dash(df: pd.DataFrame, ticker: str, backtest_results: Dict) -> None:
    app = create_dash_app(df, ticker, backtest_results)
    port = find_available_port()
    Timer(1, lambda: webbrowser.open_new(f"http://127.0.0.1:{port}/")).start()
    app.run_server(debug=False, use_reloader=False, port=port)

def find_available_port(start_port: int = START_PORT, max_tries: int = MAX_PORT_TRIES) -> int:
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    raise RuntimeError("No available ports found")

def run_dashboard():
    app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])

    app.layout = html.Div([
        dcc.Location(id='url', refresh=False),
        html.Div([
            html.H1('Trading Strategy Dashboard', className='mb-4'),
            html.Div(id='initial-input', children=[
                dbc.Row([
                    dbc.Col([
                        html.Label('Ticker:'),
                        dcc.Dropdown(id='ticker-dropdown', value=DEFAULT_TICKER)
                    ], width=6),
                    dbc.Col([
                        html.Label('Initial Capital:'),
                        dcc.Input(id='initial-capital', type='number', value=INITIAL_CAPITAL, className='form-control')
                    ], width=6)
                ], className='mb-3'),
                dbc.Row([
                    dbc.Col([
                        html.Label('Start Date:'),
                        dcc.DatePickerSingle(id='start-date', date=date.fromisoformat(START_DATE), className='form-control')
                    ], width=6),
                    dbc.Col([
                        html.Label('End Date:'),
                        dcc.DatePickerSingle(id='end-date', date=date.today(), className='form-control')
                    ], width=6)
                ], className='mb-3'),
                dbc.Button('Submit', id='submit-button', color='primary', className='mt-3')
            ], style={'display': 'block'}),
            html.Div(id='signal-selection', children=[
                html.H2('Select Signal Method', className='mb-3'),
                dcc.RadioItems(
                    id='signal-method',
                    options=[
                        {'label': 'Manual Selection', 'value': 'manual'},
                        {'label': 'Automatic Optimization', 'value': 'auto'}
                    ],
                    value='manual',
                    className='mb-3'
                ),
                dbc.Button('Next', id='method-next-button', color='primary')
            ], style={'display': 'none'}),
            html.Div(id='manual-selection', children=[
                html.H2('Manual Signal Selection', className='mb-3'),
                dbc.Row([
                    dbc.Col([
                        html.Label('Buy Signals:'),
                        dcc.Checklist(id='buy-signals', className='mb-3')
                    ], width=6),
                    dbc.Col([
                        html.Label('Sell Signals:'),
                        dcc.Checklist(id='sell-signals', className='mb-3')
                    ], width=6)
                ]),
                dbc.Button('Submit', id='manual-submit-button', color='primary')
            ], style={'display': 'none'}),
            html.Div(id='auto-optimization', children=[
                html.H2('Automatic Optimization', className='mb-3'),
                dcc.Dropdown(
                    id='optimization-method',
                    options=OPTIMIZATION_METHODS,
                    value='walk_forward',
                    className='mb-3'
                ),
                dbc.Button('Optimize', id='auto-optimize-button', color='primary')
            ], style={'display': 'none'}),
            html.Div(id='results-container', style={'display': 'none'}),
            html.Div(id='output-container', children='Enter values and press submit', className='mt-3')
        ], id='page-content', className='container mt-4')
    ])

    @app.callback(
        [Output('initial-input', 'style'),
         Output('signal-selection', 'style'),
         Output('manual-selection', 'style'),
         Output('auto-optimization', 'style'),
         Output('results-container', 'style')],
        [Input('url', 'pathname')]
    )
    def update_page_visibility(pathname):
        pages = ['/', '/signal-selection', '/manual-selection', '/auto-optimization', '/results']
        styles = [{'display': 'block' if pathname == page else 'none'} for page in pages]
        return styles

    @app.callback(
        [Output('url', 'pathname'),
         Output('output-container', 'children'),
         Output('buy-signals', 'options'),
         Output('sell-signals', 'options'),
         Output('results-container', 'children')],
        [Input('submit-button', 'n_clicks'),
         Input('method-next-button', 'n_clicks'),
         Input('manual-submit-button', 'n_clicks'),
         Input('auto-optimize-button', 'n_clicks')],
        [State('ticker-dropdown', 'value'),
         State('start-date', 'date'),
         State('end-date', 'date'),
         State('initial-capital', 'value'),
         State('signal-method', 'value'),
         State('buy-signals', 'value'),
         State('sell-signals', 'value'),
         State('optimization-method', 'value')]
    )
    def update_page(submit_n_clicks, method_n_clicks, manual_n_clicks, auto_n_clicks,
                    ticker, start_date, end_date, initial_capital, signal_method,
                    buy_signals, sell_signals, optimization_method):
        ctx = dash.callback_context
        if not ctx.triggered:
            raise PreventUpdate

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]
        params = locals()
        
        handlers = {
            'submit-button': handle_submit_button,
            'method-next-button': handle_method_next_button,
            'manual-submit-button': handle_manual_submit_button,
            'auto-optimize-button': handle_auto_optimize_button
        }
        
        handler = handlers.get(button_id)
        return handler(params) if handler else (dash.no_update,) * 5

    @app.callback(
        Output('ticker-dropdown', 'options'),
        [Input('url', 'pathname')]
    )
    def populate_ticker_dropdown(pathname):
        global all_tickers_df
        if pathname == '/':
            if all_tickers_df is None:
                all_tickers_df = get_all_tickers()
            return [{'label': row['Security'], 'value': row['Symbol']} for _, row in all_tickers_df.iterrows()]
        return []

    def open_browser():
        webbrowser.open_new(f"http://127.0.0.1:{port}/")

    port = find_available_port()
    Timer(1, open_browser).start()
    app.run_server(debug=False, use_reloader=False, port=port)

def handle_submit_button(params: Dict[str, Any]) -> Tuple[str, str, List, List, None]:
    global df
    ticker, start_date, end_date = params['ticker'], params['start_date'], params['end_date']
    
    df = yf.download(ticker, start=start_date, end=end_date)
    
    if df.empty:
        return '/', 'No data available for the selected ticker and date range.', [], [], None
    
    df = add_indicators(df)
    df, _ = generate_signals(df)
    
    return '/signal-selection', f'Data loaded for {ticker} from {start_date} to {end_date}', [], [], None

def handle_method_next_button(params: Dict[str, Any]) -> Tuple[str, str, List[Dict[str, str]], List[Dict[str, str]], None]:
    signal_method = params['signal_method']
    
    if signal_method == 'manual':
        buy_options = [{'label': col, 'value': col} for col in df.columns if 'buy' in col.lower()]
        sell_options = [{'label': col, 'value': col} for col in df.columns if 'sell' in col.lower()]
        return '/manual-selection', '', buy_options, sell_options, None
    else:
        return '/auto-optimization', '', [], [], None

def handle_manual_submit_button(params: Dict[str, Any]) -> Tuple[str, str, List, List, Any]:
    global backtest_results
    
    results = run_backtest(df, params['initial_capital'], params['buy_signals'], params['sell_signals'])
    backtest_results = create_backtest_results(results, params['ticker'], params['initial_capital'], params['buy_signals'], params['sell_signals'])
    
    plot_financial_chart_dash(results, params['ticker'], backtest_results)

    return '/results', '', [], [], html.Div("Results plotted in a new window")

def handle_auto_optimize_button(params: Dict[str, Any]) -> Tuple[str, str, List, List, Any]:
    global backtest_results
    
    if params['optimization_method'] == 'walk_forward':
        optimized_params = walk_forward_optimisation(df)
        
        results = backtest(
            df=df, 
            initial_capital=params['initial_capital'],
            buy_indicators=optimized_params['buy_indicators'],
            sell_indicators=optimized_params['sell_indicators'],
            delay=OPTIMIZATION_DELAY,
            indicator_weights=optimized_params.get('indicator_weights')
        )
        
        backtest_results = create_backtest_results(
            results, 
            params['ticker'], 
            params['initial_capital'], 
            optimized_params['buy_indicators'], 
            optimized_params['sell_indicators']
        )
        
        plot_financial_chart_dash(results, params['ticker'], backtest_results)

        return '/results', '', [], [], html.Div("Results plotted in a new window")
    
    raise PreventUpdate

if __name__ == '__main__':
    run_dashboard()