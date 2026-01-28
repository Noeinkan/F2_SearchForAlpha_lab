"""
Dashboard Callbacks
All Dash callback functions for the trading dashboard.
"""

import logging
import re
import copy
import json
from datetime import datetime
from typing import Tuple, List, Any, Dict

import pandas as pd
import numpy as np
from dash import html, dash_table, callback_context, dcc, no_update
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate
import plotly.graph_objs as go

from dash_tvlwc import Tvlwc

from lib.dash.dash_config import (
    DEFAULT_THEME, FONT_SIZES, FONT_MONO, BORDER_RADIUS, get_theme,
    DEFAULT_INDICATOR_SETTINGS, INDICATOR_SETTING_SCHEMA, PRESET_FILE_PATH,
    PLOT_OPTIONS
)
from lib.dash.state import dashboard_state
from lib.dash.styles import get_styles
from lib.dash.chart_builder import create_chart, create_empty_chart
from lib.dash.tv_chart_builder import (
    convert_df_to_tv_format,
    convert_volume_to_tv_format,
    get_tv_chart_options
)
from lib.dash.components import build_alert, build_metric_card, build_progress_bar
from lib.dash.helpers import (
    fetch_data_with_cache, format_df_for_display,
    extract_signals, generate_signal_combinations, evaluate_signal_combination
)

from lib.data_processing import get_all_tickers, create_backtest_results
from lib.signals.indicators import add_indicators, generate_signals
from lib.strategy import run_backtest

from lib.dash.preset_storage import load_presets, save_presets, normalize_preset

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


def _build_indicator_settings_panel(indicator_key: str | None, settings_store: Dict[str, Any], styles: Dict[str, Any]) -> html.Div:
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
    buy_columns: List[str],
    sell_columns: List[str],
    signal_logic: str,
    signal_window: int,
    consecutive_signal_mode: str,
    cooldown_bars: int
) -> dict:
    """Compute total accepted/rejected trigger counts for buy/sell."""
    totals = {'accepted': 0, 'rejected': 0}
    if df is None or df.empty:
        return totals

    selected_set = set(selected_signals or [])
    for signal_type, columns in (('buy', buy_columns), ('sell', sell_columns)):
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


def _compute_y_ranges_by_axis(fig: Dict[str, Any],
                              x_start: pd.Timestamp,
                              x_end: pd.Timestamp,
                              df: pd.DataFrame | None = None) -> Dict[str, Tuple[float, float]]:
    """Compute min/max y ranges per axis for the visible x-range."""
    axis_ranges: Dict[str, Tuple[float, float]] = {}
    fig_dict = _figure_dict(fig)

    if df is not None and not df.empty and {'Low', 'High'}.issubset(df.columns):
        df_index = pd.to_datetime(df.index, errors='coerce', utc=True).tz_convert(None)
        df_mask = (df_index >= x_start) & (df_index <= x_end)
        if hasattr(df_mask, "to_numpy"):
            df_mask = df_mask.to_numpy()
        else:
            df_mask = pd.Series(df_mask).to_numpy()
        if df_mask.any():
            visible_df = df.iloc[df_mask]
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


