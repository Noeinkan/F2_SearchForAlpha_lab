"""Site login: the owner plus a whitelist of invited people, one signed cookie.

Two kinds of credential open the same form:

1. **The owner** -- ``SITE_LOGIN_EMAIL`` + ``SITE_LOGIN_PASSWORD_HASH`` (a
   Werkzeug hash) from the server's ``.env``. The plain password never reaches
   the server. This is the way in that cannot be locked out by the database.
2. **Whitelisted people** -- email + the passcode they were mailed when the
   owner added them (``hosted.users``, page ``/admin/users``).

Admins are ``ADMIN_EMAILS`` (comma list), re-read on every request like
Capsar's allowlist; unset, the owner alone is admin. The gate puts the result
on ``flask.g`` (``user_email``, ``is_admin``), where Dash callbacks and the
Explain route read it through ``lib.dash.auth_context``.

The cookie is signed with ``SITE_SECRET_KEY`` and carries the email plus a
fingerprint of that person's current secret hash. Every request re-reads the
user, so a revoked person is out on their next click, and a new passcode (or a
new owner password) signs the old cookie out. Five wrong tries from one IP lock
the form for fifteen minutes.
"""

from __future__ import annotations

import hmac
import html
import os
import threading
import time
from dataclasses import dataclass, field

from flask import Flask, Response, g, jsonify, redirect, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash

from hosted.users import UserStore, fingerprint

COOKIE_NAME = "sfa_session"
SESSION_SECONDS = 14 * 24 * 3600
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60
MIN_SECRET_KEY_LENGTH = 32
EXEMPT_PREFIXES = ("/login", "/logout", "/healthz", "/robots.txt")


class LoginConfigError(RuntimeError):
    """The login cannot work, so the site must not start."""


def admin_emails(owner_email: str) -> frozenset[str]:
    raw = os.environ.get("ADMIN_EMAILS", "")
    listed = {part.strip().lower() for part in raw.split(",") if part.strip()}
    return frozenset(listed or {owner_email})


@dataclass
class SiteLogin:
    email: str
    password_hash: str
    secret_key: str
    store: UserStore | None = None
    _failures: dict[str, list[float]] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    def __post_init__(self) -> None:
        self.email = self.email.strip().lower()

    @classmethod
    def from_env(cls, store: UserStore | None = None) -> "SiteLogin":
        email = os.environ.get("SITE_LOGIN_EMAIL", "").strip().lower()
        password_hash = os.environ.get("SITE_LOGIN_PASSWORD_HASH", "").strip()
        secret_key = os.environ.get("SITE_SECRET_KEY", "").strip()
        missing = [
            name
            for name, value in (("SITE_LOGIN_EMAIL", email), ("SITE_LOGIN_PASSWORD_HASH", password_hash), ("SITE_SECRET_KEY", secret_key))
            if not value
        ]
        if missing:
            raise LoginConfigError(f"refusing to serve the workspace without a login: {', '.join(missing)} unset")
        if not password_hash.startswith(("scrypt:", "pbkdf2:")):
            raise LoginConfigError("SITE_LOGIN_PASSWORD_HASH is not a Werkzeug hash (scrypt:... or pbkdf2:...)")
        if len(secret_key) < MIN_SECRET_KEY_LENGTH:
            raise LoginConfigError(f"SITE_SECRET_KEY must be at least {MIN_SECRET_KEY_LENGTH} characters (openssl rand -hex 32)")
        return cls(email=email, password_hash=password_hash, secret_key=secret_key, store=store)

    # ------------------------------------------------------------- roles --
    def is_admin(self, email: str | None) -> bool:
        return bool(email) and email in admin_emails(self.email)

    # ------------------------------------------------------------ cookie --
    def _serializer(self) -> URLSafeTimedSerializer:
        return URLSafeTimedSerializer(self.secret_key, salt="site-login")

    def _fingerprint_for(self, email: str) -> str | None:
        """The current fingerprint for ``email``, or None if that person may not sign in."""
        if email == self.email:
            return fingerprint(self.password_hash)
        user = self.store.get(email) if self.store else None
        return user.fingerprint if user and user.is_active else None

    def current_email(self) -> str | None:
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return None
        try:
            payload = self._serializer().loads(token, max_age=SESSION_SECONDS)
        except BadSignature:
            return None
        if not isinstance(payload, dict):
            return None
        email, mark = str(payload.get("e", "")), str(payload.get("f", ""))
        expected = self._fingerprint_for(email)
        return email if expected and hmac.compare_digest(mark, expected) else None

    def signed_in(self) -> bool:
        return self.current_email() is not None

    def _record(self, email: str, kind: str, detail: str = "") -> None:
        if self.store:
            try:
                self.store.record(email, kind, detail)
            except Exception:  # an audit row must never block a sign-in
                pass

    # ----------------------------------------------------------- lockout --
    def _recent_failures(self, ip: str, now: float) -> list[float]:
        recent = [t for t in self._failures.get(ip, []) if now - t < LOCK_SECONDS]
        if recent:
            self._failures[ip] = recent
        else:
            self._failures.pop(ip, None)
        return recent

    def locked(self, ip: str) -> bool:
        with self._lock:
            return len(self._recent_failures(ip, time.monotonic())) >= MAX_FAILURES

    def _verify(self, email: str, password: str) -> str | None:
        key = email.strip().lower()
        if hmac.compare_digest(key, self.email):
            return key if check_password_hash(self.password_hash, password) else None
        user = self.store.check(key, password) if self.store else None
        return user.email if user else None

    def check(self, ip: str, email: str, password: str) -> str | None:
        """The signed-in email, or None. Counts failures per IP."""
        with self._lock:
            now = time.monotonic()
            if len(self._recent_failures(ip, now)) >= MAX_FAILURES:
                return None
            signed = self._verify(email, password)
            if signed:
                self._failures.pop(ip, None)
            else:
                self._failures.setdefault(ip, []).append(now)
        self._record(signed or email, "login" if signed else "login_failed", ip)
        return signed

    # ------------------------------------------------------------- flask --
    def install(self, server: Flask) -> None:
        """Put the gate in front of every route, ahead of any other hook."""
        server.config["SFA_AUTH_MODE"] = "hosted"

        def gate():
            email = self.current_email()
            g.user_email = email
            g.is_admin = self.is_admin(email)
            if email or request.path.startswith(EXEMPT_PREFIXES):
                return None
            if request.path.startswith(("/_dash-", "/api/")) or request.method != "GET":
                return jsonify(error="signed out"), 401
            return redirect("/login?next=" + _safe_next(request.full_path.rstrip("?")))

        server.before_request_funcs.setdefault(None, []).insert(0, gate)

        @server.route("/login", methods=["GET", "POST"])
        def login():
            ip = client_ip()
            target = _safe_next(request.values.get("next", "/"))
            if request.method == "GET":
                return _page(target, locked=self.locked(ip))
            email = self.check(ip, request.form.get("email", ""), request.form.get("password", ""))
            if email:
                response = redirect(target)
                response.set_cookie(
                    COOKIE_NAME,
                    self._serializer().dumps({"e": email, "f": self._fingerprint_for(email)}),
                    max_age=SESSION_SECONDS,
                    httponly=True,
                    secure=request.headers.get("X-Forwarded-Proto") == "https",
                    samesite="Lax",
                    path="/",
                )
                return response
            return _page(target, error=True, locked=self.locked(ip)), 401

        @server.route("/logout")
        def logout():
            email = self.current_email()
            if email:
                self._record(email, "logout")
            response = redirect("/login")
            response.delete_cookie(COOKIE_NAME, path="/")
            return response


