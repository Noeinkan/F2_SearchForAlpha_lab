"""``/admin/users``: the owner's page for the whitelist.

Only an admin (``g.is_admin``, set by ``hosted.login``) sees it; anyone else
gets a 404, so the page does not even admit it exists.

Adding an email makes a passcode and mails it through the same SMTP account
the demo uses (``demo.access.mailer``, the ``NEO_SMTP_*`` / ``EMAIL_FROM``
variables). The passcode is also shown once on the page, because a mail that
fails -- or lands in spam -- must not leave the person locked out: the owner
can forward it by hand.

Every form is a POST and is refused unless the browser says it came from this
same site (``Origin``, else ``Referer``), so another page cannot submit it with
the owner's cookie.
"""

from __future__ import annotations

import dataclasses
import html
import logging
import time
from email.utils import formataddr, parseaddr
from urllib.parse import urlsplit

from flask import Flask, Response, abort, g, request

from hosted.users import UserError, UserStore

logger = logging.getLogger(__name__)

SENDER_NAME = "SearchForAlpha Lab"


def _build_mailer():
    from demo.access.mailer import build_mailer
    from demo.access.settings import AccessSettings

    settings = AccessSettings.from_env()
    address = parseaddr(settings.mail_from)[1]
    if address:
        settings = dataclasses.replace(settings, mail_from=formataddr((SENDER_NAME, address)))
    return build_mailer(settings)


def _same_origin() -> bool:
    source = request.headers.get("Origin") or request.headers.get("Referer") or ""
    if not source:
        return False
    return urlsplit(source).netloc == request.host


def invitation_mail(email: str, passcode: str, site_url: str):
    from demo.access.mailer import Mail

    text = (
        "You have been given access to the SearchForAlpha Lab research workspace.\n\n"
        f"Sign in at {site_url}login\n"
        f"Email:    {email}\n"
        f"Passcode: {passcode}\n\n"
        "Keep the passcode private. If you did not expect this email, ignore it.\n"
    )
    safe = {k: html.escape(v) for k, v in {"email": email, "passcode": passcode, "url": f"{site_url}login"}.items()}
    body = (
        "<p>You have been given access to the SearchForAlpha Lab research workspace.</p>"
        f"<p>Sign in at <a href=\"{safe['url']}\">{safe['url']}</a></p>"
        f"<p>Email: <b>{safe['email']}</b><br>Passcode: <b style=\"font-family:monospace;font-size:16px\">{safe['passcode']}</b></p>"
        "<p>Keep the passcode private. If you did not expect this email, ignore it.</p>"
    )
    return Mail(to=email, subject="Your SearchForAlpha Lab access", text=text, html=body)


def install(server: Flask, store: UserStore, mailer=None) -> None:
    """Add the admin routes. ``mailer`` defaults to the demo's SMTP mailer, built on first use."""
    holder = {"mailer": mailer}

    def get_mailer():
        if holder["mailer"] is None:
            holder["mailer"] = _build_mailer()
        return holder["mailer"]

    def require_admin():
        if not getattr(g, "is_admin", False):
            abort(404)

    def send(email: str, passcode: str) -> str:
        try:
            get_mailer().send(invitation_mail(email, passcode, request.host_url))
        except Exception as exc:  # MailError, or SMTP not configured
            logger.error("invitation mail to %s failed: %s", email.rpartition("@")[2], exc)
            return "The email could NOT be sent — forward the passcode yourself."
        return "Invitation emailed."

    @server.route("/admin/users", methods=["GET"])
    def admin_users():
        require_admin()
        return _page(store)

    @server.route("/admin/users", methods=["POST"])
    def admin_users_post():
        require_admin()
        if not _same_origin():
            abort(403)
        by = getattr(g, "user_email", "") or ""
        action = request.form.get("action", "")
        email = request.form.get("email", "")
        try:
            if action == "add":
                passcode = store.invite(email, by)
                note = send(email.strip().lower(), passcode)
                return _page(store, notice=f"{email.strip().lower()} added. {note}", passcode=passcode)
            if action == "regenerate":
                passcode = store.regenerate(email, by)
                note = send(email.strip().lower(), passcode)
                return _page(store, notice=f"New passcode for {email}. Their open sessions are signed out. {note}", passcode=passcode)
            if action in ("revoke", "activate"):
                store.set_active(email, action == "activate", by)
                return _page(store, notice=f"{email} {'re-activated' if action == 'activate' else 'revoked — signed out on their next click'}.")
            if action == "delete":
                store.delete(email, by)
                return _page(store, notice=f"{email} deleted.")
        except UserError as exc:
            return _page(store, error=str(exc)), 400
        abort(400)


def _when(stamp: float | None) -> str:
    return time.strftime("%Y-%m-%d %H:%M UTC", time.gmtime(stamp)) if stamp else "never"


