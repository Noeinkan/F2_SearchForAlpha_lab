"""
Integrated Trading Dashboard Module

A Dash-based interactive dashboard for trading strategy visualization and backtesting.
Consolidates all notebook functionality into a single application.

Includes chart utilities (formerly chart_utils.py) for creating Plotly charts.
"""

import logging
import dash
from dash import dcc, html, dash_table
from dash.dependencies import Input, Output, State
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import date
import yfinance as yf
from threading import Timer
import socket
from typing import Dict, Any, Tuple, List, Optional
from dash.exceptions import PreventUpdate
import webbrowser
import sys
import os
from datetime import datetime
import dash_bootstrap_components as dbc
from functools import lru_cache
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np

# Configure logging
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from lib.strategy import backtest, run_backtest, percentage_of_portfolio
from lib.weights_optimization import walk_forward_optimisation
from lib.data_processing import get_all_tickers, create_backtest_results
from lib.signals.indicators import add_indicators, generate_signals
from lib.dash.dash_config import (
    TEXT_COLOR, BACKGROUND_COLOR, CHART_BACKGROUND_COLOR, BORDER_COLOR,
    CHART_HEIGHT, MAIN_CONTENT_WIDTH, SIDEBAR_WIDTH,
    SIGNAL_OPTIONS, PLOT_OPTIONS, CHART_ELEMENT_OPTIONS,
    DEFAULT_TICKER, INITIAL_CAPITAL, START_DATE,
    OPTIMIZATION_METHODS, OPTIMIZATION_DELAY,
    START_PORT, MAX_PORT_TRIES
)
from lib.utils import export_priceaction_to_excel
from lib.params_optimization import optimize_parameters, calculate_metric


# =============================================================================
# Chart Constants
# =============================================================================

CHART_ORDER = ['candlestick', 'volume', 'rsi', 'cci', 'macd', 'adx', 'atr', 'obv']

LEGEND_CONTAINER_STYLE = {
    'display': 'flex',
    'flexDirection': 'row',
    'flexWrap': 'wrap',
    'justifyContent': 'flex-start',
    'alignItems': 'center',
    'gap': '8px',
    'padding': '8px',
    'border': '1px solid #ddd',
    'borderRadius': '5px',
    'backgroundColor': '#f9f9f9',
    'maxHeight': '150px',
    'overflowY': 'auto',
    'overflowX': 'auto'
}


# =============================================================================
# Chart Creation Functions (integrated from chart_utils.py)
# =============================================================================

def create_chart(df: pd.DataFrame, config: Dict) -> go.Figure:
    """Create a multi-panel financial chart with configurable plots."""
    try:
        # Always include candlestick if it's in the config plots
        selected_plots = config['selected_plots']
        if 'candlestick' in selected_plots:
            selected_plots.remove('candlestick')
            plot_sequence = ['candlestick'] + selected_plots
        else:
            plot_sequence = selected_plots

        plot_count = len(plot_sequence)
        row_heights = [4.5 if plot == 'candlestick' else 1 for plot in plot_sequence]
        subplot_titles = [p.replace('_', ' ').title() for p in plot_sequence]

        fig = make_subplots(rows=plot_count, cols=1, shared_xaxes=True, vertical_spacing=0.02,
                            row_heights=row_heights, subplot_titles=subplot_titles)

        plot_functions = {
            'candlestick': _add_candlestick,
            'volume': _add_volume_chart,
            'rsi': _add_rsi,
            'cci': _add_cci,
            'macd': _add_macd,
            'adx': _add_adx,
            'atr': _add_atr,
            'obv': _add_obv
        }

        for row, plot in enumerate(plot_sequence, start=1):
            plot_functions[plot](fig, df, row, 1, config)

        _add_range_selector(fig, df, plot_count)
        _update_layout(fig, plot_count, row_heights, config['show_legend'], config)
        _add_vertical_line(fig, plot_count)

        return fig
    
    except Exception as e:
        logger.error(f"Error creating chart: {e}")
        raise


def _add_candlestick(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    """Add candlestick chart with optional overlays (Bollinger Bands, SMA, EMA)."""
    if config['show_candlesticks']:
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            name="Price", increasing_line_color='#26A69A', decreasing_line_color='#EF5350',
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>Open: %{open:.2f}<br>High: %{high:.2f}<br>Low: %{low:.2f}<br>Close: %{close:.2f}<extra></extra>'
        ), row=row, col=col)

    if config['show_bollinger']:
        for band, color in [('upper', '#2E7D32'), ('lower', '#C62828'), ('middle', '#9E9E9E')]:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[f'BB_{band}'], name=f"{band.capitalize()} BB", 
                line=dict(color=color, width=2)
            ), row=row, col=col)

    if config['show_sma']:
        for period, color in [('short', 'red'), ('medium', 'green'), ('long', 'blue'), ('trend', 'purple')]:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[f'SMA_{period}'], name=f"{period.capitalize()} SMA", 
                line=dict(color=color, width=2)
            ), row=row, col=col)

    if config['show_ema']:
        for period, color in [('short', 'orange'), ('medium', 'brown'), ('long', 'pink')]:
            fig.add_trace(go.Scatter(
                x=df.index, y=df[f'EMA_{period}'], name=f"{period.capitalize()} EMA", 
                line=dict(color=color, width=2)
            ), row=row, col=col)

    if config['show_buy_sell_signals']:
        _add_signal_traces(fig, df, config['selected_signals'], row, col)


