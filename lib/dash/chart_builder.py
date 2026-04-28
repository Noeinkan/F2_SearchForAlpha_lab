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

from ta.momentum import RSIIndicator
from ta.trend import CCIIndicator, MACD, ADXIndicator
from ta.volatility import AverageTrueRange
from ta.volume import VolumeWeightedAveragePrice

from lib.dash.dash_config import FONT_FAMILY
from lib.dash.overlay_registry import build_overlay_visibility, get_plotly_overlay_specs

logger = logging.getLogger(__name__)

# Chart configuration constants
CHART_ORDER = ['candlestick', 'volume', 'rsi', 'cci', 'macd', 'vwap', 'adx', 'atr', 'obv']
CHART_ROW_HEIGHT_MAIN = 4.5
CHART_ROW_HEIGHT_INDICATOR = 1
SIGNAL_OFFSET_FACTOR = 0.015


def _get_indicator_setting(config: Dict, indicator: str, key: str, default: float | int) -> float | int:
    settings = config.get('indicator_settings', {}) or {}
    return settings.get(indicator, {}).get(key, default)


def _coerce_period(value: float | int, default: int) -> int:
    try:
        return max(1, int(round(float(value))))
    except (TypeError, ValueError):
        return default


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
        if subplot_titles and plot_sequence[0] == 'candlestick':
            subplot_titles[0] = ""

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
            'vwap': _add_vwap,
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

    overlay_visibility = config.get('overlay_visibility')
    if overlay_visibility is None:
        overlay_visibility = build_overlay_visibility(
            legacy_flags={
                'show_bollinger': config.get('show_bollinger', False),
                'show_sma': config.get('show_sma', False),
                'show_ema': config.get('show_ema', False),
            }
        )

    for overlay_spec in get_plotly_overlay_specs(df, theme, overlay_visibility):
        fig.add_trace(go.Scatter(
            x=df.index,
            y=df[overlay_spec['column']],
            name=overlay_spec['name'],
            line=overlay_spec['line'],
            opacity=overlay_spec.get('opacity', 1.0),
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
            config.get('signal_logic', 'or'),
            config.get('signal_window', 0),
            config.get('consecutive_signal_mode', 'scale_in'),
            config.get('cooldown_bars', 0)
        )


def _add_volume_chart(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add volume bar chart."""
    ma_period = _coerce_period(_get_indicator_setting(config, 'volume', 'ma_period', 20), 20)
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
    if ma_period > 1:
        volume_ma = df['Volume'].rolling(window=ma_period, min_periods=1).mean()
        fig.add_trace(go.Scatter(
            x=df.index, y=volume_ma,
            name=f"Vol MA ({ma_period})",
            line=dict(color=theme['accent_blue'], width=1.2),
            hovertemplate='%{x|%Y-%m-%d}<br>Vol MA: %{y:,.0f}<extra></extra>'
        ), row=row, col=col)


def _add_rsi(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add RSI indicator."""
    period = _coerce_period(_get_indicator_setting(config, 'rsi', 'period', 14), 14)
    overbought = _get_indicator_setting(config, 'rsi', 'overbought', 70)
    oversold = _get_indicator_setting(config, 'rsi', 'oversold', 30)
    rsi_series = RSIIndicator(close=df['Close'], window=period).rsi()
    fig.add_trace(go.Scatter(
        x=df.index, y=rsi_series,
        name=f"RSI ({period})",
        line=dict(color=theme['accent_orange'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>RSI: %{y:.2f}<extra></extra>'
    ), row=row, col=col)
    fig.add_hline(y=overbought, line_dash="dash", line_color=theme['accent_red'], line_width=1, opacity=0.6, row=row, col=col)
    fig.add_hline(y=oversold, line_dash="dash", line_color=theme['accent_green'], line_width=1, opacity=0.6, row=row, col=col)
    fig.add_hline(y=50, line_dash="dot", line_color=theme['text_tertiary'], line_width=1, opacity=0.4, row=row, col=col)
    fig.add_hrect(y0=oversold, y1=overbought, fillcolor=theme['text_tertiary'], opacity=0.06, line_width=0, row=row, col=col)


def _add_cci(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add CCI indicator."""
    period = _coerce_period(_get_indicator_setting(config, 'cci', 'period', 20), 20)
    ceiling = _get_indicator_setting(config, 'cci', 'ceiling', 100)
    floor = _get_indicator_setting(config, 'cci', 'floor', -100)
    cci_series = CCIIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=period).cci()
    fig.add_trace(go.Scatter(
        x=df.index, y=cci_series,
        name=f"CCI ({period})",
        line=dict(color=theme['accent_purple'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>CCI: %{y:.2f}<extra></extra>'
    ), row=row, col=col)
    fig.add_hline(y=ceiling, line_dash="dash", line_color=theme['accent_red'], line_width=1, opacity=0.6, row=row, col=col)
    fig.add_hline(y=floor, line_dash="dash", line_color=theme['accent_green'], line_width=1, opacity=0.6, row=row, col=col)
    fig.add_hline(y=0, line_dash="dot", line_color=theme['text_tertiary'], line_width=1, opacity=0.4, row=row, col=col)
    fig.add_hrect(y0=floor, y1=ceiling, fillcolor=theme['text_tertiary'], opacity=0.04, line_width=0, row=row, col=col)


def _add_macd(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add MACD indicator."""
    fast = _coerce_period(_get_indicator_setting(config, 'macd', 'fast', 12), 12)
    slow = _coerce_period(_get_indicator_setting(config, 'macd', 'slow', 26), 26)
    signal = _coerce_period(_get_indicator_setting(config, 'macd', 'signal', 9), 9)
    macd = MACD(close=df['Close'], window_slow=slow, window_fast=fast, window_sign=signal)
    macd_line = macd.macd()
    macd_signal = macd.macd_signal()
    macd_hist = macd.macd_diff()
    fig.add_trace(go.Scatter(
        x=df.index, y=macd_line,
        name=f"MACD ({fast},{slow})",
        line=dict(color=theme['accent_blue'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>MACD: %{y:.4f}<extra></extra>'
    ), row=row, col=col)
    fig.add_trace(go.Scatter(
        x=df.index, y=macd_signal,
        name=f"Signal ({signal})",
        line=dict(color=theme['accent_orange'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>Signal: %{y:.4f}<extra></extra>'
    ), row=row, col=col)
    histogram_colors = np.where(macd_hist >= 0, theme['chart_candle_up'], theme['chart_candle_down'])
    fig.add_bar(
        x=df.index, y=macd_hist,
        name="Histogram",
        marker_color=histogram_colors,
        opacity=0.6,
        hovertemplate='%{x|%Y-%m-%d}<br>Hist: %{y:.4f}<extra></extra>',
        row=row, col=col
    )
    fig.add_hline(y=0, line_dash="dot", line_color=theme['text_tertiary'], line_width=1, opacity=0.5, row=row, col=col)


def _add_vwap(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add VWAP indicator."""
    window = _coerce_period(_get_indicator_setting(config, 'vwap', 'window', 20), 20)
    vwap_series = VolumeWeightedAveragePrice(
        high=df['High'],
        low=df['Low'],
        close=df['Close'],
        volume=df['Volume'].fillna(0),
        window=window
    ).volume_weighted_average_price()

    fig.add_trace(go.Scatter(
        x=df.index, y=vwap_series,
        name=f"VWAP ({window})",
        line=dict(color=theme['accent_blue'], width=1.6),
        hovertemplate='%{x|%Y-%m-%d}<br>VWAP: %{y:.2f}<extra></extra>'
    ), row=row, col=col)
    fig.add_trace(go.Scatter(
        x=df.index, y=df['Close'],
        name="Close",
        line=dict(color=theme['text_secondary'], width=1.1, dash='dot'),
        opacity=0.8,
        hovertemplate='%{x|%Y-%m-%d}<br>Close: %{y:.2f}<extra></extra>'
    ), row=row, col=col)


def _add_adx(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add ADX indicator."""
    period = _coerce_period(_get_indicator_setting(config, 'adx', 'period', 14), 14)
    threshold = _get_indicator_setting(config, 'adx', 'threshold', 25)
    adx = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=period).adx()
    fig.add_trace(go.Scatter(
        x=df.index, y=adx,
        name=f"ADX ({period})",
        line=dict(color=theme['accent_cyan'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>ADX: %{y:.2f}<extra></extra>'
    ), row=row, col=col)
    fig.add_hline(y=threshold, line_dash="dash", line_color=theme['text_tertiary'], line_width=1, opacity=0.6, row=row, col=col)


def _add_atr(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add ATR indicator."""
    period = _coerce_period(_get_indicator_setting(config, 'atr', 'period', 14), 14)
    atr_series = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'], window=period).average_true_range()
    atr_ma = atr_series.rolling(window=period, min_periods=1).mean()
    fig.add_trace(go.Scatter(
        x=df.index, y=atr_series,
        name=f"ATR ({period})",
        line=dict(color=theme['accent_cyan'], width=1.5),
        fill='tozeroy',
        fillcolor=f'{theme["accent_cyan"]}10',
        hovertemplate='%{x|%Y-%m-%d}<br>ATR: %{y:.2f}<extra></extra>'
    ), row=row, col=col)
    fig.add_trace(go.Scatter(
        x=df.index, y=atr_ma,
        name=f"ATR MA ({period})",
        line=dict(color=theme['accent_blue'], width=1.1, dash='dot'),
        hovertemplate='%{x|%Y-%m-%d}<br>ATR MA: %{y:.2f}<extra></extra>'
    ), row=row, col=col)


def _add_obv(fig: go.Figure, df: pd.DataFrame, row: int, col: int, config: Dict, theme: dict) -> None:
    """Add OBV indicator."""
    ma_period = _coerce_period(_get_indicator_setting(config, 'obv', 'ma_period', 20), 20)
    obv = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
    fig.add_trace(go.Scatter(
        x=df.index, y=obv,
        name="OBV",
        line=dict(color=theme['accent_purple'], width=1.5),
        hovertemplate='%{x|%Y-%m-%d}<br>OBV: %{y:,.0f}<extra></extra>'
    ), row=row, col=col)
    if ma_period > 1:
        obv_ma = obv.rolling(window=ma_period, min_periods=1).mean()
        fig.add_trace(go.Scatter(
            x=df.index, y=obv_ma,
            name=f"OBV MA ({ma_period})",
            line=dict(color=theme['accent_blue'], width=1.1, dash='dot'),
            hovertemplate='%{x|%Y-%m-%d}<br>OBV MA: %{y:,.0f}<extra></extra>'
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
    signal_logic: str = 'or',
    signal_window: int = 0,
    consecutive_signal_mode: str = 'scale_in',
    cooldown_bars: int = 0
) -> None:
    """Add combined buy/sell signal markers based on AND/OR logic."""
    signal_configs = {
        'buy': {
            'symbol': 'triangle-up',
            'offset': -1,
            'label': 'B',
            'text_position': 'top center',
            'color': theme['accent_blue']
        },
        'sell': {
            'symbol': 'triangle-down',
            'offset': 1,
            'label': 'S',
            'text_position': 'bottom center',
            'color': theme['accent_purple']
        }
    }

    def _combine_signals(columns: List[str], logic: str, window: int) -> pd.Series:
        """Combine multiple signal columns using AND or OR logic."""
        if not columns:
            return pd.Series(False, index=df.index)
        valid_cols = [c for c in columns if c in df.columns]
        if not valid_cols:
            return pd.Series(False, index=df.index)
        if logic == 'and':
            if window and window > 0:
                windowed = df[valid_cols].rolling(window=window + 1, min_periods=1).max()
                return (windowed > 0).all(axis=1)
            # AND: all signals must be True
            return df[valid_cols].all(axis=1)
        else:
            # OR: any signal triggers
            return df[valid_cols].any(axis=1)

    def _apply_consecutive_rules(signal_series: pd.Series, mode: str, cooldown: int) -> tuple[pd.Series, pd.Series]:
        mode = (mode or 'scale_in').lower()
        cooldown = max(0, int(cooldown or 0))
        accepted = np.zeros(len(signal_series), dtype=bool)
        rejected = np.zeros(len(signal_series), dtype=bool)
        wait_reset = False
        remaining_cooldown = 0

        for idx, is_signal in enumerate(signal_series.values):
            if mode == 'reset_cooldown' and not is_signal:
                wait_reset = False

            if mode == 'edge':
                prev = signal_series.values[idx - 1] if idx > 0 else False
                allow = bool(is_signal) and not bool(prev)
            elif mode == 'cooldown':
                allow = bool(is_signal) and remaining_cooldown == 0
            elif mode == 'reset_cooldown':
                allow = bool(is_signal) and remaining_cooldown == 0 and not wait_reset
            else:
                allow = bool(is_signal)

            if is_signal and allow:
                accepted[idx] = True
                if mode in ('cooldown', 'reset_cooldown') and cooldown > 0:
                    remaining_cooldown = cooldown
                if mode == 'reset_cooldown':
                    wait_reset = True
            elif is_signal and not allow:
                rejected[idx] = True

            if remaining_cooldown > 0:
                remaining_cooldown -= 1

        return pd.Series(accepted, index=signal_series.index), pd.Series(rejected, index=signal_series.index)

    def _add_combined_markers(signal_type: str, columns: List[str]) -> None:
        if signal_type not in selected_signals:
            return
        if not columns:
            return

        cfg = signal_configs[signal_type]
        accepted_col = f"{signal_type.capitalize()}_Trigger_Accepted"
        rejected_col = f"{signal_type.capitalize()}_Trigger_Rejected"
        has_acceptance = accepted_col in df.columns and rejected_col in df.columns
        if has_acceptance:
            accepted = df[df[accepted_col]]
            rejected = df[df[rejected_col]]
        else:
            combined = _combine_signals(columns, signal_logic, signal_window)
            accepted_mask, rejected_mask = _apply_consecutive_rules(
                combined, consecutive_signal_mode, cooldown_bars
            )
            accepted = df[accepted_mask]
            rejected = df[rejected_mask]

        if accepted.empty and rejected.empty:
            return

        signal_names = ", ".join([c.replace('_', ' ') for c in columns if c in df.columns])
        logic_label = ""
        if len(columns) > 1:
            if signal_logic == 'and' and signal_window and signal_window > 0:
                logic_label = f"(AND w={signal_window})"
            else:
                logic_label = f"({signal_logic.upper()})"
        name = f"{signal_type.capitalize()} {logic_label}: {signal_names}"

        if not accepted.empty:
            offset = accepted['Close'] * SIGNAL_OFFSET_FACTOR * cfg['offset']
            fig.add_trace(go.Scatter(
                x=accepted.index,
                y=accepted['Close'] + offset,
                mode='markers+text',
                text=[cfg['label']] * len(accepted),
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
                    f"{signal_type.capitalize()} {logic_label or f'({signal_logic.upper()})'}<br>{signal_names}"
                    "<br>%{x|%Y-%m-%d}<br>Price: %{y:.2f}<extra></extra>"
                )
            ), row=row, col=col)

        if not rejected.empty:
            offset = rejected['Close'] * SIGNAL_OFFSET_FACTOR * cfg['offset']
            muted_color = theme['text_tertiary']
            fig.add_trace(go.Scatter(
                x=rejected.index,
                y=rejected['Close'] + offset,
                mode='markers+text',
                text=[cfg['label']] * len(rejected),
                textposition=cfg['text_position'],
                textfont=dict(color=muted_color, size=9, family=FONT_FAMILY),
                marker=dict(
                    symbol=cfg['symbol'],
                    size=7,
                    color=muted_color,
                    opacity=0.35,
                    line=dict(color=theme['bg_primary'], width=1.0)
                ),
                name=f"{name} (filtered)",
                hovertemplate=(
                    f"{signal_type.capitalize()} filtered {logic_label or f'({signal_logic.upper()})'}<br>{signal_names}"
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
                bgcolor='rgba(0,0,0,0)',
                activecolor=theme['accent_blue'],
                font=dict(color=theme['text_primary'], size=11),
                bordercolor=theme['border_primary'],
                borderwidth=1,
                x=0,
                y=1.08,
                xanchor='left',
                yanchor='bottom'
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
        margin=dict(l=60, r=20, t=80 if title_text else 60, b=40),
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
            gridwidth=0.5,
            showline=True,
            linecolor=theme['border_secondary'],
            linewidth=1,
            zeroline=False,
            tickfont=dict(color=theme['text_secondary'], size=9),
            ticks='outside',
            ticklen=4,
            row=i, col=1
        )
        fig.update_yaxes(
            showgrid=True,
            gridcolor=theme['chart_grid'],
            gridwidth=0.5,
            showline=True,
            linecolor=theme['border_secondary'],
            linewidth=1,
            zeroline=False,
            tickfont=dict(color=theme['text_secondary'], size=9),
            ticks='outside',
            ticklen=4,
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

    for i in range(2, plot_count + 1):
        fig.update_xaxes(matches='x', row=i, col=1)


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
