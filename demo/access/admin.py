"""``/admin`` -- who signed up, what they used, and the three things to do about it.

Unlocked by ``DEMO_ADMIN_TOKEN`` (at least 24 characters, kept in the server's
``.env``). With no token set every ``/admin`` URL is a 404, so a fresh
deployment exposes nothing.

Sign-in is a form, not a token in the URL, so the token never lands in the
nginx access log. The cookie it sets holds an HMAC of the token rather than
the token itself; changing the token signs every admin browser out. It is
``SameSite=Strict`` and scoped to ``/admin``, which is what stops another site
from submitting the extend/revoke/delete forms on the owner's behalf.
"""

from __future__ import annotations

import csv
import hashlib
import hmac
import io
from urllib.parse import quote

from flask import Flask, Response, abort, redirect, request

from demo.access.pages import esc, fmt_date, fmt_time, page
from demo.access.settings import AccessSettings
from demo.access.store import AccessStore
from demo.limits import SlidingWindowLimiter

ADMIN_COOKIE = "sfa_demo_admin"

_CSS = """
.tiles{display:grid;grid-template-columns:repeat(auto-fit,minmax(150px,1fr));gap:10px;margin:0 0 18px}
.tile{background:var(--panel);border:1px solid var(--line);border-radius:6px;padding:12px 14px}
.tile b{display:block;font:600 24px/1.1 var(--mono);color:var(--text)}
.tile span{font-size:12px;color:var(--muted)}
.bar{display:flex;gap:12px;flex-wrap:wrap;align-items:center;justify-content:space-between;margin:0 0 14px}
.bar h1{margin:0}
.bar a,.bar button{width:auto;margin:0}
.scroll{overflow-x:auto;border:1px solid var(--line);border-radius:6px;margin:0 0 22px}
table{border-collapse:collapse;width:100%;font-size:13px;white-space:nowrap}
th,td{padding:7px 10px;border-bottom:1px solid var(--line);text-align:left;vertical-align:top}
th{font:600 11px/1.2 var(--mono);letter-spacing:.05em;text-transform:uppercase;color:var(--muted);background:#111;position:sticky;top:0}
td.n{text-align:right;font-family:var(--mono)}
.status{font:600 11px/1 var(--mono);padding:3px 6px;border-radius:3px;text-transform:uppercase}
.status.active{background:#173a1d;color:#8fe39a}.status.expired{background:#3a2f12;color:#FFCA28}
.status.revoked{background:#3d1717;color:#ff8a80}.status.unverified{background:#242424;color:#a8a8a8}
td form{display:inline}
td form button{width:auto;margin:0 6px 0 0;padding:4px 7px;font-size:12px;background:#262626;color:var(--text);border:1px solid #3a3a3a}
td form button.danger{color:#ff8a80}
h2{font-size:15px;margin:0 0 10px}
"""


def _csv_cell(value: object) -> object:
    # A cell starting with = + - @ runs as a formula when the CSV opens in a
    # spreadsheet; the addresses in it were typed by strangers.
    if isinstance(value, str) and value[:1] in ("=", "+", "-", "@", "\t", "\r"):
        return "'" + value
    return value


