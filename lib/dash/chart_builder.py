"""
Chart Builder Module
Professional financial chart creation with Plotly.
"""

import logging
from typing import Any, Dict, List
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

# Phase 8 — performance for large datasets. Plotly candlesticks get sluggish
# past a few thousand bars, so once the *full* series exceeds
# DOWNSAMPLE_THRESHOLD we render at most MAX_RENDER_BARS points by aggregating
# fixed-size row blocks (proper OHLCV agg). Daily equity data stays well under
# the threshold, so this is a strict no-op today and only engages when
# intraday / very-long-history series arrive.
DOWNSAMPLE_THRESHOLD = 5000
MAX_RENDER_BARS = 1500


def _downsample_ohlcv(df: pd.DataFrame, target_bars: int = MAX_RENDER_BARS) -> pd.DataFrame:
    """Aggregate ``df`` down to ~``target_bars`` rows via fixed row-block groups.

    Row-block aggregation (rather than time-based ``resample``) keeps exactly
    ~target_bars points regardless of weekend/holiday gaps and never introduces
    empty buckets. OHLCV columns use canonical agg; boolean signal columns use
    ``max`` (a block counts as a signal if any bar in it fired); every other
    column carries its last value forward — an overview-grade approximation
    that keeps the frame's shape intact so downstream plot functions never
    ``KeyError``.
    """
    n = len(df)
    if n <= target_bars or target_bars < 1:
        return df
    step = int(np.ceil(n / target_bars))
    if step <= 1:
        return df

    blocks = np.arange(n) // step
    agg_map: Dict[str, str] = {}
    for col in df.columns:
        lc = str(col).lower()
        if lc == 'open':
            agg_map[col] = 'first'
        elif lc == 'high':
            agg_map[col] = 'max'
        elif lc == 'low':
            agg_map[col] = 'min'
        elif lc == 'close':
            agg_map[col] = 'last'
        elif lc == 'volume':
            agg_map[col] = 'sum'
        elif df[col].dtype == bool:
            agg_map[col] = 'max'
        else:
            agg_map[col] = 'last'

    grouped = df.groupby(blocks)
    out = grouped.agg(agg_map)
    # Anchor each block to the timestamp of its last bar so the x-axis and the
    # 'last'-aggregated Close stay consistent.
    out.index = pd.Index([df.index[min((b + 1) * step, n) - 1] for b in range(len(out))], name=df.index.name)
    return out


def _prepare_render_df(df: pd.DataFrame, config: Dict) -> pd.DataFrame:
    """Slice to the visible window (if any) and downsample oversized series.

    A strict identity for any series at/under ``DOWNSAMPLE_THRESHOLD`` so the
    common daily-data path is byte-for-byte unchanged. When a ``view_range``
    (from the relayout zoom store) is supplied we render only that window at
    full detail, downsampling only if the window itself is still huge.
    """
    if df is None or len(df) <= DOWNSAMPLE_THRESHOLD:
        return df

    render_df = df
    view_range = config.get('view_range') or {}
    start, end = view_range.get('start'), view_range.get('end')
    if start and end:
        try:
            s, e = pd.to_datetime(start), pd.to_datetime(end)
            windowed = df.loc[(df.index >= s) & (df.index <= e)]
            if len(windowed) >= 2:
                render_df = windowed
        except (ValueError, TypeError):
            pass

    max_bars = int(config.get('max_render_bars') or MAX_RENDER_BARS)
    if len(render_df) > max_bars:
        render_df = _downsample_ohlcv(render_df, max_bars)
    return render_df