def _button(email: str, action: str, label: str, danger: bool = False) -> str:
    confirm = ' onclick="return confirm(\'Sure?\')"' if danger else ""
    return (
        '<form method="post" class="inline">'
        f'<input type="hidden" name="email" value="{html.escape(email, quote=True)}">'
        f'<button name="action" value="{action}"{confirm} class="{"danger" if danger else ""}">{label}</button></form>'
    )


def _page(store: UserStore, notice: str = "", error: str = "", passcode: str = "") -> Response:
    rows = []
    for user in store.list_users():
        state = "active" if user.is_active else "revoked"
        toggle = _button(user.email, "revoke", "Revoke") if user.is_active else _button(user.email, "activate", "Re-activate")
        rows.append(
            f"<tr class=\"{state}\"><td>{html.escape(user.email)}</td><td>{state}</td>"
            f"<td>{_when(user.invited_at)}</td><td>{_when(user.last_login)}</td>"
            f"<td>{_button(user.email, 'regenerate', 'New passcode')}{toggle}{_button(user.email, 'delete', 'Delete', danger=True)}</td></tr>"
        )
    table = "".join(rows) or '<tr><td colspan="5" class="muted">Nobody on the whitelist yet.</td></tr>'
    events = "".join(
        f"<tr><td>{_when(e['at'])}</td><td>{html.escape(e['email'])}</td><td>{html.escape(e['kind'])}</td><td>{html.escape(e['detail'])}</td></tr>"
        for e in store.events(30)
    )
    flash = ""
    if notice:
        flash += f'<p class="ok">{html.escape(notice)}</p>'
    if passcode:
        flash += f'<p class="code">Passcode (shown only now): <code>{html.escape(passcode)}</code></p>'
    if error:
        flash += f'<p class="err">{html.escape(error)}</p>'
    body = (
        _ADMIN_HTML.replace("{{flash}}", flash)
        .replace("{{rows}}", table)
        .replace("{{events}}", events)
        .replace("{{me}}", html.escape(getattr(g, "user_email", "") or ""))
    )
    response = Response(body, mimetype="text/html")
    response.headers["Cache-Control"] = "no-store"
    return response


_ADMIN_HTML = """<!DOCTYPE html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<meta name="robots" content="noindex">
<title>Users — SearchForAlpha Lab</title>
<style>
  :root { color-scheme: dark; }
  body { margin: 0; padding: 24px 16px; background: #0b0d10; color: #e6e6e6; font: 14px/1.5 system-ui, sans-serif; }
  main { max-width: 960px; margin: 0 auto; }
  h1 { margin: 0; font-size: 20px; color: #ff9f1c; }
  h2 { margin: 28px 0 8px; font-size: 15px; color: #9aa4ae; text-transform: uppercase; letter-spacing: .05em; }
  .top { display: flex; justify-content: space-between; align-items: baseline; gap: 12px; flex-wrap: wrap; }
  a { color: #ff9f1c; }
  .muted, .top span { color: #9aa4ae; }
  .add { display: flex; gap: 8px; margin-top: 20px; flex-wrap: wrap; }
  input[type=email] { flex: 1 1 260px; padding: 8px 10px; border: 1px solid #2a2f36; border-radius: 4px; background: #12161b; color: inherit; font: inherit; }
  button { padding: 6px 10px; border: 1px solid #2a2f36; border-radius: 4px; background: #1a1f26; color: inherit; font: inherit; cursor: pointer; }
  button.primary { background: #ff9f1c; color: #111; border-color: #ff9f1c; font-weight: 600; padding: 8px 14px; }
  button.danger { color: #ff6b6b; }
  form.inline { display: inline; margin-right: 4px; }
  .scroll { overflow-x: auto; }
  table { width: 100%; border-collapse: collapse; }
  th, td { text-align: left; padding: 7px 8px; border-bottom: 1px solid #1f242b; white-space: nowrap; }
  th { color: #9aa4ae; font-weight: 500; }
  tr.revoked td:first-child { text-decoration: line-through; color: #9aa4ae; }
  .ok { color: #4cd07d; } .err { color: #ff6b6b; }
  .code code { font-size: 18px; padding: 2px 8px; background: #12161b; border: 1px solid #2a2f36; border-radius: 4px; user-select: all; }
</style></head>
<body><main>
  <div class="top"><h1>Whitelist</h1><span>{{me}} · <a href="/">Back to the workspace</a> · <a href="/logout">Sign out</a></span></div>
  <form method="post" class="add">
    <input type="email" name="email" placeholder="name@example.com" required>
    <button class="primary" name="action" value="add">Add and email a passcode</button>
  </form>
  {{flash}}
  <h2>People</h2>
  <div class="scroll"><table>
    <tr><th>Email</th><th>State</th><th>Invited</th><th>Last sign-in</th><th></th></tr>
    {{rows}}
  </table></div>
  <h2>Recent activity</h2>
  <div class="scroll"><table>
    <tr><th>When</th><th>Email</th><th>Event</th><th>Detail</th></tr>
    {{events}}
  </table></div>
</main></body></html>
"""
