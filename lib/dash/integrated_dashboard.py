"""
Professional Trading Dashboard
Bloomberg Terminal-inspired design with single-page layout
"""

import logging
import dash
from dash import dcc, html, dash_table, callback_context
from dash.dependencies import Input, Output, State, ClientsideFunction
import plotly.graph_objs as go
from plotly.subplots import make_subplots
import pandas as pd
from datetime import date, datetime
import yfinance as yf
from threading import Timer
import socket
from typing import Dict, Any, Tuple, List, Optional
from dash.exceptions import PreventUpdate
import webbrowser
import sys
import os
import dash_bootstrap_components as dbc
from functools import lru_cache
import itertools
from concurrent.futures import ThreadPoolExecutor, as_completed
import numpy as np
import json

# Configure logging
logger = logging.getLogger(__name__)

sys.path.append(os.path.dirname(os.path.dirname(os.path.dirname(__file__))))

from lib.strategy import backtest, run_backtest, percentage_of_portfolio
from lib.weights_optimization import walk_forward_optimisation
from lib.data_processing import get_all_tickers, create_backtest_results
from lib.signals.indicators import add_indicators, generate_signals
from lib.dash.dash_config import (
    THEMES, DEFAULT_THEME, get_theme,
    TEXT_COLOR, BACKGROUND_COLOR, CHART_BACKGROUND_COLOR, BORDER_COLOR,
    CHART_HEIGHT, MAIN_CONTENT_WIDTH, SIDEBAR_WIDTH,
    SIGNAL_OPTIONS, PLOT_OPTIONS, CHART_ELEMENT_OPTIONS,
    DEFAULT_TICKER, INITIAL_CAPITAL, START_DATE,
    OPTIMIZATION_METHODS, OPTIMIZATION_DELAY,
    START_PORT, MAX_PORT_TRIES,
    FONT_FAMILY, FONT_MONO, FONT_SIZES, SPACING, BORDER_RADIUS
)
from lib.utils import export_priceaction_to_excel
from lib.params_optimization import optimize_parameters, calculate_metric


# =============================================================================
# STYLE GENERATORS
# =============================================================================

