"""The front door: nothing past it without a verified email and a live trial.

Flow, as a visitor meets it:

1. Any page without an access cookie redirects to ``/access``.
2. ``POST /access`` sends one email holding a 6-digit code and a link.
3. The code (``POST /access/code``) or the link (``GET`` then ``POST
   /access/verify``) signs the browser in: an opaque cookie whose hash is a
   row in ``grants``. The first sign-in starts the trial clock.
4. While the trial is live every request passes, and the dashboard's usage is
   recorded against the email (``record``, called from ``demo.guards``).
5. When it ends, pages redirect to ``/access/ended`` and a Dash callback gets
   the demo notice instead of its result -- never a login page mid-session.

Asking for a code with an address whose trial ended sends that mailbox an
"ended" note rather than saying so on screen, so the page never reveals which
addresses have had a trial.
"""

from __future__ import annotations

import json
import logging
from typing import Callable
from urllib.parse import urlencode

from flask import Flask, Response, g, has_request_context, redirect, request

from demo.access import emails, pages
from demo.access.mailer import MailError
from demo.access.settings import AccessSettings
from demo.access.store import DAY, AccessStore, Visitor

logger = logging.getLogger(__name__)

ACCESS_COOKIE = "sfa_demo_access"
ACCOUNT_MARKER = "<!--sfa-demo-account-->"

# Reachable without access. The Dash bundles are public libraries and the page
# that loads them is gated; letting them through keeps a signed-out reload from
# painting a broken app before its redirect.
_OPEN_EXACT = {"/access", "/admin", "/healthz", "/robots.txt", "/favicon.ico", "/_favicon.ico"}
_OPEN_PREFIXES = ("/access/", "/admin/", "/assets/", "/_dash-component-suites/")


def is_open_path(path: str) -> bool:
    return path in _OPEN_EXACT or path.startswith(_OPEN_PREFIXES)


def safe_next(value: str | None) -> str:
    """A same-site path to return to after sign-in; anything else becomes ``/``."""
    value = (value or "").strip()
    if not value.startswith("/") or value.startswith(("//", "/\\")) or "\n" in value or "\r" in value:
        return "/"
    if is_open_path(value.split("?", 1)[0]):
        return "/"
    return value[:300]


def _html(body: str, status: int = 200) -> Response:
    response = Response(body, status=status, mimetype="text/html")
    response.headers["Cache-Control"] = "no-store"
    return response


