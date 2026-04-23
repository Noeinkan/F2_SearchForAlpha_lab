"""
Determinism contract for the backtest engine.

Same inputs and same seed must produce identical equity curves and trade logs.
If this test ever fails, the engine has acquired hidden non-determinism (RNG
without a seed, unordered dict iteration, wall clock leakage, etc.) and that
must be fixed before any optimisation or walk forward result is trusted.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.seeds import set_global_seed
from lib.strategy import backtest


def _fixture(seed: int = 42, n_rows: int = 252) -> pd.DataFrame:
    set_global_seed(seed)
    rng = np.random.default_rng(seed)
    dates = pd.date_range("2020-01-01", periods=n_rows, freq="D")
    returns = rng.standard_normal(n_rows) * 0.02
    prices = 100.0 * np.exp(np.cumsum(returns))
    return pd.DataFrame(
        {
            "Open": prices * 1.001,
            "High": prices * 1.02,
            "Low": prices * 0.98,
            "Close": prices,
            "Volume": rng.integers(1_000_000, 10_000_000, n_rows),
            "RSI_Oversold_Buy": (rng.random(n_rows) > 0.85).astype(int),
            "RSI_Overbought_Sell": (rng.random(n_rows) > 0.85).astype(int),
        },
        index=dates,
    )


def _run(df: pd.DataFrame) -> pd.DataFrame:
    return backtest(
        df=df,
        initial_capital=10_000,
        position_sizing_strategy="percentage_of_portfolio",
        position_sizing_params={"percent": 0.1},
        buy_indicators=["RSI_Oversold_Buy"],
        sell_indicators=["RSI_Overbought_Sell"],
    )


def test_backtest_is_deterministic_under_same_seed():
    df_a = _fixture(seed=42)
    df_b = _fixture(seed=42)
    pd.testing.assert_frame_equal(df_a, df_b)

    result_a = _run(df_a)
    result_b = _run(df_b)

    pd.testing.assert_series_equal(result_a["Portfolio_Value"], result_b["Portfolio_Value"])
    pd.testing.assert_series_equal(result_a["Units"], result_b["Units"])
    pd.testing.assert_series_equal(result_a["Cash_Value"], result_b["Cash_Value"])
    pd.testing.assert_series_equal(result_a["Buy_Trigger_Accepted"], result_b["Buy_Trigger_Accepted"])
    pd.testing.assert_series_equal(result_a["Sell_Trigger_Accepted"], result_b["Sell_Trigger_Accepted"])


def test_backtest_diverges_under_different_seed():
    """Sanity check: different seeds must produce different equity curves."""
    df_a = _fixture(seed=42)
    df_b = _fixture(seed=99)

    result_a = _run(df_a)
    result_b = _run(df_b)

    assert not result_a["Portfolio_Value"].equals(result_b["Portfolio_Value"])