def _add_volume_chart(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    """Add volume bar chart with color coding based on price direction."""
    colors = ['green' if close > open else 'red' for close, open in zip(df['Close'], df['Open'])]
    fig.add_trace(go.Bar(
        x=df.index, y=df['Volume'], name="Volume", marker=dict(color=colors), opacity=0.7,
        hovertemplate='%{x|%Y-%m-%d}<br>Volume: %{y:,.0f}<extra></extra>'
    ), row=row, col=col)


def _add_rsi(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    """Add RSI indicator panel with overbought/oversold thresholds."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['RSI'], name="RSI", line=dict(color='orange', width=2),
        hovertemplate='%{x|%Y-%m-%d}<br>RSI: %{y:.2f}<extra></extra>'
    ), row=row, col=col)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=row, col=col)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=row, col=col)


def _add_cci(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    """Add CCI indicator panel with threshold lines."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['CCI'], name="CCI", line=dict(color='purple', width=2),
        hovertemplate='%{x|%Y-%m-%d}<br>CCI: %{y:.2f}<extra></extra>'
    ), row=row, col=col)
    fig.add_hline(y=100, line_dash="dash", line_color="red", row=row, col=col)
    fig.add_hline(y=-100, line_dash="dash", line_color="green", row=row, col=col)


def _add_macd(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    """Add MACD indicator panel with signal line and histogram."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MACD'], name="MACD", line=dict(color='blue', width=2),
        hovertemplate='%{x|%Y-%m-%d}<br>MACD: %{y:.4f}<extra></extra>'
    ), row=row, col=col)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MACD_Signal'], name="Signal", line=dict(color='orange', width=2),
        hovertemplate='%{x|%Y-%m-%d}<br>Signal: %{y:.4f}<extra></extra>'
    ), row=row, col=col)
    histogram_colors = np.where(df['MACD_Histogram'] >= 0, '#26A69A', '#EF5350')
    fig.add_bar(
        x=df.index, y=df['MACD_Histogram'], name="Histogram", marker_color=histogram_colors,
        hovertemplate='%{x|%Y-%m-%d}<br>Histogram: %{y:.4f}<extra></extra>',
        row=row, col=col
    )


def _add_adx(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    """Add ADX indicator panel with trend strength threshold."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['ADX'], name="ADX", line=dict(color='brown', width=2),
        hovertemplate='%{x|%Y-%m-%d}<br>ADX: %{y:.2f}<extra></extra>'
    ), row=row, col=col)
    fig.add_hline(y=25, line_dash="dash", line_color="gray", row=row, col=col)


def _add_atr(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    """Add ATR indicator panel."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['ATR'], name="ATR", line=dict(color='teal', width=2),
        hovertemplate='%{x|%Y-%m-%d}<br>ATR: %{y:.2f}<extra></extra>'
    ), row=row, col=col)


def _add_obv(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    """Add OBV indicator panel."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['OBV'], name="OBV", line=dict(color='magenta', width=2),
        hovertemplate='%{x|%Y-%m-%d}<br>OBV: %{y:,.0f}<extra></extra>'
    ), row=row, col=col)


def _add_signal_traces(fig: go.Figure, df: pd.DataFrame, selected_signals: List[str], row: int, col: int) -> None:
    """Add buy/sell signal markers to the chart."""
    signal_configs = {
        'buy': {'color': 'green', 'symbol': 'triangle-up', 'offset': -1},
        'sell': {'color': 'red', 'symbol': 'triangle-down', 'offset': 1}
    }

    for signal_type in selected_signals:
        config = signal_configs[signal_type]
        signals = df[df[f'{signal_type.capitalize()}_Position'] == 1]
        offset = signals['Close'] * 0.01 * config['offset']
        fig.add_trace(go.Scatter(
            x=signals.index,
            y=signals['Close'] + offset,
            mode='markers',
            marker=dict(symbol=config['symbol'], size=10, color=config['color']),
            name=f'{signal_type.capitalize()} Signal'
        ), row=row, col=col)


def _add_range_selector(fig: go.Figure, df: pd.DataFrame, plot_count: int) -> None:
    """Add time range selector buttons to the chart."""
    fig.update_layout(
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1m", step="month", stepmode="backward"),
                    dict(count=6, label="6m", step="month", stepmode="backward"),
                    dict(count=1, label="YTD", step="year", stepmode="todate"),
                    dict(count=1, label="1y", step="year", stepmode="backward"),
                    dict(step="all")
                ])
            ),
            rangeslider=dict(visible=False),
            type="date"
        )
    )


