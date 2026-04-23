"""
Promotion gate tests.

Cover the four gate refusal paths (missing walkforward, stale walkforward,
not robust, strategy running) and the success path. The success path also
verifies that live_params get written back to a tmp config file via
ruamel.yaml without losing the surrounding YAML structure.
"""

from __future__ import annotations

import json
import os
import sys
import sqlite3
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import pytest
from ruamel.yaml import YAML

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.promotion import gate as promotion_gate
from lib.promotion import registry as promotion_registry
from lib.store import trials as trials_store


SEED_PARAMS = {"rsi_window": 14, "bb_window": 20, "bb_std": 2.0}
NEW_PARAMS = {"rsi_window": 16, "bb_window": 22, "bb_std": 2.3}


@pytest.fixture
def tmp_config(tmp_path):
    """Write a minimal copy of strategy_config.yaml to tmp."""
    cfg = tmp_path / "strategy_config.yaml"
    cfg.write_text(
        """
agent_strategies:
  mean_reversion_rsi_bb:
    description: "Test bundle."
    ticker: SPY
    buy_signals: [RSI_Oversold_Buy, BB_MeanReversion_Buy]
    sell_signals: [RSI_Overbought_Sell, BB_MeanReversion_Sell]
    mode: trading
    live_params:
      rsi_window: 14
      bb_window: 20
      bb_std: 2.0
    search_space:
      rsi_window: { type: int, low: 5, high: 30 }
""",
        encoding="utf-8",
    )
    return cfg


@pytest.fixture
def tmp_history(tmp_path):
    return tmp_path / "param_history.yaml"


@pytest.fixture
def isolated_db(tmp_path, monkeypatch):
    db_path = tmp_path / "promo.db"
    monkeypatch.setattr(trials_store, "DEFAULT_DB_PATH", db_path)
    return db_path


def _insert_walkforward(
    db_path: Path,
    *,
    strategy: str,
    params: dict,
    aggregate: dict,
    recorded_at: datetime,
):
    with trials_store.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sfa_walkforward (
                walkforward_id, strategy_name, params_json, aggregate_json,
                windows_json, robust, oos_sharpe_mean, degradation, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                f"wf_{recorded_at.strftime('%Y%m%d_%H%M%S')}",
                strategy,
                json.dumps(params, sort_keys=True),
                json.dumps(aggregate),
                json.dumps([]),
                int(bool(aggregate["robust"])),
                float(aggregate["oos_sharpe_mean"]),
                float(aggregate["degradation"]),
                recorded_at.isoformat(),
            ),
        )


def test_gate_refuses_when_no_walkforward(isolated_db):
    decision = promotion_gate.evaluate_gate(
        strategy_name="mean_reversion_rsi_bb",
        candidate_params=NEW_PARAMS,
    )
    assert isinstance(decision, promotion_gate.GateRefusal)
    assert decision.reason == "walkforward_missing"


def test_gate_refuses_when_walkforward_stale(isolated_db):
    _insert_walkforward(
        isolated_db,
        strategy="mean_reversion_rsi_bb",
        params=NEW_PARAMS,
        aggregate={"robust": True, "oos_sharpe_mean": 1.4, "degradation": 0.2, "robust_reason": "ok"},
        recorded_at=datetime.now(UTC) - timedelta(days=10),
    )
    decision = promotion_gate.evaluate_gate(
        strategy_name="mean_reversion_rsi_bb",
        candidate_params=NEW_PARAMS,
    )
    assert isinstance(decision, promotion_gate.GateRefusal)
    assert decision.reason == "walkforward_stale"


def test_gate_refuses_when_not_robust(isolated_db):
    _insert_walkforward(
        isolated_db,
        strategy="mean_reversion_rsi_bb",
        params=NEW_PARAMS,
        aggregate={"robust": False, "oos_sharpe_mean": 0.7, "degradation": 0.5, "robust_reason": "weak"},
        recorded_at=datetime.now(UTC),
    )
    decision = promotion_gate.evaluate_gate(
        strategy_name="mean_reversion_rsi_bb",
        candidate_params=NEW_PARAMS,
    )
    assert isinstance(decision, promotion_gate.GateRefusal)
    assert decision.reason == "not_robust"