def infer_bar_interval(index: pd.Index) -> str:
    """Best-effort bar-interval label ('1D', '1W', '1H', '15m', …).

    Uses the *median* consecutive gap so weekend/holiday jumps in daily equity
    data still resolve to '1D' rather than being skewed by Fri→Mon gaps.
    """
    if index is None or len(index) < 3:
        return '—'
    try:
        deltas = pd.Series(index[1:]) - pd.Series(index[:-1])
        secs = deltas.median().total_seconds()
    except (TypeError, ValueError, AttributeError):
        return '—'
    if not secs or secs <= 0:
        return '—'

    minute, hour, day = 60, 3600, 86400
    if secs < hour:
        return f"{int(round(secs / minute))}m"
    if secs < day:
        return f"{int(round(secs / hour))}H"
    if secs < 6 * day:
        return f"{int(round(secs / day))}D"
    if secs < 20 * day:
        return "1W"
    return "1M"


def is_subdaily(index: pd.Index) -> bool:
    """True when median bar spacing is under one calendar day."""
    label = infer_bar_interval(index)
    return bool(label.endswith('H') or (len(label) > 1 and label.endswith('m')))


def _median_bar_delta(index: pd.Index) -> pd.Timedelta:
    """Median consecutive gap; falls back to 1 day."""
    if index is None or len(index) < 2:
        return pd.Timedelta(days=1)
    try:
        deltas = pd.Series(index[1:]) - pd.Series(index[:-1])
        med = deltas.median()
        if pd.isna(med) or med <= pd.Timedelta(0):
            return pd.Timedelta(days=1)
        return pd.Timedelta(med)
    except (TypeError, ValueError, AttributeError):
        return pd.Timedelta(days=1)


def _apply_intraday_hover(fig: go.Figure, df: pd.DataFrame) -> None:
    """Upgrade date-only hovertemplates to include time for sub-daily bars."""
    if not is_subdaily(df.index):
        return
    for tr in fig.data:
        ht = getattr(tr, 'hovertemplate', None)
        if isinstance(ht, str) and '%{x|%Y-%m-%d}' in ht and '%H:%M' not in ht:
            tr.hovertemplate = ht.replace('%{x|%Y-%m-%d}', '%{x|%Y-%m-%d %H:%M}')


def bar_count_summary(
    df: pd.DataFrame,
    view_range: dict | None = None,
    interval: str | None = None,
) -> str:
    """Toolbar string like ``1,247 bars · 1D · 2018-01-02 → 2024-12-31``.

    Reflects the visible window when a ``view_range`` (zoom store) is active,
    otherwise the full series. When the Plotly path downsamples (full series
    above ``DOWNSAMPLE_THRESHOLD`` and the render window still exceeds
    ``MAX_RENDER_BARS``), appends ``(showing 1,500)`` so the toolbar matches
    what is drawn.

    ``interval`` is the bar size the data was actually fetched at. Prefer it
    over ``infer_bar_interval``: a 4h series has only two bars per regular
    session, so half its gaps are the 20h overnight jump and the median lands
    on ``20H``. Inference stays the fallback for callers without that context.
    """
    if df is None or len(df) == 0:
        return ''
    interval = interval.upper() if interval else infer_bar_interval(df.index)
    visible = df
    if view_range:
        start, end = view_range.get('start'), view_range.get('end')
        if start and end:
            try:
                s, e = pd.to_datetime(start), pd.to_datetime(end)
                windowed = df.loc[(df.index >= s) & (df.index <= e)]
                if len(windowed) > 0:
                    visible = windowed
            except (ValueError, TypeError):
                pass
    n = len(visible)
    # Mirror _prepare_render_df: downsample only engages above threshold,
    # and only when the (possibly zoomed) window is still over the cap.
    downsampled = (
        len(df) > DOWNSAMPLE_THRESHOLD and n > MAX_RENDER_BARS
    )
    bars_label = (
        f"{n:,} bars (showing {MAX_RENDER_BARS:,})" if downsampled else f"{n:,} bars"
    )
    try:
        start_ts = pd.to_datetime(visible.index[0])
        end_ts = pd.to_datetime(visible.index[-1])
        if is_subdaily(df.index):
            start_s = start_ts.strftime('%Y-%m-%d %H:%M')
            end_s = end_ts.strftime('%Y-%m-%d %H:%M')
        else:
            start_s = start_ts.strftime('%Y-%m-%d')
            end_s = end_ts.strftime('%Y-%m-%d')
    except (ValueError, TypeError, IndexError):
        return f"{bars_label} · {interval}"
    return f"{bars_label} · {interval} · {start_s} → {end_s}"


