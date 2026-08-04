"""Date-window helpers and memoised indicator enrichment cache."""

from __future__ import annotations

from collections import OrderedDict
from typing import Any, Dict

import pandas as pd
from dash import dcc, html

from lib.dash.dash_config import (
    DEFAULT_INDICATOR_SETTINGS,
    FONT_SIZES,
    INDICATOR_SETTING_SCHEMA,
)
from lib.signals.indicators import add_indicators, generate_signals


_ENRICHED_CACHE: OrderedDict[tuple, pd.DataFrame] = OrderedDict()


_ENRICHED_CACHE_MAX = 8


def slice_df_to_window(
    df: pd.DataFrame, start_date: str | None, end_date: str | None
) -> tuple[pd.DataFrame, str]:
    """Return ``df`` clipped to the backtest panel's test window [start, end].

    The single definition of "what period am I evaluating". Both the backtest
    and the optimizer go through here, which is the point: the optimizer used
    to slice and the backtest did not, so a narrowed window ranked combinations
    over one period and then reported metrics for another.

    Non-datetime indexes (e.g. unit tests using a synthetic int index) are
    passed through untouched. The returned label summarises the effective
    window for the results/progress UI.
    """
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return df, "full history (no date index)"

    start = parse_date_bound(start_date)
    end = parse_date_bound(end_date)
    # `.loc[a:b]` on a DatetimeIndex is closed at *both* ends. A bare midnight
    # `end` would drop every intraday bar later that same day; `end + 1 day`
    # (what this used to do) instead reaches past it and swallows the next
    # day's 00:00 bar. Land on the last instant of the end date so daily and
    # intraday frames both stop exactly where the user said.
    end_inclusive = (
        end + pd.Timedelta(days=1) - pd.Timedelta(nanoseconds=1)
        if end is not None else None
    )

    sliced = df.loc[start:end_inclusive] if start is not None or end_inclusive is not None else df
    if sliced.empty:
        # Fall back to the full df so the user sees an error instead of a
        # silent zero-row "no combinations" run.
        return df, f"{df.index.min().date()} → {df.index.max().date()} (test window empty)"

    start_label = sliced.index.min().date().isoformat()
    end_label = sliced.index.max().date().isoformat()
    return sliced, f"{start_label} → {end_label}"


def _settings_key(settings: Dict[str, Any]) -> tuple:
    return tuple(sorted((k, _hashable(v)) for k, v in settings.items()))


def _rebuild_indicator_dataframe(df: pd.DataFrame, indicator_settings: Dict[str, Any]) -> pd.DataFrame:
    """Rebuild indicators/signals from price data using updated settings."""
    if df is None or df.empty:
        return df
    price_cols = [col for col in ['Open', 'High', 'Low', 'Close', 'Volume'] if col in df.columns]
    base_df = df[price_cols].copy() if price_cols else df.copy()
    base_df = add_indicators(base_df, indicator_settings)
    base_df, _ = generate_signals(base_df, indicator_settings)
    return base_df


def parse_date_bound(value, *, default: str | None = None) -> pd.Timestamp | None:
    """Parse a dcc.DatePickerSingle value into a tz-naive Timestamp.

    Returns ``default`` (parsed) when ``value`` is missing, ``None`` when the
    caller explicitly wants an open-ended bound (default ``None``).
    """
    if value is None or value == "":
        return pd.Timestamp(default) if default else None
    try:
        return pd.Timestamp(str(value)[:10])
    except (TypeError, ValueError):
        return pd.Timestamp(default) if default else None


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


def _hashable(v: Any) -> Any:
    if isinstance(v, dict):
        return tuple(sorted((k2, _hashable(v2)) for k2, v2 in v.items()))
    if isinstance(v, list):
        return tuple(v)
    return v


def clear_enriched_cache() -> None:
    """Discard all cached enriched DataFrames (called on new data load or state reset)."""
    _ENRICHED_CACHE.clear()


