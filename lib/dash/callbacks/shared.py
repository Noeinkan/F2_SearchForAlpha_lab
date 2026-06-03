"""
Shared helpers for dashboard callback modules.
"""

from __future__ import annotations

import copy
import logging
import re
from collections import OrderedDict
from typing import Tuple, List, Any, Dict, cast

import numpy as np
import pandas as pd
from dash import html, dash_table, dcc

from lib.dash.dash_config import (
    FONT_SIZES,
    FONT_FAMILY,
    DEFAULT_INDICATOR_SETTINGS,
    INDICATOR_SETTING_SCHEMA,
    PLOT_OPTIONS,
)
from lib.dash.preset_storage import normalize_preset
from lib.signals.indicators import add_indicators, generate_signals

logger = logging.getLogger(__name__)


SIGNAL_DESCRIPTIONS: Dict[str, str] = {
    # Bollinger Bands
    "BB_Breakout_Buy": "Price breaks above upper Bollinger Band (momentum breakout).",
    "BB_Breakout_Sell": "Price breaks below lower Bollinger Band (momentum breakdown).",
    "BB_MeanReversion_Buy": "Price crosses back above lower band (mean reversion).",
    "BB_MeanReversion_Sell": "Price crosses back below upper band (mean reversion).",
    "BB_Squeeze_Buy": "Post-squeeze breakout above upper band after narrow bands.",
    "BB_Squeeze_Sell": "Post-squeeze breakdown below lower band after narrow bands.",
    "BB_DoubleBottom_Buy": "Two lower-band touches with a rebound (double bottom).",
    "BB_DoubleTop_Sell": "Two upper-band touches with a drop (double top).",
    # MACD
    "MACD_ZeroCross_Buy": "MACD crosses above zero line (trend shifts bullish).",
    "MACD_ZeroCross_Sell": "MACD crosses below zero line (trend shifts bearish).",
    "MACD_SignalCross_Buy": "MACD crosses above its signal line.",
    "MACD_SignalCross_Sell": "MACD crosses below its signal line.",
    "MACD_Histogram_Buy": "Histogram flips positive (momentum turning up).",
    "MACD_Histogram_Sell": "Histogram flips negative (momentum turning down).",
    # RSI
    "RSI_Oversold_Buy": "RSI < 30 (oversold; potential rebound).",
    "RSI_Overbought_Sell": "RSI > 70 (overbought; potential pullback).",
    "RSI_Bullish_Divergence": "Price makes new low while RSI rises (bullish divergence).",
    "RSI_Bearish_Divergence": "Price makes new high while RSI falls (bearish divergence).",
    # CCI
    "CCI_Oversold_Buy": "CCI < -100 (oversold; potential rebound).",
    "CCI_Overbought_Sell": "CCI > 100 (overbought; potential pullback).",
    "CCI_Reversal_Buy": "CCI rebounds from extreme low (< -180).",
    "CCI_Reversal_Sell": "CCI reverses down from extreme high (> 180).",
    "CCI_ZeroCross_Buy": "CCI crosses above zero (trend turns positive).",
    "CCI_ZeroCross_Sell": "CCI crosses below zero (trend turns negative).",
    # SMA
    "SMA_TripleCross_Buy": "Short > medium > long SMAs (bullish alignment).",
    "SMA_TripleCross_Sell": "Short < medium < long SMAs (bearish alignment).",
    "SMA_PriceCross_Buy": "Price crosses above medium SMA.",
    "SMA_PriceCross_Sell": "Price crosses below medium SMA.",
    "SMA_TrendFollow_Buy": "Price above long SMA with short/medium/long aligned.",
    "SMA_TrendFollow_Sell": "Price below long SMA with short/medium/long aligned.",
    # EMA
    "EMA_TripleCross_Buy": "Short > medium > long EMAs (bullish alignment).",
    "EMA_TripleCross_Sell": "Short < medium < long EMAs (bearish alignment).",
    "EMA_Distance_Buy": "Bullish EMA alignment with strong separation.",
    "EMA_Distance_Sell": "Bearish EMA alignment with strong separation.",
    "EMA_Momentum_Buy": "Bullish EMA alignment with rising EMA slope.",
    "EMA_Momentum_Sell": "Bearish EMA alignment with falling EMA slope.",
    "EMA_ValueZone_Buy": "Price between long and medium EMA (value zone).",
    "EMA_ValueZone_Sell": "Price between long and medium EMA (value zone).",
    "EMA_Divergence_Buy": "Price low falls while short EMA rises (divergence).",
    "EMA_Divergence_Sell": "Price high rises while short EMA falls (divergence).",
    "EMA_Volatility_Buy": "Bullish EMA alignment during high volatility.",
    "EMA_Volatility_Sell": "Bearish EMA alignment during high volatility.",
}


