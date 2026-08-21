"""Build the JSON payload the Lightweight Charts glue renders.

Replaces the old Plotly ``chart_builder.create_chart``. Python no longer builds
a figure; it ships data and styling and the client draws it, which is what lets
pan/zoom/crosshair run without a server round-trip.

Consumes the same ``config`` dict the sidebar already produces (see
``callbacks.chart_plotly._build_chart_config``), so no sidebar wiring changed.

Payload contract — consumed by ``assets/10-sfa-chart.js``::

    {
      "meta":    {"ticker","interval","subdaily","bars","precision"},
      "theme":   {"bg","grid","text_secondary","text_tertiary","border","accent","up","down","font"},
      "panes":   [{"key","height"}, ...],          # index order == pane order
      "candles": [{"time","open","high","low","close"}, ...],
      "volumes": [{"time","value"}, ...],          # legend readout only
      "series":  [{"id","pane","type","options","data",["priceLines"]}, ...],
      "markers": [{"time","position","shape","color","text","size"}, ...],
    }
"""

from __future__ import annotations

import logging
import math
from typing import Any, Dict, List

import numpy as np
import pandas as pd
from ta.momentum import RSIIndicator, StochasticOscillator
from ta.trend import ADXIndicator, CCIIndicator, MACD
from ta.volatility import AverageTrueRange
from ta.volume import VolumeWeightedAveragePrice

from lib.dash.chart_meta import infer_bar_interval, is_subdaily
from lib.dash.dash_config import FONT_FAMILY
from lib.dash.overlay_registry import build_overlay_visibility, get_tv_overlay_specs
from lib.dash.signal_markers import resolve_triggers

logger = logging.getLogger(__name__)

# Price pane is 4.5x an indicator pane, matching the old subplot row heights.
PANE_HEIGHT_MAIN = 4.5
PANE_HEIGHT_INDICATOR = 1.0

# Panes the sidebar can enable, in the order they should stack under price.
INDICATOR_PANES = ('volume', 'rsi', 'cci', 'stoch', 'macd', 'vwap', 'adx', 'atr', 'obv')


# ------------------------------------------------------------------ scalars

def _num(value: Any, digits: int = 4) -> float | None:
    """JSON-safe float. NaN/inf become ``None`` so the client skips the point."""
    if value is None:
        return None
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if math.isnan(f) or math.isinf(f):
        return None
    return round(f, digits)


def _get_setting(config: Dict, indicator: str, key: str, default: float | int) -> float | int:
    settings = config.get('indicator_settings', {}) or {}
    return (settings.get(indicator, {}) or {}).get(key, default)


def _period(value: Any, default: int) -> int:
    try:
        period = int(value)
        return period if period >= 1 else default
    except (TypeError, ValueError):
        return default


def _price_precision(close: pd.Series) -> int:
    """Decimals to show. Sub-dollar instruments need more than equities do."""
    try:
        typical = float(close.dropna().abs().median())
    except (TypeError, ValueError):
        return 2
    if not typical or math.isnan(typical):
        return 2
    if typical >= 100:
        return 2
    if typical >= 1:
        return 2
    if typical >= 0.01:
        return 4
    return 6


# --------------------------------------------------------------------- time

def encode_times(index: pd.DatetimeIndex, subdaily: bool) -> List[Any]:
    """Encode a DatetimeIndex the way Lightweight Charts expects it.

    Daily bars use ``'YYYY-MM-DD'`` business-day strings. Intraday bars use UNIX
    seconds — and LWC renders numeric time as UTC, with no timezone option. The
    frames here are tz-naive *exchange-local* (``resample_ohlcv`` strips tz), so
    we localize as UTC rather than converting: that makes the axis read 09:30 →
    15:30 for a US session, which is what a trader expects, instead of shifting
    everything by the local UTC offset.
    """
    idx = pd.DatetimeIndex(index)
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    if not subdaily:
        return [d.strftime('%Y-%m-%d') for d in idx]
    # Casting the *naive* index straight to seconds reads the wall clock as UTC,
    # which is the localize-as-UTC behaviour described above — no tz round-trip
    # needed. Cast explicitly rather than dividing raw int64 by a hard-coded
    # 10**9: pandas 3 builds DatetimeIndex at microsecond resolution by default,
    # so the underlying integer unit is not something to assume.
    return [int(v) for v in idx.astype('datetime64[s]').astype('int64')]


