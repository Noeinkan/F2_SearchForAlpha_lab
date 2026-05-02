"""Sqlite persistence for paper trading fills."""

from __future__ import annotations

import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from lib.live.broker import Fill
from lib.store import trials as trials_store


_FILLS_SCHEMA_BASE = """
CREATE TABLE IF NOT EXISTS sfa_fills (
    fill_id INTEGER PRIMARY KEY AUTOINCREMENT,
    strategy_name TEXT NOT NULL,
    symbol TEXT NOT NULL,
    side TEXT NOT NULL,
    quantity REAL NOT NULL,
    price REAL NOT NULL DEFAULT 0,
    commission REAL NOT NULL DEFAULT 0,
    realised_pnl REAL,
    timestamp TEXT NOT NULL,
    client_order_id TEXT,
    status TEXT NOT NULL DEFAULT 'submitted'
);
CREATE INDEX IF NOT EXISTS idx_sfa_fills_strategy ON sfa_fills(strategy_name);
"""


def _ensure_table(conn: sqlite3.Connection) -> None:
    # Create table with new schema for fresh databases; existing tables are unaffected.
    conn.executescript(_FILLS_SCHEMA_BASE)
    # Inline migrations: add new columns to databases created before this schema version.
    cols = {row[1] for row in conn.execute("PRAGMA table_info(sfa_fills)").fetchall()}
    if "client_order_id" not in cols:
        conn.execute("ALTER TABLE sfa_fills ADD COLUMN client_order_id TEXT")
    if "status" not in cols:
        conn.execute(
            "ALTER TABLE sfa_fills ADD COLUMN status TEXT NOT NULL DEFAULT 'submitted'"
        )
    # Partial unique index requires both columns to exist before creation.
    conn.executescript(
        "CREATE UNIQUE INDEX IF NOT EXISTS idx_sfa_fills_coid"
        " ON sfa_fills(client_order_id) WHERE client_order_id IS NOT NULL;"
    )


def record_intent(
    strategy_name: str,
    symbol: str,
    side: str,
    qty: float,
    client_order_id: str,
    db_path: Path | None = None,
) -> bool:
    """Insert a pre-order intent row using INSERT OR IGNORE (idempotent).

    Returns True if the row was freshly inserted, False if it already existed.
    """
    now = datetime.now(UTC).isoformat()
    with trials_store.connect(db_path) as conn:
        _ensure_table(conn)
        cur = conn.execute(
            """
            INSERT OR IGNORE INTO sfa_fills (
                strategy_name, symbol, side, quantity, price, commission,
                realised_pnl, timestamp, client_order_id, status
            ) VALUES (?, ?, ?, ?, 0, 0, NULL, ?, ?, 'intent')
            """,
            (
                strategy_name,
                symbol,
                side.upper(),
                float(qty),
                now,
                client_order_id,
            ),
        )
        return cur.rowcount > 0


def mark_filled(
    client_order_id: str,
    fill: Fill,
    db_path: Path | None = None,
) -> None:
    """Update an intent row to filled status. Idempotent (WHERE status != 'filled')."""
    with trials_store.connect(db_path) as conn:
        _ensure_table(conn)
        conn.execute(
            """
            UPDATE sfa_fills SET
                price = ?,
                commission = ?,
                realised_pnl = ?,
                timestamp = ?,
                status = 'filled'
            WHERE client_order_id = ? AND status != 'filled'
            """,
            (
                float(fill.price),
                float(fill.commission),
                float(fill.realised_pnl),
                fill.timestamp.isoformat(),
                client_order_id,
            ),
        )


def list_fills(
    strategy_name: str | None = None,
    db_path: Path | None = None,
) -> list[dict[str, Any]]:
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
