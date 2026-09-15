"""Quick swap: run one test across many symbols without the test drifting.

The Backtest panel's quick-swap strip moves through the active watchlist. A swap
changes only the symbol: the test window is held (``held_window``), the backtest
re-runs by itself once the new data has loaded, and every run lands as a row in
a comparison table. This module is the Dash-free half — which symbol comes next,
what counts as "the same test", and how rows are kept.

"The same test" is a fingerprint of every input that shapes a result except the
symbol (``conditions_key``). Rows sharing a fingerprint get the same letter in
the table, so a run made after someone nudged a stop shows up as test B instead
of passing for a like-for-like comparison.
"""

from __future__ import annotations

import hashlib
import json
import math
from typing import Any, Iterable

import pandas as pd

# Newest rows first; older ones fall off past this.
MAX_COMPARE_ROWS = 40

# A held window counts as covered when the symbol's bars start and end within
# this many calendar days of it. Wide enough for a long weekend or a holiday
# week, narrow enough that a listing a month short is flagged.
COVERAGE_TOLERANCE_DAYS = 7

# The metrics a comparison row keeps, all in canonical units (lib/metrics).
ROW_METRICS = ('total_return', 'benchmark_return', 'sharpe', 'max_drawdown', 'num_trades')


def neighbour_symbol(symbols: Iterable[str], current: str | None, step: int) -> str | None:
    """The symbol ``step`` places from ``current`` in ``symbols``, wrapping around.

    A current symbol that is not on the list starts from the edge: next goes to
    the first symbol, previous to the last.
    """
    ordered = [str(s).strip().upper() for s in symbols if str(s or '').strip()]
    if not ordered:
        return None
    here = str(current or '').strip().upper()
    if here not in ordered:
        return ordered[0] if step > 0 else ordered[-1]
    return ordered[(ordered.index(here) + step) % len(ordered)]


def held_window(start: Any, end: Any, first: str, last: str) -> tuple[str, str]:
    """Keep a swapped-in test window exactly as it was, if the new data reaches it.

    Unlike a restored preset, which is clamped to the loaded bars, a swap keeps
    the dates untouched so every symbol is asked the same question; a symbol
    with shorter history simply has fewer bars inside it, and its row says so.
    Only a window the data does not overlap at all falls back to the full range,
    since that would otherwise measure nothing.
    """
    try:
        start_ts = pd.Timestamp(str(start)[:10])
        end_ts = pd.Timestamp(str(end)[:10])
    except (TypeError, ValueError):
        return first, last
    if start_ts >= end_ts or end_ts < pd.Timestamp(first) or start_ts > pd.Timestamp(last):
        return first, last
    return start_ts.date().isoformat(), end_ts.date().isoformat()


def window_short(requested_start: Any, requested_end: Any, df: pd.DataFrame) -> bool:
    """True when the evaluated bars miss a real part of the requested window."""
    if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return False
    tolerance = pd.Timedelta(days=COVERAGE_TOLERANCE_DAYS)
    first_bar = df.index.min().normalize()
    last_bar = df.index.max().normalize()
    try:
        if requested_start and first_bar - pd.Timestamp(str(requested_start)[:10]) > tolerance:
            return True
        if requested_end and pd.Timestamp(str(requested_end)[:10]) - last_bar > tolerance:
            return True
    except (TypeError, ValueError):
        return False
    return False


def conditions_key(conditions: dict) -> str:
    """Short, stable fingerprint of a test's inputs. Order of keys and of signal lists is ignored."""
    normalised = dict(conditions)
    for side in ('buy_signals', 'sell_signals'):
        if side in normalised:
            normalised[side] = sorted(normalised[side] or [])
    blob = json.dumps(normalised, sort_keys=True, default=str)
    return hashlib.sha1(blob.encode('utf-8')).hexdigest()[:10]


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def build_row(
    *,
    symbol: str,
    interval: str,
    key: str,
    window_label: str,
    bars: int,
    short: bool,
    metrics: dict,
) -> dict:
    """One comparison row. Non-finite metrics become ``None`` so the store stays valid JSON."""
    row = {
        'symbol': str(symbol or '').upper(),
        'interval': interval,
        'key': key,
        'window': window_label,
        'bars': int(bars),
        'short': bool(short),
    }
    for name in ROW_METRICS:
        row[name] = _finite(metrics.get(name))
    return row


def upsert_row(rows: list | None, row: dict, limit: int = MAX_COMPARE_ROWS) -> list:
    """Put ``row`` first, replacing an earlier run of the same symbol, interval and test."""
    identity = (row['symbol'], row['interval'], row['key'])
    kept = [
        existing for existing in (rows or [])
        if (existing.get('symbol'), existing.get('interval'), existing.get('key')) != identity
    ]
    return [row, *kept][:limit]


def condition_tags(rows: list | None) -> dict[str, str]:
    """Letter per fingerprint, in the order the tests were first run: A, B, C…"""
    tags: dict[str, str] = {}
    for row in reversed(rows or []):
        key = row.get('key')
        if key and key not in tags:
            n = len(tags)
            tags[key] = chr(ord('A') + n) if n < 26 else f"T{n + 1}"
    return tags
