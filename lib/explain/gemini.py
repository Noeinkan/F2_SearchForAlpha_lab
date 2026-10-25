"""One call to Gemini: "explain this thing I selected".

``build_prompt`` is pure; ``explain`` is the only function that touches the
network, and it never raises -- the dashboard shows whatever message comes
back, so a dead key or a timeout reads as a sentence, not a stack trace.

Configuration (environment, or ``.env`` for a local run):
- ``GEMINI_API_KEY`` -- required; without it Explain is switched off.
- ``GEMINI_MODEL``   -- default ``gemini-flash-latest``, Google's alias for the
  newest Flash model, so a retired model id does not break the feature.
- ``GEMINI_SEARCH``  -- ``0`` turns off Google Search grounding (the reference
  links under each answer). On by default.

With search on, Gemini runs a Google Search and returns its sources
(``groundingMetadata``). Google's terms for grounding require showing the
"Search Suggestions" it returns (``searchEntryPoint.renderedContent``, a small
HTML snippet of chips); the browser shows it in a sandboxed iframe.
"""

from __future__ import annotations

import hashlib
import logging
import os
import re
from dataclasses import dataclass

from lib.explain.glossary import glossary_for

logger = logging.getLogger(__name__)

API_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"
DEFAULT_MODEL = "gemini-flash-latest"
TIMEOUT_SECONDS = 60  # a grounded answer measured 18-26 s
MAX_SOURCES = 4
MAX_SUGGESTIONS_CHARS = 20_000

MAX_SELECTION_CHARS = 300
MAX_CONTEXT_CHARS = 600

INSTRUCTIONS = """\
You are the built-in help of a trading-research dashboard. The user selected or clicked something on screen and wants to know what it means.
Answer in English, at most 120 words (a formula line does not count).
Format, nothing else (no headings, no tables, no HTML, no LaTeX):
- one or two short sentences first, then up to 4 bullet lines starting with "- " when a list helps;
- **bold** for the one or two key terms, `backticks` for app names such as signal columns or metric keys;
- when a formula makes it clearer (a metric, an indicator), put it alone on its own line between $$ and $$, written in plain Unicode with the name on the left (e.g. $$Sharpe = (r̄ − r_f) ÷ σ × √N$$; use σ, √, Σ, ×, ÷, ≥, r_t — never backslash commands), and say in one line what each symbol is. No formula for plain controls.
If it is a number: say what it measures, how to read it, and whether this particular value is good, bad or typical — and why.
If it is a label, signal name or control: say what it is, what it is used for in this app, and what changes when the user turns it on or changes its value.
If it is an indicator or overlay: say what it measures, the parameters this app uses by default, and which Buy/Sell signals it can generate.
Use the app's own definitions below over textbook ones. If the context is not enough to be sure, say what it most likely is and what would confirm it.
This is research software, not financial advice; do not tell the user to buy or sell anything."""

SEARCH_INSTRUCTIONS = """\
Always run one Google Search for the general concept (not for this app) to find 2-3 reputable reference pages, such as Investopedia, StockCharts ChartSchool, CFA Institute or Wikipedia. Do not write links or a reference list in the answer; the sources are attached separately."""


def api_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def model_name() -> str:
    return os.environ.get("GEMINI_MODEL", "").strip() or DEFAULT_MODEL


def is_configured() -> bool:
    return bool(api_key())


def search_enabled() -> bool:
    return os.environ.get("GEMINI_SEARCH", "1").strip().lower() not in ("0", "false", "no", "off")


def _clip(text: str | None, limit: int) -> str:
    value = " ".join((text or "").split())
    return value if len(value) <= limit else value[: limit - 1] + "…"


def _section(page: str) -> str:
    """"/ticker/TSLA" -> "ticker": the kind of page, not which symbol it shows."""
    head = (page or "").strip("/").split("/", 1)[0]
    return _clip(head, 30) or "main workspace"


def build_prompt(selection: str, context: str = "", ticker: str = "", page: str = "") -> str:
    """The symbol goes in only for a number: a control or an indicator means the
    same on every ticker, so its prompt -- and its cache entry -- is shared."""
    selection, context = _clip(selection, MAX_SELECTION_CHARS), _clip(context, MAX_CONTEXT_CHARS)
    screen = [f"- Page: {_section(page)}"]
    if re.search(r"\d", selection):
        screen.append(f"- Symbol: {_clip(ticker, 20) or 'unknown'}")
    screen.append(f"- Nearby label / surrounding text: {context or 'none'}")
    parts = [
        INSTRUCTIONS,
        *([SEARCH_INSTRUCTIONS] if search_enabled() else []),
        "",
        glossary_for(selection, context),
        "",
        "What is on screen:",
        *screen,
        "",
        f"Selected text: {selection}",
    ]
    return "\n".join(parts)


def cache_key(selection: str, context: str = "", ticker: str = "", page: str = "") -> str:
    """Same model, same prompt -> same answer; a config change alters the prompt."""
    raw = "\n".join([model_name(), str(search_enabled()), build_prompt(selection, context, ticker, page)])
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


@dataclass(frozen=True)
class Source:
    title: str
    url: str


@dataclass(frozen=True)
class Explanation:
    ok: bool
    text: str
    sources: tuple[Source, ...] = ()
    suggestions: str = ""  # Google's Search Suggestions HTML, shown sandboxed


def _extract_sources(payload: dict) -> tuple[tuple[Source, ...], str]:
    for candidate in payload.get("candidates") or []:
        meta = (candidate or {}).get("groundingMetadata") or {}
        seen, sources = set(), []
        for chunk in meta.get("groundingChunks") or []:
            web = (chunk or {}).get("web") or {}
            url, title = str(web.get("uri") or ""), str(web.get("title") or "").strip()
            if not url.startswith("https://") or not title or title in seen:
                continue
            seen.add(title)
            sources.append(Source(title[:80], url))
            if len(sources) >= MAX_SOURCES:
                break
        html = str(((meta.get("searchEntryPoint") or {}).get("renderedContent")) or "")
        if sources or html:
            return tuple(sources), html if len(html) <= MAX_SUGGESTIONS_CHARS else ""
    return (), ""


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
    if search_enabled():
        body["tools"] = [{"google_search": {}}]
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
        payload = response.json()
        text = _extract_text(payload)
        sources, suggestions = _extract_sources(payload)
    except (ValueError, AttributeError):
        text = ""
    if not text:
        return Explanation(False, "Gemini returned no text (the answer may have been blocked).")
    return Explanation(True, text, sources, suggestions)
