"""One call to Gemini: "explain this thing I selected".

``build_prompt`` is pure; ``explain`` is the only function that touches the
network, and it never raises -- the dashboard shows whatever message comes
back, so a dead key or a timeout reads as a sentence, not a stack trace.

Configuration (environment, or ``.env`` for a local run):
- ``GEMINI_API_KEY`` -- required; without it Explain is switched off.
- ``GEMINI_MODEL``   -- default ``gemini-flash-latest``, Google's alias for the
  newest Flash model, so a retired model id does not break the feature.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass

from lib.explain.glossary import glossary_text

logger = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-flash-latest"
TIMEOUT_SECONDS = 25

MAX_SELECTION_CHARS = 300
MAX_CONTEXT_CHARS = 600

INSTRUCTIONS = """\
You are the built-in help of a trading-research dashboard. The user selected or clicked something on screen and wants to know what it means.
Answer in English, in plain text (no markdown, no headings), at most 120 words.
If it is a number: say what it measures, how to read it, and whether this particular value is good, bad or typical — and why.
If it is a label, signal name or control: say what it is, what it is used for in this app, and what changes when the user turns it on or changes its value.
If it is an indicator or overlay: say what it measures, the parameters this app uses by default, and which Buy/Sell signals it can generate.
Use the app's own definitions below over textbook ones. If the context is not enough to be sure, say what it most likely is and what would confirm it.
This is research software, not financial advice; do not tell the user to buy or sell anything."""


def api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def is_configured() -> bool:
    return bool(api_key())


def _clip(text: str | None, limit: int) -> str:
    value = " ".join((text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def build_prompt(selection: str, context: str = "", ticker: str = "", page: str = "") -> str:
    parts = [
        INSTRUCTIONS,
        "",
        glossary_text(),
        "",
        "What is on screen:",
        f"- Page: {_clip(page, 60) or 'main workspace'}",
        f"- Symbol: {_clip(ticker, 20) or 'unknown'}",
        f"- Nearby label / surrounding text: {_clip(context, MAX_CONTEXT_CHARS) or 'none'}",
        "",
        f"Selected text: {_clip(selection, MAX_SELECTION_CHARS)}",
    ]
    return "\n".join(parts)


@dataclass(frozen=True)
class Explanation:
    ok: bool
    text: str


def _extract_text(payload: dict) -> str:
    for candidate in payload.get("candidates") or []:
        parts = ((candidate or {}).get("content") or {}).get("parts") or []
        text = "".join(p.get("text", "") for p in parts if isinstance(p, dict) and not p.get("thought"))
        if text.strip():
            return text.strip()
    return ""


def explain(selection: str, context: str = "", ticker: str = "", page: str = "", *, session=None) -> Explanation:
    """Ask Gemini. ``session`` is anything with ``.post`` (tests pass a fake)."""
    key = api_key()
    if not key:
        return Explanation(False, "Explain is not configured: GEMINI_API_KEY is not set.")
    if not (selection or "").strip():
        return Explanation(False, "Select a number or a word first.")
    body = {"contents": [{"role": "user", "parts": [{"text": build_prompt(selection, context, ticker, page)}]}]}
    try:
        if session is None:
            import requests as session
        response = session.post(
            API_URL.format(model=model_name()),
            json=body,
            headers={"x-goog-api-key": key, "Content-Type": "application/json"},
            timeout=TIMEOUT_SECONDS,
        )
    except Exception as exc:
        logger.warning("Gemini call failed: %s", type(exc).__name__)
        return Explanation(False, f"Could not reach Gemini ({type(exc).__name__}). Try again in a moment.")
    if response.status_code == 429:
        return Explanation(False, "Gemini quota or rate limit reached. Wait a minute and try again.")
    if response.status_code in (401, 403):
        return Explanation(False, "Gemini refused the API key (check GEMINI_API_KEY).")
    if response.status_code == 404:
        return Explanation(False, f"Gemini does not know the model '{model_name()}' (check GEMINI_MODEL).")
    if not 200 <= response.status_code < 300:
        # Google puts the reason in error.message (an invalid key is a 400, not a 401).
        try:
            reason = str(((response.json() or {}).get("error") or {}).get("message") or "")[:200]
        except (ValueError, AttributeError):
            reason = ""
        return Explanation(False, f"Gemini answered HTTP {response.status_code}" + (f": {reason}" if reason else "."))
    try:
        text = _extract_text(response.json())
    except ValueError:
        text = ""
    if not text:
        return Explanation(False, "Gemini returned no text (the answer may have been blocked).")
    return Explanation(True, text)