class AccessGate:
    def __init__(
        self,
        settings: AccessSettings,
        store: AccessStore,
        mailer,
        *,
        wall: Callable[[str], str],
        client_ip: Callable[[], str],
    ) -> None:
        self.settings = settings
        self.store = store
        self.mailer = mailer
        self.wall = wall
        self.client_ip = client_ip

    # ----------------------------------------------------------------- used by demo.guards

    def email(self) -> str | None:
        return g.get("demo_email") if has_request_context() else None

    def record(self, kind: str, detail: str | None = None) -> None:
        email = self.email()
        if not email:
            return
        try:
            self.store.record(email, kind, detail)
        except Exception:  # noqa: BLE001 - tracking must never break the demo
            logger.exception("recording demo usage failed")

    def refuse_job(self) -> str | None:
        """The per-person daily optimiser cap. None means go."""
        email = self.email()
        if not email:
            return None
        cap = self.settings.jobs_per_email_per_day
        try:
            used = self.store.count_today(email, "optimizer")
        except Exception:  # noqa: BLE001
            logger.exception("reading the daily optimiser count failed")
            return None
        if used < cap:
            return None
        now = self.store.now()
        hours = max(1, round((DAY - now % DAY) / 3600))
        return (
            f"That is today's {cap} optimiser runs for your demo account. They reset at 00:00 UTC, "
            f"in about {hours} h. Charts and backtests still work meanwhile."
        )

    # ----------------------------------------------------------------- install

    def install(self, server: Flask) -> None:
        """Register the routes and the gate. Call before any other before_request hook."""
        server.before_request(self._gate)
        server.after_request(self._decorate)
        server.add_url_rule("/access", "demo_access", self._access, methods=["GET", "POST"])
        server.add_url_rule("/access/code", "demo_access_code", self._code, methods=["POST"])
        server.add_url_rule("/access/verify", "demo_access_verify", self._verify, methods=["GET", "POST"])
        server.add_url_rule("/access/ended", "demo_access_ended", self._ended, methods=["GET"])
        server.add_url_rule("/access/signout", "demo_access_signout", self._signout, methods=["POST"])
        # /access/* is open, so anything unknown under it must 404 here rather
        # than reach the Dash catch-all and serve the dashboard shell.
        server.add_url_rule("/access/", "demo_access_slash", lambda: redirect("/access", code=302))
        server.add_url_rule("/admin/", "demo_admin_slash", lambda: redirect("/admin", code=302))
        server.add_url_rule(
            "/access/<path:_rest>", "demo_access_missing", lambda _rest: Response("Not found\n", 404), methods=["GET", "POST"]
        )

    # ----------------------------------------------------------------- the gate

    def _visitor(self) -> Visitor | None:
        try:
            return self.store.grant(request.cookies.get(ACCESS_COOKIE), ip=self.client_ip())
        except Exception:  # noqa: BLE001 - a broken store closes the door, it does not crash the page
            logger.exception("reading demo access failed")
            return None

    def _gate(self):
        g.demo_email = None
        g.demo_visitor = None
        path = request.path
        if is_open_path(path):
            return None
        visitor = self._visitor()
        if visitor is not None and visitor.status(self.store.now()) == "active":
            g.demo_email = visitor.email
            g.demo_visitor = visitor
            if request.method == "GET" and not path.startswith("/_") and ("." not in path.rsplit("/", 1)[-1] or path.endswith(".html")):
                self.record("visit", path[:120])
            return None

        ended = visitor is not None
        if path == "/_dash-update-component":
            if ended:
                message = (
                    f"Your {self.settings.trial_days}-day demo access ended on {pages.fmt_date(visitor.expires_at)}. "
                    f"Reload the page for how to get more time."
                )
            else:
                message = "You are signed out of the demo. Reload the page to sign in again."
            return Response(self.wall(message), mimetype="application/json")
        if path.startswith("/_dash-"):
            return Response(json.dumps({"demo_access": "ended" if ended else "sign-in"}), status=401, mimetype="application/json")
        if request.method == "GET":
            if ended:
                return redirect("/access/ended", code=302)
            return redirect("/access?" + urlencode({"next": safe_next(request.full_path.rstrip("?"))}), code=302)
        return Response("Sign in at /access to use this demo.\n", status=401, mimetype="text/plain")

    def _decorate(self, response: Response) -> Response:
        visitor = g.get("demo_visitor")
        if visitor is None or response.mimetype != "text/html" or response.direct_passthrough:
            return response
        body = response.get_data(as_text=True)
        if ACCOUNT_MARKER in body:
            response.set_data(body.replace(ACCOUNT_MARKER, pages.account_html(visitor), 1))
            response.headers["Cache-Control"] = "private, no-store"
        return response

    # ----------------------------------------------------------------- routes

    def _https(self) -> bool:
        return request.headers.get("X-Forwarded-Proto") == "https" or request.scheme == "https"

    def _signed_in(self, token: str, visitor: Visitor, next_path: str) -> Response:
        response = redirect(safe_next(next_path), code=303)
        now = self.store.now()
        lifetime = max(0.0, (visitor.expires_at or now) - now) + 30 * DAY  # outlives the trial, so "ended" can be shown
        response.set_cookie(
            ACCESS_COOKIE, token, max_age=int(lifetime), httponly=True, samesite="Lax", secure=self._https(), path="/"
        )
        return response

    def _link_url(self, link_token: str, next_path: str) -> str:
        base = self.settings.public_url
        if not base:
            root = request.url_root.rstrip("/")
            base = root.replace("http://", "https://", 1) if request.headers.get("X-Forwarded-Proto") == "https" else root
        query = {"t": link_token}
        if next_path != "/":
            query["next"] = next_path
        return f"{base}/access/verify?{urlencode(query)}"

    def _access(self):
        next_path = safe_next(request.values.get("next"))
        if request.method == "GET":
            visitor = self._visitor()
            if visitor is not None and visitor.status(self.store.now()) == "active":
                return redirect(next_path, code=302)
            return _html(pages.signin_page(self.settings, next_path=next_path))

        s = self.settings
        address = emails.clean(request.form.get("email"))
        if not emails.is_valid(address):
            return _html(
                pages.signin_page(s, next_path=next_path, email=address, error="That does not look like an email address."),
                400,
            )
        if emails.is_blocked(address, s.blocked_domains):
            return _html(
                pages.signin_page(
                    s, next_path=next_path, email=address,
                    error="Throwaway inboxes cannot start a trial. Use an address you actually read.",
                ),
                400,
            )

        email = emails.canonical(address)
        now = self.store.now()
        ip = self.client_ip()
        if self.store.codes_sent_since(now - 3600, email=email) >= s.codes_per_email_per_hour:
            return _html(
                pages.sent_page(
                    s, address=address, next_path=next_path,
                    error="Several codes have already gone to this address in the last hour. Use the newest one, or ask again later.",
                ),
                429,
            )
        if (
            self.store.codes_sent_since(now - 3600) >= s.codes_per_hour
            or self.store.codes_sent_since(now - DAY) >= s.codes_per_day
        ):
            return _html(
                pages.signin_page(
                    s, next_path=next_path, email=address,
                    error="The demo is sending a lot of sign-in emails right now. Try again in a few minutes.",
                ),
                429,
            )
        existing = self.store.visitor(email)
        if existing is None and self.store.new_visitors_from_ip_since(ip, now - DAY) >= s.signups_per_ip_per_day:
            return _html(
                pages.signin_page(
                    s, next_path=next_path, email=address,
                    error=f"Too many new addresses have started a trial from your connection today. "
                    f"Try again tomorrow, or write to {s.contact_email}.",
                ),
                429,
            )

        code, link = self.store.create_code(
            email=email, address=address, ip=ip, user_agent=request.headers.get("User-Agent", ""), minutes=s.code_minutes
        )
        if existing is not None and existing.status(now) in ("expired", "revoked"):
            mail = pages.ended_mail(s, to=address, visitor=existing)
        else:
            mail = pages.code_mail(s, to=address, code=code, link=self._link_url(link, next_path))
        try:
            self.mailer.send(mail)
        except MailError:
            self.store.cancel_code(link)
            return _html(
                pages.signin_page(
                    s, next_path=next_path, email=address,
                    error=f"The sign-in email could not be sent just now. Try again in a minute; if it keeps failing, write to {s.contact_email}.",
                ),
                503,
            )
        self.store.sent(email)
        return _html(pages.sent_page(s, address=address, next_path=next_path))

    def _code(self):
        s = self.settings
        next_path = safe_next(request.form.get("next"))
        address = emails.clean(request.form.get("email"))
        if not emails.is_valid(address):
            return redirect("/access", code=303)
        result = self.store.verify_code(
            emails.canonical(address), request.form.get("code", ""), trial_days=s.trial_days, max_attempts=s.code_attempts
        )
        if result.status == "ok":
            return self._signed_in(result.token, result.visitor, next_path)
        if result.status == "ended":
            return _html(pages.ended_page(s, result.visitor), 403)
        if result.status == "wrong":
            tries = "1 try" if result.attempts_left == 1 else f"{result.attempts_left} tries"
            return _html(
                pages.sent_page(s, address=address, next_path=next_path, error=f"That code is not right. {tries} left."), 400
            )
        if result.status == "used_up":
            error = "Too many wrong codes. Ask for a new one below."
        else:
            error = "That code has expired or was already used. Ask for a new one below."
        return _html(pages.signin_page(s, next_path=next_path, email=address, error=error), 400)

    def _verify(self):
        token = (request.values.get("t") or "").strip()
        next_path = safe_next(request.values.get("next"))
        if not token or len(token) > 128:
            return _html(pages.link_dead_page(), 410)
        if request.method == "GET":
            email = self.store.link_email(token)
            visitor = self.store.visitor(email) if email else None
            if visitor is None:
                return _html(pages.link_dead_page(), 410)
            return _html(pages.link_confirm_page(address=visitor.address, token=token, next_path=next_path))
        result = self.store.verify_link(token, trial_days=self.settings.trial_days)
        if result.status == "ok":
            return self._signed_in(result.token, result.visitor, next_path)
        if result.status == "ended":
            return _html(pages.ended_page(self.settings, result.visitor), 403)
        return _html(pages.link_dead_page(), 410)

    def _ended(self):
        visitor = self._visitor()
        if visitor is None:
            return redirect("/access", code=302)
        if visitor.status(self.store.now()) == "active":
            return redirect("/", code=302)
        return _html(pages.ended_page(self.settings, visitor))

    def _signout(self):
        self.store.revoke_grant(request.cookies.get(ACCESS_COOKIE))
        response = redirect("/access", code=303)
        response.delete_cookie(ACCESS_COOKIE, path="/")
        return response

    # ----------------------------------------------------------------- housekeeping

    def purge(self) -> int:
        return self.store.purge(self.settings.retention_days)
