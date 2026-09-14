"""The last session's workspace, kept on disk so a restart picks up where you left off.

What is kept is *context*, not results: the symbol, bar interval, test window,
capital, chart toggles, indicator settings, signal selection, trade setup,
costs and order model — the same snapshot a UI preset takes
(``_build_preset_payload``), plus the order-model controls presets predate.
Price data is refetched (usually straight from the OHLCV cache) and backtests
are not replayed; a saved result would silently go stale the next time the
engine changed.

The file is ``state/ui_session.json`` (``UI_SESSION_FILE_PATH``), which is
gitignored: unlike presets and watchlists it changes on every click and is
nobody's to commit. ``SFA_RESTORE_SESSION=0`` switches both reading and
writing off, for a shared or demo deployment where one visitor's workspace must
not become the next one's starting point.

Callbacks: ``lib/dash/callbacks/ui_session.py``.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile
import threading
from datetime import datetime, timezone
from typing import Any

from lib.dash.preset_storage import normalize_preset

logger = logging.getLogger(__name__)

UI_SESSION_SCHEMA_VERSION = 1
RESTORE_ENV_VAR = 'SFA_RESTORE_SESSION'

# Dash serves callbacks from a thread pool, and two saves racing to os.replace
# the same file fail on Windows with a PermissionError.
_WRITE_LOCK = threading.Lock()

_OFF = {'0', 'false', 'no', 'off'}


def session_restore_enabled() -> bool:
    """On unless ``SFA_RESTORE_SESSION`` is explicitly switched off."""
    return os.environ.get(RESTORE_ENV_VAR, '1').strip().lower() not in _OFF


def normalize_session(payload: dict[str, Any] | None) -> dict[str, Any]:
    """Preset sections plus ``orders``, each guaranteed to be a dict."""
    payload = payload or {}
    session = normalize_preset(payload)
    orders = payload.get('orders')
    session['orders'] = orders if isinstance(orders, dict) else {}
    for key, value in list(session.items()):
        if not isinstance(value, dict):
            session[key] = {}
    return session


def load_ui_session(path: str) -> dict[str, Any] | None:
    """The saved session, or ``None`` if disabled, missing, unreadable or from another schema."""
    if not path or not session_restore_enabled() or not os.path.exists(path):
        return None
    try:
        with open(path, 'r', encoding='utf-8') as handle:
            data = json.load(handle)
    except (OSError, json.JSONDecodeError) as exc:
        logger.warning("Ignoring unreadable UI session file %s: %s", path, exc)
        return None
    if not isinstance(data, dict) or data.get('version') != UI_SESSION_SCHEMA_VERSION:
        return None
    if not isinstance(data.get('session'), dict):
        return None
    return normalize_session(data['session'])


def save_ui_session(path: str, payload: dict[str, Any]) -> bool:
    """Write the session atomically. Returns ``False`` (and logs) instead of raising."""
    if not path or not session_restore_enabled():
        return False
    document = {
        'version': UI_SESSION_SCHEMA_VERSION,
        'updated_at': datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        'session': normalize_session(payload),
    }
    folder = os.path.dirname(path)
    with _WRITE_LOCK:
        temp_path = None
        try:
            if folder:
                os.makedirs(folder, exist_ok=True)
            with tempfile.NamedTemporaryFile(
                'w', delete=False, encoding='utf-8', dir=folder or None, suffix='.tmp',
            ) as tmp:
                json.dump(document, tmp, indent=2, sort_keys=True)
                tmp.write('\n')
                temp_path = tmp.name
            os.replace(temp_path, path)
            return True
        except (OSError, TypeError, ValueError) as exc:
            # A session that fails to save must never break the click that
            # triggered the save.
            logger.warning("Could not save UI session to %s: %s", path, exc)
            if temp_path and os.path.exists(temp_path):
                try:
                    os.remove(temp_path)
                except OSError:
                    pass
            return False


def session_ticker(session: dict[str, Any] | None) -> str | None:
    """The symbol a loaded session was on, upper-cased, or ``None``."""
    if not session:
        return None
    ticker = (session.get('market_data') or {}).get('ticker')
    ticker = str(ticker or '').strip().upper()
    return ticker or None