def _update_layout(fig: go.Figure, plot_count: int, row_heights: List[int], show_legend: bool, config: Dict = None) -> None:
    """Update the figure layout with dark theme and responsive sizing."""
    title_text = config.get('title', 'Stock Price Chart') if config else 'Stock Price Chart'
    
    layout_kwargs = dict(
        template='plotly_dark',
        autosize=True,
        showlegend=show_legend,
        plot_bgcolor='#131722',
        paper_bgcolor='#131722',
        margin=dict(l=40, r=40, t=50, b=30),
        font=dict(color='#D3D3D3'),
        title=dict(text=title_text, x=0.5, xanchor='center', font=dict(size=18))
    )
    
    if show_legend:
        layout_kwargs['legend'] = dict(orientation="h", yanchor="bottom", y=1.02, xanchor="right", x=1)
    
    fig.update_layout(**layout_kwargs)
    for i in range(1, plot_count+1):
        fig.update_xaxes(
            rangeslider_visible=False,
            showgrid=True,
            gridcolor='rgba(211, 211, 211, 0.15)',
            row=i, col=1,
            rangeslider_thickness=0.05,
            tickfont=dict(color='#D3D3D3')
        )
        fig.update_yaxes(
            showgrid=True,
            gridcolor='rgba(211, 211, 211, 0.15)',
            row=i, col=1,
            tickfont=dict(color='#D3D3D3')
        )
        if i < plot_count:
            fig.update_xaxes(showticklabels=False, row=i, col=1)
    
    fig.update_xaxes(matches='x')


def _add_vertical_line(fig: go.Figure, plot_count: int) -> None:
    """Add crosshair functionality for hovering."""
    fig.update_layout(
        hovermode="x unified",
        hoverdistance=100,
        spikedistance=1000,
    )
    for i in range(1, plot_count + 1):
        fig.update_xaxes(
            showspikes=True, spikecolor="grey", spikethickness=1,
            spikemode="across", spikesnap="cursor",
            showline=True, showgrid=True, row=i, col=1
        )
        fig.update_yaxes(
            showspikes=True, spikecolor="grey", spikethickness=1,
            spikemode="across", showline=True, showgrid=True, row=i, col=1
        )


def create_legend_div(fig: go.Figure) -> html.Div:
    """Create a custom legend div from figure traces."""
    legend_items = []
    for trace in fig.data:
        if trace.showlegend:
            color, name = _get_trace_color_and_name(trace)
            if color and name:
                legend_items.append(_create_legend_item(color, name))
    
    return html.Div(legend_items, style=LEGEND_CONTAINER_STYLE)


def _get_trace_color_and_name(trace: go.Trace) -> Tuple[str, str]:
    """Extract color and name from a Plotly trace."""
    if isinstance(trace, go.Candlestick):
        return 'green', "Candlestick"
    elif isinstance(trace, go.Bar):
        color = trace.marker.color[0] if isinstance(trace.marker.color, list) else trace.marker.color
        return color, trace.name
    elif hasattr(trace, 'line') and hasattr(trace.line, 'color'):
        return trace.line.color, trace.name
    elif hasattr(trace, 'marker') and hasattr(trace.marker, 'color'):
        return trace.marker.color, trace.name
    return None, None


def _create_legend_item(color: str, name: str) -> html.Div:
    """Create a single legend item div."""
    return html.Div([
        html.Div(style={'width': '16px', 'height': '3px', 'backgroundColor': color, 'display': 'inline-block', 'marginRight': '4px', 'verticalAlign': 'middle'}),
        html.Span(name, style={'fontSize': '12px', 'whiteSpace': 'nowrap'})
    ], style={'display': 'inline-flex', 'alignItems': 'center', 'padding': '2px 4px'})


class DashboardState:
    """
    Encapsulates dashboard state to avoid global mutable variables.
    Thread-safe storage for dashboard data.
    """
    
    def __init__(self):
        self._df: Optional[pd.DataFrame] = None
        self._all_tickers_df: Optional[pd.DataFrame] = None
        self._backtest_results: Optional[Dict] = None
        self._data_cache: Dict[str, pd.DataFrame] = {}
    
    @property
    def df(self) -> Optional[pd.DataFrame]:
        return self._df
    
    @df.setter
    def df(self, value: pd.DataFrame) -> None:
        self._df = value
    
    @property
    def all_tickers_df(self) -> Optional[pd.DataFrame]:
        return self._all_tickers_df
    
    @all_tickers_df.setter
    def all_tickers_df(self, value: pd.DataFrame) -> None:
        self._all_tickers_df = value
    
    @property
    def backtest_results(self) -> Optional[Dict]:
        return self._backtest_results
    
    @backtest_results.setter
    def backtest_results(self, value: Dict) -> None:
        self._backtest_results = value
    
    def get_cached_data(self, key: str) -> Optional[pd.DataFrame]:
        """Get cached data by key."""
        return self._data_cache.get(key)
    
    def set_cached_data(self, key: str, data: pd.DataFrame) -> None:
        """Cache data with key."""
        self._data_cache[key] = data
    
    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._data_cache.clear()