def register_callbacks(app):
    """
    Register all callbacks for the dashboard application.

    Args:
        app: Dash application instance
    """

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
        [Output('presets-store', 'data'),
         Output('preset-selector', 'options'),
         Output('preset-selector', 'value')],
        [Input('startup-interval', 'n_intervals')]
    )
    def load_presets_on_startup(n_intervals):
        """Load UI presets from disk on startup."""
        if n_intervals is None:
            raise PreventUpdate

        data = load_presets(PRESET_FILE_PATH)
        presets = data.get("presets", {})
        options = _format_preset_options(presets)
        return data, options, None

    @app.callback(
        [Output('ticker-dropdown', 'value'),
         Output('start-date', 'date'),
         Output('end-date', 'date'),
         Output('initial-capital', 'value'),
         Output({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         Output('chart-elements-checklist', 'value'),
         Output('signal-checklist', 'value'),
         Output('chart-library-toggle', 'value', allow_duplicate=True),
         Output('strategy-mode', 'value'),
         Output('strategy-preset', 'value'),
         Output('min-holding-period', 'value', allow_duplicate=True),
         Output('trailing-stop-pct', 'value', allow_duplicate=True),
         Output('position-scaling-pct', 'value', allow_duplicate=True),
         Output('take-profit-pct', 'value', allow_duplicate=True),
         Output('amount-per-buy', 'value'),
         Output('position-size-pct', 'value'),
         Output('kelly-win-rate', 'value'),
         Output('kelly-win-loss-ratio', 'value'),
         Output('consecutive-signal-mode', 'value'),
         Output('signal-cooldown-bars', 'value', allow_duplicate=True),
         Output('signal-logic-mode', 'value'),
         Output('signal-window', 'value'),
         Output('fx-fee-pct', 'value'),
         Output('slippage-pct', 'value'),
         Output('commission-pct', 'value'),
         Output('preset-name-input', 'value'),
         Output('active-preset-name', 'data'),
         Output('preset-apply-store', 'data')],
        [Input('preset-selector', 'value')],
        [State('presets-store', 'data')],
        prevent_initial_call=True
    )
    def apply_preset(preset_name, presets_data):
        """Apply a saved preset to all UI controls."""
        if not preset_name:
            no_update_list = [no_update] * len(PLOT_OPTIONS)
            return (
                no_update, no_update, no_update, no_update, no_update_list,
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                "", None, None
            )

        presets = (presets_data or {}).get("presets", {})
        preset = presets.get(preset_name)
        if not preset:
            no_update_list = [no_update] * len(PLOT_OPTIONS)
            return (
                no_update, no_update, no_update, no_update, no_update_list,
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update, no_update, no_update, no_update, no_update,
                no_update, no_update, no_update,
                "", None, None
            )

        market = preset.get("market_data", {})
        chart = preset.get("chart", {})
        execution = preset.get("execution", {})
        trade_setup = preset.get("trade_setup", {})
        signals = preset.get("signals", {})
        costs = preset.get("costs", {})

        plot_values = _build_plot_toggle_values(chart.get("plot_toggles", []))

        return (
            market.get("ticker"),
            market.get("start_date"),
            market.get("end_date"),
            market.get("initial_capital"),
            plot_values,
            chart.get("chart_elements", []),
            chart.get("signal_checklist", []),
            chart.get("chart_library"),
            execution.get("strategy_mode"),
            trade_setup.get("strategy_preset"),
            trade_setup.get("min_holding_period"),
            trade_setup.get("trailing_stop_pct"),
            trade_setup.get("position_scaling_pct"),
            trade_setup.get("take_profit_pct"),
            trade_setup.get("amount_per_buy"),
            trade_setup.get("position_size_pct"),
            trade_setup.get("kelly_win_rate", 0.5),
            trade_setup.get("kelly_win_loss_ratio", 1.5),
            trade_setup.get("consecutive_signal_mode"),
            trade_setup.get("signal_cooldown_bars"),
            signals.get("signal_logic_mode"),
            signals.get("signal_window"),
            costs.get("fx_fee_pct"),
            costs.get("slippage_pct"),
            costs.get("commission_pct"),
            preset_name,
            preset_name,
            preset
        )

    @app.callback(
        [Output('presets-store', 'data', allow_duplicate=True),
         Output('preset-selector', 'options', allow_duplicate=True),
         Output('preset-selector', 'value', allow_duplicate=True),
         Output('preset-status', 'children')],
        [Input('preset-save-btn', 'n_clicks'),
         Input('preset-save-as-btn', 'n_clicks'),
         Input('preset-rename-btn', 'n_clicks'),
         Input('preset-delete-btn', 'n_clicks')],
        [State('presets-store', 'data'),
         State('preset-selector', 'value'),
         State('preset-name-input', 'value'),
         State('ticker-dropdown', 'value'),
         State('start-date', 'date'),
         State('end-date', 'date'),
         State('initial-capital', 'value'),
         State({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         State('chart-elements-checklist', 'value'),
         State('signal-checklist', 'value'),
         State('indicator-settings-store', 'data'),
         State('chart-library-toggle', 'value'),
         State('strategy-mode', 'value'),
         State('strategy-preset', 'value'),
         State('min-holding-period', 'value'),
         State('trailing-stop-pct', 'value'),
         State('position-scaling-pct', 'value'),
         State('take-profit-pct', 'value'),
         State('amount-per-buy', 'value'),
         State('position-size-pct', 'value'),
        State('kelly-win-rate', 'value'),
        State('kelly-win-loss-ratio', 'value'),
         State('consecutive-signal-mode', 'value'),
         State('signal-cooldown-bars', 'value'),
         State('signal-logic-mode', 'value'),
         State('signal-window', 'value'),
         State('buy-signals', 'value'),
         State('sell-signals', 'value'),
         State('fx-fee-pct', 'value'),
         State('slippage-pct', 'value'),
         State('commission-pct', 'value')],
        prevent_initial_call=True
    )
    def manage_presets(save_clicks, save_as_clicks, rename_clicks, delete_clicks,
                       presets_data, preset_selected, preset_name_input,
                       ticker, start_date, end_date, initial_capital,
                       plot_values, chart_elements, signal_checklist,
                       indicator_settings, chart_library,
                       strategy_mode, strategy_preset, min_holding_period,
                       trailing_stop_pct, position_scaling_pct, take_profit_pct,
                       amount_per_buy, position_size_pct, kelly_win_rate, kelly_win_loss_ratio,
                       consecutive_signal_mode,
                       signal_cooldown_bars, signal_logic_mode, signal_window,
                       buy_signals, sell_signals,
                       fx_fee_pct, slippage_pct, commission_pct):
        """Handle preset Save/Save As/Rename/Delete actions."""
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        action = ctx.triggered[0]['prop_id'].split('.')[0]
        data = presets_data or load_presets(PRESET_FILE_PATH)
        presets = copy.deepcopy(data.get("presets", {}))

        selected_name = _sanitize_preset_name(preset_selected)
        input_name = _sanitize_preset_name(preset_name_input)

        if action == 'preset-save-btn':
            target_name = selected_name or input_name
            if input_name and input_name != selected_name:
                target_name = input_name
                if target_name in presets:
                    return data, _format_preset_options(presets), preset_selected, _preset_status(
                        f"Preset '{target_name}' already exists. Select it to overwrite or use Save As.",
                        "warning"
                    )
            if not target_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Enter a preset name or select one to save.", "error"
                )
            presets[target_name] = _build_preset_payload(
                ticker, start_date, end_date, initial_capital,
                plot_values, chart_elements, signal_checklist,
                indicator_settings, chart_library,
                strategy_mode, strategy_preset, min_holding_period,
                trailing_stop_pct, position_scaling_pct, take_profit_pct,
                amount_per_buy, position_size_pct, kelly_win_rate, kelly_win_loss_ratio,
                consecutive_signal_mode,
                signal_cooldown_bars, signal_logic_mode, signal_window,
                buy_signals, sell_signals,
                fx_fee_pct, slippage_pct, commission_pct
            )
            data["presets"] = presets
            save_presets(PRESET_FILE_PATH, data)
            refreshed = load_presets(PRESET_FILE_PATH)
            return refreshed, _format_preset_options(refreshed["presets"]), target_name, _preset_status(
                f"Saved preset '{target_name}'.", "success"
            )

        if action == 'preset-save-as-btn':
            target_name = input_name
            if not target_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Enter a name for Save As.", "error"
                )
            if target_name in presets:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    f"Preset '{target_name}' already exists.", "warning"
                )
            presets[target_name] = _build_preset_payload(
                ticker, start_date, end_date, initial_capital,
                plot_values, chart_elements, signal_checklist,
                indicator_settings, chart_library,
                strategy_mode, strategy_preset, min_holding_period,
                trailing_stop_pct, position_scaling_pct, take_profit_pct,
                amount_per_buy, position_size_pct, kelly_win_rate, kelly_win_loss_ratio,
                consecutive_signal_mode,
                signal_cooldown_bars, signal_logic_mode, signal_window,
                buy_signals, sell_signals,
                fx_fee_pct, slippage_pct, commission_pct
            )
            data["presets"] = presets
            save_presets(PRESET_FILE_PATH, data)
            refreshed = load_presets(PRESET_FILE_PATH)
            return refreshed, _format_preset_options(refreshed["presets"]), target_name, _preset_status(
                f"Created preset '{target_name}'.", "success"
            )

        if action == 'preset-rename-btn':
            if not selected_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Select a preset to rename.", "error"
                )
            if not input_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Enter a new name to rename.", "error"
                )
            if input_name == selected_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Preset name unchanged.", "warning"
                )
            if input_name in presets:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    f"Preset '{input_name}' already exists.", "warning"
                )
            presets[input_name] = presets.pop(selected_name)
            data["presets"] = presets
            save_presets(PRESET_FILE_PATH, data)
            refreshed = load_presets(PRESET_FILE_PATH)
            return refreshed, _format_preset_options(refreshed["presets"]), input_name, _preset_status(
                f"Renamed preset to '{input_name}'.", "success"
            )

        if action == 'preset-delete-btn':
            if not selected_name:
                return data, _format_preset_options(presets), preset_selected, _preset_status(
                    "Select a preset to delete.", "error"
                )
            if selected_name in presets:
                presets.pop(selected_name, None)
                data["presets"] = presets
                save_presets(PRESET_FILE_PATH, data)
                refreshed = load_presets(PRESET_FILE_PATH)
                return refreshed, _format_preset_options(refreshed["presets"]), None, _preset_status(
                    f"Deleted preset '{selected_name}'.", "success"
                )

        return data, _format_preset_options(presets), preset_selected, _preset_status(
            "No action performed.", "warning"
        )

    @app.callback(
        [Output('data-status', 'children'),
         Output('data-loaded-store', 'data'),
         Output('buy-signals', 'options'),
         Output('sell-signals', 'options'),
         Output('signals-unified-store', 'data'),
         Output('chart-title', 'children'),
         Output('chart-subtitle', 'children'),
         Output('data-table-container', 'children')],
        [Input('load-data-button', 'n_clicks'),
         Input('autoload-interval', 'n_intervals')],
        [State('ticker-dropdown', 'value'),
         State('start-date', 'date'),
         State('end-date', 'date'),
         State('indicator-settings-store', 'data')]
    )
    def load_data(n_clicks, n_intervals, ticker, start_date, end_date, indicator_settings):
        """Load market data. Auto-loads SPY on startup."""
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # On startup, auto-load default ticker (SPY)
        if trigger_id == 'autoload-interval':
            if n_intervals is None or n_intervals < 1:
                raise PreventUpdate
        elif trigger_id == 'load-data-button':
            if not n_clicks:
                raise PreventUpdate

        theme = get_theme()

        try:
            df = fetch_data_with_cache(ticker, start_date, end_date)
            if df.empty:
                return (
                    html.Div([
                        html.Span("\u26a0", style={'color': theme['accent_orange'], 'marginRight': '6px'}),
                        html.Span("No data available for this symbol",
                                  style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_orange']})
                    ]),
                    False, [], [], [], "No data", "", None
                )

            df = add_indicators(df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
            df, _ = generate_signals(df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
            dashboard_state.df = df

            buy_columns = [col for col in df.columns if 'buy' in col.lower()]
            sell_columns = [col for col in df.columns if 'sell' in col.lower()]
            buy_options = _build_signal_options(buy_columns)
            sell_options = _build_signal_options(sell_columns)
            unified_rows = _build_unified_signal_rows(buy_columns, sell_columns)

            # Create data table
            display_df = format_df_for_display(df.tail(50)).reset_index()
            data_table = _create_data_table(display_df, theme)

            # Calculate subtitle info
            subtitle = _create_price_subtitle(df, theme)

            # Success status with animation
            status = html.Div([
                html.Span("\u2713", style={'color': theme['accent_green'], 'marginRight': '6px', 'fontWeight': 'bold'}),
                html.Span(f"{len(df)} rows loaded", style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_green']})
            ], className='fade-in')

            return status, True, buy_options, sell_options, unified_rows, ticker, subtitle, data_table

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return (
                html.Div([
                    html.Span("\u2715", style={'color': theme['accent_red'], 'marginRight': '6px', 'fontWeight': 'bold'}),
                    html.Span(str(e)[:40], style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_red']})
                ]),
                False, [], [], [], "Error", "", None
            )

    @app.callback(
        [Output('accumulation-options', 'style'),
         Output('rebalancing-options', 'style'),
         Output('preset-options', 'style'),
         Output('holding-period-options', 'style'),
         Output('trailing-stop-options', 'style'),
         Output('position-scaling-options', 'style'),
         Output('take-profit-options', 'style'),
         Output('kelly-options', 'style')],
        [Input('strategy-mode', 'value')],
        [State('theme-store', 'data')]
    )
    def toggle_strategy_options(strategy_mode, theme_name):
        """Show/hide mode-specific options based on selected strategy mode."""
        theme = get_theme(theme_name or DEFAULT_THEME)

        def panel_style(show: bool, color: str) -> dict:
            return {
                'marginBottom': '12px',
                'display': 'block' if show else 'none',
                'padding': '10px',
                'backgroundColor': f'{color}10',
                'borderRadius': BORDER_RADIUS['md'],
                'border': f'1px solid {color}40',
                'color': theme['text_primary'],
            }

        is_trading = strategy_mode == 'trading'
        is_accumulation = strategy_mode == 'accumulation'
        is_rebalancing = strategy_mode == 'rebalancing'

        accumulation_style = panel_style(is_accumulation, theme["accent_green"])
        rebalancing_style = panel_style(is_rebalancing, theme["accent_blue"])
        preset_style = panel_style(is_trading, theme["accent_purple"])
        holding_style = panel_style(is_trading or is_rebalancing, theme["accent_orange"])
        trailing_style = panel_style(is_trading or is_rebalancing, theme["accent_red"])
        scaling_style = panel_style(is_trading, theme["accent_cyan"])
        take_profit_style = panel_style(is_trading or is_rebalancing, theme["accent_green"])
        kelly_style = panel_style(is_trading, theme["accent_purple"])

        return (accumulation_style, rebalancing_style, preset_style,
                holding_style, trailing_style, scaling_style, take_profit_style,
                kelly_style)

    @app.callback(
        [Output('signal-cooldown-bars', 'value', allow_duplicate=True),
         Output('signal-cooldown-container', 'style'),
         Output('consecutive-signal-help', 'children')],
        [Input('consecutive-signal-mode', 'value')],
        [State('signal-cooldown-bars', 'value')],
        prevent_initial_call=True
    )
    def update_consecutive_signal_settings(mode, current_value):
        """Set defaults and visibility for consecutive signal controls."""
        mode = (mode or 'scale_in').lower()
        cooldown_style = {'display': 'none'}
        help_text = "Controls repeated triggers for BUY and SELL signals."
        value = current_value

        if mode == 'edge':
            help_text = "Edge: triggers only when signals flip 0→1 (no re-entry spam)."
        elif mode == 'cooldown':
            cooldown_style = {'display': 'block'}
            help_text = "Cooldown: wait N bars after a trigger before allowing another."
            if not value or value <= 0:
                value = 5
        elif mode == 'reset_cooldown':
            cooldown_style = {'display': 'block'}
            help_text = "Reset+Cooldown: wait for signal reset plus N bars."
            if not value or value <= 0:
                value = 5
        else:
            help_text = "Scale-in: repeats add to position (default behavior)."
            if value is None:
                value = 0

        return value, cooldown_style, help_text

    @app.callback(
        [Output('min-holding-period', 'value'),
         Output('trailing-stop-pct', 'value'),
         Output('position-scaling-pct', 'value'),
         Output('take-profit-pct', 'value')],
        [Input('strategy-preset', 'value')],
        prevent_initial_call=True
    )
    def apply_strategy_preset(preset):
        """Apply preset values to trade setup inputs."""
        presets = {
            'swing': {'min_hold': 5, 'trailing': 8, 'scaling': 25, 'take_profit': 12},
            'position': {'min_hold': 20, 'trailing': 15, 'scaling': 15, 'take_profit': 25},
            'trend': {'min_hold': 10, 'trailing': 12, 'scaling': 20, 'take_profit': 20},
        }

        if not preset or preset == 'custom':
            return no_update, no_update, no_update, no_update

        preset_values = presets.get(preset)
        if not preset_values:
            return no_update, no_update, no_update, no_update

        return (preset_values['min_hold'], preset_values['trailing'],
                preset_values['scaling'], preset_values['take_profit'])

    @app.callback(
        Output('signals-unified-list', 'children'),
        [Input('signals-unified-store', 'data'),
         Input('signals-search', 'value'),
         Input('signals-category-filter', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value')]
    )
    def render_unified_signal_list(signal_rows, search_value, category_values, buy_values, sell_values):
        """Render unified BUY/SELL signal rows."""
        theme = get_theme()
        header = html.Div([
            html.Span("BUY", style={
                'fontSize': FONT_SIZES['xs'],
                'fontWeight': '600',
                'color': theme['accent_green']
            }),
            html.Span("SIGNAL", style={
                'fontSize': FONT_SIZES['xs'],
                'fontWeight': '600',
                'color': theme['text_secondary']
            }),
            html.Span("SELL", style={
                'fontSize': FONT_SIZES['xs'],
                'fontWeight': '600',
                'color': theme['accent_red']
            }),
        ], className='signals-unified-header')
        if not signal_rows:
            return [
                header,
                html.Div(
                    "Load data to view signals.",
                    style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'padding': '6px'}
                )
            ]

        buy_values = set(buy_values or [])
        sell_values = set(sell_values or [])
        search_term = (search_value or '').strip().lower()
        selected_categories = set(category_values or [])
        rows = []
        for row in signal_rows:
            if selected_categories and row.get('category') not in selected_categories:
                continue
            label_text = row.get('label', '')
            if search_term and search_term not in label_text.lower():
                continue
            buy_value = row.get('buy')
            sell_value = row.get('sell')
            description = ''
            if buy_value or sell_value:
                description = _describe_signal(buy_value or sell_value)

            buy_toggle = html.Div('', className='signal-toggle-placeholder')
            if buy_value:
                buy_toggle = dcc.Checklist(
                    id={'type': 'signal-toggle', 'side': 'buy', 'value': buy_value},
                    options=[{'label': '', 'value': buy_value}],
                    value=[buy_value] if buy_value in buy_values else [],
                    className='signal-toggle signal-toggle--buy'
                )

            sell_toggle = html.Div('', className='signal-toggle-placeholder')
            if sell_value:
                sell_toggle = dcc.Checklist(
                    id={'type': 'signal-toggle', 'side': 'sell', 'value': sell_value},
                    options=[{'label': '', 'value': sell_value}],
                    value=[sell_value] if sell_value in sell_values else [],
                    className='signal-toggle signal-toggle--sell'
                )

            rows.append(
                html.Div(
                    [
                        buy_toggle,
                        html.Div(row.get('label', ''), className='signal-name', title=description),
                        sell_toggle,
                    ],
                    className='signal-row'
                )
            )

        if not rows:
            return [
                header,
                html.Div(
                    "No signals match the filter.",
                    style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'padding': '6px'}
                )
            ]

        return [header, *rows]

    @app.callback(
        [Output('signal-window', 'disabled'),
         Output('signal-window-container', 'style')],
        [Input('signal-logic-mode', 'value')]
    )
    def toggle_signal_window(signal_logic):
        """Disable AND window control unless AND logic is selected."""
        base_style = {'marginBottom': '10px'}
        if signal_logic != 'and':
            return True, {**base_style, 'opacity': 0.55}
        return False, {**base_style, 'opacity': 1}

    @app.callback(
        [Output('buy-signals', 'value'),
         Output('sell-signals', 'value')],
        [Input('preset-apply-store', 'data'),
         Input({'type': 'signal-toggle', 'side': 'buy', 'value': ALL}, 'value'),
         Input({'type': 'signal-toggle', 'side': 'sell', 'value': ALL}, 'value')],
        [State({'type': 'signal-toggle', 'side': 'buy', 'value': ALL}, 'id'),
         State({'type': 'signal-toggle', 'side': 'sell', 'value': ALL}, 'id')]
    )
    def sync_signal_selection(preset_data, buy_values, sell_values, buy_ids, sell_ids):
        """Sync row toggles to unified buy/sell selections."""
        ctx = callback_context
        if getattr(ctx, "triggered_id", None) == 'preset-apply-store':
            if not preset_data:
                raise PreventUpdate
            signals = preset_data.get("signals", {})
            return list(signals.get("buy_signals", []) or []), list(signals.get("sell_signals", []) or [])

        if not buy_ids and not sell_ids:
            return [], []

        selected_buy = [
            item_id['value']
            for item_id, value in zip(buy_ids, buy_values)
            if value
        ]
        selected_sell = [
            item_id['value']
            for item_id, value in zip(sell_ids, sell_values)
            if value
        ]

        return selected_buy, selected_sell

    @app.callback(
        [Output('summary-strategy-mode', 'children'),
         Output('summary-position-sizing', 'children'),
         Output('summary-signal-settings', 'children')],
        [Input('strategy-mode', 'value'),
         Input('strategy-preset', 'value'),
         Input('amount-per-buy', 'value'),
         Input('position-size-pct', 'value'),
         Input('kelly-win-rate', 'value'),
         Input('kelly-win-loss-ratio', 'value'),
         Input('min-holding-period', 'value'),
         Input('trailing-stop-pct', 'value'),
         Input('position-scaling-pct', 'value'),
         Input('take-profit-pct', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('signal-logic-mode', 'value'),
         Input('signal-window', 'value')]
    )
    def update_backtest_panel_summaries(strategy_mode, strategy_preset, amount_per_buy, position_size_pct,
                                        kelly_win_rate, kelly_win_loss_ratio, min_holding_period,
                                        trailing_stop_pct, position_scaling_pct, take_profit_pct,
                                        buy_signals, sell_signals, signal_logic, signal_window):
        """Update accordion titles with selected options when collapsed."""
        strategy_labels = {
            'trading': 'Trading (Full)',
            'accumulation': 'Accumulation (DCA)',
            'rebalancing': 'Rebalancing (Partial)',
        }
        strategy_summary = strategy_labels.get(strategy_mode, 'Trading (Full)')

        if strategy_mode == 'trading' and strategy_preset and strategy_preset != 'custom':
            strategy_summary = f"{strategy_summary} ({strategy_preset.title()})"

        if strategy_mode == 'accumulation':
            if amount_per_buy is None:
                sizing_summary = '$- per buy'
            else:
                sizing_summary = f'${amount_per_buy:,.0f} per buy'
        else:
            sizing_parts = []
            if strategy_mode == 'rebalancing':
                if position_size_pct is None:
                    sizing_parts.append('% per trade')
                else:
                    sizing_parts.append(f'{position_size_pct:.0f}% per trade')

            if strategy_mode == 'trading':
                kelly_win_rate = 0.5 if kelly_win_rate is None else kelly_win_rate
                kelly_win_loss_ratio = 1.5 if kelly_win_loss_ratio is None else kelly_win_loss_ratio

            if strategy_mode == 'trading' and kelly_win_rate is not None and kelly_win_loss_ratio is not None:
                sizing_parts.append(f'Kelly {kelly_win_rate:.2f}/{kelly_win_loss_ratio:.2f}')

            if min_holding_period is not None:
                sizing_parts.append(f'Hold {int(min_holding_period)}')
            if trailing_stop_pct is not None and trailing_stop_pct > 0:
                sizing_parts.append(f'TS {trailing_stop_pct:.1f}%')
            if strategy_mode == 'trading' and position_scaling_pct is not None:
                sizing_parts.append(f'Scale {position_scaling_pct:.0f}%')
            if take_profit_pct is not None and take_profit_pct > 0:
                sizing_parts.append(f'TP {take_profit_pct:.1f}%')

            sizing_summary = ' | '.join(sizing_parts) if sizing_parts else 'N/A'

        buy_signals = buy_signals or []
        sell_signals = sell_signals or []

        def _summarize_signals(values, max_items=2):
            labels = [_format_signal_label(v) for v in values]
            if not labels:
                return 'None'
            if len(labels) <= max_items:
                return ', '.join(labels)
            extra = len(labels) - max_items
            return f"{', '.join(labels[:max_items])} +{extra}"

        if not buy_signals and not sell_signals:
            signals_summary = 'No signals'
        else:
            signals_summary = (
                f"Buy: {_summarize_signals(buy_signals)} | "
                f"Sell: {_summarize_signals(sell_signals)}"
            )
            if signal_logic == 'and':
                if signal_window:
                    signals_summary += f" | AND W={signal_window}"
                else:
                    signals_summary += " | AND"
            else:
                signals_summary += " | OR"

        return strategy_summary, sizing_summary, signals_summary

    @app.callback(
        [Output('plotly-chart-container', 'style'),
         Output('tv-chart-container', 'style')],
        [Input('chart-library-toggle', 'value')]
    )
    def toggle_chart_visibility(chart_library):
        """Show/hide Plotly vs TradingView containers."""
        base_style = {
            'position': 'absolute',
            'inset': 0,
            'height': '100%',
            'width': '100%'
        }
        plotly_style = {**base_style, 'visibility': 'visible', 'opacity': 1, 'pointerEvents': 'auto', 'zIndex': 1}
        tv_style = {**base_style, 'display': 'flex', 'flexDirection': 'column', 'visibility': 'hidden',
                    'opacity': 0, 'pointerEvents': 'none', 'zIndex': 0}
        if chart_library == 'tradingview':
            return {**plotly_style, 'visibility': 'hidden', 'opacity': 0, 'pointerEvents': 'none'}, \
                {**tv_style, 'visibility': 'visible', 'opacity': 1, 'pointerEvents': 'auto', 'zIndex': 2}
        return plotly_style, tv_style

    @app.callback(
        Output('active-indicator-store', 'data'),
        [Input({'type': 'indicator-gear', 'indicator': ALL}, 'n_clicks_timestamp')],
        prevent_initial_call=True
    )
    def set_active_indicator_settings(_timestamps):
        """Update active indicator when a gear icon is clicked."""
        ctx = callback_context
        triggered_id = getattr(ctx, "triggered_id", None)
        if isinstance(triggered_id, dict) and triggered_id.get('indicator'):
            return triggered_id['indicator']

        if ctx.triggered:
            prop_id = ctx.triggered[0].get("prop_id", "")
            if prop_id and prop_id != ".":
                raw_id = prop_id.split(".")[0]
                try:
                    parsed_id = json.loads(raw_id)
                except json.JSONDecodeError:
                    parsed_id = None
                if isinstance(parsed_id, dict) and parsed_id.get("indicator"):
                    return parsed_id["indicator"]

        inputs = ctx.inputs or {}
        if inputs:
            latest_indicator = None
            latest_ts = -1
            for key, value in inputs.items():
                if not key.startswith("{"):
                    continue
                try:
                    parsed = json.loads(key.split(".")[0])
                except json.JSONDecodeError:
                    continue
                if parsed.get("type") == "indicator-gear" and isinstance(value, (int, float)):
                    if value > latest_ts:
                        latest_ts = value
                        latest_indicator = parsed.get("indicator")
            if latest_indicator:
                return latest_indicator

        raise PreventUpdate

    @app.callback(
        Output({'type': 'indicator-settings-panel', 'indicator': ALL}, 'children'),
        [Input('active-indicator-store', 'data')],
        [State('indicator-settings-store', 'data')]
    )
    def render_indicator_settings_panel(active_indicator, settings_store):
        """Render indicator settings panel for the active indicator."""
        theme = get_theme()
        styles = get_styles(theme)
        settings_store = settings_store or copy.deepcopy(DEFAULT_INDICATOR_SETTINGS)
        indicator_ids = [item['id']['indicator'] for item in callback_context.outputs_list]
        panels = []
        for indicator in indicator_ids:
            if indicator == active_indicator:
                panels.append(_build_indicator_settings_panel(indicator, settings_store, styles))
            else:
                panels.append(html.Div())
        return panels

    @app.callback(
        Output('indicator-settings-store', 'data'),
        [Input('preset-apply-store', 'data'),
         Input({'type': 'indicator-setting', 'indicator': ALL, 'key': ALL}, 'value')],
        [State('indicator-settings-store', 'data')],
        prevent_initial_call=True
    )
    def persist_indicator_settings(preset_data, _values, current_settings):
        """Persist indicator settings from the sidebar inputs."""
        ctx = callback_context
        if getattr(ctx, "triggered_id", None) == 'preset-apply-store':
            if not preset_data:
                raise PreventUpdate
            indicator_settings = preset_data.get("chart", {}).get("indicator_settings")
            if indicator_settings is None:
                raise PreventUpdate
            return indicator_settings

        if current_settings is None:
            current_settings = copy.deepcopy(DEFAULT_INDICATOR_SETTINGS)
        if not callback_context.inputs_list:
            raise PreventUpdate

        updated = copy.deepcopy(current_settings)
        settings_inputs = callback_context.inputs_list[1] if len(callback_context.inputs_list) > 1 else []
        for item in settings_inputs:
            field_id = item.get('id', {})
            indicator = field_id.get('indicator')
            key = field_id.get('key')
            if not indicator or not key:
                continue
            value = item.get('value')
            if value is None:
                continue
            updated.setdefault(indicator, {})[key] = value
        return updated

    @app.callback(
        [Output('buy-signals', 'options', allow_duplicate=True),
         Output('sell-signals', 'options', allow_duplicate=True),
         Output('signals-unified-store', 'data', allow_duplicate=True),
         Output('data-table-container', 'children', allow_duplicate=True)],
        [Input('indicator-settings-store', 'data')],
        [State('data-loaded-store', 'data')],
        prevent_initial_call=True
    )
    def refresh_signals_with_settings(indicator_settings, data_loaded):
        """Recompute signals when indicator parameters change."""
        if not data_loaded or dashboard_state.df is None:
            raise PreventUpdate

        theme = get_theme()
        indicator_settings = indicator_settings or DEFAULT_INDICATOR_SETTINGS
        df = _rebuild_indicator_dataframe(dashboard_state.df, indicator_settings)
        if df is None or df.empty:
            raise PreventUpdate
        dashboard_state.df = df

        buy_columns = [col for col in df.columns if 'buy' in col.lower()]
        sell_columns = [col for col in df.columns if 'sell' in col.lower()]
        buy_options = _build_signal_options(buy_columns)
        sell_options = _build_signal_options(sell_columns)
        unified_rows = _build_unified_signal_rows(buy_columns, sell_columns)

        display_df = format_df_for_display(df.tail(50)).reset_index()
        data_table = _create_data_table(display_df, theme)
        return buy_options, sell_options, unified_rows, data_table

    @app.callback(
        Output('chart-library-toggle', 'value'),
        [Input({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         Input('chart-elements-checklist', 'value')],
        [State('chart-library-toggle', 'value')]
    )
    def enforce_plotly_for_indicators(plot_values, chart_elements, current_library):
        """Ensure Plotly is used when indicators/overlays are requested."""
        return 'plotly'

    @app.callback(
        Output('financial-chart', 'figure'),
        [Input('data-loaded-store', 'data'),
         Input({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('chart-library-toggle', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('consecutive-signal-mode', 'value'),
         Input('signal-cooldown-bars', 'value'),
         Input('signal-logic-mode', 'value'),
         Input('signal-window', 'value'),
         Input('indicator-settings-store', 'data')],
        [State('ticker-dropdown', 'value'),
         State('layout-store', 'data')]
    )
    def update_plotly_chart(data_loaded, plot_values, chart_elements, selected_signals, chart_library,
                            buy_signals, sell_signals, consecutive_signal_mode, signal_cooldown_bars,
                            signal_logic, signal_window, indicator_settings, ticker, layout_state):
        """Update the Plotly financial chart."""
        if chart_library == 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return create_empty_chart(theme)

        df = dashboard_state.df
        df = df.copy()
        df = _rebuild_indicator_dataframe(df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
        dashboard_state.df = df

        buy_signals = buy_signals or []
        sell_signals = sell_signals or []

        config = {
            'selected_plots': _collect_selected_plots(plot_values) or ['candlestick'],
            'show_candlesticks': 'candlesticks' in (chart_elements or []),
            'show_bollinger': 'bollinger' in (chart_elements or []),
            'show_sma': 'sma' in (chart_elements or []),
            'show_ema': 'ema' in (chart_elements or []),
            'show_buy_sell_signals': 'signals' in (chart_elements or []),
            'show_legend': 'legend' in (chart_elements or []),
            'selected_signals': selected_signals or [],
            'buy_signal_columns': buy_signals,
            'sell_signal_columns': sell_signals,
            'consecutive_signal_mode': consecutive_signal_mode or 'scale_in',
            'cooldown_bars': signal_cooldown_bars or 0,
            'signal_logic': signal_logic or 'or',
            'signal_window': signal_window or 0,
            'title': '',
            'indicator_settings': indicator_settings or DEFAULT_INDICATOR_SETTINGS,
        }

        fig = create_chart(df, config, theme)
        if layout_state and layout_state.get('x_range'):
            fig.update_xaxes(range=layout_state['x_range'], autorange=False)
            x_start = _normalize_timestamp(layout_state['x_range'][0])
            x_end = _normalize_timestamp(layout_state['x_range'][1])
            if x_start and x_end:
                axis_ranges = _compute_y_ranges_by_axis(fig, x_start, x_end, df)
                layout_updates = {}
                for axis_id, (y_min, y_max) in axis_ranges.items():
                    padded_min, padded_max = _pad_range(y_min, y_max)
                    axis_key = _axis_layout_key(axis_id)
                    layout_updates[axis_key] = {'range': [padded_min, padded_max], 'autorange': False}
                _apply_layout_updates(fig, layout_updates)
        elif layout_state and layout_state.get('autorange'):
            fig.update_xaxes(autorange=True)

        return fig

    @app.callback(
        Output('signal-count-bar', 'children'),
        [Input('data-loaded-store', 'data'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('consecutive-signal-mode', 'value'),
         Input('signal-cooldown-bars', 'value'),
         Input('signal-logic-mode', 'value'),
         Input('signal-window', 'value'),
         Input('indicator-settings-store', 'data')]
    )
    def update_signal_count_bar(
        data_loaded,
        chart_elements,
        selected_signals,
        buy_signals,
        sell_signals,
        consecutive_signal_mode,
        signal_cooldown_bars,
        signal_logic,
        signal_window,
        indicator_settings
    ):
        theme = get_theme()
        if not data_loaded or dashboard_state.df is None:
            return html.Span("Signals: --", style={'color': theme['text_secondary']})

        df = dashboard_state.df.copy()
        df = _rebuild_indicator_dataframe(df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)

        counts = _compute_trigger_counts(
            df,
            selected_signals or [],
            buy_signals or [],
            sell_signals or [],
            signal_logic or 'or',
            signal_window or 0,
            consecutive_signal_mode or 'scale_in',
            signal_cooldown_bars or 0
        )

        label_style = {
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_secondary'],
            'textTransform': 'uppercase',
            'letterSpacing': '0.4px',
        }
        value_style = {
            'fontSize': FONT_SIZES['sm'],
            'fontWeight': '600',
            'fontFamily': FONT_MONO,
        }
        muted_value_style = {
            **value_style,
            'color': theme['text_tertiary'],
        }
        active_value_style = {
            **value_style,
            'color': theme['accent_blue'],
        }
        divider_style = {'color': theme['border_secondary'], 'opacity': 0.7}

        return html.Div([
            html.Span("Triggered", style=label_style),
            html.Span(f"{counts['accepted']}", style=active_value_style),
            html.Span("|", style=divider_style),
            html.Span("Rejected", style=label_style),
            html.Span(f"{counts['rejected']}", style=muted_value_style),
        ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'})

    @app.callback(
        Output('download-csv', 'data'),
        [Input('export-csv-btn', 'n_clicks')],
        [State('data-loaded-store', 'data'),
         State('ticker-dropdown', 'value')],
        prevent_initial_call=True
    )
    def export_chart_csv(n_clicks, data_loaded, ticker):
        """Export current chart data (with indicators) to CSV."""
        if not data_loaded or dashboard_state.df is None:
            raise PreventUpdate

        df = dashboard_state.df.copy()
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index().rename(columns={'index': 'Date'})
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            cols = ['Date'] + [col for col in df.columns if col != 'Date']
            df = df.loc[:, cols]

        export_date = datetime.now().strftime('%Y%m%d')
        safe_ticker = (ticker or 'data').replace('/', '-')
        filename = f"{safe_ticker}_chart_data_{export_date}.csv"
        return dcc.send_data_frame(df.to_csv, filename, index=False, float_format='%.6f')

    app.clientside_callback(
        """
        function(n_clicks, chartLibrary) {
            if (!n_clicks) {
                return window.dash_clientside.no_update;
            }
            if (chartLibrary && chartLibrary !== 'plotly') {
                return window.dash_clientside.no_update;
            }
            const graph = document.getElementById('financial-chart');
            if (!graph || !window.Plotly) {
                return window.dash_clientside.no_update;
            }
            const plotlyGraph = graph.querySelector('.js-plotly-plot');
            if (!plotlyGraph) {
                return window.dash_clientside.no_update;
            }
            window.Plotly.downloadImage(plotlyGraph, {
                format: 'png',
                filename: 'chart',
                height: 800,
                width: 1200,
                scale: 2
            });
            return Date.now();
        }
        """,
        Output('export-img-store', 'data'),
        Input('export-img-btn', 'n_clicks'),
        State('chart-library-toggle', 'value')
    )

    @app.callback(
        Output('layout-store', 'data'),
        [Input('financial-chart', 'relayoutData')],
        [State('layout-store', 'data')],
        prevent_initial_call=True
    )
    def persist_timeframe(relayout_data, current_layout):
        """Persist selected timeframe so chart refresh keeps x-range."""
        if not relayout_data:
            raise PreventUpdate

        layout_state = current_layout or {}
        if 'xaxis.range[0]' in relayout_data or 'xaxis.range[1]' in relayout_data:
            start = relayout_data.get('xaxis.range[0]')
            end = relayout_data.get('xaxis.range[1]')
            current_range = layout_state.get('x_range') or [None, None]
            if start is None:
                start = current_range[0]
            if end is None:
                end = current_range[1]
            if start is not None and end is not None:
                layout_state['x_range'] = [start, end]
                layout_state['autorange'] = False
                return layout_state
            layout_state['autorange'] = False
        if 'xaxis.range' in relayout_data and isinstance(relayout_data['xaxis.range'], list):
            layout_state['x_range'] = relayout_data['xaxis.range'][:2]
            layout_state['autorange'] = False
            return layout_state
        if relayout_data.get('xaxis.autorange') is True:
            layout_state['x_range'] = None
            layout_state['autorange'] = True
            return layout_state

        raise PreventUpdate

    @app.callback(
        Output('financial-chart', 'figure', allow_duplicate=True),
        [Input('financial-chart', 'relayoutData')],
        [State('financial-chart', 'figure'),
         State('chart-library-toggle', 'value')],
        prevent_initial_call=True
    )
    def autoscale_chart_to_timerange(relayout_data, fig, chart_library):
        """Autoscale y-axes to the visible x-axis timeframe."""
        if chart_library == 'tradingview':
            raise PreventUpdate
        if not relayout_data or not fig or dashboard_state.df is None:
            raise PreventUpdate

        df = dashboard_state.df
        x_range = _resolve_x_range(relayout_data, df, fig)
        if not x_range:
            raise PreventUpdate

        x_start, x_end = x_range
        axis_ranges = _compute_y_ranges_by_axis(fig, x_start, x_end, df)
        if not axis_ranges:
            raise PreventUpdate

        layout_updates = {}
        for axis_id, (y_min, y_max) in axis_ranges.items():
            padded_min, padded_max = _pad_range(y_min, y_max)
            axis_key = _axis_layout_key(axis_id)
            layout_updates[axis_key] = {'range': [padded_min, padded_max], 'autorange': False}
        _apply_layout_updates(fig, layout_updates)

        return fig

    @app.callback(
        Output('tv-main-chart', 'children'),
        [Input('data-loaded-store', 'data'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('chart-library-toggle', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('indicator-settings-store', 'data')],
        [State('ticker-dropdown', 'value')]
    )
    def update_tv_main_chart(data_loaded, chart_elements, selected_signals, chart_library,
                             buy_signals, sell_signals, indicator_settings, ticker):
        """Update the TradingView main chart."""
        if chart_library != 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return html.Div("Load data to view chart", style={'color': theme['text_secondary']})

        df = dashboard_state.df
        df = df.copy()
        df = _rebuild_indicator_dataframe(df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
        dashboard_state.df = df

        buy_signals = buy_signals or []
        sell_signals = sell_signals or []

        config = {
            'show_candlesticks': 'candlesticks' in (chart_elements or []),
            'show_bollinger': 'bollinger' in (chart_elements or []),
            'show_sma': 'sma' in (chart_elements or []),
            'show_ema': 'ema' in (chart_elements or []),
            'show_buy_sell_signals': 'signals' in (chart_elements or []),
            'selected_signals': selected_signals or [],
            'buy_signal_columns': buy_signals,
            'sell_signal_columns': sell_signals
        }

        series_data, series_types, series_options, series_markers = convert_df_to_tv_format(df, config, theme)
        if not series_data or not series_types:
            return html.Div("No series selected for TradingView", style={'color': theme['text_secondary']})
        chart_options = get_tv_chart_options(theme)

        return Tvlwc(
            chartOptions=chart_options,
            seriesData=series_data,
            seriesTypes=series_types,
            seriesOptions=series_options,
            seriesMarkers=series_markers,
            height=420,
            width='100%'
        )

    @app.callback(
        Output('tv-volume-chart', 'children'),
        [Input('data-loaded-store', 'data'),
         Input({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         Input('chart-library-toggle', 'value')]
    )
    def update_tv_volume_chart(data_loaded, plot_values, chart_library):
        """Update the TradingView volume chart."""
        if chart_library != 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return html.Div()

        selected_plots = _collect_selected_plots(plot_values)
        if 'volume' not in (selected_plots or []):
            return html.Div()

        df = dashboard_state.df
        series_data, series_type, series_options = convert_volume_to_tv_format(df, theme)
        chart_options = get_tv_chart_options(theme)

        return Tvlwc(
            chartOptions=chart_options,
            seriesData=[series_data],
            seriesTypes=[series_type],
            seriesOptions=[series_options],
            seriesMarkers=[[]],
            height=200,
            width='100%'
        )

    @app.callback(
        Output('backtest-results', 'children'),
        [Input('run-backtest-btn', 'n_clicks')],
        [State('ticker-dropdown', 'value'),
         State('initial-capital', 'value'),
         State('buy-signals', 'value'),
         State('sell-signals', 'value'),
         State('strategy-mode', 'value'),
         State('amount-per-buy', 'value'),
         State('position-size-pct', 'value'),
         State('kelly-win-rate', 'value'),
         State('kelly-win-loss-ratio', 'value'),
         State('min-holding-period', 'value'),
         State('trailing-stop-pct', 'value'),
         State('position-scaling-pct', 'value'),
         State('take-profit-pct', 'value'),
         State('consecutive-signal-mode', 'value'),
         State('signal-cooldown-bars', 'value'),
         State('signal-logic-mode', 'value'),
         State('signal-window', 'value'),
         State('fx-fee-pct', 'value'),
         State('slippage-pct', 'value'),
         State('commission-pct', 'value')]
    )
    def run_backtest_callback(n_clicks, ticker, initial_capital, buy_signals, sell_signals,
                              strategy_mode, amount_per_buy, position_size_pct,
                              kelly_win_rate, kelly_win_loss_ratio,
                              min_holding_period, trailing_stop_pct, position_scaling_pct,
                              take_profit_pct, consecutive_signal_mode, signal_cooldown_bars,
                              signal_logic, signal_window, fx_fee_pct, slippage_pct, commission_pct):
        """Run backtest and display results."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()

        df = dashboard_state.df
        if df is None:
            return build_alert("Please load market data first", "warning", theme=theme)

        # Validation based on strategy mode
        if not buy_signals:
            return build_alert("Select at least one buy signal", "warning", theme=theme)

        if strategy_mode == 'trading' and not sell_signals:
            return build_alert("Trading mode requires at least one sell signal", "warning", theme=theme)

        # Use empty list for sell signals if not provided in accumulation/rebalancing modes
        sell_signals = sell_signals or []

        min_holding_period = int(min_holding_period or 0)
        trailing_stop_loss = max(0.0, float(trailing_stop_pct or 0)) / 100.0
        position_scaling = max(0.0, float(position_scaling_pct or 0)) / 100.0
        take_profit = max(0.0, float(take_profit_pct or 0)) / 100.0
        fx_fee_pct = max(0.0, float(fx_fee_pct or 0)) / 100.0
        slippage_pct = max(0.0, float(slippage_pct or 0)) / 100.0
        commission_per_trade = max(0.0, float(commission_pct or 0)) / 100.0
        kelly_win_rate = float(kelly_win_rate) if kelly_win_rate is not None else 0.5
        kelly_win_rate = min(1.0, max(0.0, kelly_win_rate))
        kelly_win_loss_ratio = float(kelly_win_loss_ratio) if kelly_win_loss_ratio is not None else 1.5
        kelly_win_loss_ratio = max(0.01, kelly_win_loss_ratio)

        try:
            results = run_backtest(
                df, initial_capital, buy_signals, sell_signals,
                strategy_mode=strategy_mode,
                amount_per_buy=amount_per_buy,
                position_size_pct=position_size_pct,
                kelly_win_rate=kelly_win_rate,
                kelly_win_loss_ratio=kelly_win_loss_ratio,
                min_holding_period=min_holding_period,
                trailing_stop_loss=trailing_stop_loss,
                position_scaling=position_scaling,
                take_profit=take_profit,
                consecutive_signal_mode=consecutive_signal_mode,
                cooldown_bars=signal_cooldown_bars,
                signal_logic=signal_logic or 'or',
                signal_window=signal_window or 0,
                commission_per_trade=commission_per_trade,
                slippage_pct=slippage_pct,
                fx_fee_pct=fx_fee_pct
            )
            backtest_results = create_backtest_results(results, ticker, initial_capital, buy_signals, sell_signals)
            dashboard_state.backtest_results = backtest_results

            baseline_results = None
            if fx_fee_pct > 0 or slippage_pct > 0 or commission_per_trade > 0:
                baseline_results = run_backtest(
                    df, initial_capital, buy_signals, sell_signals,
                    strategy_mode=strategy_mode,
                    amount_per_buy=amount_per_buy,
                    position_size_pct=position_size_pct,
                    kelly_win_rate=kelly_win_rate,
                    kelly_win_loss_ratio=kelly_win_loss_ratio,
                    min_holding_period=min_holding_period,
                    trailing_stop_loss=trailing_stop_loss,
                    position_scaling=position_scaling,
                    take_profit=take_profit,
                    consecutive_signal_mode=consecutive_signal_mode,
                    cooldown_bars=signal_cooldown_bars,
                    signal_logic=signal_logic or 'or',
                    signal_window=signal_window or 0,
                    commission_per_trade=0.0,
                    slippage_pct=0.0,
                    fx_fee_pct=0.0
                )

            baseline_metrics = (
                create_backtest_results(baseline_results, ticker, initial_capital, buy_signals, sell_signals)
                if baseline_results is not None
                else backtest_results
            )
            cost_drag_pct = backtest_results['total_return'] - baseline_metrics['total_return']
            cost_drag_value = backtest_results['final_portfolio_value'] - baseline_metrics['final_portfolio_value']

            # Calculate metrics
            total_return = backtest_results['total_return']
            is_positive = total_return >= 0
            metric_help = {
                "Portfolio Value": "Final account value after the backtest period.",
                "Total Return": "Percent gain/loss from initial capital.",
                "Sharpe Ratio": "Risk-adjusted return (higher is better).",
                "Max Drawdown": "Largest peak-to-trough loss during the period.",
                "Win Rate": "Percent of trades that were profitable.",
            }

            return html.Div([
                build_alert("Backtest completed successfully!", "success", dismissable=False, theme=theme),
                html.Div([
                    build_metric_card(
                        "Return Before Costs",
                        f"{baseline_metrics['total_return']:+.2f}%",
                        baseline_metrics['total_return'] >= 0,
                        theme,
                        info_text="Backtest return with 0% fees and 0% slippage."
                    ),
                    build_metric_card(
                        "Cost Drag",
                        f"{cost_drag_pct:+.2f}%",
                        cost_drag_pct >= 0,
                        theme,
                        info_text="Difference between net return and zero-cost return."
                    ),
                    build_metric_card(
                        "Cost Impact",
                        f"${cost_drag_value:,.2f}",
                        cost_drag_value >= 0,
                        theme,
                        info_text="Final portfolio impact of fees and slippage."
                    ),
                ], style={'marginTop': '10px'}),
                html.Div([
                    build_metric_card(
                        "Portfolio Value",
                        f"${backtest_results['final_portfolio_value']:,.2f}",
                        None,
                        theme,
                        info_text=metric_help["Portfolio Value"]
                    ),
                    build_metric_card(
                        "Total Return",
                        f"{total_return:+.2f}%",
                        is_positive,
                        theme,
                        info_text=metric_help["Total Return"]
                    ),
                    build_metric_card("Sharpe Ratio", f"{backtest_results['sharpe_ratio']:.2f}",
                                     backtest_results['sharpe_ratio'] > 1, theme,
                                     info_text=metric_help["Sharpe Ratio"]),
                    build_metric_card("Max Drawdown", f"{backtest_results['max_drawdown']:.2f}%",
                                     backtest_results['max_drawdown'] > -20, theme,
                                     info_text=metric_help["Max Drawdown"]),
                    build_metric_card("Win Rate", f"{backtest_results['win_rate']:.1f}%",
                                     backtest_results['win_rate'] > 50, theme,
                                     info_text=metric_help["Win Rate"]),
                ], style={'marginTop': '12px'}),
            ], className='fade-in')

        except Exception as e:
            logger.error(f"Backtest error: {e}")
            return build_alert(f"Backtest failed: {str(e)[:60]}", "error", theme=theme)

    # ==================== OPTIMIZATION CALLBACKS ====================

    @app.callback(
        [Output('preview-buy-count', 'children'),
         Output('preview-sell-count', 'children'),
         Output('preview-combo-count', 'children')],
        [Input('data-loaded-store', 'data'),
         Input('max-signals-slider', 'value'),
         Input('max-combos-input', 'value')]
    )
    def update_signal_preview(data_loaded, max_signals, max_combos):
        """Show preview of available signals and estimated combinations."""
        if not data_loaded or dashboard_state.df is None:
            return "0", "0", "0"

        df = dashboard_state.df
        buy_signals, sell_signals = extract_signals(df)

        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        actual_combos = min(len(combinations), max_combos or 100)

        return str(len(buy_signals)), str(len(sell_signals)), str(actual_combos)

    @app.callback(
        [Output('optimization-state', 'data'),
         Output('optimization-interval', 'disabled'),
         Output('optimization-progress', 'children'),
         Output('run-optimization-btn', 'disabled'),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True)],
        [Input('run-optimization-btn', 'n_clicks')],
        [State('initial-capital', 'value'),
         State('max-signals-slider', 'value'),
         State('max-combos-input', 'value'),
         State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def start_optimization(n_clicks, initial_capital, max_signals, max_combos, current_state):
        """Initialize optimization run and enable interval for progress updates."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()
        df = dashboard_state.df

        if df is None:
            return (
                current_state,
                True,
                build_alert("Please load market data first", "warning", theme=theme),
                False,
                html.Div(),
                {'display': 'none'}
            )

        buy_signals, sell_signals = extract_signals(df)
        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        combinations = combinations[:max_combos]

        if not combinations:
            return (
                current_state,
                True,
                build_alert("No valid signal combinations found", "warning", theme=theme),
                False,
                html.Div(),
                {'display': 'none'}
            )

        # Convert tuples to lists for JSON serialization
        combinations_serializable = [[list(buy), list(sell)] for buy, sell in combinations]

        # Reset state in dashboard_state
        dashboard_state.reset_optimization()
        dashboard_state.update_optimization_state(
            running=True,
            total_combinations=len(combinations),
            combinations=combinations_serializable,
            initial_capital=initial_capital
        )

        new_state = {
            'running': True,
            'current_index': 0,
            'total_combinations': len(combinations),
            'completed': False,
            'sort_by': 'Total_Return_%',
            'sort_ascending': False
        }

        progress_ui = html.Div([
            build_progress_bar(0, f"Testing 0/{len(combinations)} combinations...", theme=theme),
            html.Div("Starting optimization...",
                     style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginTop': '4px'})
        ])

        return (
            new_state,
            False,  # Enable interval
            progress_ui,
            True,   # Disable button
            html.Div(),  # Clear previous results
            {'display': 'none'}  # Hide apply button
        )

    @app.callback(
        [Output('optimization-state', 'data', allow_duplicate=True),
         Output('optimization-progress', 'children', allow_duplicate=True),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('optimization-interval', 'disabled', allow_duplicate=True),
         Output('run-optimization-btn', 'disabled', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True),
         Output('optimization-results-store', 'data')],
        [Input('optimization-interval', 'n_intervals')],
        [State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def process_optimization_batch(n_intervals, state):
        """Process a batch of combinations on each interval tick."""
        theme = get_theme()

        if not state or not state.get('running'):
            raise PreventUpdate

        df = dashboard_state.df
        if df is None:
            raise PreventUpdate

        opt_state = dashboard_state.optimization_state
        current_idx = opt_state.get('current_index', 0)
        total = opt_state.get('total_combinations', 0)
        combinations = opt_state.get('combinations', [])
        results = opt_state.get('results', [])
        initial_capital = opt_state.get('initial_capital', 10000)

        if not combinations or current_idx >= total:
            raise PreventUpdate

        # Process batch
        end_idx = min(current_idx + OPTIMIZATION_BATCH_SIZE, total)

        for i in range(current_idx, end_idx):
            buy_combo, sell_combo = combinations[i]
            result = evaluate_signal_combination(df, initial_capital, tuple(buy_combo), tuple(sell_combo))
            results.append(result)

        # Update state
        dashboard_state.update_optimization_state(
            current_index=end_idx,
            results=results
        )

        progress_pct = int((end_idx / total) * 100)

        # Check if complete
        if end_idx >= total:
            dashboard_state.update_optimization_state(running=False, completed=True)

            results_df = pd.DataFrame(results)
            if 'Total_Return_%' in results_df.columns:
                results_df = results_df[results_df['Total_Return_%'].notna()]
                results_df = results_df.sort_values(state.get('sort_by', 'Total_Return_%'),
                                                    ascending=state.get('sort_ascending', False))

            if results_df.empty:
                state['running'] = False
                state['completed'] = True
                return (
                    state,
                    build_alert("All combinations failed", "warning", theme=theme),
                    html.Div(),
                    True,
                    False,
                    {'display': 'none'},
                    []
                )

            state['running'] = False
            state['completed'] = True

            final_progress = html.Div([
                html.Span("\u2713 ", style={'color': theme['accent_green']}),
                html.Span(f"Completed! Tested {total} combinations",
                         style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_green']})
            ])

            results_ui = html.Div([
                _create_best_strategy_highlight(results_df.iloc[0], theme),
                _create_optimization_table(results_df.head(10), theme),
            ], className='fade-in')

            return (
                state,
                final_progress,
                results_ui,
                True,   # Disable interval
                False,  # Re-enable button
                {'display': 'block'},  # Show apply button
                results_df.to_dict('records')
            )

        # Still processing - update progress
        state['current_index'] = end_idx

        progress_ui = html.Div([
            build_progress_bar(progress_pct, f"Testing {end_idx}/{total} combinations...", theme=theme),
            html.Div(f"Found {len([r for r in results if 'Total_Return_%' in r])} valid strategies so far...",
                     style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginTop': '4px'})
        ])

        # Show partial results (top 5 so far)
        valid_results = [r for r in results if 'Total_Return_%' in r]
        partial_results = html.Div()
        if len(valid_results) >= 5:
            partial_df = pd.DataFrame(valid_results).sort_values('Total_Return_%', ascending=False).head(5)
            partial_results = html.Div([
                html.Div("Top strategies so far:",
                        style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '8px'}),
                _create_optimization_table_mini(partial_df, theme)
            ], style={'marginTop': '12px'})

        return (
            state,
            progress_ui,
            partial_results,
            False,  # Keep interval enabled
            True,   # Keep button disabled
            {'display': 'none'},
            []
        )

    @app.callback(
        Output('optimization-results', 'children', allow_duplicate=True),
        [Input('sort-metric-dropdown', 'value')],
        [State('optimization-results-store', 'data'),
         State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def sort_optimization_results(sort_by, results_data, state):
        """Re-sort results when sort metric changes."""
        if not results_data or not state.get('completed'):
            raise PreventUpdate

        theme = get_theme()
        results_df = pd.DataFrame(results_data)

        # Ascending for drawdown (less negative is better), descending for others
        ascending = sort_by == 'Max_Drawdown_%'
        results_df = results_df.sort_values(sort_by, ascending=ascending)

        return html.Div([
            _create_best_strategy_highlight(results_df.iloc[0], theme),
            _create_optimization_table(results_df.head(10), theme),
        ], className='fade-in')

    @app.callback(
        [Output('buy-signals', 'value', allow_duplicate=True),
         Output('sell-signals', 'value', allow_duplicate=True),
         Output('tab-backtest', 'n_clicks', allow_duplicate=True)],
        [Input('apply-strategy-btn', 'n_clicks')],
        [State('optimization-results-store', 'data'),
         State('sort-metric-dropdown', 'value'),
         State('tab-backtest', 'n_clicks')],
        prevent_initial_call=True
    )
    def apply_best_strategy(n_clicks, results_data, sort_by, current_backtest_clicks):
        """Apply the best strategy from optimization to the backtest panel."""
        if not n_clicks or not results_data:
            raise PreventUpdate

        results_df = pd.DataFrame(results_data)
        ascending = sort_by == 'Max_Drawdown_%'
        results_df = results_df.sort_values(sort_by, ascending=ascending)

        best = results_df.iloc[0]

        # Parse signal strings back to lists
        buy_signals = [s.strip() for s in str(best['Buy_Signals']).split(',') if s.strip()]
        sell_signals_str = str(best.get('Sell_Signals', ''))
        sell_signals = [s.strip() for s in sell_signals_str.split(',') if s.strip()]

        # Return values to populate checklists and switch to backtest tab
        return buy_signals, sell_signals, (current_backtest_clicks or 0) + 1

    # ==================== END OPTIMIZATION CALLBACKS ====================

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

    @app.callback(
        [Output('theme-store', 'data'),
         Output('theme-label', 'children')],
        [Input('theme-toggle', 'n_clicks')],
        [State('theme-store', 'data')]
    )
    def toggle_theme(n_clicks, current_theme):
        """Toggle between dark and light themes."""
        if not n_clicks:
            return DEFAULT_THEME, "\u2600\ufe0f"

        new_theme = 'light' if current_theme == 'dark' else 'dark'
        icon = "\U0001f319" if new_theme == 'light' else "\u2600\ufe0f"
        dashboard_state.set_theme(new_theme)
        return new_theme, icon

    # Register clientside callback for keyboard shortcuts
    app.clientside_callback(
        """
        function(id) {
            document.addEventListener('keydown', function(e) {
                // Ctrl+Enter to load data
                if (e.ctrlKey && e.key === 'Enter') {
                    var loadBtn = document.getElementById('load-data-button');
                    if (loadBtn) {
                        loadBtn.click();
                    }
                }
                // Ctrl+B to run backtest
                if (e.ctrlKey && e.key === 'b') {
                    e.preventDefault();
                    var backtestBtn = document.getElementById('run-backtest-btn');
                    if (backtestBtn) {
                        backtestBtn.click();
                    }
                }
                // Escape to close any modals/alerts
                if (e.key === 'Escape') {
                    var alerts = document.querySelectorAll('.alert-dismissible .btn-close');
                    alerts.forEach(function(btn) { btn.click(); });
                }
            });
            return window.dash_clientside.no_update;
        }
        """,
        Output('keyboard-listener', 'children'),
        Input('startup-interval', 'n_intervals')
    )

    # Clientside callback for synced crosshair across all subplots
    app.clientside_callback(
        """
        function(hoverData, figure) {
            if (!figure || !figure.data || figure.data.length === 0) {
                return window.dash_clientside.no_update;
            }

            // Create a copy of the figure
            var newFigure = JSON.parse(JSON.stringify(figure));

            // Remove previous crosshair shapes (identified by our custom name)
            if (newFigure.layout.shapes) {
                newFigure.layout.shapes = newFigure.layout.shapes.filter(function(shape) {
                    return shape.name !== 'crosshair-vline';
                });
            } else {
                newFigure.layout.shapes = [];
            }

            // If no hover data, return figure without crosshair
            if (!hoverData || !hoverData.points || hoverData.points.length === 0) {
                return newFigure;
            }

            // Get the x value from hover data
            var xValue = hoverData.points[0].x;

            // Add vertical line shape spanning all y axes (yref: 'paper' makes it span full height)
            newFigure.layout.shapes.push({
                type: 'line',
                name: 'crosshair-vline',
                x0: xValue,
                x1: xValue,
                y0: 0,
                y1: 1,
                xref: 'x',
                yref: 'paper',
                line: {
                    color: 'rgba(128, 128, 128, 0.7)',
                    width: 1,
                    dash: 'dot'
                }
            });

            return newFigure;
        }
        """,
        Output('financial-chart', 'figure', allow_duplicate=True),
        Input('financial-chart', 'hoverData'),
        State('financial-chart', 'figure'),
        prevent_initial_call=True
    )


# Helper functions for callbacks

def _create_data_table(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create a styled data table."""
    return dash_table.DataTable(
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
    selected = set(selected or [])
    return [[value] if value in selected else [] for _, value in PLOT_OPTIONS]


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
        html.Span(f"${latest_close:.2f}", style={'fontFamily': FONT_MONO, 'color': theme['text_primary']}),
        html.Span(f" {change_sign}{change:.2f} ({change_sign}{change_pct:.2f}%)",
                 style={'fontFamily': FONT_MONO, 'color': change_color, 'marginLeft': '8px'}),
    ])


def _create_optimization_table(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create enhanced optimization results table with all columns."""
    columns = ['Buy_Signals', 'Sell_Signals', 'Total_Return_%', 'Sharpe_Ratio', 'Max_Drawdown_%', 'Trades']
    available_cols = [c for c in columns if c in display_df.columns]

    return dash_table.DataTable(
        id='optimization-table',
        columns=[{"name": c.replace('_', ' '), "id": c} for c in available_cols],
        data=display_df[available_cols].round(2).to_dict('records'),
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
        style_data_conditional=[
            {'if': {'row_index': 0}, 'backgroundColor': f'{theme["accent_green"]}15'},
            {'if': {'row_index': 1}, 'backgroundColor': f'{theme["accent_blue"]}10'},
            {'if': {'row_index': 2}, 'backgroundColor': f'{theme["accent_blue"]}05'},
        ],
        page_size=10,
    )


def _create_optimization_table_mini(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create compact mini-table for partial results during optimization."""
    return dash_table.DataTable(
        columns=[
            {"name": "Buy Signals", "id": "Buy_Signals"},
            {"name": "Return %", "id": "Total_Return_%"},
        ],
        data=display_df[['Buy_Signals', 'Total_Return_%']].round(1).to_dict('records'),
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
                    'fontFamily': FONT_MONO
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