def _get_indicator_setting(config: Dict, indicator: str, key: str, default: float | int) -> float | int:
    settings = config.get('indicator_settings', {}) or {}
    return settings.get(indicator, {}).get(key, default)


def _coerce_period(value: float | int, default: int) -> int:
    try:
        return max(1, int(round(float(value))))
    except (TypeError, ValueError):
        return default


def _hex_with_alpha(color: str, alpha_hex: str = "10") -> str:
    """Convert a 6-char hex color + alpha hex suffix to an rgba() string.

    Plotly's ``fillcolor`` validator rejects 8-char ``#RRGGBBAA`` hex values,
    so we expand to ``rgba(R, G, B, A)`` where alpha is alpha_hex / 0xFF.
    """
    if not isinstance(color, str) or not color.startswith("#"):
        return color
    hex_body = color.lstrip("#")
    if len(hex_body) != 6:
        return color
    try:
        alpha = int(alpha_hex, 16) / 255.0
    except ValueError:
        return color
    r, g, b = int(hex_body[0:2], 16), int(hex_body[2:4], 16), int(hex_body[4:6], 16)
    return f"rgba({r}, {g}, {b}, {alpha:.3f})"


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
        # Phase 8: cap rendered points for oversized series (no-op for the
        # daily-data common path). Downstream helpers all read this `df`.
        df = _prepare_render_df(df, config)

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

        # NOTE: a previous version reassigned every trace to xaxis='x'
        # (`fig.update_traces(xaxis='x')`) and then rewrote the subplot
        # x-axes' `matches` chain so the price subplot's x became the
        # reference. That left every trace on (xaxis='x', yaxis='yN')
        # while yN remained anchored to xN — a cross-axis configuration
        # that Plotly 6.x refuses to draw: the SVG canvas is created with
        # the right size and the traces are serialised into it, but no
        # geometry is painted, so the chart area stays the background
        # colour (black on the dark theme). `hovermode='x unified'` below
        # already merges every subplot's tooltip into one column when the
        # x-axes are shared via make_subplots(shared_xaxes=True), so the
        # reassignment is unnecessary as well as broken. Keep the traces
        # on their native subplot axes.

        # Force a uniform hover-label style on every trace. In `x unified`
        # mode Plotly otherwise inherits a per-row text color from each
        # trace's own line color, which makes dim overlays (e.g. SMA LONG)
        # render their value text in a color nearly identical to the
        # tooltip background and effectively invisible. Hard-code white so
        # the value column is always readable regardless of theme.
        fig.update_traces(
            hoverlabel=dict(
                bgcolor=theme['bg_tertiary'],
                font=dict(size=12, family=FONT_FAMILY, color='#FFFFFF'),
                bordercolor=theme['border_primary'],
            )
        )

        _add_range_selector(fig, plot_count, theme, df=df)
        _update_layout(fig, df, plot_count, config.get('show_legend', False), config, theme)
        _add_crosshair(fig, plot_count, theme)
        _apply_intraday_hover(fig, df)

        # Phase 8: when rendering a zoomed window (large-data path), pin the
        # x-axis to that window so _update_layout's full-range reset doesn't
        # snap the view back to ALL. Harmless on the common path where no
        # view_range is supplied.
        view_range = config.get('view_range') or {}
        vr_start, vr_end = view_range.get('start'), view_range.get('end')
        if vr_start and vr_end:
            try:
                fig.update_xaxes(
                    range=[pd.to_datetime(vr_start), pd.to_datetime(vr_end)],
                    row=plot_count, col=1,
                )
            except (ValueError, TypeError):
                pass

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
        opacity=0.6,
        hovertemplate='%{x|%Y-%m-%d}<br>Vol: %{y:,.0f}<extra></extra>'
    ), row=row, col=col)
    if config.get('show_volume_ma', False) and ma_period > 1:
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
        fillcolor=_hex_with_alpha(theme['accent_cyan'], '10'),
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
                textfont=dict(color=theme['text_primary'], size=11, family=FONT_FAMILY),
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
                textfont=dict(color=muted_color, size=11, family=FONT_FAMILY),
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


