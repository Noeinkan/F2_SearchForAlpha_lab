"""Explain: prompt, Gemini call (faked, never the network) and the admin-only routes."""

from __future__ import annotations

import pytest
from flask import Flask, g

from lib.dash.explain_route import HEADER, REQUESTS_PER_MINUTE, install_explain_routes
from lib.explain import gemini
from lib.explain.cache import AnswerCache
from lib.explain.glossary import glossary_for, glossary_text

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


def _answer(text, grounding=None):
    candidate = {"content": {"parts": [{"text": "thinking...", "thought": True}, {"text": text}]}}
    if grounding:
        candidate["groundingMetadata"] = grounding
    return {"candidates": [candidate]}


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


def test_glossary_for_sends_only_what_was_clicked():
    full = glossary_text()
    rsi = glossary_for("RSI", 'panel "Chart Settings"; control {"indicator":"rsi"}')
    assert "rsi.window=" in rsi and "RSI_Oversold_Buy" in rsi
    assert "macd.fast_period" not in rsi and "Sharpe_Ratio" not in rsi
    assert len(rsi) < len(full) / 3

    sharpe = glossary_for("1.42", 'column "Sharpe_Ratio"')
    assert "Sharpe_Ratio" in sharpe and "rsi.window" not in sharpe

    bands = glossary_for("BB_Breakout_Buy", "")
    assert "bollinger_bands.window=" in bands and "BB_Breakout_Buy" in bands

    control = glossary_for("Min Holding", 'panel "Trade Setup"')
    assert "Metrics the app shows:" in control and "rsi" in control
    assert len(control) < len(full) / 3


def test_symbol_only_in_the_prompt_for_numbers():
    assert "TSLA" in gemini.build_prompt("1.42", "Sharpe", "TSLA", "/ticker/TSLA")
    word = gemini.build_prompt("RSI", "Chart Settings", "TSLA", "/ticker/TSLA")
    assert "TSLA" not in word
    assert gemini.cache_key("RSI", "Chart Settings", "TSLA", "/ticker/TSLA") == gemini.cache_key(
        "RSI", "Chart Settings", "AAPL", "/ticker/AAPL")
    assert gemini.cache_key("1.42", "Sharpe", "TSLA") != gemini.cache_key("1.42", "Sharpe", "AAPL")


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


