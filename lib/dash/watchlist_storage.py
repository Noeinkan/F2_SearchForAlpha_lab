"""Named symbol watchlists persisted to ``config/watchlists.json``.

Same shape and atomic-write discipline as :mod:`lib.dash.preset_storage`: disk
is the source of truth, the ``watchlists-store`` in the browser is a mirror, so
starred symbols survive a cache clear and are visible to anything else that
wants to read the file.

Schema::

    {
      "version": 1,
      "updated_at": "2026-08-04T00:00:00+00:00",
      "active": "Default",
      "watchlists": {"Default": ["SPY", "QQQ", "NVDA"]}
    }
"""

from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime, timezone
from typing import Any, Dict, List


WATCHLIST_SCHEMA_VERSION = 1
DEFAULT_LIST_NAME = "Default"

# Seeded on first run so the star filter is not an empty room.
_SEED_SYMBOLS = ["SPY", "QQQ", "AAPL", "NVDA", "TSLA", "MSFT", "AMZN", "GOOGL"]

MAX_LIST_NAME_LENGTH = 40


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _default_data() -> Dict[str, Any]:
    return {
        "version": WATCHLIST_SCHEMA_VERSION,
        "updated_at": _now_iso(),
        "active": DEFAULT_LIST_NAME,
        "watchlists": {DEFAULT_LIST_NAME: list(_SEED_SYMBOLS)},
    }


def _clean_symbol(symbol: str) -> str:
    return str(symbol or "").strip().upper()


def _clean_name(name: str) -> str:
    return str(name or "").strip()[:MAX_LIST_NAME_LENGTH]


def normalize(data: Dict[str, Any] | None) -> Dict[str, Any]:
    """Coerce arbitrary input into the schema, dropping junk entries.

    Callbacks receive this straight from a browser store, so nothing here may
    assume well-formed input.
    """
    if not isinstance(data, dict):
        return _default_data()

    raw_lists = data.get("watchlists")
    if not isinstance(raw_lists, dict):
        return _default_data()

    watchlists: Dict[str, List[str]] = {}
    for name, symbols in raw_lists.items():
        clean_name = _clean_name(name)
        if not clean_name or not isinstance(symbols, (list, tuple)):
            continue
        seen: List[str] = []
        for symbol in symbols:
            value = _clean_symbol(symbol)
            if value and value not in seen:
                seen.append(value)
        watchlists[clean_name] = seen

    if not watchlists:
        watchlists = {DEFAULT_LIST_NAME: []}

    active = _clean_name(data.get("active"))
    if active not in watchlists:
        active = next(iter(watchlists))

    return {
        "version": WATCHLIST_SCHEMA_VERSION,
        "updated_at": str(data.get("updated_at") or _now_iso()),
        "active": active,
        "watchlists": watchlists,
    }


def load_watchlists(path: str) -> Dict[str, Any]:
    """Load watchlists from disk. Returns the seeded default if missing/invalid."""
    if not path or not os.path.exists(path):
        return _default_data()

    try:
        with open(path, "r", encoding="utf-8") as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError):
        return _default_data()

    return normalize(data)


def save_watchlists(path: str, data: Dict[str, Any]) -> Dict[str, Any]:
    """Persist watchlists using atomic replace. Returns the normalized payload."""
    payload = normalize(data)
    payload["updated_at"] = _now_iso()

    if not path:
        return payload

    folder = os.path.dirname(path)
    if folder and not os.path.exists(folder):
        os.makedirs(folder, exist_ok=True)

    with tempfile.NamedTemporaryFile(
        "w", delete=False, encoding="utf-8", dir=folder or None
    ) as tmp:
        json.dump(payload, tmp, indent=2, sort_keys=True)
        tmp.write("\n")
        temp_path = tmp.name

    os.replace(temp_path, path)
    return payload


def toggle_symbol(data: Dict[str, Any], list_name: str, symbol: str) -> Dict[str, Any]:
    """Add ``symbol`` to the list, or remove it when already present."""
    payload = normalize(data)
    name = _clean_name(list_name) or payload["active"]
    value = _clean_symbol(symbol)
    if not value:
        return payload

    symbols = payload["watchlists"].setdefault(name, [])
    if value in symbols:
        symbols.remove(value)
    else:
        symbols.append(value)
    return payload


def is_starred(data: Dict[str, Any] | None, list_name: str, symbol: str) -> bool:
    payload = normalize(data)
    name = _clean_name(list_name) or payload["active"]
    return _clean_symbol(symbol) in payload["watchlists"].get(name, [])


def symbols_in(data: Dict[str, Any] | None, list_name: str) -> List[str]:
    payload = normalize(data)
    name = _clean_name(list_name) or payload["active"]
    return list(payload["watchlists"].get(name, []))


def create_list(data: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Create an empty list and make it active. Existing names are left alone."""
    payload = normalize(data)
    clean = _clean_name(name)
    if not clean:
        return payload
    payload["watchlists"].setdefault(clean, [])
    payload["active"] = clean
    return payload


def delete_list(data: Dict[str, Any], name: str) -> Dict[str, Any]:
    """Delete a list. The final remaining list is emptied rather than removed."""
    payload = normalize(data)
    clean = _clean_name(name)
    if clean not in payload["watchlists"]:
        return payload

    if len(payload["watchlists"]) == 1:
        payload["watchlists"][clean] = []
        return payload

    payload["watchlists"].pop(clean)
    if payload["active"] == clean:
        payload["active"] = next(iter(payload["watchlists"]))
    return payload


def rename_list(data: Dict[str, Any], old_name: str, new_name: str) -> Dict[str, Any]:
    """Rename a list, preserving its symbols and active state."""
    payload = normalize(data)
    old = _clean_name(old_name)
    new = _clean_name(new_name)
    if old not in payload["watchlists"] or not new or new == old:
        return payload
    if new in payload["watchlists"]:
        return payload

    rebuilt = {
        (new if key == old else key): value
        for key, value in payload["watchlists"].items()
    }
    payload["watchlists"] = rebuilt
    if payload["active"] == old:
        payload["active"] = new
    return payload


def list_names(data: Dict[str, Any] | None) -> List[str]:
    return list(normalize(data)["watchlists"].keys())
