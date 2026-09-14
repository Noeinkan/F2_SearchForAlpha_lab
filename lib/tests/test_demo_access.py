"""
Public demo — the email gate, the trial clock, usage tracking and /admin.

The promise under test: nobody reaches the dashboard, or starts a callback,
without a verified address and a live trial; a trial is per mailbox, not per
spelling of it; and what signed-in visitors do is recorded where the owner can
read it.

Everything runs against a bare Flask app standing in for Dash (a catch-all
page carrying the account marker, and a ``/_dash-update-component`` that
records a backtest), with a fake clock and the console mailer, so no test
waits, sends mail or loads the dashboard. ``test_demo_mode.py`` runs the gate
once more in front of the real app.
"""

from __future__ import annotations

import re
import socket
import sys
from types import SimpleNamespace

import pytest
from flask import Flask

from demo import sealing
from demo.access import emails
from demo.access.admin import ADMIN_COOKIE, AdminPanel
from demo.access.gate import ACCESS_COOKIE, ACCOUNT_MARKER, AccessGate, safe_next
from demo.access.mailer import ConsoleMailer, MailError
from demo.access.settings import AccessSettings
from demo.access.store import DAY, AccessStore
from demo.guards import wall_response

ADMIN_TOKEN = "a" * 32
START = 1_800_000_000.0  # 2027-01-15 08:00 UTC


class Clock:
    def __init__(self) -> None:
        self.now = START

    def __call__(self) -> float:
        return self.now


@pytest.fixture
def world(tmp_path):
    clock = Clock()
    settings = AccessSettings(
        db_path=str(tmp_path / "access.sqlite3"),
        mail_backend="console",
        admin_token=ADMIN_TOKEN,
        trial_days=7,
        jobs_per_email_per_day=2,
        codes_per_email_per_hour=3,
        signups_per_ip_per_day=2,
        public_url="https://demo.test",
        contact_email="owner@example.com",
    )
    store = AccessStore(settings.db_path, clock=clock)
    mailer = ConsoleMailer()
    ip = {"value": "203.0.113.9"}
    gate = AccessGate(settings, store, mailer, wall=wall_response, client_ip=lambda: ip["value"])
    server = Flask("demo-access-test")
    gate.install(server)
    AdminPanel(settings, store, client_ip=lambda: ip["value"]).install(server)

    @server.route("/_dash-update-component", methods=["POST"])
    def update():
        gate.record("backtest", "TSLA")
        return '{"response": "ran"}'

    @server.route("/_dash-layout")
    def layout():
        return "{}"

    @server.route("/", defaults={"path": ""})
    @server.route("/<path:path>")
    def dashboard(path):
        return f"<html><body><div id=banner>{ACCOUNT_MARKER}</div>dashboard {path}</body></html>"

    yield SimpleNamespace(clock=clock, settings=settings, store=store, mailer=mailer, ip=ip, gate=gate, server=server)
    store.close()


def _code_from(mail) -> str:
    match = re.search(r"code is (\d{3}) (\d{3})", mail.text)
    assert match, mail.text
    return match.group(1) + match.group(2)


def _link_from(mail) -> str:
    match = re.search(r"https://demo\.test/access/verify\?t=([A-Za-z0-9_-]+)", mail.text)
    assert match, mail.text
    return match.group(1)


def sign_in(world, client, address="jane@example.com", next_path="/ticker/TSLA"):
    sent = client.post("/access", data={"email": address, "next": next_path})
    assert sent.status_code == 200, sent.get_data(as_text=True)
    return client.post("/access/code", data={"email": address, "code": _code_from(world.mailer.outbox[-1]), "next": next_path})


# --- Signed out ---------------------------------------------------------------

def test_signed_out_pages_redirect_to_sign_in_and_callbacks_get_a_notice(world):
    client = world.server.test_client()
    page = client.get("/ticker/TSLA")
    assert page.status_code == 302
    assert page.headers["Location"].startswith("/access?next=%2Fticker%2FTSLA")
    callback = client.post("/_dash-update-component", json={})
    assert callback.status_code == 200
    assert "demo-wall-body" in callback.get_data(as_text=True)
    assert "signed out" in callback.get_data(as_text=True)
    assert client.get("/_dash-layout").status_code == 401
    assert world.store.recent_events() == []  # nothing ran, nothing recorded


