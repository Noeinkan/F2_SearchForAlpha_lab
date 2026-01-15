import plotly.graph_objs as go
from plotly.subplots import make_subplots
import pandas as pd
import numpy as np
from typing import Dict, List, Tuple
from dash import html

# Constants
CHART_ORDER = ['candlestick', 'volume', 'rsi', 'cci', 'macd', 'adx', 'atr', 'obv']

def create_chart(df: pd.DataFrame, config: Dict) -> go.Figure:
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
            'candlestick': add_candlestick,
            'volume': add_volume_chart,
            'rsi': add_rsi,
            'cci': add_cci,
            'macd': add_macd,
            'adx': add_adx,
            'atr': add_atr,
            'obv': add_obv
        }

        for row, plot in enumerate(plot_sequence, start=1):
            plot_functions[plot](fig, df, row, 1, config)

        add_range_selector(fig, df, plot_count)
        update_layout(fig, plot_count, row_heights, config['show_legend'], config)
        add_vertical_line(fig, plot_count)

        return fig
    
    except Exception as e:
        raise

def add_candlestick(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    if config['show_candlesticks']:
        fig.add_trace(go.Candlestick(
            x=df.index, open=df['Open'], high=df['High'], low=df['Low'], close=df['Close'],
            name="Price", increasing_line_color='#26A69A', decreasing_line_color='#EF5350'
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
        add_signal_traces(fig, df, config['selected_signals'], row, col)

def add_volume_chart(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    colors = ['green' if close > open else 'red' for close, open in zip(df['Close'], df['Open'])]
    fig.add_trace(go.Bar(
        x=df.index, y=df['Volume'], name="Volume", marker=dict(color=colors), opacity=0.7
    ), row=row, col=col)

def add_rsi(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    fig.add_trace(go.Scatter(x=df.index, y=df['RSI'], name="RSI", line=dict(color='orange', width=2)), row=row, col=col)
    fig.add_hline(y=70, line_dash="dash", line_color="red", row=row, col=col)
    fig.add_hline(y=30, line_dash="dash", line_color="green", row=row, col=col)

def add_cci(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    fig.add_trace(go.Scatter(x=df.index, y=df['CCI'], name="CCI", line=dict(color='purple', width=2)), row=row, col=col)
    fig.add_hline(y=100, line_dash="dash", line_color="red", row=row, col=col)
    fig.add_hline(y=-100, line_dash="dash", line_color="green", row=row, col=col)

def add_macd(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD'], name="MACD", line=dict(color='blue', width=2)), row=row, col=col)
    fig.add_trace(go.Scatter(x=df.index, y=df['MACD_Signal'], name="Signal", line=dict(color='orange', width=2)), row=row, col=col)
    histogram_colors = np.where(df['MACD_Histogram'] >= 0, '#26A69A', '#EF5350')
    fig.add_bar(x=df.index, y=df['MACD_Histogram'], name="Histogram", marker_color=histogram_colors, row=row, col=col)

def add_adx(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    fig.add_trace(go.Scatter(x=df.index, y=df['ADX'], name="ADX", line=dict(color='brown', width=2)), row=row, col=col)
    fig.add_hline(y=25, line_dash="dash", line_color="gray", row=row, col=col)

def add_atr(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    fig.add_trace(go.Scatter(x=df.index, y=df['ATR'], name="ATR", line=dict(color='teal', width=2)), row=row, col=col)

def add_obv(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict) -> None:
    fig.add_trace(go.Scatter(x=df.index, y=df['OBV'], name="OBV", line=dict(color='magenta', width=2)), row=row, col=col)

def add_signal_traces(fig: go.Figure, df: pd.DataFrame, selected_signals: List[str], row: int, col: int) -> None:
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

def add_range_selector(fig: go.Figure, df: pd.DataFrame, plot_count: int) -> None:
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

def update_layout(fig: go.Figure, plot_count: int, row_heights: List[int], show_legend: bool, config: Dict = None) -> None:
    total_height = sum(row_heights) * 120
    title_text = config.get('title', 'Stock Price Chart') if config else 'Stock Price Chart'
    
    layout_kwargs = dict(
        template='plotly_dark',
        height=total_height,
        showlegend=show_legend,
        plot_bgcolor='#131722',
        paper_bgcolor='#131722',
        margin=dict(l=50, r=50, t=50, b=30),
        font=dict(color='#D3D3D3'),
        title=dict(text=title_text, x=0.5, xanchor='center', font=dict(size=20))
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

def add_vertical_line(fig: go.Figure, plot_count: int) -> None:
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
    legend_items = []
    for trace in fig.data:
        if trace.showlegend:
            color, name = get_trace_color_and_name(trace)
            if color and name:
                legend_items.append(create_legend_item(color, name))
    
    return html.Div(legend_items, style=legend_container_style)

def get_trace_color_and_name(trace: go.Trace) -> Tuple[str, str]:
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

def create_legend_item(color: str, name: str) -> html.Div:
    return html.Div([
        html.Div(style={'width': '20px', 'height': '3px', 'backgroundColor': color, 'display': 'inline-block', 'marginRight': '5px'}),
        html.Span(name)
    ], style={'marginBottom': '5px'})

legend_container_style = {
    'display': 'flex',
    'flexDirection': 'column',
    'justifyContent': 'flex-start',
    'alignItems': 'flex-start',
    'padding': '10px',
    'border': '1px solid #ddd',
    'borderRadius': '5px',
    'backgroundColor': '#f9f9f9',
    'maxHeight': 'calc(100vh - 200px)',
    'overflowY': 'auto'
}