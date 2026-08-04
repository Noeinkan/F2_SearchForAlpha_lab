"""Data-tab payload, filters, styles, and table builders."""

from __future__ import annotations

from typing import Any, cast

import numpy as np
import pandas as pd
from dash import dash_table, html

from lib.dash.dash_config import DATA_EXPORT_MAX_ROWS, FONT_FAMILY, FONT_SIZES
from lib.dash.helpers import format_df_for_display


_OHLCV_NAME_SET = frozenset({'open', 'high', 'low', 'close', 'volume', 'date', 'index'})


_PORTFOLIO_COLUMN_SET = frozenset({
    'Units',
    'Units_to_buy',
    'Units_to_sell',
    'Cash_Value',
    'Stocks_Value',
    'Portfolio_Value',
    'Buy_Position',
    'Sell_Position',
    'Returns',
    'Strategy_Returns',
    'Cumulative_Returns',
    'Cumulative_Market_Returns',
    'Holding_Period',
    'Trailing_Stop',
    'Buy_Trigger_Accepted',
    'Buy_Trigger_Rejected',
    'Sell_Trigger_Accepted',
    'Sell_Trigger_Rejected',
    'Avg_Entry_Price',
    'Avg_Cost_Basis',
})


_TRIGGER_BUY_FLAG_COLS = frozenset({
    'Buy_Position',
    'Buy_Trigger_Accepted',
})


_TRIGGER_SELL_FLAG_COLS = frozenset({
    'Sell_Position',
    'Sell_Trigger_Accepted',
})


_TRIGGER_REJECT_FLAG_COLS = frozenset({
    'Buy_Trigger_Rejected',
    'Sell_Trigger_Rejected',
})


_OUTLIER_NUMERIC_COLS = frozenset({'Returns', 'Strategy_Returns'})


def records_to_csv(records: list[dict], columns: list[dict[str, str]]) -> str:
    """Serialize visible records to CSV (capped at DATA_EXPORT_MAX_ROWS)."""
    if not records:
        return ''
    capped = records[:DATA_EXPORT_MAX_ROWS]
    col_ids = [col['id'] for col in columns]
    frame = pd.DataFrame(capped)
    if col_ids:
        frame = frame.reindex(columns=col_ids)
    return frame.to_csv(index=False)


def compute_data_summary(records: list[dict], date_col: str) -> dict[str, Any]:
    """Compute summary stats for the data tab strip."""
    if not records:
        return {
            'rows': 0,
            'range': '—',
            'mean_close': None,
            'sigma': None,
            'nan_count': 0,
            'last_close': None,
        }

    dates = [str(rec.get(date_col, ''))[:10] for rec in records if rec.get(date_col)]
    range_str = f"{dates[0]} → {dates[-1]}" if dates else '—'

    close_vals: list[float] = []
    nan_count = 0
    for rec in records:
        for value in rec.values():
            if value is None or (isinstance(value, float) and pd.isna(value)):
                nan_count += 1
        if 'Close' in rec and rec['Close'] is not None:
            try:
                close_vals.append(float(rec['Close']))
            except (TypeError, ValueError):
                pass

    mean_close = sum(close_vals) / len(close_vals) if close_vals else None
    sigma = float(np.std(close_vals)) if len(close_vals) > 1 else (0.0 if close_vals else None)
    last_close = close_vals[-1] if close_vals else None

    return {
        'rows': len(records),
        'range': range_str,
        'mean_close': mean_close,
        'sigma': sigma,
        'nan_count': nan_count,
        'last_close': last_close,
    }


def _percentile_outlier_bounds(
    records: list[dict],
    col_id: str,
    *,
    lo: float = 2.5,
    hi: float = 97.5,
    min_n: int = 20,
) -> tuple[float, float] | None:
    """Return (low, high) percentile bounds, or None if too few finite values."""
    vals: list[float] = []
    for rec in records:
        raw = rec.get(col_id)
        if raw is None:
            continue
        try:
            value = float(raw)
        except (TypeError, ValueError):
            continue
        if np.isfinite(value):
            vals.append(value)
    if len(vals) < min_n:
        return None
    arr = np.asarray(vals, dtype=float)
    low = float(np.percentile(arr, lo))
    high = float(np.percentile(arr, hi))
    if not np.isfinite(low) or not np.isfinite(high) or low == high:
        return None
    return low, high


def classify_data_column_groups(
    column_names: list[str],
    buy_columns: list[str],
    sell_columns: list[str],
) -> dict[str, list[str]]:
    """Partition display columns into OHLCV / indicators / signals / portfolio."""
    signal_set = set(buy_columns) | set(sell_columns)
    groups: dict[str, list[str]] = {
        'ohlcv': [],
        'indicators': [],
        'signals': [],
        'portfolio': [],
    }
    for col in column_names:
        col_lower = col.lower()
        if col in _PORTFOLIO_COLUMN_SET:
            groups['portfolio'].append(col)
        elif col in signal_set or col.endswith('_Buy') or col.endswith('_Sell'):
            groups['signals'].append(col)
        elif col_lower in _OHLCV_NAME_SET:
            groups['ohlcv'].append(col)
        else:
            groups['indicators'].append(col)
    return groups