def _dedupe_ascending(df: pd.DataFrame) -> pd.DataFrame:
    """LWC silently corrupts on unordered or duplicate timestamps.

    A 4h resample straddling a DST boundary, or two fetches stitched together,
    can produce both. Cheap to normalise here; near-impossible to debug from the
    canvas.
    """
    if not isinstance(df.index, pd.DatetimeIndex):
        return df
    if not df.index.is_monotonic_increasing:
        logger.warning("Chart payload: index not ascending; sorting")
        df = df.sort_index()
    if df.index.has_duplicates:
        logger.warning("Chart payload: duplicate timestamps; keeping last")
        df = df[~df.index.duplicated(keep='last')]
    return df


# ------------------------------------------------------------------- series

def _line_points(times: List[Any], values: pd.Series, digits: int = 4) -> List[dict]:
    """``{time, value}`` points, dropping NaN (indicator warm-up) entirely."""
    out = []
    for t, v in zip(times, values.to_numpy()):
        num = _num(v, digits)
        if num is not None:
            out.append({'time': t, 'value': num})
    return out


def _line_spec(pane: str, name: str, times, values, color, *, width=1.5,
               style: str | None = None, digits: int = 4, price_lines=None) -> dict:
    spec = {
        'id': f'{pane}:{name}',
        'pane': pane,
        'type': 'Line',
        'options': {
            'title': name,
            'color': color,
            'lineWidth': width,
            'priceLineVisible': False,
            'lastValueVisible': False,
        },
        'data': _line_points(times, values, digits),
    }
    if style == 'dotted':
        spec['options']['lineStyle'] = 1
    if price_lines:
        spec['priceLines'] = price_lines
    return spec


def _threshold(price: float, color: str, title: str, style: str = 'dashed') -> dict:
    return {'price': _num(price, 4), 'color': color, 'title': title,
            'style': style, 'lineWidth': 1, 'axisLabel': True}


# ---------------------------------------------------------------- indicators

def _volume_alpha(rvol: float | None) -> str:
    """Map relative volume (vol / SMA) to a hex alpha suffix for histogram bars."""
    if rvol is None:
        return '99'
    try:
        r = float(rvol)
    except (TypeError, ValueError):
        return '99'
    if math.isnan(r) or math.isinf(r) or r < 0:
        return '99'
    if r < 0.75:
        return '55'
    if r < 1.25:
        return '99'
    if r < 2.0:
        return 'CC'
    return 'FF'


def _volume_series(df, times, config, theme) -> List[dict]:
    up, down = theme['chart_candle_up'], theme['chart_candle_down']
    ma_period = _period(_get_setting(config, 'volume', 'ma_period', 20), 20)
    ma = df['Volume'].rolling(window=ma_period, min_periods=1).mean()

    bars = []
    closes, opens = df['Close'].to_numpy(), df['Open'].to_numpy()
    volumes = df['Volume'].to_numpy()
    ma_vals = ma.to_numpy()
    for t, v, c, o, m in zip(times, volumes, closes, opens, ma_vals):
        num = _num(v, 0)
        if num is None:
            continue
        try:
            m_f = float(m)
            rvol = (float(v) / m_f) if m_f > 0 and not math.isnan(m_f) else None
        except (TypeError, ValueError):
            rvol = None
        hue = up if c > o else down
        bars.append({'time': t, 'value': num, 'color': hue + _volume_alpha(rvol)})

    specs = [{
        'id': 'volume',
        'pane': 'volume',
        'type': 'Histogram',
        'options': {
            'title': 'Volume',
            'priceFormat': {'type': 'volume'},
            'priceLineVisible': False,
            'lastValueVisible': False,
        },
        'data': bars,
    }]

    if config.get('show_volume_ma', False) and ma_period > 1:
        specs.append(_line_spec('volume', f'Vol MA ({ma_period})', times, ma,
                                theme['text_secondary'], width=1.2, style='dotted',
                                digits=0))
    return specs


