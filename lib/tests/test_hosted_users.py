"""Whitelist login on the hosted workspace: hosted/users.py, hosted/login.py, hosted/admin_users.py."""

from __future__ import annotations

import re

import pytest
from flask import Flask, g
from werkzeug.security import generate_password_hash

from demo.access.mailer import ConsoleMailer
from hosted import admin_users
from hosted.login import COOKIE_NAME, SiteLogin
from hosted.users import PASSCODE_ALPHABET, PASSCODE_LENGTH, UserError, UserStore, _main

OWNER = "owner@example.com"
OWNER_PASSWORD = "correct horse battery staple"
GUEST = "guest@example.com"
SECRET = "k" * 40
ORIGIN = {"Origin": "http://localhost"}


@pytest.fixture()
def store(tmp_path):
    return UserStore(tmp_path / "users.sqlite3")


@pytest.fixture()
def mailer():
    return ConsoleMailer()


@pytest.fixture()
def server(store, mailer, monkeypatch):
    monkeypatch.delenv("ADMIN_EMAILS", raising=False)
    app = Flask("t")

    @app.route("/")
    def home():
        return f"{g.user_email}|{g.is_admin}"

    SiteLogin(OWNER, generate_password_hash(OWNER_PASSWORD), SECRET, store=store).install(app)
    admin_users.install(app, store, mailer=mailer)
    return app


def _login(client, email, password):
    return client.post("/login", data={"email": email, "password": password, "next": "/"})


def test_passcode_shape_and_only_its_hash_is_stored(store):
    passcode = store.invite(GUEST)
    assert len(passcode) == PASSCODE_LENGTH and set(passcode) <= set(PASSCODE_ALPHABET)
    user = store.get("  Guest@Example.com ")
    assert user and passcode not in user.passcode_hash
    with pytest.raises(UserError):
        store.invite("not-an-email")


def test_invited_user_signs_in_with_the_passcode_and_is_not_admin(server, store):
    passcode = store.invite(GUEST)
    client = server.test_client()
    assert _login(client, GUEST, "wrong-passcode").status_code == 401
    assert _login(client, GUEST.upper(), passcode).status_code == 302
    assert client.get("/").data.decode() == f"{GUEST}|False"
    assert client.get("/admin/users").status_code == 404
    assert store.get(GUEST).last_login is not None


def test_owner_is_admin_by_default_and_admin_emails_overrides(server, store, monkeypatch):
    client = server.test_client()
    _login(client, OWNER, OWNER_PASSWORD)
    assert client.get("/").data.decode() == f"{OWNER}|True"
    assert client.get("/admin/users").status_code == 200

    passcode = store.invite(GUEST)
    monkeypatch.setenv("ADMIN_EMAILS", f"{GUEST}, someone@else.com")
    guest = server.test_client()
    _login(guest, GUEST, passcode)
    assert guest.get("/").data.decode() == f"{GUEST}|True"
    # Read on every request: the owner is no longer in the list.
    assert client.get("/").data.decode() == f"{OWNER}|False"


def test_revoked_user_is_out_on_the_next_click(server, store):
    passcode = store.invite(GUEST)
    client = server.test_client()
    _login(client, GUEST, passcode)
    assert client.get("/").status_code == 200
    store.set_active(GUEST, False)
    assert client.get("/").status_code == 302
    assert client.post("/_dash-update-component").status_code == 401
    assert client.get("/api/session").status_code == 401
    assert _login(client, GUEST, passcode).status_code == 401


def test_new_passcode_signs_old_sessions_out(server, store):
    passcode = store.invite(GUEST)
    client = server.test_client()
    _login(client, GUEST, passcode)
    fresh = store.regenerate(GUEST)
    assert client.get("/").status_code == 302
    assert _login(client, GUEST, passcode).status_code == 401
    assert _login(client, GUEST, fresh).status_code == 302


def test_cookie_from_another_secret_key_is_refused(server, store):
    other = Flask("o")
    other.route("/")(lambda: "x")
    SiteLogin(OWNER, generate_password_hash(OWNER_PASSWORD), "z" * 40, store=store).install(other)
    foreign = other.test_client()
    _login(foreign, OWNER, OWNER_PASSWORD)
    client = server.test_client()
    client.set_cookie(COOKIE_NAME, foreign.get_cookie(COOKIE_NAME).value)
    assert client.get("/").status_code == 302


def test_admin_adds_a_user_who_gets_a_mail_and_can_sign_in(server, store, mailer):
    admin = server.test_client()
    _login(admin, OWNER, OWNER_PASSWORD)
    page = admin.post("/admin/users", data={"action": "add", "email": GUEST}, headers=ORIGIN)
    assert page.status_code == 200
    shown = re.search(r"<code>([^<]+)</code>", page.data.decode()).group(1)
    assert mailer.outbox and mailer.outbox[0].to == GUEST and shown in mailer.outbox[0].text

    guest = server.test_client()
    assert _login(guest, GUEST, shown).status_code == 302

    admin.post("/admin/users", data={"action": "revoke", "email": GUEST}, headers=ORIGIN)
    assert guest.get("/").status_code == 302
    admin.post("/admin/users", data={"action": "delete", "email": GUEST}, headers=ORIGIN)
    assert store.get(GUEST) is None


def test_admin_post_without_same_origin_is_refused(server, store):
    admin = server.test_client()
    _login(admin, OWNER, OWNER_PASSWORD)
    assert admin.post("/admin/users", data={"action": "add", "email": GUEST}).status_code == 403
    evil = {"Origin": "https://evil.example"}
    assert admin.post("/admin/users", data={"action": "add", "email": GUEST}, headers=evil).status_code == 403
    assert store.get(GUEST) is None


def test_failed_mail_still_shows_the_passcode(server, store, mailer):
    def boom(_mail):
        raise RuntimeError("smtp down")

    mailer.send = boom
    admin = server.test_client()
    _login(admin, OWNER, OWNER_PASSWORD)
    body = admin.post("/admin/users", data={"action": "add", "email": GUEST}, headers=ORIGIN).data.decode()
    assert "could NOT be sent" in body and "<code>" in body


def test_admin_page_escapes_emails(server, store):
    store.invite('a"<b>@example.com')
    admin = server.test_client()
    _login(admin, OWNER, OWNER_PASSWORD)
    body = admin.get("/admin/users").data.decode()
    assert "<b>@example.com" not in body and "&lt;b&gt;" in body


def test_cli_add_list_revoke(tmp_path, monkeypatch, capsys):
    monkeypatch.setenv("SITE_USERS_DB", str(tmp_path / "cli.sqlite3"))
    assert _main(["add", GUEST]) == 0
    assert "passcode:" in capsys.readouterr().out
    assert _main(["revoke", GUEST]) == 0
    assert _main(["list"]) == 0
    assert "revoked" in capsys.readouterr().out
    assert _main(["revoke", "nobody@example.com"]) == 1