def _format_signal_label(col_name: str) -> str:
    return col_name.replace("_", " ")


def _describe_signal(col_name: str) -> str:
    description = SIGNAL_DESCRIPTIONS.get(col_name)
    if description:
        return description
    base = _format_signal_label(col_name)
    return f"Signal generated from {base}."


def _collect_selected_plots(values_list: List[List[str]]) -> List[str]:
    selected = []
    for values in values_list or []:
        if not values:
            continue
        selected.extend(values)
    return selected


def _build_indicator_settings_panel(
    indicator_key: str | None,
    settings_store: Dict[str, Any],
    styles: Dict[str, Any],
) -> html.Div:
    if not indicator_key or indicator_key not in INDICATOR_SETTING_SCHEMA:
        return html.Div("Click a gear icon to edit indicator settings.", style=styles['indicator_settings_empty'])

    schema = INDICATOR_SETTING_SCHEMA[indicator_key]
    default_settings = DEFAULT_INDICATOR_SETTINGS.get(indicator_key, {})
    current_settings = settings_store.get(indicator_key, {})

    header = html.Div(
        schema['label'],
        style={'fontSize': FONT_SIZES['sm'], 'color': styles['panel_title']['color'], 'fontWeight': '600'}
    )
    fields = []
    for field in schema['fields']:
        key = field['key']
        value = current_settings.get(key, default_settings.get(key))
        input_kwargs = {
            'type': 'number',
            'value': value,
            'step': field.get('step', 1),
            'style': styles['indicator_setting_input'],
            'debounce': True,
            'id': {'type': 'indicator-setting', 'indicator': indicator_key, 'key': key}
        }
        if 'min' in field:
            input_kwargs['min'] = field['min']
        if 'max' in field:
            input_kwargs['max'] = field['max']

        fields.append(html.Div(
            [
                html.Span(field['label'], style=styles['indicator_setting_label']),
                dcc.Input(**input_kwargs),
            ],
            style=styles['indicator_setting_row']
        ))

    return html.Div([header] + fields, style=styles['indicator_settings_panel'])


def _rebuild_indicator_dataframe(df: pd.DataFrame, indicator_settings: Dict[str, Any]) -> pd.DataFrame:
    """Rebuild indicators/signals from price data using updated settings."""
    if df is None or df.empty:
        return df
    price_cols = [col for col in ['Open', 'High', 'Low', 'Close', 'Volume'] if col in df.columns]
    base_df = df[price_cols].copy() if price_cols else df.copy()
    base_df = add_indicators(base_df, indicator_settings)
    base_df, _ = generate_signals(base_df, indicator_settings)
    return base_df


# ---------------------------------------------------------------------------
# Memoised enrichment cache — avoids redundant indicator rebuilds when
# multiple callbacks receive the same indicator-settings-store update.
# ---------------------------------------------------------------------------

_ENRICHED_CACHE: OrderedDict[tuple, pd.DataFrame] = OrderedDict()
_ENRICHED_CACHE_MAX = 8


def _hashable(v: Any) -> Any:
    if isinstance(v, dict):
        return tuple(sorted((k2, _hashable(v2)) for k2, v2 in v.items()))
    if isinstance(v, list):
        return tuple(v)
    return v


def _settings_key(settings: Dict[str, Any]) -> tuple:
    return tuple(sorted((k, _hashable(v)) for k, v in settings.items()))