def _rsi_series(df, times, config, theme) -> List[dict]:
    period = _period(_get_setting(config, 'rsi', 'period', 14), 14)
    overbought = _get_setting(config, 'rsi', 'overbought', 70)
    oversold = _get_setting(config, 'rsi', 'oversold', 30)
    values = RSIIndicator(close=df['Close'], window=period).rsi()
    return [_line_spec(
        'rsi', f'RSI ({period})', times, values, theme['accent_purple'], digits=2,
        price_lines=[
            _threshold(overbought, theme['accent_red'], 'OB'),
            _threshold(oversold, theme['accent_green'], 'OS'),
            _threshold(50, theme['text_tertiary'], '', style='dotted'),
        ],
    )]


def _cci_series(df, times, config, theme) -> List[dict]:
    period = _period(_get_setting(config, 'cci', 'period', 20), 20)
    ceiling = _get_setting(config, 'cci', 'ceiling', 100)
    floor = _get_setting(config, 'cci', 'floor', -100)
    values = CCIIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=period).cci()
    return [_line_spec(
        'cci', f'CCI ({period})', times, values, theme['accent_orange'], digits=2,
        price_lines=[
            _threshold(ceiling, theme['accent_red'], '+'),
            _threshold(floor, theme['accent_green'], '-'),
            _threshold(0, theme['text_tertiary'], '', style='dotted'),
        ],
    )]


def _stoch_series(df, times, config, theme) -> List[dict]:
    period = _period(_get_setting(config, 'stoch', 'period', 14), 14)
    smooth = _period(_get_setting(config, 'stoch', 'smooth_window', 3), 3)
    overbought = _get_setting(config, 'stoch', 'overbought', 80)
    oversold = _get_setting(config, 'stoch', 'oversold', 20)
    stoch = StochasticOscillator(
        high=df['High'], low=df['Low'], close=df['Close'],
        window=period, smooth_window=smooth,
    )
    return [
        _line_spec(
            'stoch', f'%K ({period})', times, stoch.stoch(), theme['accent_blue'], digits=2,
            price_lines=[
                _threshold(overbought, theme['accent_red'], 'OB'),
                _threshold(oversold, theme['accent_green'], 'OS'),
            ],
        ),
        _line_spec('stoch', f'%D ({smooth})', times, stoch.stoch_signal(),
                   theme['accent_orange'], width=1.1, digits=2),
    ]


def _macd_series(df, times, config, theme) -> List[dict]:
    fast = _period(_get_setting(config, 'macd', 'fast', 12), 12)
    slow = _period(_get_setting(config, 'macd', 'slow', 26), 26)
    signal = _period(_get_setting(config, 'macd', 'signal', 9), 9)
    macd = MACD(close=df['Close'], window_slow=slow, window_fast=fast, window_sign=signal)

    hist = macd.macd_diff()
    up, down = theme['chart_candle_up'], theme['chart_candle_down']
    bars = []
    for t, v in zip(times, hist.to_numpy()):
        num = _num(v, 6)
        if num is not None:
            bars.append({'time': t, 'value': num, 'color': (up if num >= 0 else down) + '99'})

    return [
        {
            'id': 'macd:hist',
            'pane': 'macd',
            'type': 'Histogram',
            'options': {'title': 'Histogram', 'priceLineVisible': False,
                        'lastValueVisible': False,
                        'priceFormat': {'type': 'price', 'precision': 4, 'minMove': 0.0001}},
            'data': bars,
        },
        _line_spec('macd', f'MACD ({fast},{slow})', times, macd.macd(),
                   theme['accent_cyan'], digits=6,
                   price_lines=[_threshold(0, theme['text_tertiary'], '', style='dotted')]),
        _line_spec('macd', f'Signal ({signal})', times, macd.macd_signal(),
                   theme['accent_orange'], digits=6),
    ]


def _vwap_series(df, times, config, theme) -> List[dict]:
    window = _period(_get_setting(config, 'vwap', 'window', 20), 20)
    values = VolumeWeightedAveragePrice(
        high=df['High'], low=df['Low'], close=df['Close'],
        volume=df['Volume'].fillna(0), window=window,
    ).volume_weighted_average_price()
    return [
        _line_spec('vwap', f'VWAP ({window})', times, values, theme['text_primary'],
                   width=1.6, digits=2),
        _line_spec('vwap', 'Close', times, df['Close'], theme['text_secondary'],
                   width=1.1, style='dotted', digits=2),
    ]