def client_ip() -> str:
    # nginx (the only way in) sets X-Real-IP; the container publishes no port.
    return request.headers.get("X-Real-IP") or request.remote_addr or "?"


def _safe_next(target: str) -> str:
    # Only same-site paths: "//evil.com" and "/\evil.com" are other hosts to a browser.
    if not target.startswith("/") or target.startswith(("//", "/\\")):
        return "/"
    return target


def _page(target: str, error: bool = False, locked: bool = False) -> Response:
    if locked:
        message = '<p class="err">Too many wrong tries. Wait 15 minutes and try again.</p>'
    elif error:
        message = '<p class="err">Wrong email or password / passcode.</p>'
    else:
        message = ""
    body = _LOGIN_HTML.replace("{{message}}", message).replace("{{next}}", html.escape(target, quote=True))
    response = Response(body, mimetype="text/html")
    response.headers["Cache-Control"] = "no-store"
    return response


_LOGIN_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>SearchForAlpha Lab — sign in</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; min-height: 100vh; display: grid; place-items: center;
         background: #0b0d10; color: #e6e6e6; font: 15px/1.5 system-ui, sans-serif; }
  form { width: min(340px, calc(100vw - 32px)); padding: 28px; border: 1px solid #2a2f36;
         border-radius: 8px; background: #12161b; }
  h1 { margin: 0 0 4px; font-size: 18px; color: #ff9f1c; }
  p.sub { margin: 0 0 20px; color: #9aa4ae; font-size: 13px; }
  label { display: block; margin: 12px 0 4px; font-size: 13px; color: #9aa4ae; }
  input { box-sizing: border-box; width: 100%; padding: 9px 10px; border: 1px solid #2a2f36;
          border-radius: 4px; background: #0b0d10; color: inherit; font: inherit; }
  button { margin-top: 20px; width: 100%; padding: 10px; border: 0; border-radius: 4px;
           background: #ff9f1c; color: #111; font: 600 15px system-ui, sans-serif; cursor: pointer; }
  .err { margin: 12px 0 0; color: #ff6b6b; font-size: 13px; }
</style></head>
<body><form method="post" action="/login">
  <h1>SearchForAlpha Lab</h1>
  <p class="sub">Research workspace — invited users only</p>
  <input type="hidden" name="next" value="{{next}}">
  <label for="email">Email</label>
  <input id="email" name="email" type="email" autocomplete="username" required autofocus>
  <label for="password">Password or passcode from your invitation email</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required>
  {{message}}
  <button type="submit">Sign in</button>
</form></body></html>
"""
