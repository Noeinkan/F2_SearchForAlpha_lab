"""Tests for persistent OHLCV parquet cache and fetch_data_with_cache disk layer."""

from __future__ import annotations

from datetime import datetime, timedelta
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from lib.dash import ohlcv_disk_cache as disk
from lib.dash.helpers import fetch_data_with_cache
from lib.dash.state import dashboard_state


def _ohlcv(n: int = 10, start: str = "2024-01-01") -> pd.DataFrame:
    rng = np.random.default_rng(3)
    close = 100 + np.cumsum(rng.standard_normal(n))
    dates = pd.date_range(start, periods=n, freq="D")
    return pd.DataFrame(
        {
            "Open": close * 0.99,
            "High": close * 1.01,
            "Low": close * 0.98,
            "Close": close,
            "Volume": rng.integers(1_000_000, 2_000_000, n),
        },
        index=dates,
    )


@pytest.fixture(autouse=True)
def _isolate_cache(tmp_path, monkeypatch):
    monkeypatch.setenv("SFA_OHLCV_CACHE_DIR", str(tmp_path / "ohlcv_cache"))
    dashboard_state.clear_cache()
    yield
    dashboard_state.clear_cache()


def test_write_and_read_roundtrip_same_day():
    frame = _ohlcv()
    disk.write_cached("AAA", "1d", "1900-01-01", "2026-08-04", frame)
    hit = disk.read_cached("AAA", "1d", "1900-01-01", "2026-08-04")
    assert hit is not None
    assert len(hit) == len(frame)
    pd.testing.assert_series_equal(
        hit["Close"], frame["Close"], check_freq=False
    )


def test_daily_stale_after_midnight():
    frame = _ohlcv()
    disk.write_cached("BBB", "1d", "1900-01-01", "2026-08-04", frame)
    path = disk.cache_path("BBB", "1d", "1900-01-01", "2026-08-04")
    # Freshness compares mtime calendar day to "now"; advance now by one day.
    tomorrow = (datetime.now() + timedelta(days=1)).timestamp()
    stale = disk.read_cached(
        "BBB", "1d", "1900-01-01", "2026-08-04", now=tomorrow
    )
    assert stale is None
    assert path.is_file()


def test_intraday_stale_after_ttl():
    frame = _ohlcv()
    disk.write_cached("CCC", "1h", "2024-01-01", "2024-06-01", frame)
    path = disk.cache_path("CCC", "1h", "2024-01-01", "2024-06-01")
    old = path.stat().st_mtime
    future = old + disk._INTRADAY_TTL_SECONDS + 10
    assert disk.read_cached("CCC", "1h", "2024-01-01", "2024-06-01", now=future) is None
    assert disk.read_cached("CCC", "1h", "2024-01-01", "2024-06-01", now=old + 60) is not None


def test_corrupt_parquet_returns_none():
    path = disk.cache_path("DDD", "1d", "1900-01-01", "2026-08-04")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not-parquet", encoding="utf-8")
    assert disk.read_cached("DDD", "1d", "1900-01-01", "2026-08-04") is None


def test_fetch_uses_disk_when_memory_cold():
    first = _ohlcv(5)
    with patch("lib.data_processing.fetch_data", return_value=first) as fetch:
        assert len(fetch_data_with_cache("EEE", "1900-01-01", "2026-08-04")) == 5
        assert fetch.call_count == 1

    dashboard_state.clear_cache()

    with patch("lib.data_processing.fetch_data") as fetch:
        hit = fetch_data_with_cache("EEE", "1900-01-01", "2026-08-04")
        assert len(hit) == 5
        fetch.assert_not_called()


def test_force_skips_disk_and_rewrites():
    first = _ohlcv(5)
    second = _ohlcv(6)
    with patch("lib.data_processing.fetch_data", side_effect=[first, second]) as fetch:
        assert len(fetch_data_with_cache("FFF", "1900-01-01", "2026-08-04")) == 5
        dashboard_state.clear_cache()
        refreshed = fetch_data_with_cache(
            "FFF", "1900-01-01", "2026-08-04", force=True
        )
        assert len(refreshed) == 6
        assert fetch.call_count == 2

    dashboard_state.clear_cache()
    with patch("lib.data_processing.fetch_data") as fetch:
        assert len(fetch_data_with_cache("FFF", "1900-01-01", "2026-08-04")) == 6
        fetch.assert_not_called()


def test_miss_calls_yahoo():
    frame = _ohlcv(4)
    with patch("lib.data_processing.fetch_data", return_value=frame) as fetch:
        out = fetch_data_with_cache("GGG", "1900-01-01", "2026-08-04")
        assert len(out) == 4
        fetch.assert_called_once()
