"""
Regression: flat agent params must flow through params_to_indicator_settings
and _build_strategy_config_mappers into RSI runtime config and prepared frames.

Guards against silent drops in the two-layer mapping (historically confused with
a CLI --params bug when live_params had already been promoted).
"""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.agent_strategy import load_bundle, params_to_indicator_settings, prepare_dataframe
from lib.signals.indicators import _build_strategy_config_mappers


def _synth_ohlcv(n: int = 150) -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range("2020-01-01", periods=n, freq="D")
    close = 100 + np.cumsum(rng.standard_normal(n) * 0.5)
    return pd.DataFrame(
        {
            "Open": close * 0.998,
            "High": close * 1.002,
            "Low": close * 0.995,
            "Close": close,
            "Volume": rng.integers(1_000_000, 2_000_000, size=n),
        },
        index=dates,
    )


def test_flat_params_map_to_rsi_strategy_config():
    flat = {"rsi_window": 3, "rsi_oversold": 12, "rsi_overbought": 88}
    nested = params_to_indicator_settings(flat)
    mappers = _build_strategy_config_mappers()
    cfg = mappers["rsi"](nested.get("rsi", {}))
    assert cfg["rsi"]["window"] == 3
    assert cfg["overbought_oversold"]["upper_threshold"] == 88
    assert cfg["overbought_oversold"]["lower_threshold"] == 12


@patch("lib.agent_strategy.fetch_data")
def test_prepare_dataframe_respects_override_params(mock_fetch):
    mock_fetch.side_effect = lambda *a, **k: _synth_ohlcv(160)
    bundle = load_bundle("connors_rsi2")
    tight = {"rsi_window": 2, "rsi_oversold": 10, "rsi_overbought": 70}
    loose = {"rsi_window": 14, "rsi_oversold": 35, "rsi_overbought": 65}

    df_a = prepare_dataframe(
        bundle, window_from="2020-01-01", window_to="2020-08-01", params=tight
    )
    df_b = prepare_dataframe(
        bundle, window_from="2020-01-01", window_to="2020-08-01", params=loose
    )

    assert "RSI" in df_a.columns and "RSI" in df_b.columns

    buy_a = df_a["RSI_Oversold_Buy"].sum()
    buy_b = df_b["RSI_Oversold_Buy"].sum()
    assert buy_a != buy_b, (
        f"Expected different buy counts when RSI params change, "
        f"got {buy_a} and {buy_b}"
    )

    sell_a = df_a["RSI_Overbought_Sell"].sum()
    sell_b = df_b["RSI_Overbought_Sell"].sum()
    assert sell_a != sell_b, (
        f"Expected different sell counts when RSI params change, "
        f"got {sell_a} and {sell_b}"
    )