def test_sign_in_page_states_what_is_stored_and_for_how_long(world):
    html = world.server.test_client().get("/access").get_data(as_text=True)
    assert "What is stored" in html and "IP address" in html
    assert "12 months" in html and "owner@example.com" in html
    assert "7 days" in html


# --- Signing in ---------------------------------------------------------------

def test_the_code_signs_in_starts_the_trial_and_usage_is_recorded(world):
    client = world.server.test_client()
    response = sign_in(world, client)
    assert response.status_code == 303 and response.headers["Location"] == "/ticker/TSLA"
    cookie = client.get_cookie(ACCESS_COOKIE)
    assert cookie is not None and cookie.http_only

    page = client.get("/ticker/TSLA")
    html = page.get_data(as_text=True)
    assert page.status_code == 200
    assert "Signed in as <b>jane@example.com</b>" in html and "22 Jan 2027" in html
    assert page.headers["Cache-Control"] == "private, no-store"
    assert client.post("/_dash-update-component", json={}).get_data(as_text=True) == '{"response": "ran"}'

    visitor = world.store.visitor("jane@example.com")
    assert visitor.verified_at == START and visitor.expires_at == START + 7 * DAY
    kinds = [e["kind"] for e in world.store.recent_events()]
    assert {"code_sent", "signed_in", "visit", "backtest"} <= set(kinds)


def test_the_link_needs_a_click_so_a_mail_scanner_cannot_spend_it(world):
    client = world.server.test_client()
    client.post("/access", data={"email": "jane@example.com"})
    token = _link_from(world.mailer.outbox[-1])
    for _ in range(2):  # a scanner's GET, then the person's
        confirm = client.get(f"/access/verify?t={token}")
        assert confirm.status_code == 200 and "Open the demo" in confirm.get_data(as_text=True)
    assert client.get_cookie(ACCESS_COOKIE) is None
    assert client.post("/access/verify", data={"t": token}).status_code == 303
    assert client.get("/").status_code == 200
    assert world.server.test_client().post("/access/verify", data={"t": token}).status_code == 410  # used once


def test_wrong_codes_run_out_and_then_even_the_right_one_is_refused(world):
    client = world.server.test_client()
    client.post("/access", data={"email": "jane@example.com"})
    right = _code_from(world.mailer.outbox[-1])
    wrong = "000000" if right != "000000" else "111111"
    statuses = [client.post("/access/code", data={"email": "jane@example.com", "code": wrong}) for _ in range(5)]
    assert "4 tries left" in statuses[0].get_data(as_text=True)
    assert "Too many wrong codes" in statuses[-1].get_data(as_text=True)
    assert client.post("/access/code", data={"email": "jane@example.com", "code": right}).status_code == 400
    assert client.get_cookie(ACCESS_COOKIE) is None


def test_a_code_expires(world):
    client = world.server.test_client()
    client.post("/access", data={"email": "jane@example.com"})
    code = _code_from(world.mailer.outbox[-1])
    world.clock.now += 16 * 60
    response = client.post("/access/code", data={"email": "jane@example.com", "code": code})
    assert "expired" in response.get_data(as_text=True)


def test_mail_failure_says_so_instead_of_pretending(world):
    class Broken:
        def send(self, mail):
            raise MailError("connection refused")

    working = world.gate.mailer
    world.gate.mailer = Broken()
    client = world.server.test_client()
    for _ in range(4):  # more than the 3-an-hour cap: failures must not count against it
        response = client.post("/access", data={"email": "jane@example.com"})
        assert response.status_code == 503
        assert "could not be sent" in response.get_data(as_text=True)
    assert world.store.visitor("jane@example.com") is None  # a new address that got nothing is not kept
    assert world.store.recent_events() == []

    world.gate.mailer = working
    assert client.post("/access", data={"email": "jane@example.com"}).status_code == 200
    assert [e["kind"] for e in world.store.recent_events()] == ["code_sent"]