def _add_range_selector(
    fig: go.Figure,
    plot_count: int,
    theme: dict,
    df: pd.DataFrame | None = None,
) -> None:
    """Add time range selector buttons to the canonical (bottom) shared x-axis.

    With ``make_subplots(shared_xaxes=True)`` every row's xaxis is created
    with ``matches='x{plot_count}'`` — the bottom row's axis is the
    canonical driver and every upper axis is a follower. Plotly's range
    buttons only update the axis they are physically attached to; if they
    sit on a follower axis the ``matches`` constraint immediately reverts
    the new range to mirror the driver, so the chart appears not to move
    (the selector still highlights the clicked button, which masks the
    bug). Attach the selector to ``xaxis{plot_count}`` so clicks actually
    pan/zoom the visible window. ``rangeselector.x``/``y`` are in
    normalized paper coordinates, so the buttons stay visually at the top
    of the figure regardless of which subplot owns them.
    """
    subdaily = bool(df is not None and is_subdaily(df.index))
    if subdaily:
        buttons = [
            dict(count=5, label="5D", step="day", stepmode="backward"),
            dict(count=1, label="1M", step="month", stepmode="backward"),
            dict(count=3, label="3M", step="month", stepmode="backward"),
            dict(step="all", label="ALL"),
        ]
    else:
        buttons = [
            dict(count=1, label="1M", step="month", stepmode="backward"),
            dict(count=3, label="3M", step="month", stepmode="backward"),
            dict(count=6, label="6M", step="month", stepmode="backward"),
            dict(count=1, label="YTD", step="year", stepmode="todate"),
            dict(count=1, label="1Y", step="year", stepmode="backward"),
            dict(step="all", label="ALL"),
        ]

    fig.update_xaxes(
        rangeselector=dict(
            buttons=list(buttons),
            bgcolor='rgba(0,0,0,0)',
            activecolor=theme['accent_blue'],
            font=dict(color=theme['text_secondary'], size=11, family=FONT_FAMILY),
            bordercolor=theme['border_primary'],
            borderwidth=1,
            x=0,
            y=1.08,
            xanchor='left',
            yanchor='bottom'
        ),
        rangeslider_visible=False,
        type="date",
        row=plot_count, col=1
    )


