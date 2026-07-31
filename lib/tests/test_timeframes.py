"""Tests for lib.timeframes and interval-aware fetch / metrics."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from lib.backtest_result import metrics_from_result_df
from lib.data_processing import DataFetchError, fetch_data
from lib.timeframes import (
    IntervalError,
    clamp_window,
    normalize_interval,
    periods_per_year,
    resample_ohlcv,
)
from datetime import datetime


def test_normalize_interval_aliases():
    assert normalize_interval(None) == "1d"
    assert normalize_interval("") == "1d"
    assert normalize_interval("D") == "1d"
    assert normalize_interval("60m") == "1h"
    assert normalize_interval("4H") == "4h"
    with pytest.raises(IntervalError):
        normalize_interval("15m")


def test_periods_per_year_map():
    assert periods_per_year("1d") == 252
    assert periods_per_year("1h") == 1638
    assert periods_per_year("4h") == 410


def test_clamp_window_intraday():
    as_of = datetime(2026, 7, 31)
    # Window partially overlaps Yahoo's rolling 730d → start clamped to as_of-730
    start, end = clamp_window("2018-01-01", "2026-06-01", "1h", as_of=as_of)
    assert end == "2026-06-01"
    assert start == "2024-07-31"  # 730 days before 2026-07-31
    start_d, end_d = clamp_window("2018-01-01", "2024-07-01", "1d", as_of=as_of)
    assert start_d == "2018-01-01"
    assert end_d == "2024-07-01"


def test_clamp_window_rejects_stale_intraday_range():
    as_of = datetime(2026, 7, 31)
    with pytest.raises(IntervalError, match="outside that range"):
        clamp_window("2024-01-01", "2024-06-30", "1h", as_of=as_of)


def test_resample_ohlcv_4h():
    # Align to calendar 4h buckets so Open/Close mapping is deterministic.
    idx = pd.date_range("2024-01-02 08:00", periods=8, freq="1h")
    df = pd.DataFrame(
        {
            "Open": [100, 101, 102, 103, 104, 105, 106, 107],
            "High": [101, 102, 103, 104, 105, 106, 107, 108],
            "Low": [99, 100, 101, 102, 103, 104, 105, 106],
            "Close": [100.5, 101.5, 102.5, 103.5, 104.5, 105.5, 106.5, 107.5],
            "Volume": [10] * 8,
        },
        index=idx,
    )
    out = resample_ohlcv(df, "4h")
    assert len(out) == 2
    assert out.iloc[0]["Open"] == 100
    assert out.iloc[0]["Close"] == 103.5
    assert out.iloc[0]["High"] == 104
    assert out.iloc[0]["Low"] == 99
    assert out.iloc[0]["Volume"] == 40


@patch("lib.data_processing.yf.Ticker")
def test_fetch_data_keeps_datetime_index(mock_ticker):
    mock_history = pd.DataFrame(
        {
            "Open": [100, 101],
            "High": [102, 103],
            "Low": [98, 99],
            "Close": [101, 102],
            "Volume": [1_000_000, 1_100_000],
        },
        index=pd.to_datetime(["2020-01-01", "2020-01-02"]),
    )
    mock_ticker.return_value.history.return_value = mock_history
    result = fetch_data("AAPL", "2020-01-01", "2020-01-03", interval="1d")
    assert isinstance(result.index, pd.DatetimeIndex)
    mock_ticker.return_value.history.assert_called_once()
    kwargs = mock_ticker.return_value.history.call_args.kwargs
    assert kwargs.get("interval") == "1d"


@patch("lib.data_processing.yf.Ticker")
def test_fetch_data_4h_resamples(mock_ticker):
    idx = pd.date_range("2025-06-03 08:00", periods=8, freq="1h")
    mock_history = pd.DataFrame(
        {
            "Open": np.arange(100, 108, dtype=float),
            "High": np.arange(101, 109, dtype=float),
            "Low": np.arange(99, 107, dtype=float),
            "Close": np.arange(100.5, 108.5, dtype=float),
            "Volume": [10] * 8,
        },
        index=idx,
    )
    mock_ticker.return_value.history.return_value = mock_history
    result = fetch_data("TSLA", "2025-06-01", "2025-06-10", interval="4h")
    assert len(result) == 2
    kwargs = mock_ticker.return_value.history.call_args.kwargs
    assert kwargs.get("interval") == "1h"


def test_fetch_data_invalid_interval():
    with pytest.raises(DataFetchError):
        fetch_data("AAPL", "2020-01-01", "2020-01-03", interval="15m")


def test_metrics_annualization_differs_by_interval():
    rng = np.random.default_rng(0)
    n = 200
    returns = pd.Series(rng.normal(0.001, 0.01, n))
    df = pd.DataFrame(
        {
            "Portfolio_Value": 10_000 * (1 + returns).cumprod(),
            "Strategy_Returns": returns,
            "Units": 0,
            "Close": 100.0,
            "Units_to_buy": 0,
            "Units_to_sell": 0,
        }
    )
    daily = metrics_from_result_df(df, 10_000, interval="1d")
    hourly = metrics_from_result_df(df, 10_000, interval="1h")
    assert daily.sharpe != hourly.sharpe
    # Same mean/std → higher periods_per_year scales Sharpe up by sqrt ratio
    assert abs(hourly.sharpe) > abs(daily.sharpe)