def get_enriched(source_df: pd.DataFrame, settings: Dict[str, Any]) -> pd.DataFrame:
    """Return a cached enriched DataFrame, recomputing only when necessary.

    The cache key includes the object identity and length of *source_df* so a
    fresh load (new object, new length) always misses. Capacity is capped at
    ``_ENRICHED_CACHE_MAX`` entries with LRU eviction.
    """
    if source_df is None or source_df.empty:
        return source_df
    key = (id(source_df), len(source_df), _settings_key(settings))
    if key in _ENRICHED_CACHE:
        _ENRICHED_CACHE.move_to_end(key)
        return _ENRICHED_CACHE[key]
    enriched = _rebuild_indicator_dataframe(source_df, settings)
    _ENRICHED_CACHE[key] = enriched
    if len(_ENRICHED_CACHE) > _ENRICHED_CACHE_MAX:
        _ENRICHED_CACHE.popitem(last=False)
    return enriched


def clear_enriched_cache() -> None:
    """Discard all cached enriched DataFrames (called on new data load or state reset)."""
    _ENRICHED_CACHE.clear()


def _normalize_timestamp(value: Any) -> pd.Timestamp | None:
    """Normalize timestamps to timezone-naive UTC for comparisons."""
    ts = pd.to_datetime(value, errors='coerce', utc=True)
    if pd.isna(ts):
        return None
    return ts.tz_convert(None)


def _figure_dict(fig: Any) -> Dict[str, Any]:
    """Return a dict representation for read-only access."""
    if hasattr(fig, "to_dict"):
        return fig.to_dict()
    return fig


def _apply_layout_updates(fig: Any, updates: Dict[str, Any]) -> None:
    """Apply layout updates to either Figure or dict."""
    if not updates:
        return
    if hasattr(fig, "update_layout"):
        fig.update_layout(**updates)
        return
    layout = fig.setdefault('layout', {})
    for axis_key, axis_values in updates.items():
        axis_layout = layout.setdefault(axis_key, {})
        axis_layout.update(axis_values)


def _resolve_x_range(relayout_data: Dict[str, Any],
                     df: pd.DataFrame,
                     fig: Dict[str, Any] | None = None) -> Tuple[pd.Timestamp, pd.Timestamp] | None:
    """Resolve the active x-axis range from relayout data."""
    if not relayout_data:
        relayout_data = {}

    if 'xaxis.range[0]' in relayout_data and 'xaxis.range[1]' in relayout_data:
        start = relayout_data['xaxis.range[0]']
        end = relayout_data['xaxis.range[1]']
    elif 'xaxis.range' in relayout_data and isinstance(relayout_data['xaxis.range'], list):
        start, end = relayout_data['xaxis.range'][0], relayout_data['xaxis.range'][1]
    elif relayout_data.get('xaxis.autorange') is True:
        if df is None or df.empty:
            return None
        start, end = df.index.min(), df.index.max()
    else:
        if not fig:
            return None
        fig_dict = _figure_dict(fig)
        layout = fig_dict.get('layout', {})
        xaxis = layout.get('xaxis', {})
        if isinstance(xaxis.get('range'), list) and len(xaxis['range']) >= 2:
            start, end = xaxis['range'][0], xaxis['range'][1]
        elif xaxis.get('autorange') is True:
            if df is None or df.empty:
                return None
            start, end = df.index.min(), df.index.max()
        else:
            return None

    start_ts = _normalize_timestamp(start)
    end_ts = _normalize_timestamp(end)
    if start_ts is None or end_ts is None:
        return None
    return start_ts, end_ts


def _axis_layout_key(axis_id: str) -> str:
    """Convert trace yaxis id ('y', 'y2') to layout key ('yaxis', 'yaxis2')."""
    if axis_id == 'y':
        return 'yaxis'
    return f"yaxis{axis_id[1:]}"


def _combine_signals_for_counts(df: pd.DataFrame, columns: List[str], logic: str, window: int) -> pd.Series:
    """Combine signal columns using the same logic as the chart markers."""
    if not columns:
        return pd.Series(False, index=df.index)
    valid_cols = [c for c in columns if c in df.columns]
    if not valid_cols:
        return pd.Series(False, index=df.index)
    if logic == 'and':
        if window and window > 0:
            windowed = df[valid_cols].rolling(window=window + 1, min_periods=1).max()
            return (windowed > 0).all(axis=1)
        return df[valid_cols].all(axis=1)
    return df[valid_cols].any(axis=1)