def _update_layout(fig: go.Figure, df: pd.DataFrame, plot_count: int, show_legend: bool, config: Dict, theme: dict) -> None:
    """Update figure layout with professional styling."""
    title_text = config.get('title', '')

    fig.update_layout(
        template='plotly_dark',
        autosize=True,
        showlegend=show_legend,
        plot_bgcolor=theme['bg_primary'],
        paper_bgcolor=theme['bg_primary'],
        margin=dict(l=60, r=20, t=76 if title_text else 56, b=36),
        font=dict(family=FONT_FAMILY, color=theme['text_primary'], size=12),
        hoverlabel=dict(
            bgcolor=theme['bg_tertiary'],
            font=dict(size=12, family=FONT_FAMILY, color='#FFFFFF'),
            bordercolor=theme['border_primary'],
            align='left',
        ),
        hovermode='x unified',
        title=dict(
            text=title_text,
            x=0.5,
            xanchor='center',
            font=dict(size=14, color=theme['text_primary'], family=FONT_FAMILY)
        ) if title_text else None,
        legend=dict(
            orientation="h",
            yanchor="bottom",
            y=1.02,
            xanchor="right",
            x=1,
            bgcolor='rgba(0,0,0,0)',
            font=dict(size=11, family=FONT_FAMILY)
        ) if show_legend else None,
    )

    for i in range(1, plot_count + 1):
        x_kwargs: Dict[str, Any] = dict(
            rangeslider_visible=False,
            showgrid=True,
            gridcolor=theme['chart_grid'],
            gridwidth=0.5,
            griddash='dot',
            showline=True,
            linecolor=theme['border_primary'],
            linewidth=1,
            zeroline=False,
            tickfont=dict(color=theme['text_secondary'], size=11, family=FONT_FAMILY),
            ticks='outside',
            ticklen=4,
            row=i, col=1,
        )
        if is_subdaily(df.index):
            # Hide weekends so 1H/4H charts don't show empty Sat–Sun stretches.
            x_kwargs['rangebreaks'] = [dict(bounds=["sat", "mon"])]
            x_kwargs['tickformat'] = '%b %d\n%H:%M'
            x_kwargs['nticks'] = 10
        fig.update_xaxes(**x_kwargs)
        fig.update_yaxes(
            showgrid=True,
            gridcolor=theme['chart_grid'],
            gridwidth=0.5,
            griddash='dot',
            showline=True,
            linecolor=theme['border_primary'],
            linewidth=1,
            zeroline=False,
            tickfont=dict(color=theme['text_secondary'], size=11, family=FONT_FAMILY),
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
            text=str(annotation.text or '').upper(),
            font=dict(size=11, color=theme['text_secondary'], family=FONT_FAMILY),
            x=0.01,
            xanchor='left'
        )

    # make_subplots(shared_xaxes=True) already wires the subplot x-axes
    # together correctly (every row's xaxis.matches points at the bottom
    # row's x-axis, which is the canonical Plotly sharing layout). The
    # previous trace-reassignment + matches-rewrite here fought that
    # structure and produced a cross-axis configuration (traces on
    # xaxis='x' with yN anchored to xN) that Plotly 6.x draws as a blank
    # canvas. Leave the shared-axes layout untouched.

    # Pin the bottom row's x-axis to the data range plus a small right-side
    # buffer so Plotly's default ~5% autorange padding stops adding an empty
    # rectangle past the rightmost candle. Scale the pad to bar size so
    # intraday charts don't get a multi-day empty strip.
    right_pad = _median_bar_delta(df.index) * 3
    fig.update_xaxes(
        range=[df.index.min(), df.index.max() + right_pad],
        row=plot_count, col=1,
    )


def _add_crosshair(fig: go.Figure, plot_count: int, theme: dict) -> None:
    """Add crosshair spikes across all subplot x-axes."""
    for i in range(1, plot_count + 1):
        fig.update_xaxes(
            showspikes=True,
            spikecolor=theme['accent_blue'],
            spikethickness=1,
            spikemode="across",
            spikesnap="cursor",
            spikedash="dash",
            row=i, col=1
        )
        fig.update_yaxes(
            showspikes=False,
            row=i, col=1
        )


def create_empty_chart(theme: dict, message: str = "Load data to view chart") -> go.Figure:
    """Create an empty chart with a placeholder message.

    Layout knobs (``autosize``, margins) match ``_update_layout`` so the
    placeholder fills ``#chart-frame`` the same way a live multi-panel chart does.
    """
    fig = go.Figure()
    fig.update_layout(
        template='plotly_dark',
        autosize=True,
        margin=dict(l=60, r=20, t=56, b=36),
        plot_bgcolor=theme['bg_primary'],
        paper_bgcolor=theme['bg_primary'],
        font=dict(color=theme['text_secondary'], family=FONT_FAMILY),
        xaxis=dict(showgrid=False, visible=False),
        yaxis=dict(showgrid=False, visible=False),
        annotations=[dict(
            text=message,
            xref="paper", yref="paper",
            x=0.5, y=0.5,
            showarrow=False,
            font=dict(size=14, color=theme['text_tertiary'], family=FONT_FAMILY)
        )]
    )
    return fig
