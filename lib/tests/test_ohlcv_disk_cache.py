"""Tests for OHLCV disk cache: symbol keys, SWR, incremental merge."""

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
    # Sync executor so SWR tests are deterministic.
    disk._revalidate_executor = lambda job: job()
    yield
    disk._revalidate_executor = None
    dashboard_state.clear_cache()


def test_write_and_load_roundtrip():
    frame = _ohlcv()
    disk.write_frame("AAA", "1d", frame)
    hit = disk.load_frame("AAA", "1d")
    assert hit is not None
    assert len(hit) == len(frame)
    pd.testing.assert_series_equal(
        hit["Close"], frame["Close"], check_freq=False
    )


def test_classify_fresh_stale_expired_daily():
    frame = _ohlcv()
    disk.write_frame("BBB", "1d", frame)
    path = disk.cache_path("BBB", "1d")
    now = path.stat().st_mtime
    assert disk.classify_freshness(path, "1d", now=now) == "fresh"
    tomorrow = (datetime.fromtimestamp(now) + timedelta(days=1)).timestamp()
    assert disk.classify_freshness(path, "1d", now=tomorrow) == "stale"
    far = now + disk._HARD_DAILY_SECONDS + 10
    assert disk.classify_freshness(path, "1d", now=far) == "expired"
    assert disk.classify_freshness(path.with_name("nope.parquet"), "1d") == "missing"


def test_classify_intraday_soft_hard():
    frame = _ohlcv()
    disk.write_frame("CCC", "1h", frame)
    path = disk.cache_path("CCC", "1h")
    old = path.stat().st_mtime
    assert disk.classify_freshness(path, "1h", now=old + 60) == "fresh"
    assert (
        disk.classify_freshness(
            path, "1h", now=old + disk._SOFT_INTRADAY_SECONDS + 10
        )
        == "stale"
    )
    assert (
        disk.classify_freshness(
            path, "1h", now=old + disk._HARD_INTRADAY_SECONDS + 10
        )
        == "expired"
    )


def test_merge_ohlcv_appends_and_overwrites_overlap():
    base = _ohlcv(5, start="2024-01-01")
    # Overlap on last day of base + two new days
    tail = _ohlcv(3, start="2024-01-05")
    tail.loc[tail.index[0], "Close"] = 999.0
    merged = disk.merge_ohlcv(base, tail)
    assert len(merged) == 7  # 5 + 2 new (one overlap)
    assert merged.loc[pd.Timestamp("2024-01-05"), "Close"] == 999.0


def test_incremental_start_backs_up_one_day():
    frame = _ohlcv(5, start="2024-01-01")
    assert disk.incremental_start(frame) == "2024-01-04"


def test_corrupt_parquet_returns_none():
    path = disk.cache_path("DDD", "1d")
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("not-parquet", encoding="utf-8")
    assert disk.load_frame("DDD", "1d") is None


def test_fetch_uses_disk_when_fresh():
    first = _ohlcv(5)
    with patch("lib.data_processing.fetch_data", return_value=first) as fetch:
        assert len(fetch_data_with_cache("EEE", "1900-01-01", "2026-08-04")) == 5
        assert fetch.call_count == 1

    dashboard_state.clear_cache()

    with patch("lib.data_processing.fetch_data") as fetch:
        hit = fetch_data_with_cache("EEE", "1900-01-01", "2026-08-04")
        assert len(hit) == 5
        fetch.assert_not_called()


def test_swr_returns_stale_without_blocking_yahoo():
    first = _ohlcv(5, start="2024-01-01")
    disk.write_frame("HHH", "1d", first)
    path = disk.cache_path("HHH", "1d")
    # Age the file to yesterday (stale, not expired).
    yesterday = (datetime.now() - timedelta(days=1)).timestamp()
    os_utime = __import__("os").utime
    os_utime(path, (yesterday, yesterday))

    tail = _ohlcv(2, start="2024-01-05")
    with patch("lib.data_processing.fetch_data", return_value=tail) as fetch:
        # Request thread gets stale immediately; sync executor then refreshes.
        out = fetch_data_with_cache("HHH", "1900-01-01", "2026-08-04")
        assert len(out) == 5
        # Background revalidate ran via sync executor.
        assert fetch.call_count == 1

    dashboard_state.clear_cache()
    # Disk should now include merged bars.
    loaded = disk.load_frame("HHH", "1d")
    assert loaded is not None
    assert len(loaded) >= 5


def test_force_skips_swr_and_rewrites():
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


def test_expired_blocking_incremental_merges_tail():
    base = _ohlcv(5, start="2024-01-01")
    disk.write_frame("III", "1d", base)
    path = disk.cache_path("III", "1d")
    ancient = datetime.now().timestamp() - disk._HARD_DAILY_SECONDS - 100
    __import__("os").utime(path, (ancient, ancient))

    tail = _ohlcv(3, start="2024-01-05")
    with patch("lib.data_processing.fetch_data", return_value=tail) as fetch:
        out = fetch_data_with_cache("III", "1900-01-01", "2026-08-04")
        assert fetch.call_count == 1
        # 5 base + 2 new (1 overlap day)
        assert len(out) == 7
        start_arg = fetch.call_args[0][1]
        assert start_arg == "2024-01-04"  # incremental_start


def test_stale_if_error_serves_disk():
    base = _ohlcv(4)
    disk.write_frame("JJJ", "1d", base)
    path = disk.cache_path("JJJ", "1d")
    ancient = datetime.now().timestamp() - disk._HARD_DAILY_SECONDS - 100
    __import__("os").utime(path, (ancient, ancient))

    from lib.data_processing import DataFetchError

    with patch(
        "lib.data_processing.fetch_data",
        side_effect=DataFetchError("offline"),
    ):
        out = fetch_data_with_cache("JJJ", "1900-01-01", "2026-08-04")
        assert len(out) == 4


def test_miss_calls_yahoo():
    frame = _ohlcv(4)
    with patch("lib.data_processing.fetch_data", return_value=frame) as fetch:
        out = fetch_data_with_cache("GGG", "1900-01-01", "2026-08-04")
        assert len(out) == 4
        fetch.assert_called_once()
