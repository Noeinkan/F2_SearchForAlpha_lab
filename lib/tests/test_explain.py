"""Explain: prompt, Gemini call (faked, never the network) and the admin-only routes."""

from __future__ import annotations

import pytest
from flask import Flask, g

from lib.dash.explain_route import HEADER, REQUESTS_PER_MINUTE, install_explain_routes
from lib.explain import gemini
from lib.explain.glossary import glossary_text

HEADERS = {HEADER: "1"}


class FakeResponse:
    def __init__(self, status_code=200, payload=None):
        self.status_code = status_code
        self._payload = payload

    def json(self):
        if self._payload is None:
            raise ValueError("no json")
        return self._payload


class FakeSession:
    def __init__(self, response=None, error=None):
        self.response, self.error, self.calls = response, error, []

    def post(self, url, **kwargs):
        self.calls.append((url, kwargs))
        if self.error:
            raise self.error
        return self.response


def _answer(text):
    return {"candidates": [{"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": text}]}}]}


# ------------------------------------------------------------------ prompt --

def test_glossary_uses_the_projects_definitions():
    text = glossary_text()
    assert "Jensen" in text and "Excess_Return_%" in text and "round trip" in text


def test_glossary_carries_indicator_defaults_and_signal_rules():
    from lib.config_loader import get_config

    text = glossary_text()
    window = get_config().get_strategy_config("rsi")["rsi"]["window"]
    assert f"rsi.window={window}" in text
    assert "_Buy:" in text and "_Sell:" in text


def test_prompt_carries_context_and_clips_long_input():
    prompt = gemini.build_prompt("1.42", "column \"Sharpe\"", "TSLA", "/ticker/TSLA")
    assert "Selected text: 1.42" in prompt and "Sharpe" in prompt and "TSLA" in prompt
    assert "English" in prompt
    assert "$$" in prompt and "- " in prompt  # the light format 95-explain.js renders
    long = gemini.build_prompt("x" * 1000, "y" * 5000)
    assert "x" * gemini.MAX_SELECTION_CHARS not in long
    assert "y" * gemini.MAX_CONTEXT_CHARS not in long


# --------------------------------------------------------------- gemini ---

def test_explain_success_skips_thought_parts_and_sends_the_key(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "test-key")
    monkeypatch.delenv("GEMINI_MODEL", raising=False)
    session = FakeSession(FakeResponse(200, _answer("Sharpe of 1.42 is solid.")))
    result = gemini.explain("1.42", session=session)
    assert result.ok and result.text == "Sharpe of 1.42 is solid."
    url, kwargs = session.calls[0]
    assert gemini.DEFAULT_MODEL in url and kwargs["headers"]["x-goog-api-key"] == "test-key"
    assert "test-key" not in url


@pytest.mark.parametrize("status, needle", [(429, "quota"), (403, "API key"), (404, "model"), (500, "HTTP 500")])
def test_explain_http_errors_become_sentences(monkeypatch, status, needle):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    result = gemini.explain("1.42", session=FakeSession(FakeResponse(status, {})))
    assert not result.ok and needle in result.text


def test_explain_shows_googles_reason(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    payload = {"error": {"message": "API key not valid. Please pass a valid API key."}}
    result = gemini.explain("1.42", session=FakeSession(FakeResponse(400, payload)))
    assert not result.ok and "API key not valid" in result.text


def test_explain_never_raises(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    assert not gemini.explain("1.42", session=FakeSession(error=TimeoutError())).ok
    assert not gemini.explain("1.42", session=FakeSession(FakeResponse(200, None))).ok
    assert not gemini.explain("1.42", session=FakeSession(FakeResponse(200, {"candidates": []}))).ok
    monkeypatch.delenv("GEMINI_API_KEY")
    assert "GEMINI_API_KEY" in gemini.explain("1.42").text


# --------------------------------------------------------------- routes ---

def _app(mode=None, admin=False):
    app = Flask("t")
    if mode:
        app.config["SFA_AUTH_MODE"] = mode

    @app.before_request
    def fake_login():
        g.user_email = "me@example.com"
        g.is_admin = admin

    calls = []

    def fake_explain(selection, context, ticker, page):
        calls.append((selection, context, ticker, page))
        return gemini.Explanation(True, f"explained {selection}")

    install_explain_routes(app, explain=fake_explain)
    return app.test_client(), calls


def _post(client, payload, headers=HEADERS):
    return client.post("/api/explain", json=payload, headers=headers)


def test_local_run_is_admin_and_explains(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client, calls = _app()
    info = client.get("/api/session").get_json()
    assert info == {"mode": "local", "email": None, "admin": True, "explain": True}
    response = _post(client, {"selection": "1.42", "context": "Sharpe", "ticker": "TSLA", "page": "/"})
    assert response.get_json() == {"ok": True, "text": "explained 1.42"}
    assert calls == [("1.42", "Sharpe", "TSLA", "/")]


def test_explain_off_without_a_key(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    client, calls = _app()
    assert client.get("/api/session").get_json()["explain"] is False
    assert _post(client, {"selection": "1.42"}).status_code == 503
    assert not calls


@pytest.mark.parametrize("mode, admin", [("demo", True), ("hosted", False)])
def test_demo_and_non_admins_get_404(monkeypatch, mode, admin):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client, calls = _app(mode, admin)
    assert client.get("/api/session").get_json()["explain"] is False
    assert _post(client, {"selection": "1.42"}).status_code == 404
    assert not calls


def test_hosted_admin_sees_email_and_can_explain(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client, _ = _app("hosted", admin=True)
    info = client.get("/api/session").get_json()
    assert info["email"] == "me@example.com" and info["admin"] and info["explain"]
    assert _post(client, {"selection": "Alpha"}).status_code == 200


def test_missing_header_or_bad_input_is_refused(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client, calls = _app()
    assert _post(client, {"selection": "1.42"}, headers={}).status_code == 400
    assert client.post("/api/explain", data="selection=1.42", headers=HEADERS).status_code == 400
    assert _post(client, {"selection": "   "}).status_code == 400
    assert _post(client, {"selection": "x" * (gemini.MAX_SELECTION_CHARS + 1)}).status_code == 400
    assert not calls


def test_rate_limit(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client, _ = _app()
    for _ in range(REQUESTS_PER_MINUTE):
        assert _post(client, {"selection": "1"}).status_code == 200
    assert _post(client, {"selection": "1"}).status_code == 429
