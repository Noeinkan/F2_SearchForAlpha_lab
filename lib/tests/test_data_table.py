"""Tests for Data tab filtering, summary, and export helpers."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.dash.callbacks.shared import (
    build_data_display_payload,
    classify_data_column_groups,
    compute_data_summary,
    filter_data_display,
    records_to_csv,
)
from lib.dash.dash_config import DATA_EXPORT_MAX_ROWS


def _sample_df(n: int = 120) -> pd.DataFrame:
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.standard_normal(n))
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": rng.integers(1_000_000, 5_000_000, n),
            "RSI_14": rng.uniform(20, 80, n),
            "MACD_Buy": rng.integers(0, 2, n),
            "MACD_Sell": rng.integers(0, 2, n),
        },
        index=dates,
    )


@pytest.fixture
def payload():
    return build_data_display_payload(_sample_df())


def test_filter_by_groups_ohlcv_only(payload):
    records, columns, _ = filter_data_display(
        payload,
        row_count=50,
        col_groups=['ohlcv'],
        date_start=None,
        date_end=None,
    )
    col_ids = {col['id'] for col in columns}
    assert 'Date' in col_ids
    assert 'Close' in col_ids
    assert 'RSI_14' not in col_ids
    assert 'MACD_Buy' not in col_ids
    assert len(records) == 50


def test_slice_by_date_range(payload):
    records, _, summary = filter_data_display(
        payload,
        row_count='all',
        col_groups=['ohlcv'],
        date_start='2024-02-01',
        date_end='2024-02-29',
    )
    assert summary['rows'] > 0
    for rec in records:
        day = rec['Date']
        assert '2024-02-01' <= day <= '2024-02-29'


def test_row_count_options(payload):
    records_five, _, summary_five = filter_data_display(
        payload, 5, ['ohlcv'], None, None
    )
    records_all, _, summary_all = filter_data_display(
        payload, 'all', ['ohlcv'], None, None
    )
    assert summary_five['rows'] == 5
    assert summary_all['rows'] == len(payload['records'])


def test_summary_strip_values(payload):
    records, _, summary = filter_data_display(
        payload, 25, ['ohlcv'], None, None
    )
    assert summary['rows'] == 25
    assert summary['mean_close'] is not None
    assert summary['sigma'] is not None
    assert summary['last_close'] is not None
    assert summary['nan_count'] >= 0
    assert '→' in summary['range']


def test_compute_data_summary_empty():
    summary = compute_data_summary([], 'Date')
    assert summary['rows'] == 0
    assert summary['mean_close'] is None


def test_classify_data_column_groups():
    groups = classify_data_column_groups(
        ['Date', 'Open', 'Close', 'RSI_14', 'MACD_Buy', 'MACD_Sell'],
        buy_columns=['MACD_Buy'],
        sell_columns=['MACD_Sell'],
    )
    assert 'Date' in groups['ohlcv']
    assert 'RSI_14' in groups['indicators']
    assert 'MACD_Buy' in groups['signals']


def test_export_csv_payload(payload):
    records, columns, _ = filter_data_display(
        payload, 10, ['ohlcv'], None, None
    )
    csv_text = records_to_csv(records, columns)
    lines = csv_text.strip().splitlines()
    assert lines[0].startswith('Date,')
    assert len(lines) == 11  # header + 10 rows


def test_export_csv_respects_cap():
    from lib.dash.callbacks import shared as shared_mod

    records = [{'Date': f'2024-01-{i:02d}', 'Close': float(i)} for i in range(1, 10)]
    columns = [{'name': 'Date', 'id': 'Date'}, {'name': 'Close', 'id': 'Close'}]
    original_cap = shared_mod.DATA_EXPORT_MAX_ROWS
    try:
        shared_mod.DATA_EXPORT_MAX_ROWS = 3
        csv_text = shared_mod.records_to_csv(records, columns)
        assert len(csv_text.strip().splitlines()) == 4  # header + 3 capped rows
    finally:
        shared_mod.DATA_EXPORT_MAX_ROWS = original_cap