def _strategy_column(df: pd.DataFrame, column: str) -> pd.Series | None:
    """Return a strategy-written column, or None when absent or all-NaN.

    The ADX/ATR/OBV panes prefer the columns the signal strategies wrote so the
    plotted line is the *same* series the signal fired from. They fall back to a
    local recompute for bare frames (chart previews before signals run).
    """
    if column not in df.columns:
        return None
    series = pd.to_numeric(df[column], errors='coerce')
    if not series.notna().any():
        return None
    return series


def _adx_series(df, times, config, theme) -> List[dict]:
    period = _period(_get_setting(config, 'adx', 'period', 14), 14)
    threshold = _get_setting(config, 'adx', 'threshold', 25)
    range_threshold = _get_setting(config, 'adx', 'range_threshold', 20)

    values = _strategy_column(df, 'ADX')
    pos_di = _strategy_column(df, 'ADX_Pos_DI')
    neg_di = _strategy_column(df, 'ADX_Neg_DI')
    if values is None or pos_di is None or neg_di is None:
        indicator = ADXIndicator(high=df['High'], low=df['Low'], close=df['Close'], window=period)
        values = indicator.adx()
        pos_di = indicator.adx_pos()
        neg_di = indicator.adx_neg()

    return [
        _line_spec(
            # Neutral strength line — not directional (direction lives on ±DI).
            'adx', f'ADX ({period})', times, values, theme['text_primary'], digits=2,
            price_lines=[
                _threshold(threshold, theme['text_tertiary'], 'TREND'),
                _threshold(range_threshold, theme['text_tertiary'], 'RANGE', style='dotted'),
            ],
        ),
        # ADX_DICross_* is built entirely from these two lines, so plot them.
        _line_spec('adx', '+DI', times, pos_di, theme['chart_candle_up'], width=1.1, digits=2),
        _line_spec('adx', '-DI', times, neg_di, theme['chart_candle_down'], width=1.1, digits=2),
    ]


def _atr_series(df, times, config, theme) -> List[dict]:
    """Normalised ATR% against the mean the expansion/compression gates use.

    Plots ``ATR_Pct`` / ``ATR_Pct_MA`` rather than raw ATR and a rolling mean of
    it: those are the two series ``ATR_Expansion_*`` and ``ATR_Compression_*``
    actually compare, so a crossing on this pane corresponds to a signal, and
    tuning ``expansion_lookback`` visibly moves the line.
    """
    period = _period(_get_setting(config, 'atr', 'period', 14), 14)
    lookback = _period(_get_setting(config, 'atr', 'expansion_lookback', 20), 20)
    expansion_factor = float(_get_setting(config, 'atr', 'expansion_factor', 1.2))
    compression_factor = float(_get_setting(config, 'atr', 'compression_factor', 0.9))

    atr_pct = _strategy_column(df, 'ATR_Pct')
    atr_pct_ma = _strategy_column(df, 'ATR_Pct_MA')
    if atr_pct is None or atr_pct_ma is None:
        atr = AverageTrueRange(high=df['High'], low=df['Low'], close=df['Close'],
                               window=period).average_true_range()
        warm_atr = atr.where(atr > 0)
        atr_pct = (warm_atr / df['Close'].replace(0, np.nan)).replace([np.inf, -np.inf], np.nan)
        atr_pct_ma = atr_pct.rolling(window=lookback, min_periods=lookback).mean()

    atr_pct = atr_pct * 100
    atr_pct_ma = atr_pct_ma * 100
    cyan = theme['accent_cyan']
    return [
        {
            'id': 'atr:value',
            'pane': 'atr',
            'type': 'Area',
            'options': {
                'title': f'ATR% ({period})',
                'lineColor': cyan, 'lineWidth': 1.5,
                'topColor': cyan + '33', 'bottomColor': cyan + '05',
                'priceLineVisible': False, 'lastValueVisible': False,
            },
            'data': _line_points(times, atr_pct, 3),
        },
        _line_spec('atr', f'ATR% MA ({lookback})', times, atr_pct_ma,
                   theme['text_secondary'], width=1.1, style='dotted', digits=3),
        # The gate levels themselves — where Expansion / Compression actually fire.
        _line_spec('atr', f'Expansion (x{expansion_factor:g})', times,
                   atr_pct_ma * expansion_factor,
                   theme['accent_orange'], width=1, style='dotted', digits=3),
        _line_spec('atr', f'Compression (x{compression_factor:g})', times,
                   atr_pct_ma * compression_factor,
                   theme['accent_purple'], width=1, style='dotted', digits=3),
    ]