def get_styles(theme: dict) -> dict:
    """Generate component styles based on theme."""
    return {
        'app': {
            'fontFamily': FONT_FAMILY,
            'backgroundColor': theme['bg_primary'],
            'color': theme['text_primary'],
            'minHeight': '100vh',
            'margin': 0,
            'padding': 0,
        },
        'header': {
            'backgroundColor': theme['bg_secondary'],
            'borderBottom': f'1px solid {theme["border_primary"]}',
            'padding': '12px 20px',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
            'height': '56px',
        },
        'logo': {
            'display': 'flex',
            'alignItems': 'center',
            'gap': '12px',
        },
        'logo_icon': {
            'width': '32px',
            'height': '32px',
            'backgroundColor': theme['accent_blue'],
            'borderRadius': BORDER_RADIUS['md'],
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'center',
            'color': '#fff',
            'fontWeight': 'bold',
            'fontSize': FONT_SIZES['lg'],
        },
        'logo_text': {
            'fontSize': FONT_SIZES['lg'],
            'fontWeight': '600',
            'color': theme['text_primary'],
            'letterSpacing': '-0.5px',
        },
        'header_controls': {
            'display': 'flex',
            'alignItems': 'center',
            'gap': '16px',
        },
        'main_container': {
            'display': 'flex',
            'height': 'calc(100vh - 56px)',
            'overflow': 'hidden',
        },
        'sidebar': {
            'width': '280px',
            'minWidth': '280px',
            'backgroundColor': theme['bg_secondary'],
            'borderRight': f'1px solid {theme["border_primary"]}',
            'display': 'flex',
            'flexDirection': 'column',
            'overflow': 'hidden',
        },
        'sidebar_section': {
            'padding': '16px',
            'borderBottom': f'1px solid {theme["border_secondary"]}',
        },
        'sidebar_title': {
            'fontSize': FONT_SIZES['xs'],
            'fontWeight': '600',
            'color': theme['text_secondary'],
            'textTransform': 'uppercase',
            'letterSpacing': '0.5px',
            'marginBottom': '12px',
        },
        'chart_container': {
            'flex': 1,
            'display': 'flex',
            'flexDirection': 'column',
            'overflow': 'hidden',
            'backgroundColor': theme['bg_primary'],
        },
        'chart_toolbar': {
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
            'padding': '8px 16px',
            'backgroundColor': theme['bg_secondary'],
            'borderBottom': f'1px solid {theme["border_primary"]}',
            'gap': '12px',
            'flexWrap': 'wrap',
        },
        'chart_area': {
            'flex': 1,
            'padding': '0',
            'overflow': 'hidden',
        },
        'right_panel': {
            'width': '320px',
            'minWidth': '320px',
            'backgroundColor': theme['bg_secondary'],
            'borderLeft': f'1px solid {theme["border_primary"]}',
            'display': 'flex',
            'flexDirection': 'column',
            'overflow': 'hidden',
        },
        'panel_header': {
            'padding': '12px 16px',
            'borderBottom': f'1px solid {theme["border_primary"]}',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
        },
        'panel_title': {
            'fontSize': FONT_SIZES['sm'],
            'fontWeight': '600',
            'color': theme['text_primary'],
        },
        'panel_content': {
            'flex': 1,
            'overflow': 'auto',
            'padding': '16px',
        },
        'card': {
            'backgroundColor': theme['bg_tertiary'],
            'borderRadius': BORDER_RADIUS['lg'],
            'border': f'1px solid {theme["border_primary"]}',
            'marginBottom': '12px',
        },
        'card_header': {
            'padding': '12px 16px',
            'borderBottom': f'1px solid {theme["border_secondary"]}',
            'fontSize': FONT_SIZES['sm'],
            'fontWeight': '600',
            'color': theme['text_primary'],
        },
        'card_body': {
            'padding': '16px',
        },
        'input': {
            'backgroundColor': theme['bg_tertiary'],
            'border': f'1px solid {theme["border_primary"]}',
            'borderRadius': BORDER_RADIUS['md'],
            'color': theme['text_primary'],
            'padding': '8px 12px',
            'fontSize': FONT_SIZES['sm'],
            'width': '100%',
        },
        'input_focus': {
            'borderColor': theme['border_focus'],
            'outline': 'none',
        },
        'button_primary': {
            'backgroundColor': theme['accent_blue'],
            'color': '#fff',
            'border': 'none',
            'borderRadius': BORDER_RADIUS['md'],
            'padding': '10px 20px',
            'fontSize': FONT_SIZES['sm'],
            'fontWeight': '600',
            'cursor': 'pointer',
            'transition': 'all 0.2s ease',
        },
        'button_success': {
            'backgroundColor': theme['accent_green'],
            'color': '#fff',
            'border': 'none',
            'borderRadius': BORDER_RADIUS['md'],
            'padding': '10px 20px',
            'fontSize': FONT_SIZES['sm'],
            'fontWeight': '600',
            'cursor': 'pointer',
        },
        'button_outline': {
            'backgroundColor': 'transparent',
            'color': theme['text_secondary'],
            'border': f'1px solid {theme["border_primary"]}',
            'borderRadius': BORDER_RADIUS['md'],
            'padding': '8px 16px',
            'fontSize': FONT_SIZES['sm'],
            'cursor': 'pointer',
        },
        'metric_card': {
            'backgroundColor': theme['bg_tertiary'],
            'borderRadius': BORDER_RADIUS['md'],
            'padding': '12px',
            'marginBottom': '8px',
        },
        'metric_label': {
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_secondary'],
            'marginBottom': '4px',
        },
        'metric_value': {
            'fontSize': FONT_SIZES['xl'],
            'fontWeight': '600',
            'color': theme['text_primary'],
            'fontFamily': FONT_MONO,
        },
        'metric_positive': {
            'color': theme['accent_green'],
        },
        'metric_negative': {
            'color': theme['accent_red'],
        },
        'checklist_container': {
            'display': 'flex',
            'flexDirection': 'column',
            'gap': '4px',
        },
        'checklist_item': {
            'display': 'flex',
            'alignItems': 'center',
            'padding': '6px 8px',
            'borderRadius': BORDER_RADIUS['sm'],
            'cursor': 'pointer',
            'transition': 'background-color 0.15s ease',
        },
        'status_badge': {
            'display': 'inline-flex',
            'alignItems': 'center',
            'padding': '2px 8px',
            'borderRadius': BORDER_RADIUS['full'],
            'fontSize': FONT_SIZES['xs'],
            'fontWeight': '500',
        },
        'status_success': {
            'backgroundColor': f'{theme["accent_green"]}20',
            'color': theme['accent_green'],
        },
        'status_warning': {
            'backgroundColor': f'{theme["accent_orange"]}20',
            'color': theme['accent_orange'],
        },
        'status_error': {
            'backgroundColor': f'{theme["accent_red"]}20',
            'color': theme['accent_red'],
        },
        'tab_container': {
            'display': 'flex',
            'borderBottom': f'1px solid {theme["border_primary"]}',
            'backgroundColor': theme['bg_secondary'],
        },
        'tab': {
            'padding': '12px 20px',
            'fontSize': FONT_SIZES['sm'],
            'color': theme['text_secondary'],
            'cursor': 'pointer',
            'borderBottom': '2px solid transparent',
            'transition': 'all 0.2s ease',
        },
        'tab_active': {
            'color': theme['text_primary'],
            'borderBottomColor': theme['accent_blue'],
        },
    }


