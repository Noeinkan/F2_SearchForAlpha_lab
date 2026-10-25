"""The hosted workspace's site login (owner path) and data-volume layout (hosted/).

The whitelist side of the login is in test_hosted_users.py.
"""

from __future__ import annotations

import pytest
from flask import Flask
from werkzeug.security import generate_password_hash

from hosted import persist
from hosted.login import COOKIE_NAME, MAX_FAILURES, LoginConfigError, SiteLogin

EMAIL = "owner@example.com"
PASSWORD = "correct horse battery staple"
SECRET = "s" * 40


@pytest.fixture()
def client():
    server = Flask("t")

    @server.route("/")
    def home():
        return "workspace"

    @server.route("/_dash-update-component", methods=["POST"])
    def dash_update():
        return "{}"

    @server.route("/healthz")
    def healthz():
        return "ok"

    SiteLogin(EMAIL, generate_password_hash(PASSWORD), SECRET).install(server)
    return server.test_client()


def _login(client, email=EMAIL, password=PASSWORD, next_="/"):
    return client.post("/login", data={"email": email, "password": password, "next": next_})


def test_pages_redirect_to_login_and_callbacks_get_401(client):
    page = client.get("/ticker/TSLA?x=1")
    assert page.status_code == 302
    assert page.headers["Location"].startswith("/login?next=/ticker/TSLA")
    assert client.post("/_dash-update-component").status_code == 401
    assert client.get("/healthz").status_code == 200


def test_right_credentials_open_the_site_case_insensitive_email(client):
    response = _login(client, email="  Owner@Example.com ")
    assert response.status_code == 302
    assert client.get("/").data == b"workspace"
    assert client.post("/_dash-update-component").status_code == 200


def test_wrong_password_is_refused_and_five_lock_the_form(client):
    for _ in range(MAX_FAILURES):
        assert _login(client, password="nope").status_code == 401
    # Locked: even the right password is refused now.
    assert _login(client).status_code == 401
    assert client.get("/").status_code == 302


def test_next_cannot_leave_the_site(client):
    for target in ("//evil.com", "https://evil.com", "/\\evil.com"):
        assert _login(client, next_=target).headers["Location"] == "/"


def test_logout_and_forged_cookie(client):
    client.set_cookie(COOKIE_NAME, "forged")
    assert client.get("/").status_code == 302
    _login(client)
    client.get("/logout")
    assert client.get("/").status_code == 302


def test_missing_secrets_refuse_to_start(monkeypatch):
    monkeypatch.delenv("SITE_LOGIN_EMAIL", raising=False)
    monkeypatch.setenv("SITE_LOGIN_PASSWORD_HASH", generate_password_hash(PASSWORD))
    monkeypatch.setenv("SITE_SECRET_KEY", SECRET)
    with pytest.raises(LoginConfigError):
        SiteLogin.from_env()
    monkeypatch.setenv("SITE_LOGIN_EMAIL", EMAIL)
    monkeypatch.setenv("SITE_LOGIN_PASSWORD_HASH", PASSWORD)  # plain text, not a hash
    with pytest.raises(LoginConfigError):
        SiteLogin.from_env()
    monkeypatch.setenv("SITE_LOGIN_PASSWORD_HASH", generate_password_hash(PASSWORD))
    monkeypatch.delenv("SITE_SECRET_KEY")
    with pytest.raises(LoginConfigError):
        SiteLogin.from_env()
    monkeypatch.setenv("SITE_SECRET_KEY", "short")
    with pytest.raises(LoginConfigError):
        SiteLogin.from_env()
    monkeypatch.setenv("SITE_SECRET_KEY", SECRET)
    assert SiteLogin.from_env().email == EMAIL


def test_changing_the_owner_password_signs_the_old_cookie_out(client):
    _login(client)
    cookie = client.get_cookie(COOKIE_NAME).value
    other = Flask("t2")
    other.route("/")(lambda: "workspace")
    SiteLogin(EMAIL, generate_password_hash("a new password"), SECRET).install(other)
    second = other.test_client()
    second.set_cookie(COOKIE_NAME, cookie)
    assert second.get("/").status_code == 302


def test_persist_refreshes_config_but_keeps_user_files(tmp_path):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "strategy_config.yaml").write_text("new")
    (dist / "watchlists.json").write_text("repo")
    data = tmp_path / "data"
    (data / "config").mkdir(parents=True)
    (data / "config" / "strategy_config.yaml").write_text("old")
    (data / "config" / "watchlists.json").write_text("mine")

    persist.prepare(data, dist)

    assert (data / "config" / "strategy_config.yaml").read_text() == "new"
    assert (data / "config" / "watchlists.json").read_text() == "mine"
    assert all((data / name).is_dir() for name in persist.DATA_SUBDIRS)
    assert persist.prepare(None, dist) is None