def test_sign_in_emails_are_capped_per_day_to_protect_the_shared_mailbox(world):
    world.gate.settings = AccessSettings(**{**world.settings.__dict__, "codes_per_day": 3, "signups_per_ip_per_day": 50})
    client = world.server.test_client()
    statuses = []
    for hour in range(4):
        statuses.append(client.post("/access", data={"email": f"person{hour}@example.com"}).status_code)
        world.clock.now += 3601  # step past the hourly cap each time
    assert statuses == [200, 200, 200, 429]
    world.clock.now += DAY
    assert client.post("/access", data={"email": "late@example.com"}).status_code == 200


# --- The trial ------------------------------------------------------------------

def test_an_ended_trial_redirects_walls_callbacks_and_cannot_be_restarted(world):
    client = world.server.test_client()
    sign_in(world, client)
    world.clock.now += 7 * DAY + 1

    page = client.get("/ticker/TSLA")
    assert page.status_code == 302 and page.headers["Location"] == "/access/ended"
    ended = client.get("/access/ended").get_data(as_text=True)
    assert "Your free trial has ended" in ended and "owner@example.com" in ended
    callback = client.post("/_dash-update-component", json={}).get_data(as_text=True)
    assert "demo-wall-body" in callback and "ended on 22 Jan 2027" in callback

    # A fresh browser asking again sees the same "check your inbox" page (no
    # reveal that this address had a trial) and the mailbox gets no code.
    fresh = world.server.test_client()
    sent = fresh.post("/access", data={"email": "jane@example.com"})
    assert "Check your inbox" in sent.get_data(as_text=True)
    assert "trial for this address ended" in world.mailer.outbox[-1].text
    assert "code is" not in world.mailer.outbox[-1].text


def test_a_trial_belongs_to_the_mailbox_not_the_spelling(world):
    assert emails.canonical("Jane.Doe+demo@GoogleMail.com") == "janedoe@gmail.com"
    assert emails.canonical("jane.doe+x@example.com") == "jane.doe@example.com"
    sign_in(world, world.server.test_client(), "Jane.Doe+demo@gmail.com")
    world.clock.now += 8 * DAY
    other = world.server.test_client()
    other.post("/access", data={"email": "janedoe@gmail.com"})
    assert "ended" in world.mailer.outbox[-1].text


def test_throwaway_inboxes_and_malformed_addresses_are_refused(world):
    client = world.server.test_client()
    assert client.post("/access", data={"email": "x@mailinator.com"}).status_code == 400
    assert client.post("/access", data={"email": "not-an-email"}).status_code == 400
    assert client.post("/access", data={"email": "a@b"}).status_code == 400
    assert world.mailer.outbox == []


def test_code_requests_are_capped_per_address_and_new_addresses_per_connection(world):
    client = world.server.test_client()
    codes = [client.post("/access", data={"email": "jane@example.com"}).status_code for _ in range(4)]
    assert codes == [200, 200, 200, 429]
    assert client.post("/access", data={"email": "second@example.com"}).status_code == 200
    assert client.post("/access", data={"email": "third@example.com"}).status_code == 429  # 2 new per IP per day
    world.ip["value"] = "198.51.100.4"
    assert client.post("/access", data={"email": "third@example.com"}).status_code == 200


def test_the_daily_optimiser_cap_counts_per_person_and_resets_at_utc_midnight(world):
    client = world.server.test_client()
    sign_in(world, client)
    with world.server.test_request_context("/"):
        from flask import g

        g.demo_email = "jane@example.com"
        assert world.gate.refuse_job() is None
        world.gate.record("optimizer", "combos")
        world.gate.record("optimizer", "grid")
        refusal = world.gate.refuse_job()
        assert refusal and "2 optimiser runs" in refusal and "00:00 UTC" in refusal
        world.clock.now += DAY
        assert world.gate.refuse_job() is None


