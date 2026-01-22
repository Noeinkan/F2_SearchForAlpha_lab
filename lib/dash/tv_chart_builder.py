"""
TradingView Lightweight Charts builder utilities.
"""

import logging
from typing import Dict, List, Tuple

import pandas as pd

logger = logging.getLogger(__name__)


def _format_time_index(df: pd.DataFrame) -> List[int]:
    if isinstance(df.index, pd.DatetimeIndex):
        dt_index = df.index
    else:
        dt_index = pd.to_datetime(df.index)
    if dt_index.tz is not None:
        dt_index = dt_index.tz_convert('UTC')
    return (dt_index.view('int64') // 10**9).astype(int).tolist()


def convert_volume_to_tv_format(df: pd.DataFrame, theme: dict) -> Tuple[List, str, Dict]:
    """Convert volume data to histogram format with up/down colors."""
    times = _format_time_index(df)
    colors = [
        theme['chart_candle_up'] if close >= open_ else theme['chart_candle_down']
        for close, open_ in zip(df['Close'], df['Open'])
    ]
    series_data = [
        {'time': t, 'value': float(v), 'color': c}
        for t, v, c in zip(times, df['Volume'], colors)
    ]
    series_type = 'histogram'
    series_options = {
        'priceFormat': {'type': 'volume'},
        'scaleMargins': {'top': 0.8, 'bottom': 0.0},
    }
    return series_data, series_type, series_options


def convert_df_to_tv_format(df: pd.DataFrame, config: Dict, theme: dict) -> Tuple[List, List, List, List]:
    """
    Convert DataFrame to TradingView format.
    Returns: (seriesData, seriesTypes, seriesOptions, seriesMarkers)
    """
    times = _format_time_index(df)

    series_data: List[List[Dict]] = []
    series_types: List[str] = []
    series_options: List[Dict] = []
    series_markers: List[List[Dict]] = []

    if config.get('show_candlesticks', True):
        ohlc_data = [
            {
                'time': t,
                'open': float(o),
                'high': float(h),
                'low': float(l),
                'close': float(c)
            }
            for t, o, h, l, c in zip(times, df['Open'], df['High'], df['Low'], df['Close'])
        ]
        series_data.append(ohlc_data)
        series_types.append('candlestick')
        series_options.append({
            'upColor': theme['chart_candle_up'],
            'downColor': theme['chart_candle_down'],
            'borderUpColor': theme['chart_candle_up'],
            'borderDownColor': theme['chart_candle_down'],
            'wickUpColor': theme['chart_candle_up'],
            'wickDownColor': theme['chart_candle_down'],
        })

        markers: List[Dict] = []
        if config.get('show_buy_sell_signals', False):
            selected_signals = config.get('selected_signals', [])
            buy_signal_columns = config.get('buy_signal_columns', [])
            sell_signal_columns = config.get('sell_signal_columns', [])

            color_palette = [
                theme['accent_blue'],
                theme['accent_green'],
                theme['accent_orange'],
                theme['accent_purple'],
                theme['accent_cyan'],
                theme['accent_red']
            ]

            def _strategy_color(index: int) -> str:
                return color_palette[index % len(color_palette)]

            def _strategy_label(column_name: str) -> str:
                base = column_name.rsplit('_', 1)[0]
                label = base.replace('_', ' ')
                return label[:8]

            if 'buy' in selected_signals:
                for idx, col_name in enumerate(buy_signal_columns):
                    if col_name not in df.columns:
                        continue
                    buy_rows = df[df[col_name] == 1]
                    if buy_rows.empty:
                        continue
                    buy_times = _format_time_index(buy_rows)
                    for t in buy_times:
                        markers.append({
                            'time': t,
                            'position': 'belowBar',
                            'shape': 'arrowUp',
                            'color': _strategy_color(idx),
                            'text': _strategy_label(col_name)
                        })

            if 'sell' in selected_signals:
                for idx, col_name in enumerate(sell_signal_columns):
                    if col_name not in df.columns:
                        continue
                    sell_rows = df[df[col_name] == 1]
                    if sell_rows.empty:
                        continue
                    sell_times = _format_time_index(sell_rows)
                    for t in sell_times:
                        markers.append({
                            'time': t,
                            'position': 'aboveBar',
                            'shape': 'arrowDown',
                            'color': _strategy_color(idx),
                            'text': _strategy_label(col_name)
                        })
        series_markers.append(markers)

    def _add_line_series(column: str, color: str, label: str) -> None:
        if column not in df.columns:
            return
        series_data.append([
            {'time': t, 'value': float(v)}
            for t, v in zip(times, df[column])
        ])
        series_types.append('line')
        series_options.append({
            'color': color,
            'lineWidth': 1.5,
            'title': label
        })
        series_markers.append([])

    if config.get('show_bollinger', False):
        _add_line_series('BB_upper', theme['accent_green'], 'BB Upper')
        _add_line_series('BB_lower', theme['accent_red'], 'BB Lower')
        _add_line_series('BB_middle', theme['text_secondary'], 'BB Middle')

    if config.get('show_sma', False):
        sma_colors = [theme['accent_red'], theme['accent_green'], theme['accent_blue'], theme['accent_purple']]
        for color, period in zip(sma_colors, ['short', 'medium', 'long', 'trend']):
            _add_line_series(f'SMA_{period}', color, f'SMA {period.upper()}')

    if config.get('show_ema', False):
        ema_colors = [theme['accent_orange'], theme['accent_cyan'], theme['accent_purple']]
        for color, period in zip(ema_colors, ['short', 'medium', 'long']):
            _add_line_series(f'EMA_{period}', color, f'EMA {period.upper()}')

    return series_data, series_types, series_options, series_markers


def get_tv_chart_options(theme: dict) -> Dict:
    """Get chart options matching dashboard theme."""
    return {
        'layout': {
            'background': {'type': 'solid', 'color': theme['chart_bg']},
            'textColor': theme['text_secondary'],
            'fontSize': 12,
        },
        'grid': {
            'vertLines': {'color': theme['chart_grid']},
            'horzLines': {'color': theme['chart_grid']},
        },
        'rightPriceScale': {
            'borderColor': theme['border_primary'],
        },
        'timeScale': {
            'borderColor': theme['border_primary'],
        },
        'crosshair': {
            'mode': 1,
            'vertLine': {
                'color': theme['text_tertiary'],
                'width': 1,
                'style': 2,
                'labelBackgroundColor': theme['bg_tertiary'],
            },
            'horzLine': {
                'color': theme['text_tertiary'],
                'width': 1,
                'style': 2,
                'labelBackgroundColor': theme['bg_tertiary'],
            }
        }
    }
