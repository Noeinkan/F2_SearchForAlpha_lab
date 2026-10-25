"""Whitelist of people allowed into the hosted workspace.

Modelled on Capsar's beta invites: the owner adds an email, the server makes a
one-off passcode, stores only its hash and mails the plain passcode to that
address. The person then signs in with email + passcode on the normal login
form. Nobody can register themselves.

Who is admin is not stored here: ``ADMIN_EMAILS`` (see ``hosted.login``) is
read on every request, so it can change without touching the database.

The database lives under ``state/``, which the deploy keeps on the ``/data``
volume, so the whitelist survives a redeploy.

Command line, for the server shell or a laptop:

    python -m hosted.users add someone@example.com
    python -m hosted.users list
    python -m hosted.users revoke someone@example.com
"""

from __future__ import annotations

import hashlib
import os
import secrets
import sqlite3
import sys
import threading
import time
from dataclasses import dataclass
from pathlib import Path

from werkzeug.security import check_password_hash, generate_password_hash

DEFAULT_DB = "state/hosted-users/users.sqlite3"

# No 0/O, 1/l/I: a passcode is often read off a phone and typed by hand.
PASSCODE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZabcdefghjkmnpqrstuvwxyz23456789"
PASSCODE_LENGTH = 12

_SCHEMA = """
CREATE TABLE IF NOT EXISTS users (
    email         TEXT PRIMARY KEY,
    passcode_hash TEXT NOT NULL,
    is_active     INTEGER NOT NULL DEFAULT 1,
    invited_at    REAL NOT NULL,
    invited_by    TEXT NOT NULL DEFAULT '',
    last_login    REAL
);
CREATE TABLE IF NOT EXISTS events (
    id     INTEGER PRIMARY KEY AUTOINCREMENT,
    at     REAL NOT NULL,
    email  TEXT NOT NULL,
    kind   TEXT NOT NULL,
    detail TEXT NOT NULL DEFAULT ''
);
"""


class UserError(ValueError):
    """A request the whitelist cannot carry out (bad email, unknown user)."""


@dataclass(frozen=True)
class User:
    email: str
    passcode_hash: str
    is_active: bool
    invited_at: float
    invited_by: str
    last_login: float | None

    @property
    def fingerprint(self) -> str:
        """Goes into the session cookie: a new passcode changes it and signs the old cookie out."""
        return fingerprint(self.passcode_hash)


def fingerprint(secret_hash: str) -> str:
    return hashlib.sha256(b"sfa-session\0" + secret_hash.encode()).hexdigest()[:16]


def normalize_email(email: str) -> str:
    value = (email or "").strip().lower()
    local, at, domain = value.partition("@")
    if not at or not local or "." not in domain or domain.startswith(".") or domain.endswith(".") or " " in value:
        raise UserError(f"{email!r} is not an email address")
    return value


def new_passcode() -> str:
    return "".join(secrets.choice(PASSCODE_ALPHABET) for _ in range(PASSCODE_LENGTH))