def test_guards_refuse_a_job_past_the_personal_cap_and_record_the_refusal():
    from demo.guards import DemoGuards
    from demo.sessions import SessionStore
    from demo.settings import DemoSettings

    class _App:
        callback_map: dict = {}

    class _Access:
        def __init__(self):
            self.recorded = []

        def refuse_job(self):
            return "That is today's 25 optimiser runs for your demo account."

        def record(self, kind, detail=None):
            self.recorded.append((kind, detail))

    access = _Access()
    guards = DemoGuards(_App(), SessionStore(max_sessions=2, idle_seconds=60), DemoSettings(), access=access)
    with Flask("t").test_request_context("/", headers={"X-Real-IP": "203.0.113.1"}):
        assert guards._refuse_job("combos").startswith("That is today's 25")
    assert access.recorded and access.recorded[0][0] == "limit"


def test_sign_out_forgets_the_browser(world):
    client = world.server.test_client()
    sign_in(world, client)
    assert client.post("/access/signout").status_code == 303
    assert client.get("/").status_code == 302


# --- Admin ----------------------------------------------------------------------

def test_admin_is_a_404_without_a_token(tmp_path):
    settings = AccessSettings(db_path=str(tmp_path / "a.sqlite3"), mail_backend="console", admin_token="")
    store = AccessStore(settings.db_path)
    server = Flask("t")
    AdminPanel(settings, store, client_ip=lambda: "1.1.1.1").install(server)
    client = server.test_client()
    assert client.get("/admin").status_code == 404
    assert client.post("/admin/login", data={"token": ""}).status_code == 404
    assert client.get("/admin/visitors.csv").status_code == 404
    store.close()


def test_admin_shows_usage_exports_it_and_can_extend_a_trial(world):
    visitor = world.server.test_client()
    sign_in(world, visitor)
    visitor.get("/ticker/TSLA")
    visitor.post("/_dash-update-component", json={})

    admin = world.server.test_client()
    assert "Admin token" in admin.get("/admin").get_data(as_text=True)
    assert admin.post("/admin/login", data={"token": "wrong"}).status_code == 401
    assert admin.post("/admin/login", data={"token": ADMIN_TOKEN}).status_code == 303
    cookie = admin.get_cookie(ADMIN_COOKIE, path="/admin")
    assert cookie is not None and ADMIN_TOKEN not in cookie.value

    html = admin.get("/admin").get_data(as_text=True)
    assert "jane@example.com" in html and "TSLA" in html and "active" in html
    csv_text = admin.get("/admin/visitors.csv").get_data(as_text=True)
    assert csv_text.splitlines()[0].startswith("email,address,status")
    assert "jane@example.com" in csv_text
    assert "backtest" in admin.get("/admin/events.csv").get_data(as_text=True)

    world.clock.now += 6 * DAY
    admin.post("/admin/visitor", data={"email": "jane@example.com", "action": "extend"})
    assert world.store.visitor("jane@example.com").expires_at == START + 14 * DAY

    admin.post("/admin/visitor", data={"email": "jane@example.com", "action": "revoke"})
    assert visitor.get("/").status_code == 302

    admin.post("/admin/visitor", data={"email": "jane@example.com", "action": "delete"})
    assert world.store.visitor("jane@example.com") is None
    assert world.store.recent_events() == []


def test_csv_cells_cannot_run_as_spreadsheet_formulas(world):
    world.store.create_code(email="=cmd@example.com", address="=cmd@example.com", ip="1.1.1.1", user_agent="", minutes=15)
    admin = world.server.test_client()
    admin.post("/admin/login", data={"token": ADMIN_TOKEN})
    assert "'=cmd@example.com" in admin.get("/admin/visitors.csv").get_data(as_text=True)


def test_admin_forms_escape_what_strangers_typed(world):
    world.store.create_code(email="<b>x@example.com", address="<b>x@example.com", ip="1.1.1.1", user_agent="", minutes=15)
    admin = world.server.test_client()
    admin.post("/admin/login", data={"token": ADMIN_TOKEN})
    html = admin.get("/admin").get_data(as_text=True)
    assert "<b>x@example.com" not in html and "&lt;b&gt;x@example.com" in html


