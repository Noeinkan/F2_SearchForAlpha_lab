"""
Tests for the _ENRICHED_CACHE in lib/dash/callbacks/shared.py.

Verifies:
 - Same object + same settings → cache hit (identity equal)
 - Same object + different settings → cache miss (new enriched object)
 - LRU eviction at capacity 8
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.dash.callbacks.shared import (
    _ENRICHED_CACHE,
    _ENRICHED_CACHE_MAX,
    clear_enriched_cache,
    get_enriched,
)


def _make_price_df(n: int = 60, seed: int = 0) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    close = 100 + np.cumsum(rng.standard_normal(n))
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


_SETTINGS_A = {"sma": {"sma_short": 10, "sma_medium": 20, "sma_long": 50}}
_SETTINGS_B = {"sma": {"sma_short": 5, "sma_medium": 15, "sma_long": 30}}


@pytest.fixture(autouse=True)
def clean_cache():
    clear_enriched_cache()
    yield
    clear_enriched_cache()


def test_cache_hit_same_object_same_settings():
    df = _make_price_df()
    result1 = get_enriched(df, _SETTINGS_A)
    result2 = get_enriched(df, _SETTINGS_A)
    assert result1 is result2, "Expected cache hit — same object should be returned"


def test_cache_miss_different_settings():
    df = _make_price_df()
    result1 = get_enriched(df, _SETTINGS_A)
    result2 = get_enriched(df, _SETTINGS_B)
    assert result1 is not result2, "Different settings should produce different enriched frames"


def test_cache_miss_different_dataframe():
    df1 = _make_price_df(seed=0)
    df2 = _make_price_df(seed=1)
    result1 = get_enriched(df1, _SETTINGS_A)
    result2 = get_enriched(df2, _SETTINGS_A)
    assert result1 is not result2, "Different source DataFrames should produce independent results"


def test_lru_eviction_at_capacity():
    dfs = [_make_price_df(seed=i) for i in range(_ENRICHED_CACHE_MAX + 2)]
    settings_list = [{"sma": {"sma_short": i + 5}} for i in range(_ENRICHED_CACHE_MAX + 2)]

    for df, settings in zip(dfs, settings_list):
        get_enriched(df, settings)

    assert len(_ENRICHED_CACHE) <= _ENRICHED_CACHE_MAX, (
        f"Cache size {len(_ENRICHED_CACHE)} exceeds max {_ENRICHED_CACHE_MAX}"
    )


def test_clear_enriched_cache():
    df = _make_price_df()
    get_enriched(df, _SETTINGS_A)
    assert len(_ENRICHED_CACHE) > 0
    clear_enriched_cache()
    assert len(_ENRICHED_CACHE) == 0