class AdminPanel:
    def __init__(self, settings: AccessSettings, store: AccessStore, *, client_ip) -> None:
        self.settings = settings
        self.store = store
        self.client_ip = client_ip
        self.logins = SlidingWindowLimiter(5, 900)

    def install(self, server: Flask) -> None:
        server.add_url_rule("/admin", "demo_admin", self._home, methods=["GET"])
        server.add_url_rule("/admin/login", "demo_admin_login", self._login, methods=["POST"])
        server.add_url_rule("/admin/logout", "demo_admin_logout", self._logout, methods=["POST"])
        server.add_url_rule("/admin/visitor", "demo_admin_visitor", self._visitor_action, methods=["POST"])
        server.add_url_rule("/admin/visitors.csv", "demo_admin_visitors_csv", self._visitors_csv, methods=["GET"])
        server.add_url_rule("/admin/events.csv", "demo_admin_events_csv", self._events_csv, methods=["GET"])
        # Anything else under /admin is a 404 here, not the Dash catch-all page.
        server.add_url_rule("/admin/<path:_rest>", "demo_admin_missing", lambda _rest: abort(404), methods=["GET", "POST"])

    # ----------------------------------------------------------------- auth

    def _cookie_value(self) -> str:
        return hmac.new(self.settings.admin_token.encode(), b"sfa-demo-admin-v1", hashlib.sha256).hexdigest()

    def _authed(self) -> bool:
        if not self.settings.admin_enabled:
            abort(404)
        return hmac.compare_digest(request.cookies.get(ADMIN_COOKIE, ""), self._cookie_value())

    def _respond(self, body: str, status: int = 200) -> Response:
        response = Response(body, status=status, mimetype="text/html")
        response.headers["Cache-Control"] = "no-store"
        response.headers["X-Robots-Tag"] = "noindex, nofollow"
        return response

    def _login_page(self, error: str | None = None, status: int = 200) -> Response:
        alert = f'<p class="alert bad" role="alert">{esc(error)}</p>' if error else ""
        body = (
            '<div class="card"><h1>Demo admin</h1>'
            f"{alert}"
            '<form method="post" action="/admin/login">'
            '<label for="token">Admin token</label>'
            '<input id="token" name="token" type="password" autocomplete="current-password" required autofocus>'
            '<button type="submit">Open</button></form></div>'
        )
        return self._respond(page("Admin", body), status)

    def _login(self):
        if not self.settings.admin_enabled:
            abort(404)
        if self.logins.hit(self.client_ip()):
            return self._login_page("Too many attempts. Wait 15 minutes.", 429)
        if not hmac.compare_digest(request.form.get("token", "").strip().encode(), self.settings.admin_token.encode()):
            return self._login_page("That token is not right.", 401)
        response = redirect("/admin", code=303)
        response.set_cookie(
            ADMIN_COOKIE, self._cookie_value(), max_age=12 * 3600, httponly=True, samesite="Strict",
            secure=request.headers.get("X-Forwarded-Proto") == "https" or request.scheme == "https", path="/admin",
        )
        return response

    def _logout(self):
        if not self.settings.admin_enabled:
            abort(404)
        response = redirect("/admin", code=303)
        response.delete_cookie(ADMIN_COOKIE, path="/admin")
        return response

    # ----------------------------------------------------------------- pages

    def _home(self):
        if not self._authed():
            return self._login_page()
        s = self.settings
        summary = self.store.summary()
        rows = self.store.visitor_rows()
        events = self.store.recent_events(100)
        done = request.args.get("done", "")

        tiles = "".join(
            f'<div class="tile"><b>{value}</b><span>{esc(label)}</span></div>'
            for label, value in (
                ("signed up (verified)", summary["signed_up"]),
                ("trials running now", summary["active_trials"]),
                ("new this week", summary["new_this_week"]),
                ("seen this week", summary["seen_this_week"]),
                ("backtests this week", summary["backtests_this_week"]),
                ("optimiser runs today", summary["optimizer_today"]),
                ("asked, never verified", summary["never_verified"]),
            )
        )

        def actions(row) -> str:
            email = esc(row["email"])
            hidden = f'<input type="hidden" name="email" value="{email}">'
            revoke = (
                f'<form method="post" action="/admin/visitor">{hidden}<input type="hidden" name="action" value="revoke">'
                '<button type="submit">Revoke</button></form>'
                if row["status"] != "revoked" else ""
            )
            return (
                f'<form method="post" action="/admin/visitor">{hidden}<input type="hidden" name="action" value="extend">'
                f'<button type="submit">+{s.trial_days} days</button></form>'
                f"{revoke}"
                # The address stays out of the confirm() text: it was typed by a stranger and would run as script there.
                '<form method="post" action="/admin/visitor" onsubmit="return confirm(\'Delete this person and all their usage?\')">'
                f'{hidden}<input type="hidden" name="action" value="delete"><button type="submit" class="danger">Delete</button></form>'
            )

        visitor_rows = "".join(
            "<tr>"
            f'<td>{esc(r["address"])}</td>'
            f'<td><span class="status {esc(r["status"])}">{esc(r["status"])}</span></td>'
            f'<td>{esc(fmt_date(r["verified_at"]))}</td>'
            f'<td>{esc(fmt_date(r["expires_at"]))}</td>'
            f'<td>{esc(fmt_time(r["last_seen"]))}</td>'
            f'<td class="n">{r["active_days"]}</td><td class="n">{r["visits"]}</td>'
            f'<td class="n">{r["backtests"]}</td><td class="n">{r["optimizer_runs"]}</td>'
            f'<td class="n">{r["data_loads"]}</td><td class="n">{r["fundamentals"]}</td>'
            f'<td class="n">{r["limits_hit"]}</td>'
            f'<td>{esc(", ".join(r["tickers"]) or "—")}</td>'
            f'<td>{esc(r["last_ip"] or "—")}</td>'
            f"<td>{actions(r)}</td>"
            "</tr>"
            for r in rows
        ) or '<tr><td colspan="15" class="muted">Nobody has asked for a code yet.</td></tr>'

        event_rows = "".join(
            f'<tr><td>{esc(fmt_time(e["at"]))}</td><td>{esc(e["email"])}</td><td>{esc(e["kind"])}</td>'
            f'<td>{esc(e["detail"] or "")}</td></tr>'
            for e in events
        ) or '<tr><td colspan="4" class="muted">No activity yet.</td></tr>'

        notice = f'<p class="alert good">Done: {esc(done)}.</p>' if done else ""
        body = (
            f"<style>{_CSS}</style>"
            '<div class="bar"><h1>Demo usage</h1><div class="row" style="margin:0">'
            '<a href="/admin/visitors.csv">Visitors CSV</a><a href="/admin/events.csv">Events CSV</a>'
            '<form method="post" action="/admin/logout"><button class="link" type="submit">Sign out</button></form>'
            "</div></div>"
            f"{notice}<div class=\"tiles\">{tiles}</div>"
            "<h2>People</h2><div class=\"scroll\"><table><thead><tr>"
            "<th>Email</th><th>Status</th><th>Signed up</th><th>Access until</th><th>Last seen</th>"
            "<th>Active days</th><th>Page loads</th><th>Backtests</th><th>Optimiser runs</th>"
            "<th>Data loads</th><th>Fundamentals</th><th>Limits hit</th><th>Tickers</th><th>Last IP</th><th></th>"
            f"</tr></thead><tbody>{visitor_rows}</tbody></table></div>"
            "<h2>Latest 100 events</h2><div class=\"scroll\"><table><thead><tr>"
            "<th>When</th><th>Account</th><th>What</th><th>Detail</th>"
            f"</tr></thead><tbody>{event_rows}</tbody></table></div>"
            f'<p class="muted small">Times in UTC. Trials last {s.trial_days} days from the first sign-in; '
            f"{s.jobs_per_email_per_day} optimiser runs per person per day; people unseen for {s.retention_days} days are deleted.</p>"
        )
        return self._respond(page("Admin", body, wide=True))

    def _visitor_action(self):
        if not self._authed():
            return redirect("/admin", code=303)
        email = request.form.get("email", "")
        action = request.form.get("action", "")
        if action == "extend":
            ok = self.store.extend(email, self.settings.trial_days)
            done = f"{email} extended by {self.settings.trial_days} days"
        elif action == "revoke":
            ok = self.store.revoke(email)
            done = f"{email} revoked"
        elif action == "delete":
            ok = self.store.delete(email)
            done = f"{email} deleted with its usage"
        else:
            abort(400)
        return redirect("/admin?done=" + quote(done if ok else f"nothing to change for {email}"), code=303)

    def _csv(self, filename: str, header: list[str], rows) -> Response:
        buffer = io.StringIO()
        writer = csv.writer(buffer)
        writer.writerow(header)
        for row in rows:
            writer.writerow([_csv_cell(value) for value in row])
        response = Response(buffer.getvalue(), mimetype="text/csv")
        response.headers["Content-Disposition"] = f'attachment; filename="{filename}"'
        response.headers["Cache-Control"] = "no-store"
        return response

    def _visitors_csv(self):
        if not self._authed():
            abort(404)
        columns = [
            "email", "address", "status", "requested_at", "verified_at", "expires_at", "last_seen", "active_days",
            "visits", "backtests", "optimizer_runs", "data_loads", "fundamentals", "limits_hit", "codes_sent",
            "tickers", "signup_ip", "last_ip",
        ]
        times = {"requested_at", "verified_at", "expires_at", "last_seen"}

        def values(row):
            for column in columns:
                value = row[column]
                if column in times:
                    value = fmt_time(value) if value else ""
                elif column == "tickers":
                    value = " ".join(value)
                yield value

        return self._csv("demo-visitors.csv", columns, (list(values(r)) for r in self.store.visitor_rows()))

    def _events_csv(self):
        if not self._authed():
            abort(404)
        return self._csv(
            "demo-events.csv",
            ["at_utc", "email", "kind", "detail"],
            ([fmt_time(e["at"]), e["email"], e["kind"], e["detail"] or ""] for e in self.store.iter_events()),
        )