# Okabe–Ito sky — OBV identity, distinct from RSI purple / MACD+ATR cyan.
_OBV_COLOR = '#56B4E9'


def _obv_series(df, times, config, theme) -> List[dict]:
    ma_period = _period(_get_setting(config, 'obv', 'ma_period', 20), 20)

    obv = _strategy_column(df, 'OBV')
    if obv is None:
        obv = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()

    specs = [_line_spec('obv', 'OBV', times, obv, _OBV_COLOR, digits=0)]
    if ma_period > 1:
        obv_ma = _strategy_column(df, 'OBV_MA')
        if obv_ma is None:
            # min_periods=ma_period, matching OBV_TradingStrategy — a chart MA
            # drawn through the warmup would show a cross the strategy cannot see.
            obv_ma = obv.rolling(window=ma_period, min_periods=ma_period).mean()
        specs.append(_line_spec('obv', f'OBV MA ({ma_period})', times, obv_ma,
                                theme['text_secondary'], width=1.1, style='dotted',
                                digits=0))
    return specs


_PANE_BUILDERS = {
    'volume': _volume_series,
    'rsi': _rsi_series,
    'cci': _cci_series,
    'stoch': _stoch_series,
    'macd': _macd_series,
    'vwap': _vwap_series,
    'adx': _adx_series,
    'atr': _atr_series,
    'obv': _obv_series,
}


# ------------------------------------------------------------------ markers

def _build_markers(df, times, config, theme) -> List[dict]:
    """Buy/sell markers, including the muted 'filtered' (rejected) ones.

    LWC positions markers relative to the bar, so the old ``Close * 1.5%``
    offset arithmetic is gone — ``aboveBar``/``belowBar`` does it properly at
    any zoom level.
    """
    if not config.get('show_buy_sell_signals', False):
        return []

    selected = set(config.get('selected_signals') or [])
    sides = {
        'buy': {
            'columns': config.get('buy_signal_columns') or [],
            'shape': 'arrowUp', 'position': 'belowBar',
            'color': theme['chart_candle_up'], 'text': 'B',
        },
        'sell': {
            'columns': config.get('sell_signal_columns') or [],
            'shape': 'arrowDown', 'position': 'aboveBar',
            'color': theme['chart_candle_down'], 'text': 'S',
        },
    }

    time_by_pos = list(times)
    markers: List[dict] = []
    for side, cfg in sides.items():
        if side not in selected:
            continue
        accepted, rejected = resolve_triggers(
            df, side, cfg['columns'],
            logic=config.get('signal_logic', 'or'),
            window=config.get('signal_window', 0) or 0,
            mode=config.get('consecutive_signal_mode', 'scale_in'),
            cooldown=config.get('cooldown_bars', 0) or 0,
        )
        for mask, muted in ((accepted, False), (rejected, True)):
            for pos in np.flatnonzero(mask.to_numpy()):
                markers.append({
                    'time': time_by_pos[pos],
                    'position': cfg['position'],
                    'shape': cfg['shape'],
                    # Rejected triggers stay visible but recede, so you can see
                    # what the consecutive-signal rules filtered out.
                    'color': theme['text_tertiary'] if muted else cfg['color'],
                    'text': '' if muted else cfg['text'],
                    'size': 1 if muted else 2,
                })

    # LWC requires markers in ascending time order.
    markers.sort(key=lambda m: (m['time'] if isinstance(m['time'], str) else m['time']))
    return markers


# -------------------------------------------------------------------- entry

