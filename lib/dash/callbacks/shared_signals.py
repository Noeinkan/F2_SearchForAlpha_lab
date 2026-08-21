"""Signal labeling, option rows, and plot-toggle helpers."""

from __future__ import annotations

import re
from typing import Any, Dict, List

import pandas as pd
from dash import html

from lib.dash.dash_config import OVERLAY_ONLY_INDICATOR_KEYS, PLOT_INDICATOR_OPTIONS


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
    # Stochastic
    "STOCH_Oversold_Buy": "%K < 20 (close near the bottom of its recent range).",
    "STOCH_Overbought_Sell": "%K > 80 (close near the top of its recent range).",
    "STOCH_Cross_Buy": "%K crosses above %D (momentum turns up).",
    "STOCH_Cross_Sell": "%K crosses below %D (momentum turns down).",
    "STOCH_Reversal_Buy": "%K crosses above %D on the way out of oversold.",
    "STOCH_Reversal_Sell": "%K crosses below %D on the way out of overbought.",
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


def _strip_signal_side(col_name: str) -> str:
    return re.sub(r'_(buy|sell)$', '', col_name, flags=re.IGNORECASE)


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
    """Total accepted/rejected trigger counts for buy/sell.

    Thin wrapper over ``lib.dash.signal_markers.trigger_counts``, which the
    chart payload also uses — the counts and the markers therefore cannot
    disagree. Kept as a positional-argument shim because several callbacks and
    tests already call it this way.
    """
    from lib.dash.signal_markers import trigger_counts

    return trigger_counts(
        df,
        selected_signals,
        buy_signals,
        sell_signals,
        logic=signal_logic,
        window=signal_window,
        mode=consecutive_signal_mode,
        cooldown=cooldown_bars,
    )


def _extract_selected_plots(plot_values: List[List[str]]) -> List[str]:
    """Convert pattern-matched plot toggle values into selected indicator list."""
    selected = []
    plot_values = plot_values or []
    for idx, (_, value) in enumerate(PLOT_INDICATOR_OPTIONS):
        values = plot_values[idx] if idx < len(plot_values) else []
        if values:
            selected.append(value)
    return selected


def _build_plot_toggle_values(selected: List[str]) -> List[List[str]]:
    """Build pattern output values for plot toggles from selected list."""
    selected_set = {
        v for v in (selected or []) if v not in OVERLAY_ONLY_INDICATOR_KEYS
    }
    return [
        [value] if value in selected_set else []
        for _, value in PLOT_INDICATOR_OPTIONS
    ]


def _collect_selected_plots(values_list: List[List[str]]) -> List[str]:
    selected = []
    for values in values_list or []:
        if not values:
            continue
        selected.extend(values)
    return selected


def _describe_signal(col_name: str) -> str:
    description = SIGNAL_DESCRIPTIONS.get(col_name)
    if description:
        return description
    base = _format_signal_label(col_name)
    return f"Signal generated from {base}."


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


