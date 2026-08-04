"""Unit tests for unified search-space grid helpers and capped grid search."""

from __future__ import annotations

import os
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.execution_params import (
    DEFAULT_EXECUTION_SEARCH_SPACE,
    partition_params,
)
from lib import grid_search as gsearch
from lib.store import trials as trials_store
from lib.walkforward.spaces import (
    discretize_dimension,
    enumerate_grid,
    estimate_grid_size,
    resolve_search_space,
    validate_space,
)


def test_partition_params_splits_indicator_and_execution():
    parted = partition_params(
        {
            "rsi_window": 14,
            "trailing_stop_loss": 0.05,
            "signal_logic": "and",
            "signal_window": 3,
            "kelly_win_rate": 0.55,
            "kelly_win_loss_ratio": 2.0,
        }
    )
    assert parted.indicator_params == {"rsi_window": 14}
    assert parted.signal_logic == "and"
    assert parted.signal_window == 3
    assert parted.backtest_kwargs["trailing_stop_loss"] == 0.05
    assert parted.backtest_kwargs["position_sizing_strategy"] == "kelly_criterion"
    assert parted.backtest_kwargs["position_sizing_params"]["win_rate"] == 0.55


def test_discretize_int_and_float_step():
    assert discretize_dimension("a", {"type": "int", "low": 0, "high": 10, "step": 5}) == [0, 5, 10]
    vals = discretize_dimension(
        "b", {"type": "float", "low": 0.25, "high": 1.0, "step": 0.25}
    )
    assert vals == [0.25, 0.5, 0.75, 1.0]


def test_enumerate_grid_respects_max_combos():
    space = {
        "x": {"type": "int", "low": 1, "high": 3},
        "y": {"type": "int", "low": 1, "high": 3},
    }
    assert estimate_grid_size(space) == 9
    combos = enumerate_grid(space, max_combos=9)
    assert len(combos) == 9
    with pytest.raises(ValueError, match="cap=4"):
        enumerate_grid(space, max_combos=4)


def test_resolve_search_space_merges_execution_and_filters():
    bundle = {"rsi_window": {"type": "int", "low": 5, "high": 10, "step": 5}}
    merged = resolve_search_space(
        bundle,
        include_execution=True,
        only_keys=["rsi_window", "trailing_stop_loss"],
        execution_space=DEFAULT_EXECUTION_SEARCH_SPACE,
    )
    assert set(merged) == {"rsi_window", "trailing_stop_loss"}
    validate_space(merged)


def test_resolve_search_space_unknown_key():
    with pytest.raises(ValueError, match="Unknown search-space keys"):
        resolve_search_space(
            {"rsi_window": {"type": "int", "low": 5, "high": 10}},
            only_keys=["not_a_real_key"],
        )


def _fake_fetch(symbol: str, start_date: str, end_date: str, validate: bool = True, interval: str = "1d") -> pd.DataFrame:
    rng = np.random.default_rng(7)
    dates = pd.date_range(start_date, end_date, freq="D")
    n = max(len(dates), 120)
    if len(dates) == 0:
        dates = pd.date_range(start_date, periods=n, freq="D")
    returns = rng.standard_normal(n) * 0.01
    close = 100.0 * np.exp(np.cumsum(returns))
    return pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": rng.integers(1_000_000, 3_000_000, n),
        },
        index=dates[:n] if len(dates) >= n else dates,
    )


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "grid.db"
    monkeypatch.setattr(gsearch, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(trials_store, "DEFAULT_DB_PATH", db_path)
    return db_path


def test_run_grid_search_dry_run():
    payload = gsearch.run_grid_search(
        strategy_name="mean_reversion_rsi_bb",
        window_from="2023-01-01",
        window_to="2023-06-01",
        only_keys=["rsi_window"],
        dry_run=True,
    )
    assert payload["mode"] == "grid"
    assert payload["combinations_total"] > 0
    assert payload["within_cap"] is True
    assert payload["space_keys"] == ["rsi_window"]


def test_run_grid_search_persists_best(isolated_db):
    with patch("lib.grid_search.fetch_data", side_effect=_fake_fetch):
        result = gsearch.run_grid_search(
            strategy_name="mean_reversion_rsi_bb",
            metric="sharpe",
            window_from="2023-01-01",
            window_to="2023-06-01",
            only_keys=["rsi_window"],
            max_combos=50,
            seed=3,
            json_output=True,
        )
    assert result.combinations_tested >= 1
    assert "rsi_window" in result.best_params
    contract = result.to_contract()
    assert contract["mode"] == "grid"
    assert contract["best_trial"]["metric"] == "sharpe"

    persisted = trials_store.list_trials(
        strategy_name="mean_reversion_rsi_bb", study_id=result.study_id
    )
    assert len(persisted) == result.combinations_tested
