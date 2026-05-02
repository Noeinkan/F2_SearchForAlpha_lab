"""
Sqlite trial persistence.

Optuna's RDB storage handles the study itself (sampler state, trial graph,
resume across runs). This module stores the richer per trial record an agent
needs: full metric breakdown, seed, wall time, git commit hash. Both stores
sit at state/optuna.db (Optuna namespaces its tables with study_*).
"""

from __future__ import annotations

import json
import os
import sqlite3
import subprocess
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Iterator

DEFAULT_DB_PATH = Path("state/optuna.db")


_SCHEMA = """
CREATE TABLE IF NOT EXISTS sfa_trials (
    trial_id INTEGER PRIMARY KEY AUTOINCREMENT,
    study_id TEXT NOT NULL,
    strategy_name TEXT NOT NULL,
    optuna_trial_number INTEGER,
    metric TEXT NOT NULL,
    objective_value REAL NOT NULL,
    params_json TEXT NOT NULL,
    metrics_json TEXT NOT NULL,
    seed INTEGER NOT NULL,
    wall_seconds REAL NOT NULL,
    git_commit TEXT,
    created_at TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sfa_trials_study ON sfa_trials(study_id);
CREATE INDEX IF NOT EXISTS idx_sfa_trials_strategy ON sfa_trials(strategy_name);

CREATE TABLE IF NOT EXISTS sfa_walkforward (
    walkforward_id TEXT PRIMARY KEY,
    strategy_name TEXT NOT NULL,
    params_json TEXT NOT NULL,
    aggregate_json TEXT NOT NULL,
    windows_json TEXT NOT NULL,
    robust INTEGER NOT NULL,
    oos_sharpe_mean REAL NOT NULL,
    degradation REAL NOT NULL,
    recorded_at TEXT NOT NULL,
    schema_version INTEGER NOT NULL DEFAULT 1
);
CREATE INDEX IF NOT EXISTS idx_sfa_wf_strategy ON sfa_walkforward(strategy_name);
"""


def _ensure_parent(path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)


@contextmanager
def connect(path: Path | None = None) -> Iterator[sqlite3.Connection]:
    target = Path(path) if path else DEFAULT_DB_PATH
    _ensure_parent(target)
    conn = sqlite3.connect(target.as_posix(), isolation_level=None)
    try:
        conn.row_factory = sqlite3.Row
        conn.executescript(_SCHEMA)
        _migrate(conn)
        yield conn
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive schema migrations for existing databases."""
    wf_cols = {row[1] for row in conn.execute("PRAGMA table_info(sfa_walkforward)").fetchall()}
    if "schema_version" not in wf_cols:
        conn.execute(
            "ALTER TABLE sfa_walkforward ADD COLUMN schema_version INTEGER NOT NULL DEFAULT 1"
        )


def get_git_commit() -> str | None:
    try:
        result = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            capture_output=True,
            text=True,
            timeout=2.0,
            check=False,
        )
        if result.returncode == 0:
            return result.stdout.strip()
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None
    return None


@dataclass(frozen=True)
class TrialRecord:
    trial_id: int
    study_id: str
    strategy_name: str
    optuna_trial_number: int | None
    metric: str
    objective_value: float
    params: dict[str, Any]
    metrics: dict[str, Any]
    seed: int
    wall_seconds: float
    git_commit: str | None
    created_at: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "trial_id": self.trial_id,
            "study_id": self.study_id,
            "strategy_name": self.strategy_name,
            "optuna_trial_number": self.optuna_trial_number,
            "metric": self.metric,
            "objective_value": self.objective_value,
            "params": self.params,
            "metrics": self.metrics,
            "seed": self.seed,
            "wall_seconds": self.wall_seconds,
            "git_commit": self.git_commit,
            "created_at": self.created_at,
        }


def save_trial(
    *,
    study_id: str,
    strategy_name: str,
    optuna_trial_number: int | None,
    metric: str,
    objective_value: float,
    params: dict[str, Any],
    metrics: dict[str, Any],
    seed: int,
    wall_seconds: float,
    db_path: Path | None = None,
) -> int:
    """Insert a trial row, return its trial_id."""
    created_at = datetime.now(UTC).isoformat()
    git_commit = get_git_commit()
    with connect(db_path) as conn:
        cur = conn.execute(
            """
            INSERT INTO sfa_trials (
                study_id, strategy_name, optuna_trial_number, metric, objective_value,
                params_json, metrics_json, seed, wall_seconds, git_commit, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                study_id,
                strategy_name,
                optuna_trial_number,
                metric,
                float(objective_value),
                json.dumps(params, default=str),
                json.dumps(metrics, default=str),
                int(seed),
                float(wall_seconds),
                git_commit,
                created_at,
            ),
        )
        return int(cur.lastrowid)


def list_trials(
    *,
    strategy_name: str,
    study_id: str | None = None,
    limit: int | None = None,
    db_path: Path | None = None,
) -> list[TrialRecord]:
    where = "WHERE strategy_name = ?"
    args: list[Any] = [strategy_name]
    if study_id:
        where += " AND study_id = ?"
        args.append(study_id)
    sql = f"SELECT * FROM sfa_trials {where} ORDER BY objective_value DESC"
    if limit:
        sql += " LIMIT ?"
        args.append(int(limit))
    with connect(db_path) as conn:
        rows = conn.execute(sql, args).fetchall()
    return [_row_to_trial(r) for r in rows]


def get_trial(trial_id: int, db_path: Path | None = None) -> TrialRecord | None:
    with connect(db_path) as conn:
        row = conn.execute("SELECT * FROM sfa_trials WHERE trial_id = ?", (int(trial_id),)).fetchone()
    return _row_to_trial(row) if row else None


def _row_to_trial(row: sqlite3.Row) -> TrialRecord:
    return TrialRecord(
        trial_id=int(row["trial_id"]),
        study_id=str(row["study_id"]),
        strategy_name=str(row["strategy_name"]),
        optuna_trial_number=row["optuna_trial_number"],
        metric=str(row["metric"]),
        objective_value=float(row["objective_value"]),
        params=json.loads(row["params_json"]),
        metrics=json.loads(row["metrics_json"]),
        seed=int(row["seed"]),
        wall_seconds=float(row["wall_seconds"]),
        git_commit=row["git_commit"],
        created_at=str(row["created_at"]),
    )
