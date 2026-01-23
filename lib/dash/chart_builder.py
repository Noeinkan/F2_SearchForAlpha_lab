"""
Chart Builder Module
Professional financial chart creation with Plotly.
"""

import logging
from typing import Dict, List
import numpy as np
import pandas as pd
import plotly.graph_objs as go
from plotly.subplots import make_subplots

from lib.dash.dash_config import FONT_FAMILY

logger = logging.getLogger(__name__)

# Chart configuration constants
CHART_ORDER = ['candlestick', 'volume', 'rsi', 'cci', 'macd', 'adx', 'atr', 'obv']
CHART_ROW_HEIGHT_MAIN = 4.5
CHART_ROW_HEIGHT_INDICATOR = 1
SIGNAL_OFFSET_FACTOR = 0.015


def create_chart(df: pd.DataFrame, config: Dict, theme: dict) -> go.Figure:
    """
    Create a multi-panel financial chart with professional styling.

    Args:
        df: DataFrame with OHLCV data and indicators
        config: Chart configuration dict with keys:
            - selected_plots: List of plot types to include
            - show_candlesticks: Whether to show candlestick chart
            - show_bollinger: Whether to show Bollinger Bands
            - show_sma: Whether to show SMA lines
            - show_ema: Whether to show EMA lines
            - show_buy_sell_signals: Whether to show trading signals
            - show_legend: Whether to show legend
            - selected_signals: List of signal types ('buy', 'sell')
            - title: Optional chart title
        theme: Theme configuration dict

    Returns:
        Plotly Figure object
    """
    try:
        selected_plots = config['selected_plots'].copy()
        if 'candlestick' in selected_plots:
            selected_plots.remove('candlestick')
            plot_sequence = ['candlestick'] + selected_plots
        else:
            plot_sequence = selected_plots

        plot_count = len(plot_sequence)
        if plot_count == 0:
            return go.Figure()

        row_heights = [
            CHART_ROW_HEIGHT_MAIN if plot == 'candlestick' else CHART_ROW_HEIGHT_INDICATOR
            for plot in plot_sequence
        ]
        subplot_titles = [p.replace('_', ' ').upper() for p in plot_sequence]

        # Adjust vertical spacing based on number of plots
        vertical_spacing = 0.02 if plot_count <= 3 else 0.015

        fig = make_subplots(
            rows=plot_count, cols=1,
            shared_xaxes=True,
            vertical_spacing=vertical_spacing,
            row_heights=row_heights,
            subplot_titles=subplot_titles
        )

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
            if plot in plot_functions:
                plot_functions[plot](fig, df, row, 1, config, theme)

        _add_range_selector(fig, theme)
        _update_layout(fig, plot_count, config.get('show_legend', False), config, theme)
        _add_crosshair(fig, plot_count)


        # Set y-axis range for main candlestick chart based only on price data
        if not df.empty and all(col in df.columns for col in ['Low', 'High']):
            min_y = df['Low'].min()
            max_y = df['High'].max()
            y_margin = (max_y - min_y) * 0.02 if max_y > min_y else 1
            fig.update_yaxes(range=[min_y - y_margin, max_y + y_margin], fixedrange=False, row=1, col=1)

        return fig

    except Exception as e:
        logger.error(f"Error creating chart: {e}")
        raise


