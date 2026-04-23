"""Runner state: PID files and per strategy snapshot rows in sqlite."""

from __future__ import annotations

import json
import os
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.store import trials as trials_store


PID_DIR = Path("state/running")


_STATE_SCHEMA = """
CREATE TABLE IF NOT EXISTS sfa_runner_state (
    strategy_name TEXT PRIMARY KEY,
    pid INTEGER,
    started_at TEXT,
    starting_equity REAL,
    last_heartbeat TEXT,
    guard_state_json TEXT,
    snapshot_json TEXT
);
"""


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_STATE_SCHEMA)


def write_pid(strategy_name: str, pid_dir: Path | None = None) -> Path:
    target_dir = Path(pid_dir) if pid_dir else PID_DIR
    target_dir.mkdir(parents=True, exist_ok=True)
    path = target_dir / f"{strategy_name}.pid"
    path.write_text(str(os.getpid()))
    return path


def remove_pid(strategy_name: str, pid_dir: Path | None = None) -> None:
    target_dir = Path(pid_dir) if pid_dir else PID_DIR
    path = target_dir / f"{strategy_name}.pid"
    if path.exists():
        path.unlink()


def read_pid(strategy_name: str, pid_dir: Path | None = None) -> int | None:
    target_dir = Path(pid_dir) if pid_dir else PID_DIR
    path = target_dir / f"{strategy_name}.pid"
    if not path.exists():
        return None
    try:
        return int(path.read_text().strip())
    except ValueError:
        return None


def upsert_state(
    *,
    strategy_name: str,
    starting_equity: float,
    snapshot: dict[str, Any],
    guard_state: list[dict[str, Any]],
    db_path: Path | None = None,
) -> None:
    now = datetime.now(UTC).isoformat()
    with trials_store.connect(db_path) as conn:
        _ensure_table(conn)
        conn.execute(
            """
            INSERT INTO sfa_runner_state (strategy_name, pid, started_at, starting_equity,
                                          last_heartbeat, guard_state_json, snapshot_json)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(strategy_name) DO UPDATE SET
                last_heartbeat = excluded.last_heartbeat,
                guard_state_json = excluded.guard_state_json,
                snapshot_json = excluded.snapshot_json
            """,
            (
                strategy_name,
                os.getpid(),
                now,
                float(starting_equity),
                now,
                json.dumps(guard_state, default=str),
                json.dumps(snapshot, default=str),
            ),
        )


def read_state(strategy_name: str | None = None, db_path: Path | None = None) -> list[dict[str, Any]]:
    with trials_store.connect(db_path) as conn:
        _ensure_table(conn)
        if strategy_name:
            rows = conn.execute(
                "SELECT * FROM sfa_runner_state WHERE strategy_name = ?", (strategy_name,)
            ).fetchall()
        else:
            rows = conn.execute("SELECT * FROM sfa_runner_state").fetchall()
    out = []
    for r in rows:
        d = dict(r)
        d["guard_state"] = json.loads(d.pop("guard_state_json") or "[]")
        d["snapshot"] = json.loads(d.pop("snapshot_json") or "{}")
        out.append(d)
    return out


def clear_state(strategy_name: str, db_path: Path | None = None) -> None:
    with trials_store.connect(db_path) as conn:
        _ensure_table(conn)
        conn.execute("DELETE FROM sfa_runner_state WHERE strategy_name = ?", (strategy_name,))