def _apply_consecutive_rules_for_counts(
    signal_series: pd.Series,
    mode: str,
    cooldown: int
) -> tuple[pd.Series, pd.Series]:
    """Return accepted/rejected masks for consecutive signal rules."""
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


def _compute_trigger_counts(
    df: pd.DataFrame,
    selected_signals: List[str],
    buy_signals: List[str],
    sell_signals: List[str],
    signal_logic: str,
    signal_window: int,
    consecutive_signal_mode: str,
    cooldown_bars: int
) -> Dict[str, int]:
    """Compute total accepted/rejected trigger counts for buy/sell."""
    totals = {'accepted': 0, 'rejected': 0}
    if df is None or df.empty:
        return totals

    selected_set = set(selected_signals or [])
    for signal_type, columns in (("buy", buy_signals), ("sell", sell_signals)):
        if signal_type not in selected_set:
            continue

        accepted_col = f"{signal_type.capitalize()}_Trigger_Accepted"
        rejected_col = f"{signal_type.capitalize()}_Trigger_Rejected"
        if accepted_col in df.columns and rejected_col in df.columns:
            accepted = int(df[accepted_col].fillna(False).astype(bool).sum())
            rejected = int(df[rejected_col].fillna(False).astype(bool).sum())
        else:
            combined = _combine_signals_for_counts(df, columns, signal_logic, signal_window)
            accepted_mask, rejected_mask = _apply_consecutive_rules_for_counts(
                combined, consecutive_signal_mode, cooldown_bars
            )
            accepted = int(accepted_mask.sum())
            rejected = int(rejected_mask.sum())

        totals['accepted'] += accepted
        totals['rejected'] += rejected

    return totals


def _compute_y_ranges_by_axis(fig: Any,
                              x_start: pd.Timestamp,
                              x_end: pd.Timestamp,
                              df: pd.DataFrame | None = None) -> Dict[str, Tuple[float, float]]:
    """Compute min/max y ranges per axis for the visible x-range."""
    axis_ranges: Dict[str, Tuple[float, float]] = {}
    fig_dict = _figure_dict(fig)

    if df is not None and not df.empty and {'Low', 'High'}.issubset(df.columns):
        df_index = pd.to_datetime(df.index, errors='coerce', utc=True).tz_convert(None)
        df_mask = (df_index >= x_start) & (df_index <= x_end)
        if isinstance(df_mask, pd.Series):
            mask_arr = df_mask.to_numpy()
        else:
            mask_arr = np.asarray(df_mask)
        if mask_arr.any():
            visible_df = df.iloc[mask_arr]
            if not visible_df.empty:
                price_min = float(pd.to_numeric(visible_df['Low'], errors='coerce').min())
                price_max = float(pd.to_numeric(visible_df['High'], errors='coerce').max())
                for trace in fig_dict.get('data', []):
                    if trace.get('type') == 'candlestick':
                        axis_id = trace.get('yaxis', 'y')
                        axis_ranges[axis_id] = (price_min, price_max)

    traces = fig_dict.get('data', [])
    for trace in traces:
        if trace.get('visible') == 'legendonly':
            continue

        axis_id = trace.get('yaxis', 'y')
        if trace.get('type') == 'candlestick' and axis_id in axis_ranges:
            continue
        x_values = trace.get('x', [])
        if x_values is None or (hasattr(x_values, "__len__") and len(x_values) == 0):
            continue

        x_series = pd.to_datetime(pd.Series(x_values), errors='coerce', utc=True).dt.tz_convert(None)
        mask = (x_series >= x_start) & (x_series <= x_end)
        mask_values = mask.to_numpy()
        if not mask.any():
            continue

        y_min = y_max = None
        if trace.get('type') == 'candlestick':
            lows = pd.to_numeric(pd.Series(trace.get('low', [])), errors='coerce')
            highs = pd.to_numeric(pd.Series(trace.get('high', [])), errors='coerce')
            values_len = min(len(mask_values), len(lows), len(highs))
            if values_len == 0:
                continue
            low_vals = lows.to_numpy()[:values_len][mask_values[:values_len]]
            high_vals = highs.to_numpy()[:values_len][mask_values[:values_len]]
            if low_vals.size == 0 or high_vals.size == 0:
                continue
            y_min = float(low_vals.min())
            y_max = float(high_vals.max())
        else:
            y_values = pd.to_numeric(pd.Series(trace.get('y', [])), errors='coerce')
            values_len = min(len(mask_values), len(y_values))
            if values_len == 0:
                continue
            y_vals = y_values.to_numpy()[:values_len][mask_values[:values_len]]
            if y_vals.size == 0:
                continue
            y_min = float(y_vals.min())
            y_max = float(y_vals.max())

        if y_min is None or y_max is None:
            continue

        current = axis_ranges.get(axis_id)
        if current:
            axis_ranges[axis_id] = (min(current[0], y_min), max(current[1], y_max))
        else:
            axis_ranges[axis_id] = (y_min, y_max)

    return axis_ranges


