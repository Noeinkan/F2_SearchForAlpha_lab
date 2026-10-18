"""Owner login: one email, one password hash, a signed session cookie.

The hosted workspace has a single user, so there is no user table: the email
and a Werkzeug password hash come from the environment
(``SITE_LOGIN_EMAIL``, ``SITE_LOGIN_PASSWORD_HASH``), set in the server's
``.env``. The plain password never reaches the server.

The cookie is signed with a key derived from the hash, so changing the
password signs every browser out. Five wrong tries from one IP lock the form
for fifteen minutes.
"""

from __future__ import annotations

import hashlib
import hmac
import html
import os
import threading
import time
from dataclasses import dataclass, field

from flask import Flask, Response, jsonify, redirect, request
from itsdangerous import BadSignature, URLSafeTimedSerializer
from werkzeug.security import check_password_hash

COOKIE_NAME = "sfa_owner"
SESSION_SECONDS = 14 * 24 * 3600
MAX_FAILURES = 5
LOCK_SECONDS = 15 * 60
EXEMPT_PREFIXES = ("/login", "/logout", "/healthz", "/robots.txt")


class LoginConfigError(RuntimeError):
    """The login cannot work, so the site must not start."""


@dataclass
class OwnerLogin:
    email: str
    password_hash: str
    _failures: dict[str, list[float]] = field(default_factory=dict, repr=False)
    _lock: threading.Lock = field(default_factory=threading.Lock, repr=False)

    @classmethod
    def from_env(cls) -> "OwnerLogin":
        email = os.environ.get("SITE_LOGIN_EMAIL", "").strip().lower()
        password_hash = os.environ.get("SITE_LOGIN_PASSWORD_HASH", "").strip()
        missing = [name for name, value in (("SITE_LOGIN_EMAIL", email), ("SITE_LOGIN_PASSWORD_HASH", password_hash)) if not value]
        if missing:
            raise LoginConfigError(f"refusing to serve the workspace without a login: {', '.join(missing)} unset")
        if not password_hash.startswith(("scrypt:", "pbkdf2:")):
            raise LoginConfigError("SITE_LOGIN_PASSWORD_HASH is not a Werkzeug hash (scrypt:... or pbkdf2:...)")
        return cls(email=email, password_hash=password_hash)

    # ------------------------------------------------------------ cookie --
    def _serializer(self) -> URLSafeTimedSerializer:
        key = hashlib.sha256(b"sfa-owner-cookie\0" + self.password_hash.encode()).hexdigest()
        return URLSafeTimedSerializer(key, salt="owner-login")

    def signed_in(self) -> bool:
        token = request.cookies.get(COOKIE_NAME)
        if not token:
            return False
        try:
            email = self._serializer().loads(token, max_age=SESSION_SECONDS)
        except BadSignature:
            return False
        return hmac.compare_digest(str(email), self.email)

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

    def check(self, ip: str, email: str, password: str) -> bool:
        with self._lock:
            now = time.monotonic()
            if len(self._recent_failures(ip, now)) >= MAX_FAILURES:
                return False
            ok = hmac.compare_digest(email.strip().lower(), self.email) and check_password_hash(self.password_hash, password)
            if ok:
                self._failures.pop(ip, None)
            else:
                self._failures.setdefault(ip, []).append(now)
            return ok

    # ------------------------------------------------------------- flask --
    def install(self, server: Flask) -> None:
        """Put the gate in front of every route, ahead of any other hook."""

        def gate():
            if request.path.startswith(EXEMPT_PREFIXES) or self.signed_in():
                return None
            if request.path.startswith("/_dash-") or request.method != "GET":
                return jsonify(error="signed out"), 401
            return redirect("/login?next=" + _safe_next(request.full_path.rstrip("?")))

        server.before_request_funcs.setdefault(None, []).insert(0, gate)

        @server.route("/login", methods=["GET", "POST"])
        def login():
            ip = client_ip()
            target = _safe_next(request.values.get("next", "/"))
            if request.method == "GET":
                return _page(target, locked=self.locked(ip))
            if self.check(ip, request.form.get("email", ""), request.form.get("password", "")):
                response = redirect(target)
                response.set_cookie(
                    COOKIE_NAME,
                    self._serializer().dumps(self.email),
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
        message = '<p class="err">Wrong email or password.</p>'
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
  <p class="sub">Research workspace — owner sign-in</p>
  <input type="hidden" name="next" value="{{next}}">
  <label for="email">Email</label>
  <input id="email" name="email" type="email" autocomplete="username" required autofocus>
  <label for="password">Password</label>
  <input id="password" name="password" type="password" autocomplete="current-password" required>
  {{message}}
  <button type="submit">Sign in</button>
</form></body></html>
"""
