"""
Optimizer run-history helpers (last N combinatorial searches per session).

Persisted via ``dcc.Store(storage_type='local')`` — keep payloads small
(summary + top row only, not full leaderboards).
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from lib.metrics import DEFAULT_SORT_KEY

MAX_HISTORY_ENTRIES = 12


def summarize_run(
    *,
    ticker: str,
    results: list[dict[str, Any]],
    total_combos: int,
    sort_by: str | None = None,
    realistic: bool = False,
    max_signals: int | None = None,
) -> dict[str, Any]:
    """Build a compact history entry from a finished combinatorial run."""
    top = results[0] if results else None
    return {
        "id": f"run_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}",
        "recorded_at": datetime.now(UTC).isoformat(),
        "ticker": (ticker or "").upper(),
        "kind": "combo",
        "total_combos": int(total_combos or 0),
        "valid_count": len(results),
        "sort_by": sort_by or DEFAULT_SORT_KEY,
        "realistic": bool(realistic),
        "max_signals": max_signals,
        "top": {
            "Buy_Signals": (top or {}).get("Buy_Signals"),
            "Sell_Signals": (top or {}).get("Sell_Signals"),
            "Total_Return_%": (top or {}).get("Total_Return_%"),
            "Sharpe_Ratio": (top or {}).get("Sharpe_Ratio"),
            "Max_Drawdown_%": (top or {}).get("Max_Drawdown_%"),
            "Trades": (top or {}).get("Trades"),
        }
        if top
        else None,
    }


def append_history(
    history: list[dict[str, Any]] | None,
    entry: dict[str, Any],
    *,
    max_entries: int = MAX_HISTORY_ENTRIES,
) -> list[dict[str, Any]]:
    """Prepend ``entry`` and cap length (newest first)."""
    out = [entry, *(history or [])]
    return out[: max(1, int(max_entries))]


def history_for_ticker(
    history: list[dict[str, Any]] | None,
    ticker: str | None,
) -> list[dict[str, Any]]:
    """Filter history to one ticker (case-insensitive). Empty ticker → all."""
    rows = history or []
    if not ticker:
        return list(rows)
    key = ticker.upper()
    return [r for r in rows if str(r.get("ticker", "")).upper() == key]
