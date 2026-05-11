"""
Regression: flat agent params must flow through params_to_indicator_settings
and _build_strategy_config_mappers into RSI runtime config and prepared frames.

Guards against silent drops in the two-layer mapping (historically confused with
a CLI --params bug when live_params had already been promoted). Also parametrizes
over every registered agent strategy bundle so future PARAM_KEY_MAP regressions
are caught before they mask optimisation results.
"""

from __future__ import annotations

import os
import sys
from typing import Any
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.agent_strategy import load_bundle, params_to_indicator_settings, prepare_dataframe
from lib.config_loader import get_config
from lib.signals.indicators import _build_strategy_config_mappers


def _strategy_names() -> list[str]:
    cfg = get_config()
    return list((cfg.get("agent_strategies") or {}).keys())


def _low_params(search_space: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {k: v["low"] for k, v in search_space.items() if "low" in v}


def _high_params(search_space: dict[str, dict[str, Any]]) -> dict[str, Any]:
    return {k: v["high"] for k, v in search_space.items() if "high" in v}


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


# ── parametrized sweep over every registered bundle ──────────────────────────

@pytest.mark.parametrize("strategy_name", _strategy_names())
@patch("lib.agent_strategy.fetch_data")
def test_search_space_bounds_produce_distinct_signals(mock_fetch, strategy_name: str) -> None:
    """Low-end vs high-end search_space params must yield different signal totals.

    If this test fails for a strategy, the most likely cause is a missing or
    mis-typed key in PARAM_KEY_MAP (lib/agent_strategy.py) so params silently
    pass through as defaults instead of the requested values.
    """
    mock_fetch.side_effect = lambda *a, **k: _synth_ohlcv(500)
    bundle = load_bundle(strategy_name)

    if not bundle.search_space:
        pytest.skip(f"{strategy_name}: no search_space defined")

    low = _low_params(bundle.search_space)
    high = _high_params(bundle.search_space)

    if low == high:
        pytest.skip(f"{strategy_name}: low == high in every dimension")

    df_low = prepare_dataframe(
        bundle, window_from="2020-01-01", window_to="2021-12-31", params=low
    )
    df_high = prepare_dataframe(
        bundle, window_from="2020-01-01", window_to="2021-12-31", params=high
    )

    buy_cols = [c for c in df_low.columns if c.lower().endswith("_buy")]
    sell_cols = [c for c in df_low.columns if c.lower().endswith("_sell")]

    buy_low  = int(df_low[buy_cols].sum().sum())  if buy_cols  else 0
    buy_high = int(df_high[buy_cols].sum().sum()) if buy_cols  else 0
    sell_low  = int(df_low[sell_cols].sum().sum())  if sell_cols else 0
    sell_high = int(df_high[sell_cols].sum().sum()) if sell_cols else 0

    assert (buy_low, sell_low) != (buy_high, sell_high), (
        f"{strategy_name}: low params {low} and high params {high} both produced "
        f"(buy={buy_low}, sell={sell_low}). "
        "Likely a missing key in PARAM_KEY_MAP (lib/agent_strategy.py)."
    )
