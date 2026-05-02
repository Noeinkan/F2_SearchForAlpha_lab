"""
Walk forward orchestrator and verdict tests.

Synthetic OHLCV is large enough to cover the default 5x12+3 month span. The
fetch is mocked so tests are offline. sqlite is redirected to a tmp file.
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.store import trials as trials_store
from lib.walkforward import runner as wf_runner
from lib.walkforward.verdict import (
    DEGRADATION_LIMIT,
    OOS_SHARPE_THRESHOLD,
    ROBUST_FRACTION,
    aggregate,
)


def _fake_long_fetch(symbol: str, start_date: str, end_date: str, validate: bool = True) -> pd.DataFrame:
    """Multi year synthetic OHLCV. Long enough for any walk forward window."""
    rng = np.random.default_rng(2025)
    dates = pd.date_range(start_date, end_date, freq="D")
    if len(dates) < 30:
        dates = pd.date_range(start_date, periods=2000, freq="D")
    n = len(dates)
    returns = rng.standard_normal(n) * 0.012 + 0.0003
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
    db_path = tmp_path / "wf.db"
    monkeypatch.setattr(trials_store, "DEFAULT_DB_PATH", db_path)
    return db_path


def _make_window(idx: int, is_sharpe: float, oos_sharpe: float) -> dict:
    return {
        "index": idx,
        "train": {"sharpe": is_sharpe, "from": "2024-01-01", "to": "2024-12-31"},
        "test": {"sharpe": oos_sharpe, "from": "2025-01-01", "to": "2025-03-31"},
    }


def test_aggregate_robust_when_thresholds_met():
    windows = [
        _make_window(0, 1.8, 1.4),
        _make_window(1, 1.7, 1.3),
        _make_window(2, 1.9, 1.5),
        _make_window(3, 2.0, 1.2),
        _make_window(4, 1.6, 0.8),
    ]
    verdict = aggregate(windows)
    assert verdict.fraction_oos_above_threshold >= ROBUST_FRACTION
    assert verdict.degradation < DEGRADATION_LIMIT
    assert verdict.robust is True
    assert "OOS Sharpe" in verdict.robust_reason


def test_aggregate_not_robust_when_too_few_above_threshold():
    windows = [
        _make_window(0, 1.5, 0.5),
        _make_window(1, 1.5, 0.4),
        _make_window(2, 1.5, 0.3),
        _make_window(3, 1.5, 1.2),
        _make_window(4, 1.5, 1.1),
    ]
    verdict = aggregate(windows)
    assert verdict.robust is False
    assert "windows above OOS Sharpe" in verdict.robust_reason


def test_aggregate_not_robust_when_degradation_high():
    # 5/5 above OOS threshold but huge IS->OOS drop should fail on degradation
    windows = [
        _make_window(0, 5.0, 1.1),
        _make_window(1, 5.0, 1.2),
        _make_window(2, 5.0, 1.05),
        _make_window(3, 5.0, 1.3),
        _make_window(4, 5.0, 1.15),
    ]
    verdict = aggregate(windows)
    assert verdict.fraction_oos_above_threshold == 1.0
    assert verdict.degradation >= DEGRADATION_LIMIT
    assert verdict.robust is False


def test_aggregate_empty_windows_safe():
    verdict = aggregate([])
    assert verdict.robust is False
    assert verdict.is_sharpe_mean == 0.0


def test_run_walkforward_persists_record(isolated_db):
    with patch("lib.walkforward.runner.fetch_data", side_effect=_fake_long_fetch):
        payload = wf_runner.run_walkforward(
            strategy_name="mean_reversion_rsi_bb",
            params={"rsi_window": 14, "bb_window": 20, "bb_std": 2.0},
            options=wf_runner.WalkForwardOptions(n_windows=3, train_months=6, test_months=2),
        )
    assert payload["strategy"] == "mean_reversion_rsi_bb"
    assert len(payload["windows"]) == 3
    assert "aggregate" in payload
    for w in payload["windows"]:
        for key in ("from", "to", "sharpe", "sortino", "max_drawdown"):
            assert key in w["train"]
            assert key in w["test"]

    found = wf_runner.find_recent_walkforward(
        "mean_reversion_rsi_bb",
        {"rsi_window": 14, "bb_window": 20, "bb_std": 2.0},
    )
    assert found is not None
    assert found["walkforward_id"] == payload["walkforward_id"]


def test_find_recent_walkforward_misses_on_different_params(isolated_db):
    with patch("lib.walkforward.runner.fetch_data", side_effect=_fake_long_fetch):
        wf_runner.run_walkforward(
            strategy_name="mean_reversion_rsi_bb",
            params={"rsi_window": 14, "bb_window": 20, "bb_std": 2.0},
            options=wf_runner.WalkForwardOptions(n_windows=2, train_months=6, test_months=2),
        )
    miss = wf_runner.find_recent_walkforward(
        "mean_reversion_rsi_bb",
        {"rsi_window": 99, "bb_window": 20, "bb_std": 2.0},
    )
    assert miss is None


def test_non_overlapping_default(isolated_db):
    """Consecutive train windows must not overlap when step_months is None."""
    with patch("lib.walkforward.runner.fetch_data", side_effect=_fake_long_fetch):
        payload = wf_runner.run_walkforward(
            strategy_name="mean_reversion_rsi_bb",
            params={"rsi_window": 14, "bb_window": 20, "bb_std": 2.0},
            options=wf_runner.WalkForwardOptions(n_windows=3, train_months=6, test_months=2),
        )

    windows = payload["windows"]
    for i in range(len(windows) - 1):
        current_train_end = windows[i]["train"]["to"]
        next_train_start = windows[i + 1]["train"]["from"]
        assert next_train_start >= current_train_end, (
            f"Window {i+1} train start {next_train_start!r} overlaps window {i} "
            f"train end {current_train_end!r}"
        )


def test_params_drive_sizing(isolated_db):
    """params with position_sizing_params reach _backtest_metrics without error."""
    params_with_sizing = {
        "rsi_window": 14,
        "bb_window": 20,
        "bb_std": 2.0,
        "position_sizing_strategy": "percentage_of_portfolio",
        "position_sizing_params": {"percent": 0.5},
    }
    with patch("lib.walkforward.runner.fetch_data", side_effect=_fake_long_fetch):
        payload = wf_runner.run_walkforward(
            strategy_name="mean_reversion_rsi_bb",
            params=params_with_sizing,
            options=wf_runner.WalkForwardOptions(n_windows=2, train_months=6, test_months=2),
        )
    assert len(payload["windows"]) == 2


def test_walkforward_schema_version_2(isolated_db):
    """run_walkforward persists records with schema_version=2."""
    with patch("lib.walkforward.runner.fetch_data", side_effect=_fake_long_fetch):
        payload = wf_runner.run_walkforward(
            strategy_name="mean_reversion_rsi_bb",
            params={"rsi_window": 14, "bb_window": 20, "bb_std": 2.0},
            options=wf_runner.WalkForwardOptions(n_windows=2, train_months=6, test_months=2),
        )

    from lib.store import trials as trials_store

    with trials_store.connect(isolated_db) as conn:
        row = conn.execute(
            "SELECT schema_version FROM sfa_walkforward WHERE walkforward_id = ?",
            (payload["walkforward_id"],),
        ).fetchone()
    assert row is not None
    assert row["schema_version"] == 2, f"Expected schema_version=2, got {row['schema_version']}"
