"""
Slice an enriched tape into calendar regimes and score each one.

Each regime is backtested **on its own**: flat at its first bar, fresh capital,
metrics from that slice only. A position carried in from the previous regime
would otherwise let one period's trade be scored in another. Indicators and
signals are computed once over the whole tape *before* slicing, so the first
bars of a regime see a warmed-up indicator instead of a cold start.

A regime is **counted** toward the verdict only when the data reaches both of
its ends. Yahoo intraday history stops ~728 days back and young tickers start
mid-calendar, so an uncovered regime is reported but never scored as a pass or
a fail — an unknown is not a failure.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime, timedelta
from typing import Any

import pandas as pd

from lib.regimes.calendar import Regime, RegimeCalendar, RegimeRule

ScoreFn = Callable[[pd.DataFrame], dict[str, Any]]

COVERAGE_FULL = "full"
COVERAGE_PARTIAL = "partial"
COVERAGE_NONE = "none"

STATUS_PASS = "pass"
STATUS_FAIL = "fail"
STATUS_INCONCLUSIVE = "inconclusive"

# A slice shorter than this cannot produce a return series.
_MIN_SCORABLE_BARS = 2


@dataclass(frozen=True)
class RegimeVerdict:
    status: str
    passing: int
    evaluated: int
    total: int
    min_passing: int
    required_passed: bool | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _bar_date(ts: Any) -> date:
    if isinstance(ts, datetime):
        return ts.date()
    if isinstance(ts, date):
        return ts
    return pd.Timestamp(ts).date()


def slice_regime(df: pd.DataFrame, regime: Regime, today: date) -> pd.DataFrame:
    """Rows whose bar date falls inside the regime, both ends inclusive."""
    if df.empty:
        return df
    lo = pd.Timestamp(regime.start)
    hi = pd.Timestamp(regime.resolved_end(today) + timedelta(days=1))
    index = pd.DatetimeIndex(df.index)
    return df[(index >= lo) & (index < hi)]


def coverage_of(
    slice_df: pd.DataFrame,
    regime: Regime,
    *,
    today: date,
    grace_days: int,
) -> str:
    if slice_df.empty:
        return COVERAGE_NONE
    grace = timedelta(days=grace_days)
    first = _bar_date(slice_df.index[0])
    last = _bar_date(slice_df.index[-1])
    end = min(regime.resolved_end(today), today)
    if first <= regime.start + grace and last >= end - grace:
        return COVERAGE_FULL
    return COVERAGE_PARTIAL


def judge(rows: list[dict[str, Any]], rule: RegimeRule) -> RegimeVerdict:
    """Apply the rule to scored regime rows.

    ``pass``         — at least ``min_passing`` counted regimes beat the
                       threshold, and every required regime is among them.
    ``fail``         — a required regime was counted and missed, or too few
                       passed even if every uncounted regime would have passed.
    ``inconclusive`` — the uncounted regimes could still flip the answer.
    """
    total = len(rows)
    counted = [r for r in rows if r["counted"]]
    passed_ids = {r["id"] for r in counted if r["passed"]}
    counted_ids = {r["id"] for r in counted}
    labels = {r["id"]: r["label"] for r in rows}
    uncounted = total - len(counted)
    n_pass = len(passed_ids)

    required_failing = [rid for rid in rule.required if rid in counted_ids and rid not in passed_ids]
    required_missing = [rid for rid in rule.required if rid not in counted_ids]
    required_passed: bool | None
    if not rule.required:
        required_passed = None
    elif required_failing:
        required_passed = False
    elif required_missing:
        required_passed = None
    else:
        required_passed = True

    metric = rule.metric
    head = f"{metric} > {rule.threshold:g} in {n_pass}/{len(counted)} regimes with full data"
    bits = [head]
    if uncounted:
        bits.append(f"{uncounted} of {total} regimes lack full data")

    if required_failing:
        status = STATUS_FAIL
        bits.append("missed required: " + ", ".join(labels[r] for r in required_failing))
    elif n_pass >= rule.min_passing and not required_missing:
        status = STATUS_PASS
    elif required_missing or n_pass + uncounted >= rule.min_passing:
        status = STATUS_INCONCLUSIVE
        if required_missing:
            bits.append("no full data for required: " + ", ".join(labels[r] for r in required_missing))
        else:
            bits.append(f"needs {rule.min_passing}, uncovered regimes could still decide it")
    else:
        status = STATUS_FAIL
        bits.append(f"needs {rule.min_passing}")

    return RegimeVerdict(
        status=status,
        passing=n_pass,
        evaluated=len(counted),
        total=total,
        min_passing=rule.min_passing,
        required_passed=required_passed,
        reason="; ".join(bits),
    )


def score_regimes(
    enriched: pd.DataFrame,
    *,
    calendar: RegimeCalendar,
    score: ScoreFn,
    today: date,
) -> dict[str, Any]:
    """Score every regime and judge the set.

    ``enriched`` carries indicators and signal columns over the whole calendar
    span; ``score`` backtests one slice and returns a ``BacktestMetrics``
    dict. Returns ``{"regimes": [...], "verdict": {...}, "rule": {...}}``.
    """
    rule = calendar.rule
    rows: list[dict[str, Any]] = []
    for regime in calendar.regimes:
        slice_df = slice_regime(enriched, regime, today)
        coverage = coverage_of(
            slice_df, regime, today=today, grace_days=calendar.coverage_grace_days
        )
        metrics = score(slice_df) if len(slice_df) >= _MIN_SCORABLE_BARS else None
        counted = coverage == COVERAGE_FULL and metrics is not None
        passed = bool(float(metrics[rule.metric]) > rule.threshold) if counted else None
        rows.append(
            {
                "id": regime.id,
                "label": regime.label,
                "character": regime.character,
                "from": regime.start.isoformat(),
                "to": regime.resolved_end(today).isoformat(),
                "open_ended": regime.end is None,
                "coverage": coverage,
                "bars": int(len(slice_df)),
                "counted": counted,
                "passed": passed,
                "metrics": metrics,
            }
        )

    return {
        "rule": rule.as_dict(),
        "regimes": rows,
        "verdict": judge(rows, rule).as_dict(),
    }
