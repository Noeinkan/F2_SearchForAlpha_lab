"""Sqlite persistence for paper trading fills."""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.live.broker import Fill
from lib.store import trials as trials_store


_FILLS_SCHEMA = """
CREATE TABLE IF NOT EXISTS sfa_fills (
    fill_id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL,
    commission REAL NOT NULL DEFAULT 0,
    realised_pnl REAL,
    timestamp TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sfa_fills_strategy ON sfa_fills(strategy_name);
"""


def _ensure_table(conn: sqlite3.Connection) -> None:
    conn.executescript(_FILLS_SCHEMA)


def save_fill(strategy_name: str, fill: Fill, db_path: Path | None = None) -> int:
    with trials_store.connect(db_path) as conn:
        _ensure_table(conn)
        cur = conn.execute(
            """
            INSERT INTO sfa_fills (
                strategy_name, symbol, side, quantity, price, commission, realised_pnl, timestamp
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                strategy_name,
                fill.order.symbol,
                fill.order.side.upper(),
                float(fill.quantity),
                float(fill.price),
                float(fill.commission),
                float(fill.realised_pnl),
                fill.timestamp.isoformat(),
            ),
        )
        return int(cur.lastrowid)


def list_fills(strategy_name: str | None = None, db_path: Path | None = None) -> list[dict[str, Any]]:
    with trials_store.connect(db_path) as conn:
        _ensure_table(conn)
        if strategy_name:
            rows = conn.execute(
                "SELECT * FROM sfa_fills WHERE strategy_name = ? ORDER BY timestamp DESC",
                (strategy_name,),
            ).fetchall()
        else:
            rows = conn.execute(
                "SELECT * FROM sfa_fills ORDER BY timestamp DESC"
            ).fetchall()
    return [dict(r) for r in rows]