def build_data_display_payload(df: pd.DataFrame) -> dict[str, Any]:
    """Build the payload stored in ``data-display-store``."""
    from lib.signals.indicators import classify_signal_columns

    display_df = _normalize_display_frame(df)
    classified = classify_signal_columns(df.columns.tolist())
    groups = classify_data_column_groups(
        display_df.columns.tolist(),
        classified['buy'],
        classified['sell'],
    )
    date_col = 'Date' if 'Date' in display_df.columns else display_df.columns[0]
    records = _serialize_data_records(display_df)
    columns = [{"name": c, "id": c} for c in display_df.columns]
    range_start = pd.Timestamp(display_df[date_col].iloc[0]).strftime('%Y-%m-%d')
    range_end = pd.Timestamp(display_df[date_col].iloc[-1]).strftime('%Y-%m-%d')
    return {
        'records': records,
        'columns': columns,
        'groups': groups,
        'range_start': range_start,
        'range_end': range_end,
        'date_column': date_col,
    }


def build_data_table_style_rules(
    records: list[dict],
    column_ids: list[str],
    theme: dict,
) -> list[dict[str, Any]]:
    """Conditional styles: Close vs Open, triggers, and return outliers."""
    style_rules: list[dict[str, Any]] = [
        {'if': {'row_index': 'odd'}, 'backgroundColor': theme['table_row_alt']},
    ]
    col_set = set(column_ids)

    if 'Close' in col_set and 'Open' in col_set:
        style_rules.extend([
            {
                'if': {'filter_query': '{Close} > {Open}', 'column_id': 'Close'},
                'color': theme['accent_green'],
                'fontWeight': '600',
            },
            {
                'if': {'filter_query': '{Close} < {Open}', 'column_id': 'Close'},
                'color': theme['accent_red'],
                'fontWeight': '600',
            },
            {
                'if': {'filter_query': '{Close} is blank', 'column_id': 'Close'},
                'color': theme['text_tertiary'],
            },
        ])

    green_tint = f"{theme['accent_green']}30"
    red_tint = f"{theme['accent_red']}30"
    green_strong = f"{theme['accent_green']}45"
    red_strong = f"{theme['accent_red']}45"
    orange_tint = f"{theme['accent_orange']}35"

    for col_id in column_ids:
        if col_id in _PORTFOLIO_COLUMN_SET:
            if col_id in _TRIGGER_BUY_FLAG_COLS:
                style_rules.append({
                    'if': {'filter_query': f'{{{col_id}}} = 1', 'column_id': col_id},
                    'backgroundColor': green_strong,
                    'fontWeight': '600',
                })
            elif col_id in _TRIGGER_SELL_FLAG_COLS:
                style_rules.append({
                    'if': {'filter_query': f'{{{col_id}}} = 1', 'column_id': col_id},
                    'backgroundColor': red_strong,
                    'fontWeight': '600',
                })
            elif col_id in _TRIGGER_REJECT_FLAG_COLS:
                style_rules.append({
                    'if': {'filter_query': f'{{{col_id}}} = 1', 'column_id': col_id},
                    'backgroundColor': orange_tint,
                })
            elif col_id == 'Units_to_buy':
                style_rules.append({
                    'if': {'filter_query': f'{{{col_id}}} > 0', 'column_id': col_id},
                    'backgroundColor': green_strong,
                    'fontWeight': '600',
                })
            elif col_id == 'Units_to_sell':
                style_rules.append({
                    'if': {'filter_query': f'{{{col_id}}} > 0', 'column_id': col_id},
                    'backgroundColor': red_strong,
                    'fontWeight': '600',
                })
            elif col_id in _OUTLIER_NUMERIC_COLS:
                bounds = _percentile_outlier_bounds(records, col_id)
                if bounds is not None:
                    low, high = bounds
                    style_rules.extend([
                        {
                            'if': {
                                'filter_query': f'{{{col_id}}} > {high}',
                                'column_id': col_id,
                            },
                            'backgroundColor': orange_tint,
                            'fontWeight': '600',
                        },
                        {
                            'if': {
                                'filter_query': f'{{{col_id}}} < {low}',
                                'column_id': col_id,
                            },
                            'backgroundColor': orange_tint,
                            'fontWeight': '600',
                        },
                    ])
            continue

        if col_id.endswith('_Buy'):
            style_rules.append({
                'if': {'filter_query': f'{{{col_id}}} = 1', 'column_id': col_id},
                'backgroundColor': green_tint,
            })
        elif col_id.endswith('_Sell'):
            style_rules.append({
                'if': {'filter_query': f'{{{col_id}}} = 1', 'column_id': col_id},
                'backgroundColor': red_tint,
            })

    return style_rules


