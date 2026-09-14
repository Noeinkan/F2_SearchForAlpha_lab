"""
Load the market regime calendar from ``config/regimes.yaml``.

These are **calendar** regimes — named historical periods such as the 2022
bear — not the ADX/ATR regime indicators under ``lib/signals/``, which classify
each bar from price action.
"""

from __future__ import annotations

from dataclasses import dataclass, fields
from datetime import date, datetime
from pathlib import Path
from typing import Any

import yaml

from lib.metrics import BacktestMetrics

DEFAULT_CALENDAR_PATH = Path(__file__).resolve().parents[2] / "config" / "regimes.yaml"

_METRIC_FIELDS = frozenset(f.name for f in fields(BacktestMetrics))


class RegimeCalendarError(ValueError):
    """Raised when ``regimes.yaml`` is malformed."""


@dataclass(frozen=True)
class Regime:
    id: str
    label: str
    character: str
    start: date
    end: date | None  # inclusive; None = up to today

    def resolved_end(self, today: date) -> date:
        return self.end if self.end is not None else today


@dataclass(frozen=True)
class RegimeRule:
    metric: str = "sortino"
    threshold: float = 0.0
    min_passing: int = 3
    required: tuple[str, ...] = ()

    def as_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "threshold": self.threshold,
            "min_passing": self.min_passing,
            "required": list(self.required),
        }


@dataclass(frozen=True)
class RegimeCalendar:
    regimes: tuple[Regime, ...]
    rule: RegimeRule
    coverage_grace_days: int = 7

    @property
    def earliest_start(self) -> date:
        return min(r.start for r in self.regimes)


def _as_date(value: Any, *, where: str) -> date:
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    try:
        return datetime.strptime(str(value), "%Y-%m-%d").date()
    except ValueError as exc:
        raise RegimeCalendarError(f"{where}: {value!r} is not a YYYY-MM-DD date") from exc


def parse_calendar(raw: dict[str, Any]) -> RegimeCalendar:
    """Build a calendar from the YAML mapping, validating as it goes."""
    entries = raw.get("regimes") or []
    if not entries:
        raise RegimeCalendarError("regimes.yaml defines no regimes")

    regimes: list[Regime] = []
    for i, entry in enumerate(entries):
        where = f"regimes[{i}]"
        rid = str(entry.get("id") or "").strip()
        if not rid:
            raise RegimeCalendarError(f"{where}: missing id")
        start = _as_date(entry.get("from"), where=f"{where}.from")
        end = None if entry.get("to") is None else _as_date(entry["to"], where=f"{where}.to")
        if end is not None and end < start:
            raise RegimeCalendarError(f"{where}: to {end} is before from {start}")
        regimes.append(
            Regime(
                id=rid,
                label=str(entry.get("label") or rid),
                character=str(entry.get("character") or ""),
                start=start,
                end=end,
            )
        )

    ids = [r.id for r in regimes]
    if len(set(ids)) != len(ids):
        raise RegimeCalendarError(f"duplicate regime ids in {ids}")

    rule_raw = raw.get("rule") or {}
    rule = RegimeRule(
        metric=str(rule_raw.get("metric", "sortino")),
        threshold=float(rule_raw.get("threshold", 0.0)),
        min_passing=int(rule_raw.get("min_passing", 3)),
        required=tuple(str(r) for r in (rule_raw.get("required") or [])),
    )
    if rule.metric not in _METRIC_FIELDS:
        raise RegimeCalendarError(f"rule.metric {rule.metric!r} is not a BacktestMetrics field")
    unknown = [r for r in rule.required if r not in ids]
    if unknown:
        raise RegimeCalendarError(f"rule.required names unknown regimes: {unknown}")

    return RegimeCalendar(
        regimes=tuple(regimes),
        rule=rule,
        coverage_grace_days=int(raw.get("coverage_grace_days", 7)),
    )


def load_calendar(path: Path | None = None) -> RegimeCalendar:
    with open(path or DEFAULT_CALENDAR_PATH, encoding="utf-8") as fh:
        return parse_calendar(yaml.safe_load(fh) or {})