# Create a single instance for state management
dashboard_state = DashboardState()


# =============================================================================
# Signal Combination Optimizer Functions (merged from notebooks)
# =============================================================================

def extract_signals(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """Extract buy and sell signals from DataFrame columns."""
    buy_signals = [col for col in df.columns if 'buy' in col.lower()]
    sell_signals = [col for col in df.columns if 'sell' in col.lower()]
    return buy_signals, sell_signals


def generate_signal_combinations(
    buy_signals: List[str], 
    sell_signals: List[str], 
    max_signals: int = 3
) -> List[Tuple[Tuple[str, ...], Tuple[str, ...]]]:
    """Generate combinations of buy and sell signals."""
    all_combinations = []
    for i in range(1, min(max_signals + 1, len(buy_signals) + 1)):
        for j in range(1, min(max_signals + 1, len(sell_signals) + 1)):
            buy_combos = list(itertools.combinations(buy_signals, i))
            sell_combos = list(itertools.combinations(sell_signals, j))
            all_combinations.extend(itertools.product(buy_combos, sell_combos))
    return all_combinations


def test_signal_combination(
    df: pd.DataFrame, 
    initial_capital: float,
    buy_combo: Tuple[str, ...], 
    sell_combo: Tuple[str, ...]
) -> Dict[str, Any]:
    """Test a single combination of buy and sell signals."""
    try:
        result_df = run_backtest(
            df=df,
            initial_capital=initial_capital,
            buy_indicators=list(buy_combo),
            sell_indicators=list(sell_combo)
        )
        
        final_value = result_df['Portfolio_Value'].iloc[-1]
        total_return = (final_value - initial_capital) / initial_capital * 100
        
        # Calculate metrics
        returns = result_df['Strategy_Returns'].dropna()
        sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0
        
        # Max drawdown
        cumulative = (1 + returns).cumprod()
        peak = cumulative.expanding().max()
        drawdown = ((cumulative - peak) / peak).min() * 100
        
        return {
            'Buy_Signals': ', '.join(buy_combo),
            'Sell_Signals': ', '.join(sell_combo),
            'Final_Value': final_value,
            'Total_Return_%': total_return,
            'Sharpe_Ratio': sharpe,
            'Max_Drawdown_%': drawdown,
            'Trades': result_df['Position'].diff().abs().sum() / 2
        }
    except Exception as e:
        logger.error(f"Error testing combination: {e}")
        return {
            'Buy_Signals': ', '.join(buy_combo),
            'Sell_Signals': ', '.join(sell_combo),
            'Error': str(e)
        }


def run_combo_optimization(
    df: pd.DataFrame,
    initial_capital: float,
    max_signals: int = 3,
    max_combinations: int = 100
) -> pd.DataFrame:
    """Run signal combination optimization and return results DataFrame."""
    buy_signals, sell_signals = extract_signals(df)
    combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
    combinations = combinations[:max_combinations]
    
    results = []
    for buy_combo, sell_combo in combinations:
        result = test_signal_combination(df, initial_capital, buy_combo, sell_combo)
        results.append(result)
    
    results_df = pd.DataFrame(results)
    if 'Total_Return_%' in results_df.columns:
        results_df = results_df.sort_values('Total_Return_%', ascending=False)
    return results_df


# =============================================================================
# Dashboard Helper Functions
# =============================================================================

def format_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Format DataFrame for display in the dashboard."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == 'float64':
            df[col] = df[col].round(2)
    return df


def fetch_data_with_cache(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    Fetch data with caching to avoid repeated API calls.
    
    Args:
        ticker: Stock ticker symbol.
        start_date: Start date for data.
        end_date: End date for data.
        
    Returns:
        DataFrame with OHLCV data.
        
    Raises:
        ValueError: If no data is available.
    """
    cache_key = f"{ticker}_{start_date}_{end_date}"
    cached = dashboard_state.get_cached_data(cache_key)
    
    if cached is not None:
        logger.info(f"Using cached data for {ticker}")
        return cached
    
    logger.info(f"Fetching data for {ticker} from {start_date} to {end_date}")
    try:
        df = yf.download(ticker, start=start_date, end=end_date)
        if df.empty:
            raise ValueError(f"No data available for {ticker}")
        
        # Handle multi-level columns from yfinance (single ticker returns MultiIndex)
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = df.columns.get_level_values(0)
        
        dashboard_state.set_cached_data(cache_key, df)
        return df
    except Exception as e:
        logger.error(f"Error fetching data for {ticker}: {e}")
        raise


def create_dash_app(df: pd.DataFrame, ticker: str, backtest_results: Dict) -> dash.Dash:
    app = dash.Dash(
        __name__, 
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}]
    )
    
    ticker = ticker or 'SPY'
    
    app.layout = html.Div([
        dbc.Tabs([
            dbc.Tab(label="Chart", children=[
                html.Div([
                    # Main chart area
                    html.Div([
                        html.H4(f"{ticker} Financial Dashboard", id='dashboard-title', 
                               style={'textAlign': 'center', 'color': TEXT_COLOR, 'padding': '10px'}),
                        html.Button('View as Spreadsheet', id='view-spreadsheet-button', n_clicks=0, 
                                   className='btn btn-outline-secondary mb-2', 
                                   style={'minHeight': '48px', 'padding': '12px 20px', 'fontSize': '14px'}),
                        dcc.Graph(id='financial-chart', style={'height': '75vh', 'width': '100%'}, config={'responsive': True})
                    ], style={'width': '100%', 'backgroundColor': BACKGROUND_COLOR}),
                    
                    # Controls sidebar - now below on small screens
                    html.Div([
                        dbc.Row([
                            dbc.Col([
                                html.Div([
                                    html.H5("Controls", style={'textAlign': 'center', 'color': TEXT_COLOR}),
                                    create_checklist('Buy/Sell Signals:', 'signal-checklist', SIGNAL_OPTIONS),
                                    create_checklist('Plots:', 'plot-checklist', PLOT_OPTIONS),
                                    create_checklist('Chart Elements:', 'chart-elements-checklist', CHART_ELEMENT_OPTIONS)
                                ], style={'padding': '10px', 'border': f'1px solid {BORDER_COLOR}', 'borderRadius': '5px', 
                                         'backgroundColor': CHART_BACKGROUND_COLOR})
                            ], xs=12, md=6, lg=4),
                            dbc.Col([
                                html.Div(id='legend-container', style={'overflowY': 'auto', 'maxHeight': '200px', 'color': TEXT_COLOR})
                            ], xs=12, md=6, lg=4),
                            dbc.Col([
                                create_backtest_results_div(backtest_results)
                            ], xs=12, lg=4)
                        ], className='g-2 p-2')
                    ], style={'backgroundColor': BACKGROUND_COLOR, 'color': TEXT_COLOR})
                ], style={'backgroundColor': BACKGROUND_COLOR})
            ]),
            dbc.Tab(label="Data Table", children=[
                html.Div([
                    html.H6(f"Full price and indicator data for {ticker}", 
                           className='text-muted mb-2 px-2 pt-2', style={'fontSize': '14px'}),
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
def create_checklist(label: str, id: str, options: List[Tuple[str, str]]) -> html.Fieldset:
    legend_id = f"{id}-legend"
    return html.Fieldset([
        html.Legend(label, id=legend_id, style={'color': TEXT_COLOR, 'fontSize': '14px', 'fontWeight': 'bold'}),
        dcc.Checklist(
            id=id,
            options=[{'label': html.Span(f" {opt_label}", style={'padding': '4px 8px', 'cursor': 'pointer'}), 'value': value} for opt_label, value in options],
            value=[value for _, value in options],
            inline=True,
            style={'color': TEXT_COLOR, 'padding': '10px 0'},
            inputStyle={'minWidth': '24px', 'minHeight': '24px', 'marginRight': '8px', 'cursor': 'pointer'},
            labelStyle={'display': 'inline-flex', 'alignItems': 'center', 'marginRight': '12px', 'marginBottom': '8px'}
        )
    ], style={'marginTop': '10px', 'border': 'none', 'padding': '0'}, role='group', **{'aria-labelledby': legend_id})

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
    app.run(debug=False, use_reloader=False, port=port)

def find_available_port(start_port: int = START_PORT, max_tries: int = MAX_PORT_TRIES) -> int:
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    raise RuntimeError("No available ports found")

def run_dashboard():
    app = dash.Dash(
        __name__, 
        external_stylesheets=[dbc.themes.BOOTSTRAP], 
        suppress_callback_exceptions=True,
        meta_tags=[{"name": "viewport", "content": "width=device-width, initial-scale=1"}]
    )

    # Shared data input controls
    def create_data_input_controls():
        return dbc.Card([
            dbc.CardBody([
                dbc.Row([
                    dbc.Col([
                        html.Label('Ticker:', htmlFor='ticker-dropdown', className='small mb-1 fw-semibold'),
                        dcc.Dropdown(id='ticker-dropdown', value=DEFAULT_TICKER, style={'fontSize': '14px', 'minHeight': '48px'})
                    ], xs=12, sm=6, md=4, lg=2),
                    dbc.Col([
                        html.Label('Capital:', htmlFor='initial-capital', className='small mb-1 fw-semibold'),
                        dcc.Input(id='initial-capital', type='number', value=INITIAL_CAPITAL, className='form-control', style={'minHeight': '48px', 'fontSize': '14px'})
                    ], xs=6, sm=6, md=4, lg=2),
                    dbc.Col([
                        html.Label('Start:', htmlFor='start-date', className='small mb-1 fw-semibold'),
                        dcc.DatePickerSingle(id='start-date', date=date.fromisoformat(START_DATE), style={'fontSize': '14px'}, className='w-100')
                    ], xs=6, sm=6, md=4, lg=2),
                    dbc.Col([
                        html.Label('End:', htmlFor='end-date', className='small mb-1 fw-semibold'),
                        dcc.DatePickerSingle(id='end-date', date=date.today(), style={'fontSize': '14px'}, className='w-100')
                    ], xs=6, sm=6, md=4, lg=2),
                    dbc.Col([
                        dbc.Button('Load Data', id='load-data-button', color='primary', size='lg', className='w-100 mt-2 mt-lg-3', style={'minHeight': '48px', 'fontWeight': '600'})
                    ], xs=12, sm=6, md=4, lg=4)
                ], className='g-3 align-items-end'),
                dcc.Loading(type='circle', children=[
                    html.Div(id='data-status', className='small text-muted mt-2', role='status', **{'aria-live': 'polite'})
                ])
            ], className='py-3 px-3')
        ], className='mb-2')

    app.layout = html.Div([
        dcc.Store(id='data-loaded-store', data=False),
        html.H5('SearchForAlpha - Trading Strategy Lab', className='text-center my-1'),
        
        # Shared data input at the top
        html.Div([create_data_input_controls()], className='px-2'),
        
        # Main tabbed interface
        dbc.Tabs([
            # Tab 1: Manual Backtest
            dbc.Tab(label="📊 Backtest", children=[
                dbc.Row([
                    dbc.Col([
                        dbc.Card([
                            dbc.CardBody([
                                html.Fieldset([
                                    html.Legend('Buy Signals:', id='buy-signals-legend', className='small fw-bold mb-2'),
                                    dcc.Checklist(
                                        id='buy-signals', 
                                        className='small', 
                                        style={'maxHeight': '140px', 'overflowY': 'auto', 'fontSize': '13px'},
                                        inputStyle={'minWidth': '24px', 'minHeight': '24px', 'marginRight': '8px', 'cursor': 'pointer'},
                                        labelStyle={'display': 'flex', 'alignItems': 'center', 'padding': '6px 0', 'cursor': 'pointer'}
                                    )
                                ], style={'border': 'none', 'padding': '0'}, role='group', **{'aria-labelledby': 'buy-signals-legend'}),
                                html.Fieldset([
                                    html.Legend('Sell Signals:', id='sell-signals-legend', className='small fw-bold mb-2 mt-3'),
                                    dcc.Checklist(
                                        id='sell-signals', 
                                        className='small', 
                                        style={'maxHeight': '140px', 'overflowY': 'auto', 'fontSize': '13px'},
                                        inputStyle={'minWidth': '24px', 'minHeight': '24px', 'marginRight': '8px', 'cursor': 'pointer'},
                                        labelStyle={'display': 'flex', 'alignItems': 'center', 'padding': '6px 0', 'cursor': 'pointer'}
                                    )
                                ], style={'border': 'none', 'padding': '0'}, role='group', **{'aria-labelledby': 'sell-signals-legend'}),
                                dbc.Button('Run Backtest', id='manual-submit-button', color='success', size='lg', className='w-100 mt-3', style={'minHeight': '48px', 'fontWeight': '600'})
                            ], className='p-3')
                        ])
                    ], xs=12, sm=12, md=5, lg=4),
                    dbc.Col([
                        dcc.Loading(type='circle', children=[
                            html.Div(id='backtest-results-container', role='region', **{'aria-live': 'polite', 'aria-label': 'Backtest results'})
                        ])
                    ], xs=12, sm=12, md=7, lg=8)
                ], className='g-3 px-2 mt-1')
            ]),
            
            # Tab 2: Signal Combination Optimizer
            dbc.Tab(label="🔍 Optimizer", children=[
                dbc.Card([
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Label('Max Signals:', htmlFor='max-signals-slider', className='small mb-1 fw-semibold'),
                                dcc.Slider(id='max-signals-slider', min=1, max=5, value=2, step=1,
                                          marks={i: {'label': str(i), 'style': {'fontSize': '14px'}} for i in range(1, 6)},
                                          className='mt-2')
                            ], xs=12, sm=12, md=5, lg=4),
                            dbc.Col([
                                html.Label('Max Combos:', htmlFor='max-combos-input', className='small mb-1 fw-semibold'),
                                dcc.Input(id='max-combos-input', type='number', value=100, 
                                         min=10, max=1000, className='form-control', style={'minHeight': '48px', 'fontSize': '14px'})
                            ], xs=6, sm=6, md=4, lg=4),
                            dbc.Col([
                                dbc.Button('Run Optimization', id='run-combo-opt-button', color='warning', size='lg', className='w-100 mt-2 mt-md-3', style={'minHeight': '48px', 'fontWeight': '600'})
                            ], xs=6, sm=6, md=3, lg=4)
                        ], className='g-3 align-items-end'),
                        dcc.Loading(id='combo-loading', type='circle', children=[
                            html.Div(id='combo-opt-results', className='mt-3', role='region', **{'aria-live': 'polite', 'aria-label': 'Optimization results'})
                        ])
                    ], className='p-3')
                ], className='mx-2 mt-1')
            ]),
            
            # Tab 3: Walk-Forward Optimization
            dbc.Tab(label="⚙️ Auto", children=[
                dbc.Card([
                    dbc.CardBody([
                        dbc.Row([
                            dbc.Col([
                                html.Label('Optimization Method:', htmlFor='optimization-method', className='small mb-1 fw-semibold'),
                                dcc.Dropdown(id='optimization-method', options=OPTIMIZATION_METHODS, value='walk_forward', style={'minHeight': '48px', 'fontSize': '14px'})
                            ], xs=12, sm=8, md=8, lg=8),
                            dbc.Col([
                                dbc.Button('Run Optimization', id='auto-optimize-button', color='info', size='lg', className='w-100 mt-2 mt-sm-3', style={'minHeight': '48px', 'fontWeight': '600'})
                            ], xs=12, sm=4, md=4, lg=4)
                        ], className='g-3 align-items-end'),
                        dcc.Loading(id='auto-opt-loading', type='circle', children=[
                            html.Div(id='auto-opt-results', className='mt-3', role='region', **{'aria-live': 'polite', 'aria-label': 'Auto optimization results'})
                        ])
                    ], className='p-3')
                ], className='mx-2 mt-1')
            ]),
            
            # Tab 4: Data Table
            dbc.Tab(label="📋 Data", children=[
                dcc.Loading(type='circle', children=[
                    html.Div(id='data-table-container', className='mt-1 px-1', style={'overflowX': 'auto'})
                ])
            ])
        ], className='px-1'),
        
        # Hidden stores for state
        html.Div(id='output-container', style={'display': 'none'}),
        dcc.Interval(id='startup-interval', interval=500, max_intervals=1)
    ], style={'height': '100vh', 'overflow': 'auto'})

    # Callback: Populate ticker dropdown on startup
    @app.callback(
        Output('ticker-dropdown', 'options'),
        [Input('startup-interval', 'n_intervals')]
    )
    def populate_ticker_dropdown(_):
        if dashboard_state.all_tickers_df is None:
            try:
                dashboard_state.all_tickers_df = get_all_tickers()
            except Exception as e:
                logger.error(f"Error fetching tickers: {e}")
                return [{'label': 'SPY - SPDR S&P 500 ETF', 'value': 'SPY'}]
        return [
            {'label': f"{row['Symbol']} - {row['Security']}", 'value': row['Symbol']} 
            for _, row in dashboard_state.all_tickers_df.iterrows()
        ]

    # Callback: Load data button
    @app.callback(
        [Output('data-status', 'children'),
         Output('data-loaded-store', 'data'),
         Output('buy-signals', 'options'),
         Output('sell-signals', 'options'),
         Output('data-table-container', 'children')],
        [Input('load-data-button', 'n_clicks')],
        [State('ticker-dropdown', 'value'),
         State('start-date', 'date'),
         State('end-date', 'date')]
    )
    def load_data(n_clicks, ticker, start_date, end_date):
        if not n_clicks:
            raise PreventUpdate
        
        try:
            df = fetch_data_with_cache(ticker, start_date, end_date)
            if df.empty:
                return 'No data available for selected ticker.', False, [], [], None
            
            df = add_indicators(df)
            df, _ = generate_signals(df)
            dashboard_state.df = df
            
            # Prepare signal options
            buy_options = [{'label': col, 'value': col} for col in df.columns if 'buy' in col.lower()]
            sell_options = [{'label': col, 'value': col} for col in df.columns if 'sell' in col.lower()]
            
            # Create data table with caption for accessibility
            display_df = format_df_for_display(df.tail(100)).reset_index()
            data_table = html.Div([
                html.H6(f"Recent price and indicator data for {ticker} (last 100 rows)", 
                       className='text-muted mb-2', style={'fontSize': '14px'}),
                dash_table.DataTable(
                    columns=[{"name": i, "id": i} for i in display_df.columns],
                    data=display_df.to_dict('records'),
                    style_table={'height': '500px', 'overflowY': 'auto'},
                    style_cell={'textAlign': 'left', 'padding': '10px', 'fontSize': '13px'},
                    style_header={'fontWeight': 'bold', 'backgroundColor': '#f8f9fa'},
                    page_size=50
                )
            ])
            
            status = f"✅ Loaded {len(df)} rows for {ticker} ({start_date} to {end_date})"
            logger.info(status)
            return status, True, buy_options, sell_options, data_table
            
        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return f"❌ Error: {str(e)}", False, [], [], None

    # Callback: Manual backtest
    @app.callback(
        Output('backtest-results-container', 'children'),
        [Input('manual-submit-button', 'n_clicks')],
        [State('ticker-dropdown', 'value'),
         State('initial-capital', 'value'),
         State('buy-signals', 'value'),
         State('sell-signals', 'value')]
    )
    def run_manual_backtest(n_clicks, ticker, initial_capital, buy_signals, sell_signals):
        if not n_clicks:
            raise PreventUpdate
        
        df = dashboard_state.df
        if df is None:
            return dbc.Alert("Please load data first!", color="warning")
        
        if not buy_signals or not sell_signals:
            return dbc.Alert("Please select at least one buy and one sell signal.", color="warning")
        
        try:
            results = run_backtest(df, initial_capital, buy_signals, sell_signals)
            backtest_results = create_backtest_results(
                results, ticker, initial_capital, buy_signals, sell_signals
            )
            dashboard_state.backtest_results = backtest_results
            
            # Open chart in new window
            plot_financial_chart_dash(results, ticker, backtest_results)
            
            return dbc.Alert([
                html.H5("Backtest Complete!"),
                html.P(f"Final Value: ${backtest_results['final_portfolio_value']:,.2f}"),
                html.P(f"Total Return: {backtest_results['total_return']:.2f}%"),
                html.P(f"Sharpe Ratio: {backtest_results['sharpe_ratio']:.2f}"),
                html.P("Chart opened in new window.")
            ], color="success")
            
        except Exception as e:
            logger.error(f"Backtest error: {e}")
            return dbc.Alert(f"Error: {str(e)}", color="danger")

    # Callback: Signal combination optimizer
    @app.callback(
        Output('combo-opt-results', 'children'),
        [Input('run-combo-opt-button', 'n_clicks')],
        [State('initial-capital', 'value'),
         State('max-signals-slider', 'value'),
         State('max-combos-input', 'value')]
    )
    def run_signal_combo_optimization(n_clicks, initial_capital, max_signals, max_combos):
        if not n_clicks:
            raise PreventUpdate
        
        df = dashboard_state.df
        if df is None:
            return dbc.Alert("Please load data first!", color="warning")
        
        try:
            results_df = run_combo_optimization(df, initial_capital, max_signals, max_combos)
            
            if results_df.empty:
                return dbc.Alert("No valid combinations found.", color="warning")
            
            # Format for display
            display_df = results_df.head(20).round(2)
            
            return html.Div([
                dbc.Alert(f"✅ Tested {len(results_df)} combinations. Top 20 shown below:", color="success"),
                dash_table.DataTable(
                    columns=[{"name": i, "id": i} for i in display_df.columns],
                    data=display_df.to_dict('records'),
                    style_table={'overflowX': 'auto'},
                    style_cell={'textAlign': 'left', 'padding': '8px'},
                    style_header={'fontWeight': 'bold', 'backgroundColor': '#f8f9fa'},
                    style_data_conditional=[
                        {'if': {'row_index': 0}, 'backgroundColor': '#d4edda', 'fontWeight': 'bold'}
                    ],
                    sort_action='native',
                    filter_action='native'
                )
            ])
            
        except Exception as e:
            logger.error(f"Combo optimization error: {e}")
            return dbc.Alert(f"Error: {str(e)}", color="danger")

    # Callback: Auto optimization
    @app.callback(
        Output('auto-opt-results', 'children'),
        [Input('auto-optimize-button', 'n_clicks')],
        [State('ticker-dropdown', 'value'),
         State('initial-capital', 'value'),
         State('optimization-method', 'value')]
    )
    def run_auto_optimization(n_clicks, ticker, initial_capital, opt_method):
        if not n_clicks:
            raise PreventUpdate
        
        df = dashboard_state.df
        if df is None:
            return dbc.Alert("Please load data first!", color="warning")
        
        try:
            if opt_method == 'walk_forward':
                optimized_params = walk_forward_optimisation(df)
                
                results = backtest(
                    df=df,
                    initial_capital=initial_capital,
                    buy_indicators=optimized_params['buy_indicators'],
                    sell_indicators=optimized_params['sell_indicators'],
                    delay=OPTIMIZATION_DELAY,
                    indicator_weights=optimized_params.get('indicator_weights')
                )
                
                backtest_results = create_backtest_results(
                    results, ticker, initial_capital,
                    optimized_params['buy_indicators'],
                    optimized_params['sell_indicators']
                )
                dashboard_state.backtest_results = backtest_results
                
                # Open chart
                plot_financial_chart_dash(results, ticker, backtest_results)
                
                return dbc.Alert([
                    html.H5("Optimization Complete!"),
                    html.P(f"Best Buy Signals: {', '.join(optimized_params['buy_indicators'])}"),
                    html.P(f"Best Sell Signals: {', '.join(optimized_params['sell_indicators'])}"),
                    html.P(f"Final Value: ${backtest_results['final_portfolio_value']:,.2f}"),
                    html.P(f"Total Return: {backtest_results['total_return']:.2f}%"),
                    html.P("Chart opened in new window.")
                ], color="success")
            else:
                return dbc.Alert("Selected optimization method not yet implemented.", color="info")
                
        except Exception as e:
            logger.error(f"Auto optimization error: {e}")
            return dbc.Alert(f"Error: {str(e)}", color="danger")

    def open_browser():
        webbrowser.open_new(f"http://127.0.0.1:{port}/")

    port = find_available_port()
    Timer(1, open_browser).start()
    app.run(debug=False, use_reloader=False, port=port)

if __name__ == '__main__':
    run_dashboard()