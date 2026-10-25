"""Flask routes behind the Explain popover and the header's account links.

``GET /api/session`` tells the browser who it is (hosted only), whether it is
admin, and whether Explain is on. ``assets/95-explain.js`` reads it once on
load: no Explain button unless ``explain`` is true, and the account links
(Users, Sign out) only on the hosted site.

``POST /api/explain`` is admin-only and answers 404 to anyone else, the demo
included. It takes JSON and needs the ``X-SFA-Explain`` header: a browser
will not send a custom header cross-site without a CORS pre-flight this server
never approves, so another page cannot spend the Gemini quota with the
owner's cookie. Calls to Gemini are capped per user per minute; an answer
already in the cache (``lib/explain/cache.py``) is free and not counted.
``"fresh": true`` in the body skips the cache and replaces the entry -- the
popover's Refresh button.

``"part"`` picks which of the two calls in ``lib/explain/gemini.py`` to make:
``"answer"`` (default, the text) or ``"sources"`` (the Google Search links).
The browser asks for both at once and shows the text as soon as it lands.
Each part has its own cache entry and its own per-minute limit, so one click
counts once against each.
"""

from __future__ import annotations

import logging
import threading
import time
from collections import deque

from flask import Flask, abort, jsonify, request

from lib.dash import auth_context
from lib.explain import gemini

logger = logging.getLogger(__name__)

HEADER = "X-SFA-Explain"
REQUESTS_PER_MINUTE = 20


class _Limiter:
    def __init__(self, per_minute: int) -> None:
        self.per_minute = per_minute
        self._hits: dict[str, deque] = {}
        self._lock = threading.Lock()

    def allow(self, key: str) -> bool:
        now = time.monotonic()
        with self._lock:
            hits = self._hits.setdefault(key, deque())
            while hits and now - hits[0] > 60:
                hits.popleft()
            if len(hits) >= self.per_minute:
                return False
            hits.append(now)
            return True


def explain_enabled() -> bool:
    return auth_context.is_admin() and gemini.is_configured()


def _payload(answer: gemini.Explanation, cached_at: float | None = None) -> dict:
    return {
        "ok": answer.ok,
        "text": answer.text,
        "sources": [{"title": s.title, "url": s.url} for s in answer.sources],
        "suggestions": answer.suggestions,
        "cached": cached_at is not None,
        "cached_at": cached_at,
    }


def install_explain_routes(server: Flask, *, explain=None, sources=None, cache=None) -> None:
    """``explain`` / ``sources`` replace ``gemini.explain`` / ``gemini.find_sources``
    and ``cache`` the on-disk ``AnswerCache`` (tests). The real cache is opened
    on the first question, so the demo, where Explain is off, never creates the file."""
    calls = {
        "answer": explain or gemini.explain,
        "sources": sources or (lambda selection, context, ticker, page: gemini.find_sources(selection, context)),
    }
    limiters = {part: _Limiter(REQUESTS_PER_MINUTE) for part in gemini.PARTS}
    store = {"cache": cache}

    def answers():
        if store["cache"] is None:
            try:
                from lib.explain.cache import AnswerCache

                store["cache"] = AnswerCache.from_env()
            except Exception:
                logger.warning("Explain cache unavailable; answering without it", exc_info=True)
                store["cache"] = False
        return store["cache"] or None

    @server.route("/api/session", methods=["GET"])
    def sfa_session_info():
        response = jsonify(
            mode=auth_context.auth_mode(),
            email=auth_context.current_email(),
            admin=auth_context.is_admin(),
            explain=explain_enabled(),
            sources=explain_enabled() and gemini.search_enabled(),
        )
        response.headers["Cache-Control"] = "no-store"
        return response

    @server.route("/api/explain", methods=["POST"])
    def sfa_explain():
        if not auth_context.is_admin():
            abort(404)
        if request.headers.get(HEADER) != "1" or not request.is_json:
            abort(400)
        if not gemini.is_configured():
            return jsonify(ok=False, text="Explain is not configured: GEMINI_API_KEY is not set."), 503
        data = request.get_json(silent=True) or {}
        selection = str(data.get("selection") or "")
        if not selection.strip():
            return jsonify(ok=False, text="Select a number or a word first."), 400
        if len(selection) > gemini.MAX_SELECTION_CHARS:
            return jsonify(ok=False, text=f"Select at most {gemini.MAX_SELECTION_CHARS} characters."), 400
        part = str(data.get("part") or "answer")
        if part not in gemini.PARTS:
            return jsonify(ok=False, text="Unknown part."), 400
        question = (
            selection,
            str(data.get("context") or "")[: gemini.MAX_CONTEXT_CHARS],
            str(data.get("ticker") or "")[:20],
            str(data.get("page") or "")[:60],
        )
        cache = answers()
        key = gemini.cache_key(*question, part=part) if cache else ""
        hit = cache.get(key) if cache and not data.get("fresh") else None
        if hit:
            body = _payload(*hit)
        else:
            # Only a real call to Gemini counts against the limit.
            who = auth_context.current_email() or request.remote_addr or "local"
            if not limiters[part].allow(who):
                return jsonify(ok=False, text=f"Slow down: at most {REQUESTS_PER_MINUTE} explanations a minute."), 429
            result = calls[part](*question)
            if cache and result.ok:
                cache.put(key, selection, result)
            body = _payload(result)
        response = jsonify(body)
        response.headers["Cache-Control"] = "no-store"
        return response