def build_chart_payload(df: pd.DataFrame, config: Dict, theme: dict) -> Dict[str, Any]:
    """Translate an enriched OHLCV frame into the client render payload.

    ``config`` keys are the ones ``_build_chart_config`` already emits:
    ``selected_plots``, ``show_candlesticks``, ``overlay_visibility`` (or the
    legacy ``show_bollinger``/``show_sma``/``show_ema`` flags),
    ``show_buy_sell_signals``, ``selected_signals``, ``buy_signal_columns``,
    ``sell_signal_columns``, ``signal_logic``, ``signal_window``,
    ``consecutive_signal_mode``, ``cooldown_bars``, ``indicator_settings``.
    """
    df = _dedupe_ascending(df)
    subdaily = is_subdaily(df.index)
    times = encode_times(df.index, subdaily)
    precision = _price_precision(df['Close'])

    selected = list(config.get('selected_plots') or [])
    panes = [{'key': 'price', 'height': PANE_HEIGHT_MAIN}]
    for key in INDICATOR_PANES:
        if key in selected:
            panes.append({'key': key, 'height': PANE_HEIGHT_INDICATOR})

    candles: List[dict] = []
    if config.get('show_candlesticks', True):
        cols = df[['Open', 'High', 'Low', 'Close']].to_numpy()
        for t, (o, h, low, c) in zip(times, cols):
            o_, h_, l_, c_ = (_num(o, precision), _num(h, precision),
                              _num(low, precision), _num(c, precision))
            if None in (o_, h_, l_, c_):
                continue
            candles.append({'time': t, 'open': o_, 'high': h_, 'low': l_, 'close': c_})
    else:
        # The glue always needs a price series to anchor the crosshair legend
        # and markers; a flat Close line is the honest degenerate case.
        for t, c in zip(times, df['Close'].to_numpy()):
            c_ = _num(c, precision)
            if c_ is not None:
                candles.append({'time': t, 'open': c_, 'high': c_, 'low': c_, 'close': c_})

    series: List[dict] = []

    overlay_visibility = config.get('overlay_visibility') or build_overlay_visibility(
        legacy_flags={
            'show_bollinger': config.get('show_bollinger', False),
            'show_sma': config.get('show_sma', False),
            'show_ema': config.get('show_ema', False),
        }
    )
    for spec in get_tv_overlay_specs(df, theme, overlay_visibility):
        series.append(_line_spec(
            'price', spec['title'], times, df[spec['column']],
            spec['color'], width=spec.get('lineWidth', 1.5),
            style=spec.get('style'), digits=precision,
        ))

    for pane in panes[1:]:
        builder = _PANE_BUILDERS.get(pane['key'])
        if not builder:
            continue
        try:
            series.extend(builder(df, times, config, theme))
        except Exception as exc:   # one bad indicator must not blank the chart
            logger.warning("Chart payload: %s pane failed: %s", pane['key'], exc)
            panes.remove(pane)

    volumes = []
    if 'Volume' in df.columns:
        for t, v in zip(times, df['Volume'].to_numpy()):
            volumes.append({'time': t, 'value': _num(v, 0)})

    return {
        'meta': {
            'ticker': config.get('ticker', ''),
            'interval': config.get('interval') or infer_bar_interval(df.index),
            'subdaily': subdaily,
            'bars': len(df),
            'precision': precision,
        },
        'theme': {
            'bg': theme['chart_bg'],
            'grid': theme['chart_grid'],
            'text_secondary': theme['text_secondary'],
            'text_tertiary': theme['text_tertiary'],
            'border': theme['border_primary'],
            'accent': theme['accent_blue'],
            'up': theme['chart_candle_up'],
            'down': theme['chart_candle_down'],
            'font': FONT_FAMILY,
        },
        'panes': panes,
        'candles': candles,
        'volumes': volumes,
        'series': series,
        'markers': _build_markers(df, times, config, theme),
    }


def empty_payload(theme: dict, message: str = 'Load data to view chart') -> Dict[str, Any]:
    """Placeholder payload. The glue renders the message and no series."""
    return {
        'meta': {'ticker': '', 'interval': '', 'subdaily': False, 'bars': 0,
                 'precision': 2, 'message': message},
        'theme': {
            'bg': theme['chart_bg'],
            'grid': theme['chart_grid'],
            'text_secondary': theme['text_secondary'],
            'text_tertiary': theme['text_tertiary'],
            'border': theme['border_primary'],
            'accent': theme['accent_blue'],
            'up': theme['chart_candle_up'],
            'down': theme['chart_candle_down'],
            'font': FONT_FAMILY,
        },
        'panes': [{'key': 'price', 'height': PANE_HEIGHT_MAIN}],
        'candles': [],
        'volumes': [],
        'series': [],
        'markers': [],
    }
