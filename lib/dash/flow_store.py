"""Per-ticker Flow Scanner reports on disk, and the one way to (re)write them.

Until ROADMAP 6.8 every scan overwrote a single ``flow_report.json``, so
``/flow/AAPL`` showed whatever had been scanned last, whichever ticker that
was. Reports now live one file per ticker under ``state/flow/``, which lets the
scheduled refresh (``lib/dash/flow_refresh.py``) and the RESCAN button write
side by side without clobbering each other.

A failed scan never replaces a good report. The scanner writes into
``state/flow/.partial/`` first, and the result is promoted only when it carries
data, or when there is no earlier report to lose -- so a rate-limited refresh
leaves the last good chain on screen instead of an error card.
"""

from __future__ import annotations

import json
import logging
import os
import threading
import uuid
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable
from urllib.parse import quote, unquote

from scripts.flow_runner import run_flow_scan

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
# Module attribute, not a constant baked into paths at import: tests and the
# public demo point it elsewhere.
FLOW_DIR = REPO_ROOT / "state" / "flow"

_locks: dict[str, threading.Lock] = {}
_locks_guard = threading.Lock()


def normalize_ticker(ticker: Any) -> str:
    return str(ticker or "").strip().upper()


def _stem(ticker: str) -> str:
    # Percent-encoding keeps index and futures symbols (^SPX, ES=F) reversible
    # and turns anything path-like into a plain file name.
    return quote(normalize_ticker(ticker), safe="")


def json_path(ticker: str) -> Path:
    return FLOW_DIR / f"{_stem(ticker)}.json"


def html_path(ticker: str) -> Path:
    return FLOW_DIR / f"{_stem(ticker)}.html"


def _read_json(path: Path) -> dict | None:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except (OSError, json.JSONDecodeError):
        return None
    return data if isinstance(data, dict) else None


def load_report(ticker: str) -> dict | None:
    """The stored payload for ``ticker`` (``{"generated_at", "reports": [...]}``), if any."""
    if not normalize_ticker(ticker):
        return None
    return _read_json(json_path(ticker))


def stored_tickers() -> list[str]:
    """Tickers that have a stored report, oldest report first."""
    if not FLOW_DIR.is_dir():
        return []
    files = sorted(FLOW_DIR.glob("*.json"), key=lambda p: p.stat().st_mtime)
    return [unquote(p.stem) for p in files]


def stored_at(ticker: str) -> datetime | None:
    """When the stored report was last written (timezone-aware, from the file's mtime)."""
    try:
        mtime = json_path(ticker).stat().st_mtime
    except OSError:
        return None
    return datetime.fromtimestamp(mtime).astimezone()


def report_error(payload: dict | None) -> tuple[str | None, str | None]:
    """``(error_kind, error)`` of the payload's report; ``(None, None)`` when it has data."""
    reports = (payload or {}).get("reports") or []
    if not reports:
        return "error", "Scanner produced no report"
    first = reports[0]
    if not first.get("error"):
        return None, None
    return first.get("error_kind") or "error", str(first["error"])


@dataclass
class ScanOutcome:
    ticker: str
    # The store now holds this scan's result.
    promoted: bool
    # None on success; "rate_limited" / "error" from the report, "scan_failed"
    # when the scanner process itself failed.
    error_kind: str | None
    message: str
    # What the store holds for the ticker after the scan -- new or kept.
    payload: dict | None


def _lock_for(ticker: str) -> threading.Lock:
    with _locks_guard:
        return _locks.setdefault(ticker, threading.Lock())


def scan_into_store(
    ticker: str,
    *,
    blocking: bool = True,
    runner: Callable[..., tuple[int, str]] | None = None,
) -> ScanOutcome | None:
    """Scan ``ticker`` and promote the result into the store if it is worth keeping.

    Returns ``None`` only when ``blocking`` is false and another scan of the
    same ticker is already running.
    """
    symbol = normalize_ticker(ticker)
    lock = _lock_for(symbol)
    if not lock.acquire(blocking=blocking):
        return None
    try:
        return _scan_locked(symbol, runner or run_flow_scan)
    finally:
        lock.release()


def _scan_locked(symbol: str, runner: Callable[..., tuple[int, str]]) -> ScanOutcome:
    partial = FLOW_DIR / ".partial"
    partial.mkdir(parents=True, exist_ok=True)
    token = uuid.uuid4().hex
    tmp_json = partial / f"{_stem(symbol)}.{token}.json"
    tmp_html = partial / f"{_stem(symbol)}.{token}.html"
    try:
        rc, tail = runner([symbol], tmp_html, json_path=tmp_json, quiet=True)
        if rc != 0:
            return ScanOutcome(symbol, False, "scan_failed", f"Scan failed (rc={rc}): {tail}", load_report(symbol))

        fresh = _read_json(tmp_json)
        if fresh is None:
            return ScanOutcome(symbol, False, "scan_failed", "Scanner wrote no JSON report", load_report(symbol))
        error_kind, error = report_error(fresh)
        final_json = json_path(symbol)
        if error_kind is not None and final_json.exists():
            logger.info("Flow scan of %s failed (%s); keeping the stored report", symbol, error)
            return ScanOutcome(symbol, False, error_kind, error or "", load_report(symbol))

        os.replace(tmp_json, final_json)
        if tmp_html.exists():
            os.replace(tmp_html, html_path(symbol))
        return ScanOutcome(symbol, True, error_kind, error or "", fresh)
    finally:
        for leftover in (tmp_json, tmp_html):
            try:
                leftover.unlink()
            except OSError:
                pass
