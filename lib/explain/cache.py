"""Answers already paid for: the same question is answered from disk.

A click on the RSI toggle asks the same thing every time, so the second ask
costs nothing and comes back at once. The key is ``gemini.cache_key`` -- a
hash of the model and the full prompt -- so a different number, a different
config default or a different model is a new question. Only good answers are
stored. Entries expire after ``MAX_AGE_DAYS``, because the Google redirect
links in the sources do not live for ever; the popover's Refresh button asks
again before that.

SQLite under ``state/`` (``SFA_EXPLAIN_CACHE`` overrides the path), which the
hosted deploy keeps on the ``/data`` volume.
"""

from __future__ import annotations

import json
import os
import sqlite3
import threading
import time
from contextlib import closing
from pathlib import Path

from lib.explain.gemini import Explanation, Source

DEFAULT_PATH = "state/explain-cache/answers.sqlite3"
MAX_AGE_DAYS = 30

_SCHEMA = """
CREATE TABLE IF NOT EXISTS answers (
    key         TEXT PRIMARY KEY,
    created_at  REAL NOT NULL,
    selection   TEXT NOT NULL DEFAULT '',
    text        TEXT NOT NULL,
    sources     TEXT NOT NULL DEFAULT '[]',
    suggestions TEXT NOT NULL DEFAULT ''
);
"""


class AnswerCache:
    def __init__(self, path: str | os.PathLike, max_age_days: float = MAX_AGE_DAYS) -> None:
        self.path = Path(path)
        self.max_age = max_age_days * 86400
        self._lock = threading.Lock()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock, closing(self._connect()) as db, db:
            db.executescript(_SCHEMA)

    @classmethod
    def from_env(cls) -> "AnswerCache":
        return cls(os.environ.get("SFA_EXPLAIN_CACHE", "").strip() or DEFAULT_PATH)

    def _connect(self) -> sqlite3.Connection:
        return sqlite3.connect(self.path, timeout=10)

    def get(self, key: str) -> tuple[Explanation, float] | None:
        """(answer, when it was stored), or None when missing or too old."""
        with self._lock, closing(self._connect()) as db:
            row = db.execute(
                "SELECT created_at, text, sources, suggestions FROM answers WHERE key = ?", (key,)
            ).fetchone()
        if row is None or time.time() - row[0] > self.max_age:
            return None
        try:
            sources = tuple(Source(str(s["title"]), str(s["url"])) for s in json.loads(row[2]))
        except (ValueError, KeyError, TypeError):
            sources = ()
        return Explanation(True, row[1], sources, row[3]), row[0]

    def put(self, key: str, selection: str, answer: Explanation) -> float:
        if not answer.ok:
            return 0.0
        now = time.time()
        sources = json.dumps([{"title": s.title, "url": s.url} for s in answer.sources])
        with self._lock, closing(self._connect()) as db, db:
            db.execute(
                "INSERT OR REPLACE INTO answers (key, created_at, selection, text, sources, suggestions) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (key, now, selection[:300], answer.text, sources, answer.suggestions),
            )
            db.execute("DELETE FROM answers WHERE created_at < ?", (now - self.max_age,))
        return now
