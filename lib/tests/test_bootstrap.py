"""Tests for server-side default session bootstrap."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

from lib.dash.bootstrap import (
    BootstrapSnapshot,
    build_default_chart_config,
    load_market_session,
    try_bootstrap_default_session,
)
from lib.dash.state import dashboard_state


def _sample_ohlcv(n: int = 80) -> pd.DataFrame:
    rng = np.random.default_rng(7)
    close = 200 + np.cumsum(rng.standard_normal(n))
    dates = pd.date_range("2024-01-01", periods=n, freq="D")
    return pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": rng.integers(1_000_000, 5_000_000, n),
        },
        index=dates,
    )


@pytest.fixture(autouse=True)
def reset_state():
    dashboard_state.reset()
    yield
    dashboard_state.reset()


def test_build_default_chart_config_matches_sidebar_defaults():
    config = build_default_chart_config()
    assert "candlestick" in config["selected_plots"]
    assert "volume" in config["selected_plots"]
    assert config["show_candlesticks"] is True
    assert config["show_bollinger"] is True


@patch("lib.dash.bootstrap.fetch_data_with_cache")
def test_load_market_session_returns_snapshot(mock_fetch):
    mock_fetch.return_value = _sample_ohlcv()
    snapshot = load_market_session("TSLA", "2024-01-01", "2024-06-01")
    assert isinstance(snapshot, BootstrapSnapshot)
    assert snapshot.header_symbol == "TSLA"
    assert snapshot.data_status.endswith("ROWS")
    assert dashboard_state.df is not None
    assert dashboard_state.ticker == "TSLA"


def test_snapshot_carries_no_chart_artifact():
    """The chart is built by callbacks.chart, never by the bootstrap.

    Seeding a payload here would serialise a megabyte of bars into the page
    that the client renderer immediately replaces.
    """
    assert not hasattr(BootstrapSnapshot, "chart_payload")
    assert "chart_payload" not in BootstrapSnapshot.__dataclass_fields__
    assert "chart_figure" not in BootstrapSnapshot.__dataclass_fields__


@patch("lib.dash.bootstrap.load_market_session", side_effect=RuntimeError("offline"))
def test_try_bootstrap_default_session_returns_none_on_failure(_mock_load):
    assert try_bootstrap_default_session() is None
    assert dashboard_state.df is None