def _add_candlestick(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add candlestick chart with overlays."""
    if config.get('show_candlesticks', True):
        # Dynamically set candlestick width based on number of visible data points
        n_points = len(df)
        width = 0.7 if n_points < 30 else (0.5 if n_points < 100 else 0.3)
        fig.add_trace(go.Candlestick(
            x=df.index,
            open=df['Open'],
            high=df['High'],
            low=df['Low'],
            close=df['Close'],
            name="Price",
            increasing_line_color=theme['chart_candle_up'],
            decreasing_line_color=theme['chart_candle_down'],
            increasing_fillcolor=theme['chart_candle_up'],
            decreasing_fillcolor=theme['chart_candle_down'],
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>O: %{open:.2f}<br>H: %{high:.2f}<br>L: %{low:.2f}<br>C: %{close:.2f}<extra></extra>',
            whiskerwidth=width
        ), row=row, col=col)

    if config.get('show_bollinger', False):
        bb_colors = [theme['accent_green'], theme['accent_red'], theme['text_secondary']]
        for (band, color) in zip(['upper', 'lower', 'middle'], bb_colors):
            if f'BB_{band}' in df.columns:
                fig.add_trace(go.Scatter(
                    x=df.index, y=df[f'BB_{band}'],
                    name=f"BB {band.upper()}",
                    line=dict(color=color, width=1, dash='dot'),
                    opacity=0.7
                ), row=row, col=col)

    if config.get('show_sma', False):
        sma_colors = [theme['accent_red'], theme['accent_green'], theme['accent_blue'], theme['accent_purple']]
        for i, period in enumerate(['short', 'medium', 'long', 'trend']):
            col_name = f'SMA_{period}'
            if col_name in df.columns:
                fig.add_trace(go.Scatter(
                    x=df.index, y=df[col_name],
                    name=f"SMA {period.upper()}",
                    line=dict(color=sma_colors[i], width=1.5)
                ), row=row, col=col)

    if config.get('show_ema', False):
        ema_colors = [theme['accent_orange'], theme['accent_cyan'], theme['accent_purple']]
        for i, period in enumerate(['short', 'medium', 'long']):
            col_name = f'EMA_{period}'
            if col_name in df.columns:
                fig.add_trace(go.Scatter(
                    x=df.index, y=df[col_name],
                    name=f"EMA {period.upper()}",
                    line=dict(color=ema_colors[i], width=1.5)
                ), row=row, col=col)

    if config.get('show_buy_sell_signals', False):
        _add_signal_traces(
            fig,
            df,
            config.get('selected_signals', []),
            row,
            col,
            theme,
            config.get('buy_signal_columns', []),
            config.get('sell_signal_columns', []),
            config.get('signal_logic', 'or')
        )


def _add_volume_chart(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add volume bar chart."""
    colors = [
        theme['chart_candle_up'] if c > o else theme['chart_candle_down']
        for c, o in zip(df['Close'], df['Open'])
    ]
    fig.add_trace(go.Bar(
        x=df.index, y=df['Volume'],
        name="Volume",
        marker=dict(color=colors, line=dict(width=0)),
        opacity=0.7,
        hovertemplate='%{x|%Y-%m-%d}<br>Vol: %{y:,.0f}<extra></extra>'
    ), row=row, col=col)


def _add_rsi(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add RSI indicator."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['RSI'],
        name="RSI",
        line=dict(color=theme['accent_orange'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>RSI: %{y:.2f}<extra></extra>'
    ), row=row, col=col)
    fig.add_hline(y=70, line_dash="dash", line_color=theme['accent_red'], line_width=1, opacity=0.5, row=row, col=col)
    fig.add_hline(y=30, line_dash="dash", line_color=theme['accent_green'], line_width=1, opacity=0.5, row=row, col=col)
    fig.add_hrect(y0=30, y1=70, fillcolor=theme['text_tertiary'], opacity=0.05, line_width=0, row=row, col=col)


def _add_cci(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add CCI indicator."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['CCI'],
        name="CCI",
        line=dict(color=theme['accent_purple'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>CCI: %{y:.2f}<extra></extra>'
    ), row=row, col=col)
    fig.add_hline(y=100, line_dash="dash", line_color=theme['accent_red'], line_width=1, opacity=0.5, row=row, col=col)
    fig.add_hline(y=-100, line_dash="dash", line_color=theme['accent_green'], line_width=1, opacity=0.5, row=row, col=col)


def _add_macd(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add MACD indicator."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MACD'],
        name="MACD",
        line=dict(color=theme['accent_blue'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>MACD: %{y:.4f}<extra></extra>'
    ), row=row, col=col)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['MACD_Signal'],
        name="Signal",
        line=dict(color=theme['accent_orange'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>Signal: %{y:.4f}<extra></extra>'
    ), row=row, col=col)
    histogram_colors = np.where(df['MACD_Histogram'] >= 0, theme['chart_candle_up'], theme['chart_candle_down'])
    fig.add_bar(
        x=df.index, y=df['MACD_Histogram'],
        name="Histogram",
        marker_color=histogram_colors,
        opacity=0.6,
        hovertemplate='%{x|%Y-%m-%d}<br>Hist: %{y:.4f}<extra></extra>',
        row=row, col=col
    )


def _add_adx(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add ADX indicator."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['ADX'],
        name="ADX",
        line=dict(color=theme['accent_cyan'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>ADX: %{y:.2f}<extra></extra>'
    ), row=row, col=col)
    fig.add_hline(y=25, line_dash="dash", line_color=theme['text_tertiary'], line_width=1, opacity=0.5, row=row, col=col)


def _add_atr(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add ATR indicator."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['ATR'],
        name="ATR",
        line=dict(color=theme['accent_cyan'], width=1.5),
        fill='tozeroy',
        fillcolor=f'{theme["accent_cyan"]}10',
        hovertemplate='%{x|%Y-%m-%d}<br>ATR: %{y:.2f}<extra></extra>'
    ), row=row, col=col)


def _add_obv(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add OBV indicator."""
    fig.add_trace(go.Scatter(
        x=df.index, y=df['OBV'],
        name="OBV",
        line=dict(color=theme['accent_purple'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>OBV: %{y:,.0f}<extra></extra>'
    ), row=row, col=col)


def _add_signal_traces(
    fig: go.Figure,
    df: pd.DataFrame,
    selected_signals: List[str],
    row: int,
    col: int,
    theme: dict,
    buy_signal_columns: List[str],
    sell_signal_columns: List[str],
    signal_logic: str = 'or'
) -> None:
    """Add combined buy/sell signal markers based on AND/OR logic."""
    signal_configs = {
        'buy': {
            'symbol': 'triangle-up',
            'offset': -1,
            'label': 'B',
            'text_position': 'top center',
            'color': theme['accent_green']
        },
        'sell': {
            'symbol': 'triangle-down',
            'offset': 1,
            'label': 'S',
            'text_position': 'bottom center',
            'color': theme['accent_red']
        }
    }

    def _combine_signals(columns: List[str], logic: str) -> pd.Series:
        """Combine multiple signal columns using AND or OR logic."""
        if not columns:
            return pd.Series(False, index=df.index)
        valid_cols = [c for c in columns if c in df.columns]
        if not valid_cols:
            return pd.Series(False, index=df.index)
        if logic == 'and':
            # AND: all signals must be True
            return df[valid_cols].all(axis=1)
        else:
            # OR: any signal triggers
            return df[valid_cols].any(axis=1)

    def _add_combined_markers(signal_type: str, columns: List[str]) -> None:
        if signal_type not in selected_signals:
            return
        if not columns:
            return

        cfg = signal_configs[signal_type]
        combined = _combine_signals(columns, signal_logic)
        signals = df[combined]

        if signals.empty:
            return

        offset = signals['Close'] * SIGNAL_OFFSET_FACTOR * cfg['offset']

        # Create label showing the logic mode
        logic_label = f"({signal_logic.upper()})" if len(columns) > 1 else ""
        signal_names = ", ".join([c.replace('_', ' ') for c in columns if c in df.columns])
        name = f"{signal_type.capitalize()} {logic_label}: {signal_names}"

        fig.add_trace(go.Scatter(
            x=signals.index,
            y=signals['Close'] + offset,
            mode='markers+text',
            text=[cfg['label']] * len(signals),
            textposition=cfg['text_position'],
            textfont=dict(color=theme['text_primary'], size=9, family=FONT_FAMILY),
            marker=dict(
                symbol=cfg['symbol'],
                size=14,
                color=cfg['color'],
                opacity=0.95,
                line=dict(color=theme['bg_primary'], width=1.5)
            ),
            name=name,
            hovertemplate=(
                f"{signal_type.capitalize()} ({signal_logic.upper()})<br>{signal_names}"
                "<br>%{x|%Y-%m-%d}<br>Price: %{y:.2f}<extra></extra>"
            )
        ), row=row, col=col)

    _add_combined_markers('buy', buy_signal_columns or [])
    _add_combined_markers('sell', sell_signal_columns or [])


def _add_range_selector(fig: go.Figure, theme: dict) -> None:
    """Add time range selector buttons."""
    fig.update_layout(
        xaxis=dict(
            rangeselector=dict(
                buttons=list([
                    dict(count=1, label="1M", step="month", stepmode="backward"),
                    dict(count=3, label="3M", step="month", stepmode="backward"),
                    dict(count=6, label="6M", step="month", stepmode="backward"),
                    dict(count=1, label="YTD", step="year", stepmode="todate"),
                    dict(count=1, label="1Y", step="year", stepmode="backward"),
                    dict(step="all", label="ALL")
                ]),
                bgcolor=theme['bg_tertiary'],
                activecolor=theme['accent_blue'],
                font=dict(color=theme['text_primary'], size=11),
                bordercolor=theme['border_primary'],
                borderwidth=1,
                x=0,
                y=1.02,
            ),
            rangeslider=dict(visible=False),
            type="date"
        )
    )


def _update_layout(fig: go.Figure, plot_count: int, show_legend: bool, config: Dict, theme: dict) -> None:
    """Update figure layout with professional styling."""
    title_text = config.get('title', '')

    # Calculate dynamic height based on number of plots
    # Base height for main chart (candlestick) + additional height per indicator
    base_height = 400  # Main chart minimum height
    indicator_height = 120  # Height per indicator panel
    calculated_height = max(500, base_height + (plot_count - 1) * indicator_height)

    fig.update_layout(
        template='plotly_dark',
        autosize=True,
        height=calculated_height,
        showlegend=show_legend,
        plot_bgcolor=theme['chart_bg'],
        paper_bgcolor=theme['chart_bg'],
        margin=dict(l=60, r=20, t=60 if title_text else 40, b=40),
        font=dict(family=FONT_FAMILY, color=theme['text_primary'], size=12),
        title=dict(
            text=title_text,
            x=0.5,
            xanchor='center',
            font=dict(size=16, color=theme['text_primary'])
        ) if title_text else None,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor='rgba(0,0,0,0)',
            font=dict(size=11)
        ) if show_legend else None,
        hoverlabel=dict(
            bgcolor=theme['bg_tertiary'],
            font_size=12,
            font_family=FONT_FAMILY,
            bordercolor=theme['border_primary']
        )
    )

    for i in range(1, plot_count + 1):
        fig.update_xaxes(
            rangeslider_visible=False,
            showgrid=True,
            gridcolor=theme['chart_grid'],
            gridwidth=1,
            showline=True,
            linecolor=theme['border_primary'],
            linewidth=1,
            tickfont=dict(color=theme['text_secondary'], size=10),
            row=i, col=1
        )
        fig.update_yaxes(
            showgrid=True,
            gridcolor=theme['chart_grid'],
            gridwidth=1,
            showline=True,
            linecolor=theme['border_primary'],
            linewidth=1,
            tickfont=dict(color=theme['text_secondary'], size=10),
            side='right',
            autorange=True,  # Always fit y-axis to visible data
            row=i, col=1
        )
        if i < plot_count:
            fig.update_xaxes(showticklabels=False, row=i, col=1)

    # Update subplot titles styling
    for annotation in fig.layout.annotations:
        annotation.update(
            font=dict(size=11, color=theme['text_secondary']),
            x=0.01,
            xanchor='left'
        )

    fig.update_xaxes(matches='x')


def _add_crosshair(fig: go.Figure, plot_count: int) -> None:
    """Add crosshair functionality with spikes on all subplots."""
    fig.update_layout(
        hovermode="x unified",
        hoverdistance=100,
        spikedistance=-1,  # Always show spikes regardless of distance
    )
    for i in range(1, plot_count + 1):
        # Vertical spikes (x-axis) - handled by clientside callback for cross-subplot sync
        fig.update_xaxes(
            showspikes=True,
            spikecolor="rgba(128,128,128,0.5)",
            spikethickness=1,
            spikemode="across",
            spikesnap="cursor",
            spikedash="dot",
            row=i, col=1
        )
        # Horizontal spikes (y-axis) - show in each subplot individually
        fig.update_yaxes(
            showspikes=True,
            spikecolor="rgba(128,128,128,0.7)",
            spikethickness=1,
            spikemode="across",
            spikesnap="cursor",
            spikedash="dot",
            row=i, col=1
        )


def create_empty_chart(theme: dict, message: str = "Load data to view chart") -> go.Figure:
    """Create an empty chart with a placeholder message."""
    fig = go.Figure()
    fig.update_layout(
        template='plotly_dark',
        plot_bgcolor=theme['chart_bg'],
        paper_bgcolor=theme['chart_bg'],
        font=dict(color=theme['text_secondary']),
        xaxis=dict(showgrid=False, visible=False),
        yaxis=dict(showgrid=False, visible=False),
        annotations=[dict(
            text=message,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=16, color=theme['text_tertiary'])
        )]
    )
    return fig
