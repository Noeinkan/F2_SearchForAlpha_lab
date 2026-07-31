"""
Utilities for loading/saving UI presets to JSON.
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict


PRESET_SCHEMA_VERSION = 2


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_data() -> Dict[str, Any]:
    return {
        "version": PRESET_SCHEMA_VERSION,
        "updated_at": _now_iso(),
        "presets": {}
    }


def load_presets(path: str) -> Dict[str, Any]:
    """Load preset data from disk. Returns default structure if missing/invalid."""
    if not path:
        return _default_data()

    if not os.path.exists(path):
        return _default_data()

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _default_data()

    if not isinstance(data, dict) or "presets" not in data or not isinstance(data["presets"], dict):
        return _default_data()

    if "version" not in data:
        data["version"] = PRESET_SCHEMA_VERSION
    if "updated_at" not in data:
        data["updated_at"] = _now_iso()

    return data


def save_presets(path: str, data: Dict[str, Any]) -> None:
    """Save preset data to disk using atomic replace."""
    if not path:
        return

    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

    data = data or _default_data()
    data["version"] = PRESET_SCHEMA_VERSION
    data["updated_at"] = _now_iso()

    with tempfile.NamedTemporaryFile("w", delete=False, encoding="utf-8", dir=folder or None) as tmp:
        json.dump(data, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        temp_path = tmp.name

    os.replace(temp_path, path)


def normalize_preset(values: Dict[str, Any]) -> Dict[str, Any]:
    """Ensure preset payload has consistent keys and types."""
    values = values or {}
    preset = {
        "market_data": values.get("market_data", {}),
        "chart": values.get("chart", {}),
        "execution": values.get("execution", {}),
        "trade_setup": values.get("trade_setup", {}),
        "signals": values.get("signals", {}),
        "costs": values.get("costs", {})
    }
    return preset