# =============================================================================
# DASHBOARD STATE
# =============================================================================

class DashboardState:
    """Encapsulates dashboard state to avoid global mutable variables."""

    def __init__(self):
        self._df: Optional[pd.DataFrame] = None
        self._all_tickers_df: Optional[pd.DataFrame] = None
        self._backtest_results: Optional[Dict] = None
        self._data_cache: Dict[str, pd.DataFrame] = {}
        self._current_theme: str = DEFAULT_THEME

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

    @property
    def theme(self) -> dict:
        return get_theme(self._current_theme)

    def set_theme(self, theme_name: str) -> None:
        self._current_theme = theme_name

    def get_cached_data(self, key: str) -> Optional[pd.DataFrame]:
        return self._data_cache.get(key)

    def set_cached_data(self, key: str, data: pd.DataFrame) -> None:
        self._data_cache[key] = data

    def clear_cache(self) -> None:
        self._data_cache.clear()


dashboard_state = DashboardState()


# =============================================================================
# CHART FUNCTIONS
# =============================================================================

CHART_ORDER = ['candlestick', 'volume', 'rsi', 'cci', 'macd', 'adx', 'atr', 'obv']


def create_chart(df: pd.DataFrame, config: Dict, theme: dict) -> go.Figure:
    """Create a multi-panel financial chart with professional styling."""
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

        row_heights = [4.5 if plot == 'candlestick' else 1 for plot in plot_sequence]
        subplot_titles = [p.replace('_', ' ').upper() for p in plot_sequence]

        fig = make_subplots(
            rows=plot_count, cols=1,
            shared_xaxes=True,
            vertical_spacing=0.03,
            row_heights=row_heights,
            subplot_titles=subplot_titles
        )

        plot_functions = {
            'candlestick': lambda f, d, r, c, cfg: _add_candlestick(f, d, r, c, cfg, theme),
            'volume': lambda f, d, r, c, cfg: _add_volume_chart(f, d, r, c, cfg, theme),
            'rsi': lambda f, d, r, c, cfg: _add_rsi(f, d, r, c, cfg, theme),
            'cci': lambda f, d, r, c, cfg: _add_cci(f, d, r, c, cfg, theme),
            'macd': lambda f, d, r, c, cfg: _add_macd(f, d, r, c, cfg, theme),
            'adx': lambda f, d, r, c, cfg: _add_adx(f, d, r, c, cfg, theme),
            'atr': lambda f, d, r, c, cfg: _add_atr(f, d, r, c, cfg, theme),
            'obv': lambda f, d, r, c, cfg: _add_obv(f, d, r, c, cfg, theme)
        }

        for row, plot in enumerate(plot_sequence, start=1):
            if plot in plot_functions:
                plot_functions[plot](fig, df, row, 1, config)

        _add_range_selector(fig, df, plot_count, theme)
        _update_layout(fig, plot_count, row_heights, config.get('show_legend', False), config, theme)
        _add_crosshair(fig, plot_count)

        return fig

    except Exception as e:
        logger.error(f"Error creating chart: {e}")
        raise