# --- Housekeeping, settings, redirects --------------------------------------------

def test_visitors_unseen_past_retention_are_deleted_with_their_usage(world):
    sign_in(world, world.server.test_client())
    world.clock.now += 366 * DAY
    assert world.store.purge(365) == 1
    assert world.store.visitor("jane@example.com") is None
    assert world.store.recent_events() == []


def test_addresses_nobody_verified_are_gone_after_a_month(world):
    world.server.test_client().post("/access", data={"email": "typed-by-someone-else@example.com"})
    world.clock.now += 29 * DAY
    assert world.store.purge(365) == 0
    world.clock.now += 2 * DAY
    assert world.store.purge(365) == 1
    assert world.store.visitor("typed-by-someone-else@example.com") is None


@pytest.mark.parametrize("value, expected", [
    ("/ticker/TSLA?x=1", "/ticker/TSLA?x=1"),
    ("//evil.example", "/"),
    ("/\\evil.example", "/"),
    ("https://evil.example", "/"),
    ("/admin", "/"),
    ("/access/ended", "/"),
    (None, "/"),
])
def test_return_paths_stay_on_the_site(value, expected):
    assert safe_next(value) == expected


_MAIL_VARS = (
    "NEO_SMTP_HOST", "NEO_SMTP_PORT", "NEO_SMTP_USER", "NEO_SMTP_PASS",
    "SMTP_HOST", "SMTP_PORT", "SMTP_USER", "SMTP_PASS", "EMAIL_FROM", "SMTP_FROM",
    "DEMO_SMTP_SECURITY", "DEMO_MAIL_BACKEND", "DEMO_ACCESS_GATE",
)


def test_mail_settings_read_capsars_neo_names_first(monkeypatch):
    for name in _MAIL_VARS:
        monkeypatch.delenv(name, raising=False)
    # The block from Capsar's .env, pasted as is.
    monkeypatch.setenv("NEO_SMTP_HOST", "smtp0001.neo.space")
    monkeypatch.setenv("NEO_SMTP_PORT", "465")
    monkeypatch.setenv("NEO_SMTP_USER", "owner@noeinsolutions.example")
    monkeypatch.setenv("NEO_SMTP_PASS", " pass word ")
    monkeypatch.setenv("SMTP_HOST", "smtp-relay.fallback.example")
    monkeypatch.setenv("SMTP_PORT", "587")
    settings = AccessSettings.from_env()
    assert (settings.smtp_host, settings.smtp_port, settings.tls_mode) == ("smtp0001.neo.space", 465, "ssl")
    assert settings.smtp_password == " pass word "  # taken exactly as written
    assert settings.mail_from == "owner@noeinsolutions.example"  # Neo sends only as the mailbox
    assert settings.problems() == []

    for name in ("NEO_SMTP_HOST", "NEO_SMTP_PORT"):
        monkeypatch.delenv(name)
    settings = AccessSettings.from_env()
    assert (settings.smtp_host, settings.smtp_port, settings.tls_mode) == ("smtp-relay.fallback.example", 587, "starttls")
    monkeypatch.setenv("EMAIL_FROM", "demo@noeinsolutions.example")
    monkeypatch.setenv("DEMO_SMTP_SECURITY", "none")
    settings = AccessSettings.from_env()
    assert settings.mail_from == "demo@noeinsolutions.example" and settings.tls_mode == "none"


def test_settings_refuse_an_smtp_gate_with_no_server(monkeypatch):
    for name in _MAIL_VARS:
        monkeypatch.delenv(name, raising=False)
    problems = AccessSettings.from_env().problems()
    assert any("NEO_SMTP_HOST" in p for p in problems)
    assert any("NEO_SMTP_PASS" in p for p in problems)
    monkeypatch.setenv("DEMO_MAIL_BACKEND", "console")
    assert AccessSettings.from_env().problems() == []
    monkeypatch.setenv("DEMO_ACCESS_GATE", "false")
    monkeypatch.setenv("DEMO_MAIL_BACKEND", "carrier-pigeon")
    assert AccessSettings.from_env().problems() == []
    monkeypatch.setenv("DEMO_TRIAL_DAYS", "3")
    monkeypatch.setenv("DEMO_BLOCKED_EMAIL_DOMAINS", "Spam.example, junk.example")
    settings = AccessSettings.from_env()
    assert settings.trial_days == 3 and "spam.example" in settings.blocked_domains


