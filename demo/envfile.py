"""Read the repo's ``.env`` for a local run of the demo.

In production Docker Compose reads ``/opt/sites/alpha/.env`` and hands the
values to the container, and the image carries no ``.env`` of its own, so this
does nothing there. On a laptop nothing else reads the file: without this,
``python -m demo.server`` ignores the mail settings written in it and refuses
to start.

The rules follow Compose's closely enough that one file works in both places:
a variable already set in the environment wins; ``KEY=value`` lines only, an
optional ``export`` in front; blank lines and ``#`` comment lines skipped;
one pair of matching quotes around a value removed, and what is inside them
kept exactly. Unlike Compose, ``$`` is never expanded -- but quote a password
that contains one anyway, because the server's file goes through Compose.
"""

from __future__ import annotations

import os
import re
from pathlib import Path

REPO_ENV = Path(__file__).resolve().parents[1] / ".env"

_LINE = re.compile(r"^\s*(?:export\s+)?([A-Za-z_][A-Za-z0-9_]*)\s*=(.*)$")


def parse(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        if not raw.strip() or raw.lstrip().startswith("#"):
            continue
        match = _LINE.match(raw)
        if not match:
            continue
        key, value = match.group(1), match.group(2).strip()
        if len(value) >= 2 and value[0] == value[-1] and value[0] in ("'", '"'):
            value = value[1:-1]
        values[key] = value
    return values


def load(path: Path = REPO_ENV) -> list[str]:
    """Set the file's variables that the environment does not already have. Returns their names."""
    try:
        text = path.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return []
    loaded = []
    for key, value in parse(text).items():
        if key not in os.environ:
            os.environ[key] = value
            loaded.append(key)
    return loaded