def test_answer_never_searches_and_sources_do(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("GEMINI_SEARCH", raising=False)
    answer = FakeSession(FakeResponse(200, _answer("RSI is momentum.")))
    gemini.explain("RSI", "Chart Settings", "TSLA", "/ticker/TSLA", session=answer)
    assert "tools" not in answer.calls[0][1]["json"]
    assert "Google Search" not in gemini.build_prompt("RSI")
    prompt = gemini.build_sources_prompt("RSI", "Chart Settings")
    assert "Google Search" in prompt and "Chart Settings" in prompt
    assert gemini.cache_key("RSI", part="sources") != gemini.cache_key("RSI", part="answer")
    # The links are about the concept: one search serves every symbol.
    assert gemini.cache_key("RSI", "x", "TSLA", "/a", part="sources") == gemini.cache_key("RSI", "x", "AAPL", "/b", part="sources")


def test_find_sources_returns_googles_links(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    monkeypatch.delenv("GEMINI_SEARCH", raising=False)
    web = lambda title, uri: {"web": {"title": title, "uri": uri}}
    grounding = {
        "groundingChunks": [
            web("investopedia.com", "https://redirect/1"),
            web("investopedia.com", "https://redirect/2"),  # same site twice: kept once
            web("evil", "javascript:alert(1)"),             # not https: dropped
            web("wikipedia.org", "https://redirect/3"),
        ],
        "searchEntryPoint": {"renderedContent": "<div class=chip>rsi</div>"},
    }
    session = FakeSession(FakeResponse(200, _answer("Relative Strength Index", grounding)))
    result = gemini.find_sources("RSI", session=session)
    assert session.calls[0][1]["json"]["tools"] == [{"google_search": {}}]
    assert [s.title for s in result.sources] == ["investopedia.com", "wikipedia.org"]
    assert result.ok and result.suggestions == "<div class=chip>rsi</div>"

    # Gemini answered without searching: not ok, so it is not cached for 30 days.
    assert not gemini.find_sources("RSI", session=FakeSession(FakeResponse(200, _answer("RSI")))).ok

    monkeypatch.setenv("GEMINI_SEARCH", "0")
    off = FakeSession(FakeResponse(200, _answer("x")))
    result = gemini.find_sources("RSI", session=off)
    assert result.ok and not result.sources and not off.calls  # search off: no call at all


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

def _app(mode=None, admin=False, cache=False):
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
        sources = (gemini.Source("investopedia.com", "https://example.test/rsi"),)
        return gemini.Explanation(True, f"explained {selection}", sources, "<b>chips</b>")

    def fake_sources(selection, context, ticker, page):
        calls.append(("sources", selection))
        return gemini.Explanation(True, "concept", (gemini.Source("wikipedia.org", "https://example.test/w"),), "<i>s</i>")

    install_explain_routes(app, explain=fake_explain, sources=fake_sources, cache=cache)
    return app.test_client(), calls


def _post(client, payload, headers=HEADERS):
    return client.post("/api/explain", json=payload, headers=headers)


def test_local_run_is_admin_and_explains(monkeypatch):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client, calls = _app()
    info = client.get("/api/session").get_json()
    assert info == {"mode": "local", "email": None, "admin": True, "explain": True, "sources": True}
    response = _post(client, {"selection": "1.42", "context": "Sharpe", "ticker": "TSLA", "page": "/"})
    body = response.get_json()
    assert body["ok"] and body["text"] == "explained 1.42" and not body["cached"]
    assert body["sources"] == [{"title": "investopedia.com", "url": "https://example.test/rsi"}]
    assert calls == [("1.42", "Sharpe", "TSLA", "/")]


def test_second_ask_comes_from_the_cache_and_refresh_asks_again(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client, calls = _app(cache=AnswerCache(tmp_path / "answers.sqlite3"))
    question = {"selection": "RSI", "context": "Chart Settings", "ticker": "TSLA", "page": "/ticker/TSLA"}
    first = _post(client, question).get_json()
    # Another symbol, same control: same answer, no new call.
    second = _post(client, {**question, "ticker": "AAPL", "page": "/ticker/AAPL"}).get_json()
    assert len(calls) == 1
    assert second["cached"] and second["cached_at"] and second["text"] == first["text"]
    assert second["sources"] == first["sources"] and second["suggestions"] == "<b>chips</b>"

    fresh = _post(client, {**question, "fresh": True}).get_json()
    assert len(calls) == 2 and not fresh["cached"]


def test_sources_part_has_its_own_call_and_cache_entry(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client, calls = _app(cache=AnswerCache(tmp_path / "answers.sqlite3"))
    question = {"selection": "RSI", "context": "Chart Settings"}
    answer = _post(client, question).get_json()
    links = _post(client, {**question, "part": "sources"}).get_json()
    assert answer["text"] == "explained RSI" and links["sources"][0]["title"] == "wikipedia.org"
    assert _post(client, {**question, "part": "sources"}).get_json()["cached"]
    assert len(calls) == 2
    assert _post(client, {**question, "part": "nope"}).status_code == 400


def test_cached_answers_do_not_count_against_the_limit(monkeypatch, tmp_path):
    monkeypatch.setenv("GEMINI_API_KEY", "k")
    client, calls = _app(cache=AnswerCache(tmp_path / "answers.sqlite3"))
    for _ in range(REQUESTS_PER_MINUTE + 5):
        assert _post(client, {"selection": "RSI"}).status_code == 200
    assert len(calls) == 1


def test_cache_expires_and_skips_failures(tmp_path):
    cache = AnswerCache(tmp_path / "answers.sqlite3", max_age_days=-1)
    cache.put("k", "RSI", gemini.Explanation(True, "text"))
    assert cache.get("k") is None
    cache = AnswerCache(tmp_path / "answers.sqlite3")
    cache.put("bad", "RSI", gemini.Explanation(False, "quota"))
    assert cache.get("bad") is None


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
