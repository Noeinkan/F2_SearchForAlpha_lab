"""
End to end tests for the Optuna based Bayesian optimiser.

Tests run a small (5 trial) study against synthetic OHLCV data so they finish
fast and never hit the network. The sqlite stores are isolated to a temp
directory so concurrent test runs do not collide on state/optuna.db.
"""

from __future__ import annotations

import json
import os
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib import bayesian_optimization as bopt
from lib.backtest_result import BacktestMetrics
from lib.store import trials as trials_store


def _fake_fetch(symbol: str, start_date: str, end_date: str, validate: bool = True) -> pd.DataFrame:
    rng = np.random.default_rng(2024)
    dates = pd.date_range(start_date, end_date, freq="D")
    n = max(len(dates), 200)
    if len(dates) == 0:
        dates = pd.date_range(start_date, periods=200, freq="D")
        n = 200
    returns = rng.standard_normal(n) * 0.012
    close = 400.0 * np.exp(np.cumsum(returns))
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
    """Point both the Optuna RDB and the sfa_trials store at a temp sqlite file."""
    db_path = tmp_path / "optuna.db"
    storage_url = f"sqlite:///{db_path.as_posix()}"
    monkeypatch.setattr(bopt, "DEFAULT_STORAGE_URL", storage_url)
    monkeypatch.setattr(bopt, "DEFAULT_DB_PATH", db_path)
    monkeypatch.setattr(trials_store, "DEFAULT_DB_PATH", db_path)
    return db_path


def test_score_metrics_known_values():
    m = BacktestMetrics(
        total_return=0.1, sharpe=1.5, sortino=2.0, calmar=0.9,
        max_drawdown=0.1, num_trades=20, win_rate=0.6, profit_factor=1.8, turnover=0.4,
    )
    assert bopt.score_metrics("sharpe", m) == pytest.approx(1.5)
    assert bopt.score_metrics("sortino", m) == pytest.approx(2.0)
    assert bopt.score_metrics("calmar", m) == pytest.approx(0.9)
    composite = bopt.score_metrics("composite", m)
    expected = 1.0 * 2.0 - 2.0 * 0.1 - 0.5 * 0.4
    assert composite == pytest.approx(expected)


def test_score_metrics_rejects_unknown():
    m = BacktestMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0)
    with pytest.raises(ValueError):
        bopt.score_metrics("not_a_metric", m)


def test_run_study_persists_trials_and_returns_best(isolated_db):
    with patch("lib.bayesian_optimization.fetch_data", side_effect=_fake_fetch):
        result = bopt.run_study(
            strategy_name="mean_reversion_rsi_bb",
            n_trials=5,
            metric="sharpe",
            window_from="2023-01-01",
            window_to="2024-01-01",
            seed=7,
        )
    assert result.trials_completed == 5
    assert result.metric == "sharpe"
    assert isinstance(result.best_value, float)
    assert "rsi_window" in result.best_params

    persisted = trials_store.list_trials(strategy_name="mean_reversion_rsi_bb", study_id=result.study_id)
    assert len(persisted) == 5
    values = [t.objective_value for t in persisted]
    assert values == sorted(values, reverse=True)
    top = persisted[0]
    assert top.objective_value == pytest.approx(result.best_value)
    assert top.metric == "sharpe"
    assert top.metrics.get("sharpe") is not None


def test_run_study_is_deterministic_under_same_seed(isolated_db):
    with patch("lib.bayesian_optimization.fetch_data", side_effect=_fake_fetch):
        first = bopt.run_study(
            strategy_name="mean_reversion_rsi_bb",
            n_trials=4,
            metric="sortino",
            window_from="2023-01-01",
            window_to="2024-01-01",
            seed=11,
            study_id="det_a",
        )
        second = bopt.run_study(
            strategy_name="mean_reversion_rsi_bb",
            n_trials=4,
            metric="sortino",
            window_from="2023-01-01",
            window_to="2024-01-01",
            seed=11,
            study_id="det_b",
        )
    assert first.best_params == second.best_params
    assert first.best_value == pytest.approx(second.best_value)


def test_run_study_rejects_unknown_metric(isolated_db):
    with pytest.raises(ValueError):
        bopt.run_study(
            strategy_name="mean_reversion_rsi_bb",
            n_trials=2,
            metric="garbage",
            window_from="2023-01-01",
            window_to="2024-01-01",
        )


def test_run_study_rejects_missing_window(isolated_db):
    with pytest.raises(ValueError):
        bopt.run_study(
            strategy_name="mean_reversion_rsi_bb",
            n_trials=2,
            metric="sharpe",
        )


def test_run_study_unknown_strategy_raises(isolated_db):
    from lib.agent_strategy import StrategyNotFoundError

    with pytest.raises(StrategyNotFoundError):
        bopt.run_study(
            strategy_name="ghost",
            n_trials=2,
            metric="sharpe",
            window_from="2023-01-01",
            window_to="2024-01-01",
        )


def test_optimise_contract_shape(isolated_db):
    from typer.testing import CliRunner

    from lib.cli.app import app

    runner = CliRunner()
    with patch("lib.bayesian_optimization.fetch_data", side_effect=_fake_fetch):
        result = runner.invoke(
            app,
            [
                "optimise",
                "--name", "mean_reversion_rsi_bb",
                "--trials", "3",
                "--metric", "sharpe",
                "--from", "2023-01-01",
                "--to", "2024-01-01",
                "--seed", "5",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    for key in ("study_id", "trials_completed", "best_trial", "duration_seconds"):
        assert key in payload
    bt = payload["best_trial"]
    for key in ("trial_id", "params", "value", "metric"):
        assert key in bt
    assert payload["trials_completed"] == 3