def _pad_range(y_min: float, y_max: float, pad_ratio: float = 0.04) -> Tuple[float, float]:
    """Apply a small padding to y ranges for visual breathing room."""
    span = y_max - y_min
    if span <= 0:
        span = max(abs(y_max) * 0.02, 1e-6)
    pad = span * pad_ratio
    return y_min - pad, y_max + pad


def _build_signal_options(columns: List[str]) -> List[Dict[str, Any]]:
    options = []
    for col in columns:
        label = html.Span(
            _format_signal_label(col),
            title=_describe_signal(col),
            style={'marginLeft': '8px'}
        )
        options.append({'label': label, 'value': col})
    return options


def _strip_signal_side(col_name: str) -> str:
    return re.sub(r'_(buy|sell)$', '', col_name, flags=re.IGNORECASE)


def _build_unified_signal_rows(buy_columns: List[str], sell_columns: List[str]) -> List[Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for col in buy_columns:
        base = _strip_signal_side(col)
        rows.setdefault(base, {})['buy'] = col
    for col in sell_columns:
        base = _strip_signal_side(col)
        rows.setdefault(base, {})['sell'] = col

    unified_rows = []
    for base, sides in rows.items():
        category = base.split('_')[0].upper() if base else 'OTHER'
        unified_rows.append({
            'label': _format_signal_label(base),
            'category': category,
            'buy': sides.get('buy'),
            'sell': sides.get('sell')
        })

    return sorted(unified_rows, key=lambda row: row['label'].lower())


def _create_data_table(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create a styled data table."""
    return dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in display_df.columns],
        data=cast(Any, display_df.to_dict('records')),
        style_table={'height': '400px', 'overflowY': 'auto'},
        style_cell={
            'textAlign': 'right',
            'padding': '8px',
            'backgroundColor': theme['bg_tertiary'],
            'color': theme['text_primary'],
            'border': f'1px solid {theme["border_secondary"]}',
            'fontSize': '11px',
            'fontFamily': FONT_FAMILY,
        },
        style_header={
            'fontWeight': '600',
            'backgroundColor': theme['bg_secondary'],
            'color': theme['text_secondary'],
            'textTransform': 'uppercase',
            'fontSize': '10px',
        },
        style_data_conditional=cast(Any, [
            {'if': {'row_index': 'odd'}, 'backgroundColor': theme['table_row_alt']}
        ]),
        page_size=50,
        fixed_rows={'headers': True}
    )


def _sanitize_preset_name(name: Any) -> str:
    """Normalize preset names for consistent storage."""
    if not name:
        return ""
    normalized = re.sub(r"\s+", " ", str(name)).strip()
    return normalized


def _extract_selected_plots(plot_values: List[List[str]]) -> List[str]:
    """Convert pattern-matched plot toggle values into selected indicator list."""
    selected = []
    plot_values = plot_values or []
    for idx, (_, value) in enumerate(PLOT_OPTIONS):
        values = plot_values[idx] if idx < len(plot_values) else []
        if values:
            selected.append(value)
    return selected


def _build_plot_toggle_values(selected: List[str]) -> List[List[str]]:
    """Build pattern output values for plot toggles from selected list."""
    selected_set = set(selected or [])
    return [[value] if value in selected_set else [] for _, value in PLOT_OPTIONS]


def _build_preset_payload(
    ticker: str,
    start_date: str,
    end_date: str,
    initial_capital: Any,
    plot_values: List[List[str]],
    chart_elements: List[str],
    signal_checklist: List[str],
    indicator_settings: Dict[str, Any],
    chart_library: str,
    strategy_mode: str,
    strategy_preset: str,
    min_holding_period: Any,
    trailing_stop_pct: Any,
    position_scaling_pct: Any,
    take_profit_pct: Any,
    amount_per_buy: Any,
    position_size_pct: Any,
    kelly_win_rate: Any,
    kelly_win_loss_ratio: Any,
    consecutive_signal_mode: str,
    signal_cooldown_bars: Any,
    signal_logic_mode: str,
    signal_window: Any,
    buy_signals: List[str],
    sell_signals: List[str],
    fx_fee_pct: Any,
    slippage_pct: Any,
    commission_pct: Any
) -> Dict[str, Any]:
    payload = {
        "market_data": {
            "ticker": ticker,
            "start_date": start_date,
            "end_date": end_date,
            "initial_capital": initial_capital
        },
        "chart": {
            "plot_toggles": _extract_selected_plots(plot_values),
            "chart_elements": chart_elements or [],
            "signal_checklist": signal_checklist or [],
            "indicator_settings": copy.deepcopy(indicator_settings or {}),
            "chart_library": chart_library
        },
        "execution": {
            "strategy_mode": strategy_mode
        },
        "trade_setup": {
            "strategy_preset": strategy_preset,
            "min_holding_period": min_holding_period,
            "trailing_stop_pct": trailing_stop_pct,
            "position_scaling_pct": position_scaling_pct,
            "take_profit_pct": take_profit_pct,
            "amount_per_buy": amount_per_buy,
            "position_size_pct": position_size_pct,
            "kelly_win_rate": kelly_win_rate,
            "kelly_win_loss_ratio": kelly_win_loss_ratio,
            "consecutive_signal_mode": consecutive_signal_mode,
            "signal_cooldown_bars": signal_cooldown_bars
        },
        "signals": {
            "signal_logic_mode": signal_logic_mode,
            "signal_window": signal_window,
            "buy_signals": list(buy_signals or []),
            "sell_signals": list(sell_signals or [])
        },
        "costs": {
            "fx_fee_pct": fx_fee_pct,
            "slippage_pct": slippage_pct,
            "commission_pct": commission_pct
        }
    }
    return normalize_preset(payload)


def _preset_status(message: str, level: str = "info") -> html.Span:
    """Simple status message with theme color."""
    from lib.dash.dash_config import get_theme

    theme = get_theme()
    color_map = {
        "success": theme["accent_green"],
        "error": theme["accent_red"],
        "warning": theme["accent_orange"]
    }
    return html.Span(message, style={"color": color_map.get(level, theme["text_secondary"])})


def _format_preset_options(presets: Dict[str, Any]) -> List[Dict[str, str]]:
    names = sorted(presets.keys(), key=lambda name: str(name).lower())
    return [{"label": name, "value": name} for name in names]


def _create_price_subtitle(df: pd.DataFrame, theme: dict) -> html.Span:
    """Create price change subtitle."""
    latest_close = df['Close'].iloc[-1]
    prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
    change = latest_close - prev_close
    change_pct = (change / prev_close) * 100
    change_color = theme['accent_green'] if change >= 0 else theme['accent_red']
    change_sign = '+' if change >= 0 else ''

    return html.Span([
        html.Span(f"${latest_close:.2f}", className='num', style={'color': theme['text_primary']}),
        html.Span(f" {change_sign}{change:.2f} ({change_sign}{change_pct:.2f}%)",
                 className='num', style={'color': change_color, 'marginLeft': '8px'}),
    ])


def _create_optimization_table(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create enhanced optimization results table with all columns."""
    columns = ['Buy_Signals', 'Sell_Signals', 'Total_Return_%', 'Sharpe_Ratio', 'Max_Drawdown_%', 'Trades']
    available_cols = [c for c in columns if c in display_df.columns]

    return dash_table.DataTable(
        id='optimization-table',
        columns=[{"name": c.replace('_', ' '), "id": c} for c in available_cols],
        data=cast(Any, display_df[available_cols].round(2).to_dict('records')),
        style_cell={
            'textAlign': 'left',
            'padding': '8px',
            'backgroundColor': theme['bg_tertiary'],
            'color': theme['text_primary'],
            'fontSize': '11px',
            'border': f'1px solid {theme["border_secondary"]}',
            'maxWidth': '150px',
            'overflow': 'hidden',
            'textOverflow': 'ellipsis',
        },
        style_header={
            'fontWeight': '600',
            'backgroundColor': theme['bg_secondary'],
            'fontSize': '10px',
            'textTransform': 'uppercase',
        },
        style_data_conditional=cast(Any, [
            {'if': {'row_index': 0}, 'backgroundColor': f'{theme["accent_green"]}15'},
            {'if': {'row_index': 1}, 'backgroundColor': f'{theme["accent_blue"]}10'},
            {'if': {'row_index': 2}, 'backgroundColor': f'{theme["accent_blue"]}05'},
        ]),
        page_size=10,
    )


def _create_optimization_table_mini(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create compact mini-table for partial results during optimization."""
    return dash_table.DataTable(
        columns=[
            {"name": "Buy Signals", "id": "Buy_Signals"},
            {"name": "Return %", "id": "Total_Return_%"},
        ],
        data=cast(Any, display_df[['Buy_Signals', 'Total_Return_%']].round(1).to_dict('records')),
        style_cell={
            'textAlign': 'left',
            'padding': '4px 6px',
            'backgroundColor': theme['bg_tertiary'],
            'color': theme['text_primary'],
            'fontSize': '10px',
            'border': 'none',
        },
        style_header={'display': 'none'},
    )


def _create_best_strategy_highlight(best_row: pd.Series, theme: dict) -> html.Div:
    """Create highlight card for the best strategy."""
    total_return = best_row.get('Total_Return_%', 0)
    sharpe = best_row.get('Sharpe_Ratio', 0)
    drawdown = best_row.get('Max_Drawdown_%', 0)

    return html.Div([
        html.Div([
            html.Span("\U0001f3c6 ", style={'fontSize': '16px'}),
            html.Span("Best Strategy", style={
                'color': theme['text_secondary'],
                'fontSize': FONT_SIZES['sm'],
                'fontWeight': '600'
            }),
        ], style={'marginBottom': '8px'}),
        html.Div([
            html.Div([
                html.Span("Buy: ", style={'color': theme['text_secondary'], 'fontSize': FONT_SIZES['xs']}),
                html.Span(str(best_row.get('Buy_Signals', '')), style={
                    'color': theme['accent_green'],
                    'fontSize': FONT_SIZES['xs']
                }),
            ], style={'marginBottom': '4px'}),
            html.Div([
                html.Span("Sell: ", style={'color': theme['text_secondary'], 'fontSize': FONT_SIZES['xs']}),
                html.Span(str(best_row.get('Sell_Signals', '')), style={
                    'color': theme['accent_red'],
                    'fontSize': FONT_SIZES['xs']
                }),
            ], style={'marginBottom': '8px'}),
            html.Div([
                html.Span(f"{total_return:+.1f}% return", style={
                    'color': theme['accent_green'] if total_return > 0 else theme['accent_red'],
                    'fontWeight': '600',
                    'fontSize': FONT_SIZES['base'],
                    'fontFamily': FONT_FAMILY
                }),
                html.Span(f" | Sharpe: {sharpe:.2f}", style={
                    'color': theme['text_secondary'],
                    'fontSize': FONT_SIZES['xs'],
                    'marginLeft': '8px'
                }),
                html.Span(f" | DD: {drawdown:.1f}%", style={
                    'color': theme['text_secondary'],
                    'fontSize': FONT_SIZES['xs'],
                    'marginLeft': '8px'
                }),
            ]),
        ]),
    ], style={
        'backgroundColor': theme['bg_tertiary'],
        'padding': '12px',
        'borderRadius': '6px',
        'marginBottom': '12px',
        'border': f'1px solid {theme["accent_green"]}40'
    })


# Batch size for optimization processing (combinations per interval tick)
OPTIMIZATION_BATCH_SIZE = 5