def _create_data_table(
    records: list[dict],
    columns: list[dict[str, str]],
    theme: dict,
    *,
    table_id: str = 'data-table',
) -> dash_table.DataTable:
    """Create a styled, sortable data table for the Data tab."""
    column_ids = [col['id'] for col in columns]
    style_rules = build_data_table_style_rules(records, column_ids, theme)

    return dash_table.DataTable(
        id=table_id,
        columns=columns,
        data=cast(Any, records),
        sort_action='native',
        filter_action='native',
        page_action='none',
        export_format='csv',
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
        style_data_conditional=cast(Any, style_rules),
        fixed_rows={'headers': True},
    )


def _normalize_display_frame(df: pd.DataFrame) -> pd.DataFrame:
    """Reset index and ensure a Date column for display/export."""
    display_df = format_df_for_display(df).reset_index()
    first_col = display_df.columns[0]
    if first_col != 'Date' and (
        first_col in ('index', 'Index')
        or pd.api.types.is_datetime64_any_dtype(display_df[first_col])
    ):
        display_df = display_df.rename(columns={first_col: 'Date'})
    return display_df


def _serialize_data_records(display_df: pd.DataFrame) -> list[dict]:
    """Convert a display frame to JSON-safe row dicts."""
    records = cast(list[dict], display_df.to_dict('records'))
    date_col = 'Date' if 'Date' in display_df.columns else display_df.columns[0]
    for rec in records:
        value = rec.get(date_col)
        if value is not None and not isinstance(value, str):
            rec[date_col] = pd.Timestamp(value).strftime('%Y-%m-%d')
    return records


def _create_summary_strip(summary: dict[str, Any], theme: dict) -> html.Div:
    """Compact one-line stats above the data table."""
    mean_close = summary.get('mean_close')
    sigma = summary.get('sigma')
    last_close = summary.get('last_close')
    mean_text = f"${mean_close:.2f}" if mean_close is not None else '—'
    sigma_text = f"{sigma:.2f}" if sigma is not None else '—'
    last_text = f"${last_close:.2f}" if last_close is not None else '—'
    return html.Div(
        [
            html.Span(f"{summary.get('rows', 0)} rows", className='num'),
            html.Span(' · ', style={'color': theme['text_tertiary']}),
            html.Span(summary.get('range', '—'), className='num'),
            html.Span(' · ', style={'color': theme['text_tertiary']}),
            html.Span(f"mean Close {mean_text}", className='num'),
            html.Span(' · ', style={'color': theme['text_tertiary']}),
            html.Span(f"σ {sigma_text}", className='num'),
            html.Span(' · ', style={'color': theme['text_tertiary']}),
            html.Span(f"last {last_text}", className='num'),
            html.Span(' · ', style={'color': theme['text_tertiary']}),
            html.Span(f"NaNs {summary.get('nan_count', 0)}", className='num'),
        ],
        style={
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_secondary'],
            'marginBottom': '8px',
            'flexWrap': 'wrap',
        },
    )


def filter_data_display(
    payload: dict[str, Any] | None,
    row_count: Any,
    col_groups: list[str] | None,
    date_start: str | None,
    date_end: str | None,
) -> tuple[list[dict], list[dict[str, str]], dict[str, Any]]:
    """Filter store payload by controls; returns records, columns, summary."""
    if not payload or not payload.get('records'):
        return [], [], compute_data_summary([], payload.get('date_column', 'Date') if payload else 'Date')

    records = list(payload['records'])
    all_columns = payload['columns']
    groups = payload.get('groups', {})
    date_col = payload.get('date_column', 'Date')
    selected_groups = col_groups or ['ohlcv', 'indicators', 'signals', 'portfolio']

    visible_col_ids: list[str] = []
    for group in selected_groups:
        visible_col_ids.extend(groups.get(group, []))
    if date_col and date_col not in visible_col_ids:
        visible_col_ids = [date_col, *visible_col_ids]

    seen: set[str] = set()
    ordered_ids: list[str] = []
    for col_id in visible_col_ids:
        if col_id not in seen:
            seen.add(col_id)
            ordered_ids.append(col_id)

    column_lookup = {col['id']: col for col in all_columns}
    visible_columns = [column_lookup[col_id] for col_id in ordered_ids if col_id in column_lookup]

    if date_start or date_end:
        filtered: list[dict] = []
        start_key = str(date_start)[:10] if date_start else None
        end_key = str(date_end)[:10] if date_end else None
        for rec in records:
            raw_date = rec.get(date_col)
            if raw_date is None:
                continue
            day = str(raw_date)[:10]
            if start_key and day < start_key:
                continue
            if end_key and day > end_key:
                continue
            filtered.append(rec)
        records = filtered

    if row_count not in (None, 'all', 'All'):
        try:
            records = records[-int(row_count):]
        except (TypeError, ValueError):
            records = records[-50:]

    summary = compute_data_summary(records, date_col)
    trimmed = [{key: rec.get(key) for key in ordered_ids} for rec in records]
    return trimmed, visible_columns, summary


