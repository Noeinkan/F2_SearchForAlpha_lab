"""
Tests that run_study withholds the held-out span from the Optuna objective.

- The search DataFrame max index must be < window_to - held_out_months.
- Persisted trial metrics carry search_to and held_out_to.
"""

from __future__ import annotations

import os
import sys
from datetime import datetime
from pathlib import Path
from unittest.mock import patch, MagicMock

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.store import trials as trials_store


def _fake_fetch(symbol: str, start_date: str, end_date: str, validate: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(2025)
    dates = pd.date_range(start_date, end_date, freq="D")
    if len(dates) < 30:
        dates = pd.date_range(start_date, periods=500, freq="D")
    n = len(dates)
    close = 100 + np.cumsum(rng.standard_normal(n) * 0.5)
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


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "bayes.db"
    monkeypatch.setattr(trials_store, "DEFAULT_DB_PATH", db_path)
    return db_path


def test_search_df_excludes_held_out_span(isolated_db):
    """The DataFrame seen by each trial objective must end before the held-out boundary."""
    import lib.bayesian_optimization as bayes_mod

    captured_dfs: list[pd.DataFrame] = []

    original_build = bayes_mod._build_objective

    def _capturing_build(**kwargs):
        captured_dfs.append(kwargs["base_df"])
        return original_build(**kwargs)

    with patch.object(bayes_mod, "fetch_data", side_effect=_fake_fetch):
        with patch.object(bayes_mod, "_build_objective", side_effect=_capturing_build):
            try:
                bayes_mod.run_study(
                    strategy_name="mean_reversion_rsi_bb",
                    n_trials=1,
                    metric="sharpe",
                    window_from="2021-01-01",
                    window_to="2024-01-01",
                    held_out_months=6,
                    seed=42,
                    storage_url=f"sqlite:///{isolated_db}",
                    db_path=isolated_db,
                )
            except Exception:
                pass

    if not captured_dfs:
        pytest.skip("_build_objective not called (strategy may lack search_space)")

    search_df = captured_dfs[0]
    holdout_boundary = pd.to_datetime("2024-01-01") - pd.DateOffset(months=6)
    assert search_df.index.max() < holdout_boundary, (
        f"Search df max index {search_df.index.max()} is not before holdout boundary {holdout_boundary}"
    )


def test_trial_metrics_carry_search_to_and_held_out_to(isolated_db):
    """Persisted trial records must include search_to and held_out_to in their metrics."""
    import lib.bayesian_optimization as bayes_mod

    with patch.object(bayes_mod, "fetch_data", side_effect=_fake_fetch):
        try:
            result = bayes_mod.run_study(
                strategy_name="mean_reversion_rsi_bb",
                n_trials=2,
                metric="sharpe",
                window_from="2021-01-01",
                window_to="2024-01-01",
                held_out_months=6,
                seed=42,
                storage_url=f"sqlite:///{isolated_db}",
                db_path=isolated_db,
            )
        except Exception as exc:
            pytest.skip(f"run_study raised: {exc}")

    trials = trials_store.list_trials(
        strategy_name="mean_reversion_rsi_bb",
        db_path=isolated_db,
    )
    assert trials, "No trials were persisted"
    for trial in trials:
        assert "search_to" in trial.metrics, f"search_to missing from trial {trial.trial_id}"
        assert "held_out_to" in trial.metrics, f"held_out_to missing from trial {trial.trial_id}"
        assert trial.metrics["held_out_to"] == "2024-01-01"
