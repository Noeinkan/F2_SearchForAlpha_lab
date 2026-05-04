"""
Param history registry.

Writes promoted live_params back to config/strategy_config.yaml using
ruamel.yaml so existing comments and key order are preserved. Also appends to
config/param_history.yaml as a human readable audit log, and writes to the
sfa_promotions sqlite table for programmatic queries.
"""

from __future__ import annotations

import json
import sqlite3
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from ruamel.yaml import YAML

from lib.store import trials as trials_store

CONFIG_PATH = Path("config/strategy_config.yaml")
# update_live_params(..., last_promoted=...) default: stamp a new promotion time
_LAST_PROMOTED_STAMP_NEW = object()
HISTORY_PATH = Path("config/param_history.yaml")
HISTORY_SQL = Path(__file__).parent / "history.sql"


def _yaml() -> YAML:
    y = YAML()
    y.preserve_quotes = True
    y.width = 200
    return y


def get_last_promoted(strategy_name: str, *, config_path: Path | None = None) -> str | None:
    """Return the bundle's last_promoted ISO string if set, else None."""
    target = Path(config_path) if config_path else CONFIG_PATH
    yaml = _yaml()
    with target.open("r", encoding="utf-8") as f:
        data = yaml.load(f)
    bundles = data.get("agent_strategies") or {}
    if strategy_name not in bundles:
        raise KeyError(f"agent_strategies.{strategy_name} not found in {target}")
    raw = bundles[strategy_name].get("last_promoted")
    if raw is None:
        return None
    return str(raw)


def update_live_params(
    strategy_name: str,
    new_params: dict[str, Any],
    *,
    config_path: Path | None = None,
    last_promoted: Any = _LAST_PROMOTED_STAMP_NEW,
) -> dict[str, Any]:
    """Overwrite live_params on the named strategy bundle. Return the prior values.

    ``last_promoted``:
      * default — set ``last_promoted`` to the current UTC time (normal promotion).
      * ``str`` — set to that value (rollback restore).
      * ``None`` — remove ``last_promoted`` from the bundle.
    """
    target = Path(config_path) if config_path else CONFIG_PATH
    yaml = _yaml()
    with target.open("r", encoding="utf-8") as f:
        data = yaml.load(f)

    bundles = data.get("agent_strategies") or {}
    if strategy_name not in bundles:
        raise KeyError(f"agent_strategies.{strategy_name} not found in {target}")

    prior = dict(bundles[strategy_name].get("live_params") or {})
    bundles[strategy_name]["live_params"] = dict(new_params)
    if last_promoted is _LAST_PROMOTED_STAMP_NEW:
        bundles[strategy_name]["last_promoted"] = datetime.now(UTC).isoformat()
    elif last_promoted is None:
        bundles[strategy_name].pop("last_promoted", None)
    else:
        bundles[strategy_name]["last_promoted"] = str(last_promoted)

    with target.open("w", encoding="utf-8") as f:
        yaml.dump(data, f)
    return prior


def append_history_yaml(entry: dict[str, Any], path: Path | None = None) -> None:
    """Append a structured entry to config/param_history.yaml. Creates the file if absent."""
    target = Path(path) if path else HISTORY_PATH
    yaml = _yaml()
    if target.exists():
        with target.open("r", encoding="utf-8") as f:
            current = yaml.load(f) or {}
    else:
        current = {"history": []}
    history = current.setdefault("history", [])
    history.append(entry)
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open("w", encoding="utf-8") as f:
        yaml.dump(current, f)


def _ensure_promotions_table(conn: sqlite3.Connection) -> None:
    conn.executescript(HISTORY_SQL.read_text(encoding="utf-8"))


def record_promotion(entry: dict[str, Any], db_path: Path | None = None) -> None:
    """Insert a row into sfa_promotions. Creates the table on first use."""
    with trials_store.connect(db_path) as conn:
        _ensure_promotions_table(conn)
        conn.execute(
            """
            INSERT INTO sfa_promotions (
                history_entry_id, strategy_name, walkforward_id,
                from_params_json, to_params_json, diff_json, gate_json,
                git_commit, promoted_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                entry["history_entry_id"],
                entry["strategy"],
                entry.get("walkforward_id"),
                json.dumps(entry["from_params"], sort_keys=True),
                json.dumps(entry["to_params"], sort_keys=True),
                json.dumps(entry["diff"], sort_keys=True),
                json.dumps(entry["gate"], sort_keys=True),
                trials_store.get_git_commit(),
                entry["promoted_at"],
            ),
        )


def diff_params(old: dict[str, Any], new: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Return {key: {from, to}} for every key whose value changed or was added."""
    out: dict[str, dict[str, Any]] = {}
    keys = set(old) | set(new)
    for key in sorted(keys):
        before = old.get(key)
        after = new.get(key)
        if before != after:
            out[key] = {"from": before, "to": after}
    return out