def _add_candlestick(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add candlestick chart with overlays."""
    if config.get('show_candlesticks', True):
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
            hovertemplate='<b>%{x|%Y-%m-%d}</b><br>O: %{open:.2f}<br>H: %{high:.2f}<br>L: %{low:.2f}<br>C: %{close:.2f}<extra></extra>'
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
        _add_signal_traces(fig, df, config.get('selected_signals', []), row, col, theme)


def _add_volume_chart(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add volume bar chart."""
    colors = [theme['chart_candle_up'] if c > o else theme['chart_candle_down']
              for c, o in zip(df['Close'], df['Open'])]
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


def _add_signal_traces(fig: go.Figure, df: pd.DataFrame, selected_signals: List[str], row: int, col: int, theme: dict) -> None:
    """Add buy/sell signal markers."""
    signal_configs = {
        'buy': {'color': theme['accent_green'], 'symbol': 'triangle-up', 'offset': -1},
        'sell': {'color': theme['accent_red'], 'symbol': 'triangle-down', 'offset': 1}
    }

    for signal_type in selected_signals:
        if signal_type not in signal_configs:
            continue
        cfg = signal_configs[signal_type]
        col_name = f'{signal_type.capitalize()}_Position'
        if col_name in df.columns:
            signals = df[df[col_name] == 1]
            if not signals.empty:
                offset = signals['Close'] * 0.015 * cfg['offset']
                fig.add_trace(go.Scatter(
                    x=signals.index,
                    y=signals['Close'] + offset,
                    mode='markers',
                    marker=dict(symbol=cfg['symbol'], size=12, color=cfg['color'],
                               line=dict(color='white', width=1)),
                    name=f'{signal_type.capitalize()} Signal',
                    hovertemplate=f'{signal_type.capitalize()}<br>%{{x|%Y-%m-%d}}<br>Price: %{{y:.2f}}<extra></extra>'
                ), row=row, col=col)


def _add_range_selector(fig: go.Figure, df: pd.DataFrame, plot_count: int, theme: dict) -> None:
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


def _update_layout(fig: go.Figure, plot_count: int, row_heights: List[int], show_legend: bool, config: Dict, theme: dict) -> None:
    """Update figure layout with professional styling."""
    title_text = config.get('title', '')

    fig.update_layout(
        template='plotly_dark',
        autosize=True,
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
    """Add crosshair functionality."""
    fig.update_layout(
        hovermode="x unified",
        hoverdistance=100,
        spikedistance=1000,
    )
    for i in range(1, plot_count + 1):
        fig.update_xaxes(
            showspikes=True, spikecolor="rgba(128,128,128,0.5)", spikethickness=1,
            spikemode="across", spikesnap="cursor",
            row=i, col=1
        )
        fig.update_yaxes(
            showspikes=True, spikecolor="rgba(128,128,128,0.5)", spikethickness=1,
            spikemode="across",
            row=i, col=1
        )


# =============================================================================
# HELPER FUNCTIONS
# =============================================================================

def format_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """Format DataFrame for display."""
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == 'float64':
            df[col] = df[col].round(2)
    return df


def fetch_data_with_cache(ticker: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch data with caching."""
    cache_key = f"{ticker}_{start_date}_{end_date}"
    cached = dashboard_state.get_cached_data(cache_key)

    if cached is not None:
        return cached

    logger.info(f"Fetching data for {ticker}")
    df = yf.download(ticker, start=start_date, end=end_date)
    if df.empty:
        raise ValueError(f"No data available for {ticker}")

    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    dashboard_state.set_cached_data(cache_key, df)
    return df


def find_available_port(start_port: int = START_PORT, max_tries: int = MAX_PORT_TRIES) -> int:
    """Find an available port."""
    for port in range(start_port, start_port + max_tries):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as s:
            if s.connect_ex(('127.0.0.1', port)) != 0:
                return port
    raise RuntimeError("No available ports found")


# =============================================================================
# SIGNAL COMBINATION OPTIMIZER
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

        returns = result_df['Strategy_Returns'].dropna()
        sharpe = (returns.mean() / returns.std() * np.sqrt(252)) if returns.std() > 0 else 0

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
    """Run signal combination optimization."""
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
# COMPONENT BUILDERS
# =============================================================================

def build_metric_card(label: str, value: str, is_positive: bool = None, theme: dict = None) -> html.Div:
    """Build a metric display card."""
    if theme is None:
        theme = get_theme()

    styles = get_styles(theme)
    value_style = styles['metric_value'].copy()

    if is_positive is not None:
        if is_positive:
            value_style.update(styles['metric_positive'])
        else:
            value_style.update(styles['metric_negative'])

    return html.Div([
        html.Div(label, style=styles['metric_label']),
        html.Div(value, style=value_style)
    ], style=styles['metric_card'])


def build_status_badge(text: str, status: str, theme: dict = None) -> html.Span:
    """Build a status badge."""
    if theme is None:
        theme = get_theme()

    styles = get_styles(theme)
    badge_style = styles['status_badge'].copy()

    status_styles = {
        'success': styles['status_success'],
        'warning': styles['status_warning'],
        'error': styles['status_error'],
    }
    badge_style.update(status_styles.get(status, {}))

    return html.Span(text, style=badge_style)


# =============================================================================
# MAIN DASHBOARD APP
# =============================================================================

def create_dashboard_layout(theme: dict) -> html.Div:
    """Create the main dashboard layout."""
    styles = get_styles(theme)

    return html.Div([
        # Hidden stores
        dcc.Store(id='theme-store', data=DEFAULT_THEME),
        dcc.Store(id='data-loaded-store', data=False),
        dcc.Store(id='layout-store', data={}),
        dcc.Interval(id='startup-interval', interval=500, max_intervals=1),

        # Header
        html.Header([
            html.Div([
                html.Div("S", style=styles['logo_icon']),
                html.Span("SearchForAlpha", style=styles['logo_text']),
            ], style=styles['logo']),

            html.Div([
                # Theme toggle
                html.Button(
                    id='theme-toggle',
                    children=[html.Span("Dark", id='theme-label')],
                    style=styles['button_outline'],
                    n_clicks=0
                ),
                # Current time/status
                html.Div(id='header-status', style={
                    'fontSize': FONT_SIZES['sm'],
                    'color': theme['text_secondary'],
                    'fontFamily': FONT_MONO,
                }),
            ], style=styles['header_controls']),
        ], style=styles['header']),

        # Main container
        html.Div([
            # Left Sidebar - Controls
            html.Aside([
                # Data Input Section
                html.Div([
                    html.Div("MARKET DATA", style=styles['sidebar_title']),

                    html.Div([
                        html.Label("Symbol", style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '4px', 'display': 'block'}),
                        dcc.Dropdown(
                            id='ticker-dropdown',
                            value=DEFAULT_TICKER,
                            placeholder="Search symbol...",
                            style={'fontSize': FONT_SIZES['sm']},
                            className='dark-dropdown'
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
                        "Load Data",
                        id='load-data-button',
                        style={**styles['button_primary'], 'width': '100%'},
                        n_clicks=0
                    ),

                    dcc.Loading(
                        id='loading-data',
                        type='circle',
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
            ], style=styles['sidebar']),

            # Main Chart Area
            html.Main([
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

                # Chart
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
                ], style={**styles['chart_area'], 'height': 'calc(100vh - 56px - 60px)'}),
            ], style=styles['chart_container']),

            # Right Panel - Backtest & Results
            html.Aside([
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
                    html.Div(id='panel-backtest', children=[
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

                        html.Div(id='backtest-results', style={'marginTop': '16px'}),
                    ]),

                    # Optimizer Panel
                    html.Div(id='panel-optimizer', children=[
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

                        dcc.Loading(
                            type='circle',
                            color=theme['accent_orange'],
                            children=[html.Div(id='optimization-results', style={'marginTop': '16px'})]
                        ),
                    ], style={'display': 'none'}),

                    # Data Panel
                    html.Div(id='panel-data', children=[
                        html.Div(id='data-table-container', style={'fontSize': FONT_SIZES['xs']}),
                    ], style={'display': 'none'}),

                ], style=styles['panel_content']),
            ], style=styles['right_panel']),

        ], style=styles['main_container']),

        # Hidden elements
        html.Div(id='hidden-output', style={'display': 'none'}),

    ], style=styles['app'], id='app-container')


def run_dashboard():
    """Run the professional trading dashboard."""
    theme = get_theme(DEFAULT_THEME)

    # Custom CSS for dark theme components
    custom_css = '''
        /* Dark theme dropdown */
        .dark-dropdown .Select-control {
            background-color: #21262d !important;
            border-color: #30363d !important;
        }
        .dark-dropdown .Select-menu-outer {
            background-color: #21262d !important;
            border-color: #30363d !important;
        }
        .dark-dropdown .Select-option {
            background-color: #21262d !important;
            color: #e6edf3 !important;
        }
        .dark-dropdown .Select-option:hover {
            background-color: #30363d !important;
        }
        .dark-dropdown .Select-value-label {
            color: #e6edf3 !important;
        }
        .dark-dropdown .Select-placeholder {
            color: #8b949e !important;
        }

        /* Date picker dark theme */
        .SingleDatePickerInput {
            background-color: #21262d !important;
            border: 1px solid #30363d !important;
            border-radius: 6px !important;
        }
        .DateInput_input {
            background-color: #21262d !important;
            color: #e6edf3 !important;
            font-size: 14px !important;
            padding: 8px 12px !important;
        }
        .CalendarDay__selected {
            background: #58a6ff !important;
            border-color: #58a6ff !important;
        }

        /* Panel tabs */
        .panel-tab {
            background: transparent !important;
            transition: all 0.2s ease !important;
        }
        .panel-tab:hover {
            background-color: #21262d !important;
        }
        .panel-tab.active {
            border-bottom-color: #58a6ff !important;
            color: #e6edf3 !important;
        }

        /* Scrollbar styling */
        ::-webkit-scrollbar {
            width: 8px;
            height: 8px;
        }
        ::-webkit-scrollbar-track {
            background: #161b22;
        }
        ::-webkit-scrollbar-thumb {
            background: #30363d;
            border-radius: 4px;
        }
        ::-webkit-scrollbar-thumb:hover {
            background: #484f58;
        }

        /* Loading spinner */
        ._dash-loading {
            background-color: transparent !important;
        }

        /* Checkbox styling */
        input[type="checkbox"] {
            accent-color: #58a6ff;
        }

        /* Button hover states */
        button:hover {
            opacity: 0.9;
        }
        button:active {
            transform: translateY(1px);
        }
    '''

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
            <style>{custom_css}</style>
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

    # ==========================================================================
    # CALLBACKS
    # ==========================================================================

    @app.callback(
        Output('ticker-dropdown', 'options'),
        [Input('startup-interval', 'n_intervals')]
    )
    def populate_tickers(_):
        """Populate ticker dropdown on startup."""
        if dashboard_state.all_tickers_df is None:
            try:
                dashboard_state.all_tickers_df = get_all_tickers()
            except Exception as e:
                logger.error(f"Error fetching tickers: {e}")
                return [{'label': 'SPY - SPDR S&P 500 ETF', 'value': 'SPY'}]
        return [
            {'label': f"{row['Symbol']} - {row['Security'][:30]}", 'value': row['Symbol']}
            for _, row in dashboard_state.all_tickers_df.iterrows()
        ]

    @app.callback(
        [Output('data-status', 'children'),
         Output('data-loaded-store', 'data'),
         Output('buy-signals', 'options'),
         Output('sell-signals', 'options'),
         Output('chart-title', 'children'),
         Output('chart-subtitle', 'children'),
         Output('data-table-container', 'children')],
        [Input('load-data-button', 'n_clicks')],
        [State('ticker-dropdown', 'value'),
         State('start-date', 'date'),
         State('end-date', 'date')]
    )
    def load_data(n_clicks, ticker, start_date, end_date):
        """Load market data."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()
        styles = get_styles(theme)

        try:
            df = fetch_data_with_cache(ticker, start_date, end_date)
            if df.empty:
                return build_status_badge("No data available", "error", theme), False, [], [], "No data", "", None

            df = add_indicators(df)
            df, _ = generate_signals(df)
            dashboard_state.df = df

            buy_options = [{'label': html.Span(col.replace('_', ' '), style={'marginLeft': '8px'}), 'value': col}
                          for col in df.columns if 'buy' in col.lower()]
            sell_options = [{'label': html.Span(col.replace('_', ' '), style={'marginLeft': '8px'}), 'value': col}
                           for col in df.columns if 'sell' in col.lower()]

            # Create data table
            display_df = format_df_for_display(df.tail(50)).reset_index()
            data_table = dash_table.DataTable(
                columns=[{"name": i, "id": i} for i in display_df.columns],
                data=display_df.to_dict('records'),
                style_table={'height': '400px', 'overflowY': 'auto'},
                style_cell={
                    'textAlign': 'right',
                    'padding': '8px',
                    'backgroundColor': theme['bg_tertiary'],
                    'color': theme['text_primary'],
                    'border': f'1px solid {theme["border_secondary"]}',
                    'fontSize': '11px',
                    'fontFamily': FONT_MONO,
                },
                style_header={
                    'fontWeight': '600',
                    'backgroundColor': theme['bg_secondary'],
                    'color': theme['text_secondary'],
                    'textTransform': 'uppercase',
                    'fontSize': '10px',
                },
                style_data_conditional=[
                    {'if': {'row_index': 'odd'}, 'backgroundColor': theme['table_row_alt']}
                ],
                page_size=50,
                fixed_rows={'headers': True}
            )

            # Calculate subtitle info
            latest_close = df['Close'].iloc[-1]
            prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
            change = latest_close - prev_close
            change_pct = (change / prev_close) * 100
            change_color = theme['accent_green'] if change >= 0 else theme['accent_red']
            change_sign = '+' if change >= 0 else ''

            subtitle = html.Span([
                html.Span(f"${latest_close:.2f}", style={'fontFamily': FONT_MONO, 'color': theme['text_primary']}),
                html.Span(f" {change_sign}{change:.2f} ({change_sign}{change_pct:.2f}%)",
                         style={'fontFamily': FONT_MONO, 'color': change_color, 'marginLeft': '8px'}),
            ])

            status = build_status_badge(f"Loaded {len(df)} rows", "success", theme)

            return status, True, buy_options, sell_options, ticker, subtitle, data_table

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return build_status_badge(str(e)[:50], "error", theme), False, [], [], "Error", "", None

    @app.callback(
        Output('financial-chart', 'figure'),
        [Input('data-loaded-store', 'data'),
         Input('plot-checklist', 'value'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value')],
        [State('ticker-dropdown', 'value')]
    )
    def update_chart(data_loaded, selected_plots, chart_elements, selected_signals, ticker):
        """Update the financial chart."""
        if not data_loaded or dashboard_state.df is None:
            theme = get_theme()
            fig = go.Figure()
            fig.update_layout(
                template='plotly_dark',
                plot_bgcolor=theme['chart_bg'],
                paper_bgcolor=theme['chart_bg'],
                font=dict(color=theme['text_secondary']),
                xaxis=dict(showgrid=False, visible=False),
                yaxis=dict(showgrid=False, visible=False),
                annotations=[dict(
                    text="Load data to view chart",
                    xref="paper", yref="paper",
                    x=0.5, y=0.5,
                    showarrow=False,
                    font=dict(size=16, color=theme['text_tertiary'])
                )]
            )
            return fig

        theme = get_theme()
        df = dashboard_state.df

        config = {
            'selected_plots': selected_plots or ['candlestick'],
            'show_candlesticks': 'candlesticks' in (chart_elements or []),
            'show_bollinger': 'bollinger' in (chart_elements or []),
            'show_sma': 'sma' in (chart_elements or []),
            'show_ema': 'ema' in (chart_elements or []),
            'show_buy_sell_signals': 'signals' in (chart_elements or []),
            'show_legend': 'legend' in (chart_elements or []),
            'selected_signals': selected_signals or [],
            'title': '',
        }

        return create_chart(df, config, theme)

    @app.callback(
        Output('backtest-results', 'children'),
        [Input('run-backtest-btn', 'n_clicks')],
        [State('ticker-dropdown', 'value'),
         State('initial-capital', 'value'),
         State('buy-signals', 'value'),
         State('sell-signals', 'value')]
    )
    def run_backtest_callback(n_clicks, ticker, initial_capital, buy_signals, sell_signals):
        """Run backtest and display results."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()
        styles = get_styles(theme)

        df = dashboard_state.df
        if df is None:
            return html.Div([build_status_badge("Load data first", "warning", theme)])

        if not buy_signals or not sell_signals:
            return html.Div([build_status_badge("Select signals", "warning", theme)])

        try:
            results = run_backtest(df, initial_capital, buy_signals, sell_signals)
            backtest_results = create_backtest_results(results, ticker, initial_capital, buy_signals, sell_signals)
            dashboard_state.backtest_results = backtest_results

            # Calculate metrics
            total_return = backtest_results['total_return']
            is_positive = total_return >= 0

            return html.Div([
                build_status_badge("Backtest Complete", "success", theme),
                html.Div([
                    build_metric_card("Portfolio Value", f"${backtest_results['final_portfolio_value']:,.2f}", None, theme),
                    build_metric_card("Total Return", f"{total_return:+.2f}%", is_positive, theme),
                    build_metric_card("Sharpe Ratio", f"{backtest_results['sharpe_ratio']:.2f}",
                                     backtest_results['sharpe_ratio'] > 1, theme),
                    build_metric_card("Max Drawdown", f"{backtest_results['max_drawdown']:.2f}%",
                                     backtest_results['max_drawdown'] > -20, theme),
                    build_metric_card("Win Rate", f"{backtest_results['win_rate']:.1f}%",
                                     backtest_results['win_rate'] > 50, theme),
                ], style={'marginTop': '12px'}),
            ])

        except Exception as e:
            logger.error(f"Backtest error: {e}")
            return html.Div([build_status_badge(str(e)[:40], "error", theme)])

    @app.callback(
        Output('optimization-results', 'children'),
        [Input('run-optimization-btn', 'n_clicks')],
        [State('initial-capital', 'value'),
         State('max-signals-slider', 'value'),
         State('max-combos-input', 'value')]
    )
    def run_optimization_callback(n_clicks, initial_capital, max_signals, max_combos):
        """Run signal combination optimization."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()

        df = dashboard_state.df
        if df is None:
            return html.Div([build_status_badge("Load data first", "warning", theme)])

        try:
            results_df = run_combo_optimization(df, initial_capital, max_signals, max_combos)

            if results_df.empty:
                return html.Div([build_status_badge("No valid combinations", "warning", theme)])

            display_df = results_df.head(10).round(2)

            return html.Div([
                build_status_badge(f"Tested {len(results_df)} combinations", "success", theme),
                html.Div([
                    html.Div(f"Top result: {display_df.iloc[0]['Total_Return_%']:.1f}% return",
                            style={'fontSize': FONT_SIZES['sm'], 'color': theme['accent_green'], 'marginTop': '8px', 'marginBottom': '8px'}),
                    dash_table.DataTable(
                        columns=[{"name": i, "id": i} for i in ['Buy_Signals', 'Total_Return_%', 'Sharpe_Ratio']],
                        data=display_df[['Buy_Signals', 'Total_Return_%', 'Sharpe_Ratio']].to_dict('records'),
                        style_cell={
                            'textAlign': 'left',
                            'padding': '6px',
                            'backgroundColor': theme['bg_tertiary'],
                            'color': theme['text_primary'],
                            'fontSize': '11px',
                            'border': f'1px solid {theme["border_secondary"]}',
                        },
                        style_header={
                            'fontWeight': '600',
                            'backgroundColor': theme['bg_secondary'],
                            'fontSize': '10px',
                            'textTransform': 'uppercase',
                        },
                        style_data_conditional=[
                            {'if': {'row_index': 0}, 'backgroundColor': f'{theme["accent_green"]}20'}
                        ],
                    )
                ], style={'marginTop': '8px'}),
            ])

        except Exception as e:
            logger.error(f"Optimization error: {e}")
            return html.Div([build_status_badge(str(e)[:40], "error", theme)])

    @app.callback(
        [Output('panel-backtest', 'style'),
         Output('panel-optimizer', 'style'),
         Output('panel-data', 'style'),
         Output('tab-backtest', 'style'),
         Output('tab-optimizer', 'style'),
         Output('tab-data', 'style')],
        [Input('tab-backtest', 'n_clicks'),
         Input('tab-optimizer', 'n_clicks'),
         Input('tab-data', 'n_clicks')]
    )
    def switch_panel(backtest_clicks, optimizer_clicks, data_clicks):
        """Switch between right panel tabs."""
        theme = get_theme()
        styles = get_styles(theme)

        ctx = callback_context
        if not ctx.triggered:
            # Default to backtest tab
            return (
                {'display': 'block'},
                {'display': 'none'},
                {'display': 'none'},
                {**styles['tab'], **styles['tab_active']},
                styles['tab'],
                styles['tab']
            )

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'tab-backtest':
            return (
                {'display': 'block'},
                {'display': 'none'},
                {'display': 'none'},
                {**styles['tab'], **styles['tab_active']},
                styles['tab'],
                styles['tab']
            )
        elif button_id == 'tab-optimizer':
            return (
                {'display': 'none'},
                {'display': 'block'},
                {'display': 'none'},
                styles['tab'],
                {**styles['tab'], **styles['tab_active']},
                styles['tab']
            )
        else:  # tab-data
            return (
                {'display': 'none'},
                {'display': 'none'},
                {'display': 'block'},
                styles['tab'],
                styles['tab'],
                {**styles['tab'], **styles['tab_active']}
            )

    @app.callback(
        Output('header-status', 'children'),
        [Input('startup-interval', 'n_intervals')]
    )
    def update_header_status(_):
        """Update header status."""
        return datetime.now().strftime("%H:%M:%S")

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

def create_dash_app(df: pd.DataFrame, ticker: str, backtest_results: Dict) -> dash.Dash:
    """Legacy function for backwards compatibility."""
    # This creates a simplified chart view
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


def plot_financial_chart_dash(df: pd.DataFrame, ticker: str, backtest_results: Dict) -> None:
    """Legacy function for backwards compatibility."""
    app = create_dash_app(df, ticker, backtest_results)
    port = find_available_port()
    Timer(1, lambda: webbrowser.open_new(f"http://127.0.0.1:{port}/")).start()
    app.run(debug=False, use_reloader=False, port=port)


if __name__ == '__main__':
    run_dashboard()
