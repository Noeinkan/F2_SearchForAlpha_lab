"""Flask routes behind the Explain popover and the header's account links.

``GET /api/session`` tells the browser who it is (hosted only), whether it is
admin, and whether Explain is on. ``assets/95-explain.js`` reads it once on
load: no Explain button unless ``explain`` is true, and the account links
(Users, Sign out) only on the hosted site.

``POST /api/explain`` is admin-only and answers 404 to anyone else, the demo
included. It takes JSON and needs the ``X-SFA-Explain`` header: a browser
will not send a custom header cross-site without a CORS pre-flight this server
never approves, so another page cannot spend the Gemini quota with the
owner's cookie. Requests are capped per user per minute.
"""

from __future__ import annotations

import threading
import time
from collections import deque

from flask import Flask, abort, jsonify, request

from lib.dash import auth_context
from lib.explain import gemini

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


def install_explain_routes(server: Flask, *, explain=None) -> None:
    """``explain`` replaces ``gemini.explain`` (tests)."""
    ask = explain or gemini.explain
    limiter = _Limiter(REQUESTS_PER_MINUTE)

    @server.route("/api/session", methods=["GET"])
    def sfa_session_info():
        response = jsonify(
            mode=auth_context.auth_mode(),
            email=auth_context.current_email(),
            admin=auth_context.is_admin(),
            explain=explain_enabled(),
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
        who = auth_context.current_email() or request.remote_addr or "local"
        if not limiter.allow(who):
            return jsonify(ok=False, text=f"Slow down: at most {REQUESTS_PER_MINUTE} explanations a minute."), 429
        data = request.get_json(silent=True) or {}
        selection = str(data.get("selection") or "")
        if not selection.strip():
            return jsonify(ok=False, text="Select a number or a word first."), 400
        if len(selection) > gemini.MAX_SELECTION_CHARS:
            return jsonify(ok=False, text=f"Select at most {gemini.MAX_SELECTION_CHARS} characters."), 400
        result = ask(
            selection,
            str(data.get("context") or "")[: gemini.MAX_CONTEXT_CHARS],
            str(data.get("ticker") or "")[:20],
            str(data.get("page") or "")[:60],
        )
        response = jsonify(ok=result.ok, text=result.text)
        response.headers["Cache-Control"] = "no-store"
        return response