def test_smtp_mailer_speaks_implicit_tls_to_neo_as_the_mailbox(monkeypatch):
    import smtplib

    from demo.access.mailer import Mail, SmtpMailer, sender

    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None, context=None):
            calls.append(("connect", type(self).__name__, host, port, context is not None))

        def __enter__(self):
            return self

        def __exit__(self, *exc):
            return False

        def starttls(self, context=None):
            calls.append(("starttls",))

        def login(self, user, password):
            calls.append(("login", user, password))

        def send_message(self, message):
            calls.append(("send", message["From"], message["To"]))

    class FakeSMTP_SSL(FakeSMTP):
        pass

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    monkeypatch.setattr(smtplib, "SMTP_SSL", FakeSMTP_SSL)
    mail = Mail(to="jane@example.com", subject="s", text="t", html="<p>t</p>")

    neo = AccessSettings(smtp_host="smtp0001.neo.space", smtp_port=465, smtp_user="owner@noeinsolutions.example",
                         smtp_password="pw", mail_from="owner@noeinsolutions.example")
    SmtpMailer(neo).send(mail)
    assert calls == [
        ("connect", "FakeSMTP_SSL", "smtp0001.neo.space", 465, True),
        ("login", "owner@noeinsolutions.example", "pw"),
        ("send", "SearchForAlpha Lab demo <owner@noeinsolutions.example>", "jane@example.com"),
    ]

    calls.clear()
    SmtpMailer(AccessSettings(smtp_host="relay.example", smtp_port=587, smtp_user="u", smtp_password="p",
                              mail_from="Named <n@example.com>")).send(mail)
    assert [c[0] for c in calls] == ["connect", "starttls", "login", "send"]
    assert calls[0][1] == "FakeSMTP" and calls[-1][1] == "Named <n@example.com>"
    assert sender("") == ""


def test_network_seal_opens_only_the_mail_server(monkeypatch):
    real_yf = sys.modules.get("yfinance")
    connected = []
    fake_ip = "198.51.100.25"

    def fake_getaddrinfo(host, port, *args, **kwargs):
        return [(socket.AF_INET, socket.SOCK_STREAM, 6, "", (fake_ip, int(port)))]

    monkeypatch.setitem(sealing._ORIGINAL, "getaddrinfo", fake_getaddrinfo)
    monkeypatch.setitem(sealing._ORIGINAL, "connect", lambda self, address: connected.append(address))
    sealing.install_network_seal()
    sealing.allow_outbound("smtp.example.com", 587)
    try:
        assert socket.getaddrinfo("smtp.example.com", 587)[0][4] == (fake_ip, 587)
        with pytest.raises(sealing.NetworkRefused):
            socket.getaddrinfo("smtp.example.com", 25)  # same host, other port
        with pytest.raises(sealing.NetworkRefused):
            socket.getaddrinfo("query1.finance.yahoo.com", 443)
        sock = socket.socket()
        try:
            sock.connect((fake_ip, 587))
            with pytest.raises(sealing.NetworkRefused):
                sock.connect(("198.51.100.26", 587))
            with pytest.raises(sealing.NetworkRefused):
                sock.connect((fake_ip, 443))
        finally:
            sock.close()
        assert connected == [(fake_ip, 587)]
    finally:
        # Undo first: remove_network_seal restores sockets from _ORIGINAL,
        # which still holds the fakes until the monkeypatch is undone.
        monkeypatch.undo()
        sealing.remove_network_seal(real_yf)
    assert not sealing._ALLOWED_HOSTS