class UserStore:
    def __init__(self, path: str | os.PathLike = DEFAULT_DB) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.Lock()
        with self._connect() as db:
            db.executescript(_SCHEMA)

    @classmethod
    def from_env(cls) -> "UserStore":
        return cls(os.environ.get("SITE_USERS_DB", DEFAULT_DB))

    def _connect(self) -> sqlite3.Connection:
        db = sqlite3.connect(self.path, timeout=10)
        db.row_factory = sqlite3.Row
        return db

    # ------------------------------------------------------------ reading --
    def get(self, email: str) -> User | None:
        try:
            key = normalize_email(email)
        except UserError:
            return None
        with self._connect() as db:
            row = db.execute("SELECT * FROM users WHERE email = ?", (key,)).fetchone()
        return _user(row) if row else None

    def list_users(self) -> list[User]:
        with self._connect() as db:
            rows = db.execute("SELECT * FROM users ORDER BY invited_at DESC").fetchall()
        return [_user(row) for row in rows]

    def events(self, limit: int = 50) -> list[dict]:
        with self._connect() as db:
            rows = db.execute("SELECT at, email, kind, detail FROM events ORDER BY id DESC LIMIT ?", (limit,)).fetchall()
        return [dict(row) for row in rows]

    # ------------------------------------------------------------ writing --
    def invite(self, email: str, invited_by: str = "") -> str:
        """Add ``email`` (or reactivate it) with a fresh passcode. Returns the plain passcode, once."""
        key = normalize_email(email)
        passcode = new_passcode()
        with self._lock, self._connect() as db:
            db.execute(
                "INSERT INTO users (email, passcode_hash, is_active, invited_at, invited_by) VALUES (?, ?, 1, ?, ?) "
                "ON CONFLICT(email) DO UPDATE SET passcode_hash = excluded.passcode_hash, is_active = 1",
                (key, generate_password_hash(passcode), time.time(), invited_by),
            )
            self._log(db, key, "invite", invited_by)
        return passcode

    def regenerate(self, email: str, by: str = "") -> str:
        """New passcode for an existing user; the old one and every open session stop working."""
        if self.get(email) is None:
            raise UserError(f"{email} is not on the whitelist")
        key = normalize_email(email)
        passcode = new_passcode()
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET passcode_hash = ? WHERE email = ?", (generate_password_hash(passcode), key))
            self._log(db, key, "regenerate", by)
        return passcode

    def set_active(self, email: str, active: bool, by: str = "") -> None:
        if self.get(email) is None:
            raise UserError(f"{email} is not on the whitelist")
        key = normalize_email(email)
        with self._lock, self._connect() as db:
            db.execute("UPDATE users SET is_active = ? WHERE email = ?", (1 if active else 0, key))
            self._log(db, key, "activate" if active else "revoke", by)

    def delete(self, email: str, by: str = "") -> None:
        key = normalize_email(email)
        with self._lock, self._connect() as db:
            db.execute("DELETE FROM users WHERE email = ?", (key,))
            self._log(db, key, "delete", by)

    def check(self, email: str, passcode: str) -> User | None:
        """The active user whose passcode this is, else None."""
        user = self.get(email)
        if user is None or not user.is_active or not check_password_hash(user.passcode_hash, passcode or ""):
            return None
        return user

    def record(self, email: str, kind: str, detail: str = "") -> None:
        """Audit a login event; ``login`` also stamps ``last_login``."""
        key = (email or "").strip().lower()[:254]
        with self._lock, self._connect() as db:
            if kind == "login":
                db.execute("UPDATE users SET last_login = ? WHERE email = ?", (time.time(), key))
            self._log(db, key, kind, detail)

    @staticmethod
    def _log(db: sqlite3.Connection, email: str, kind: str, detail: str) -> None:
        db.execute("INSERT INTO events (at, email, kind, detail) VALUES (?, ?, ?, ?)", (time.time(), email, kind, detail[:200]))


def _user(row: sqlite3.Row) -> User:
    return User(
        email=row["email"],
        passcode_hash=row["passcode_hash"],
        is_active=bool(row["is_active"]),
        invited_at=row["invited_at"],
        invited_by=row["invited_by"],
        last_login=row["last_login"],
    )


def _main(argv: list[str]) -> int:
    usage = "usage: python -m hosted.users add|regenerate|revoke|activate|delete <email> | list"
    if not argv:
        print(usage)
        return 2
    store = UserStore.from_env()
    command, rest = argv[0], argv[1:]
    try:
        if command == "list":
            for user in store.list_users():
                state = "active" if user.is_active else "revoked"
                last = time.strftime("%Y-%m-%d %H:%M", time.gmtime(user.last_login)) if user.last_login else "never"
                print(f"{user.email:40} {state:8} last login {last}")
            return 0
        if len(rest) != 1:
            print(usage)
            return 2
        email = rest[0]
        if command in ("add", "regenerate"):
            passcode = store.invite(email, "cli") if command == "add" else store.regenerate(email, "cli")
            print(f"{normalize_email(email)} passcode: {passcode}")
            print("It is shown only now. Send it to the person; they sign in with email + passcode.")
        elif command in ("revoke", "activate"):
            store.set_active(email, command == "activate", "cli")
            print(f"{normalize_email(email)} {command}d")
        elif command == "delete":
            store.delete(email, "cli")
            print(f"{normalize_email(email)} deleted")
        else:
            print(usage)
            return 2
    except UserError as exc:
        print(f"error: {exc}")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(_main(sys.argv[1:]))