def test_gate_refuses_when_strategy_running(isolated_db, tmp_path, monkeypatch):
    _insert_walkforward(
        isolated_db,
        strategy="mean_reversion_rsi_bb",
        params=NEW_PARAMS,
        aggregate={"robust": True, "oos_sharpe_mean": 1.4, "degradation": 0.2, "robust_reason": "ok"},
        recorded_at=datetime.now(UTC),
    )
    monkeypatch.chdir(tmp_path)
    pid_dir = Path("state/running")
    pid_dir.mkdir(parents=True, exist_ok=True)
    (pid_dir / "mean_reversion_rsi_bb.pid").write_text("12345")

    decision = promotion_gate.evaluate_gate(
        strategy_name="mean_reversion_rsi_bb",
        candidate_params=NEW_PARAMS,
    )
    assert isinstance(decision, promotion_gate.GateRefusal)
    assert decision.reason == "strategy_running"


def test_gate_force_overrides_running(isolated_db, tmp_path, monkeypatch):
    _insert_walkforward(
        isolated_db,
        strategy="mean_reversion_rsi_bb",
        params=NEW_PARAMS,
        aggregate={"robust": True, "oos_sharpe_mean": 1.4, "degradation": 0.2, "robust_reason": "ok"},
        recorded_at=datetime.now(UTC),
    )
    monkeypatch.chdir(tmp_path)
    pid_dir = Path("state/running")
    pid_dir.mkdir(parents=True, exist_ok=True)
    (pid_dir / "mean_reversion_rsi_bb.pid").write_text("12345")

    decision = promotion_gate.evaluate_gate(
        strategy_name="mean_reversion_rsi_bb",
        candidate_params=NEW_PARAMS,
        force=True,
    )
    assert isinstance(decision, dict)
    assert decision["walkforward_age_days"] >= 0


def test_gate_passes_and_promotes_to_yaml(isolated_db, tmp_config, tmp_history):
    _insert_walkforward(
        isolated_db,
        strategy="mean_reversion_rsi_bb",
        params=NEW_PARAMS,
        aggregate={"robust": True, "oos_sharpe_mean": 1.4, "degradation": 0.2, "robust_reason": "ok"},
        recorded_at=datetime.now(UTC),
    )

    payload = promotion_gate.promote(
        strategy_name="mean_reversion_rsi_bb",
        candidate_params=NEW_PARAMS,
        config_path=tmp_config,
        history_path=tmp_history,
    )
    assert payload["promoted"] is True
    assert payload["from_params"] == SEED_PARAMS
    assert payload["to_params"] == NEW_PARAMS
    assert payload["diff"]["rsi_window"] == {"from": 14, "to": 16}

    yaml = YAML()
    with tmp_config.open("r", encoding="utf-8") as f:
        doc = yaml.load(f)
    assert dict(doc["agent_strategies"]["mean_reversion_rsi_bb"]["live_params"]) == NEW_PARAMS
    assert doc["agent_strategies"]["mean_reversion_rsi_bb"]["last_promoted"]

    assert tmp_history.exists()
    with tmp_history.open("r", encoding="utf-8") as f:
        history = yaml.load(f)
    assert history["history"]
    assert history["history"][-1]["strategy"] == "mean_reversion_rsi_bb"


def test_diff_params_only_changed_keys():
    diff = promotion_registry.diff_params(
        {"a": 1, "b": 2, "c": 3},
        {"a": 1, "b": 5, "d": 7},
    )
    assert "a" not in diff
    assert diff["b"] == {"from": 2, "to": 5}
    assert diff["c"] == {"from": 3, "to": None}
    assert diff["d"] == {"from": None, "to": 7}
