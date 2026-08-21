"""Tests for lib.timeframes and interval-aware fetch / metrics."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from lib.backtest_result import metrics_from_result_df
from lib.data_processing import DataFetchError, fetch_data
from lib.timeframes import (
    EARLIEST_HISTORY,
    IntervalError,
    clamp_window,
    full_history_window,
    normalize_interval,
    periods_per_year,
    resample_ohlcv,
)
from datetime import datetime


# --- full_history_window ------------------------------------------------------

_AS_OF = datetime(2026, 8, 4)


def test_full_history_window_daily_is_unbounded():
    """Daily has no Yahoo cap, so "everything" really means everything."""
    start, end = full_history_window("1d", as_of=_AS_OF)
    assert start == EARLIEST_HISTORY
    assert end == "2026-08-04"


@pytest.mark.parametrize("interval", ["1h", "4h"])
def test_full_history_window_intraday_uses_the_lookback_cap(interval):
    start, end = full_history_window(interval, as_of=_AS_OF)
    assert (pd.Timestamp(end) - pd.Timestamp(start)).days == 728


@pytest.mark.parametrize("interval", ["1d", "1h", "4h"])
def test_full_history_window_survives_clamp_unchanged(interval):
    """The two must agree about where the cap is.

    `clamp_window` is applied again inside `fetch_data`. If it disagreed with
    `full_history_window` the fetch would silently narrow, or log a spurious
    "clamping start" warning on every single load.
    """
    window = full_history_window(interval, as_of=_AS_OF)
    assert clamp_window(*window, interval, as_of=_AS_OF) == window


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
    assert periods_per_year("1h") == 1764  # 252 sessions x 7 hourly bars
    assert periods_per_year("4h") == 504   # 252 sessions x 2 four-hour bars


def test_clamp_window_intraday():
    as_of = datetime(2026, 7, 31)
    # Window partially overlaps Yahoo's rolling intraday cap → start clamped
    start, end = clamp_window("2018-01-01", "2026-06-01", "1h", as_of=as_of)
    assert end == "2026-06-01"
    assert start == "2024-08-02"  # 728 days before 2026-07-31
    start_d, end_d = clamp_window("2018-01-01", "2024-07-01", "1d", as_of=as_of)
    assert start_d == "2018-01-01"
    assert end_d == "2024-07-01"


def test_clamp_window_rejects_stale_intraday_range():
    as_of = datetime(2026, 7, 31)
    with pytest.raises(IntervalError, match="outside that range"):
        clamp_window("2024-01-01", "2024-06-30", "1h", as_of=as_of)


def test_clamp_window_relocates_stale_intraday_range():
    as_of = datetime(2026, 7, 31)
    start, end = clamp_window(
        "2018-05-01", "2020-07-27", "4h", as_of=as_of, relocate=True
    )
    assert end == "2026-07-31"
    assert start == "2024-08-02"  # duration exceeds lookback → clipped to it


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


def test_resample_sums_dividends_across_a_bucket():
    """A dividend on any bar of a 4h bucket must survive the resample.

    Regression: non-OHLCV columns were aggregated with "last", so a dividend
    landing on the first 1h bar was overwritten by the final bar's 0.0.
    """
    idx = pd.date_range("2024-03-01 08:00", periods=4, freq="1h")
    df = pd.DataFrame(
        {
            "Open": [10.0, 11.0, 12.0, 13.0],
            "High": [11.0, 12.0, 13.0, 14.0],
            "Low": [9.0, 10.0, 11.0, 12.0],
            "Close": [11.0, 12.0, 13.0, 13.5],
            "Volume": [100, 200, 300, 400],
            "Dividends": [0.25, 0.0, 0.0, 0.0],
            "Stock Splits": [0.0, 0.0, 2.0, 0.0],
        },
        index=idx,
    )

    out = resample_ohlcv(df, "4h")

    assert len(out) == 1
    assert out["Dividends"].iloc[0] == 0.25
    assert out["Stock Splits"].iloc[0] == 2.0
    # OHLCV aggregation must be unchanged by the fix.
    assert out["Open"].iloc[0] == 10.0
    assert out["High"].iloc[0] == 14.0
    assert out["Low"].iloc[0] == 9.0
    assert out["Close"].iloc[0] == 13.5
    assert out["Volume"].iloc[0] == 1000


def test_resample_rejects_a_frame_with_only_action_columns():
    df = pd.DataFrame(
        {"Dividends": [0.1, 0.2]},
        index=pd.date_range("2024-03-01 09:00", periods=2, freq="1h"),
    )
    with pytest.raises(ValueError, match="no OHLCV columns"):
        resample_ohlcv(df, "4h")
