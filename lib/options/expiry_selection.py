"""Choose a small set of option expiries across useful time horizons."""

from __future__ import annotations

from calendar import monthrange
from datetime import date, timedelta
from typing import Iterable

HORIZONS = (("2 settimane", 0), ("1 mese", 1), ("3 mesi", 3), ("6 mesi", 6), ("12 mesi", 12))


def add_months(day: date, months: int) -> date:
    month_index = day.year * 12 + day.month - 1 + months
    year, month_zero = divmod(month_index, 12)
    month = month_zero + 1
    return date(year, month, min(day.day, monthrange(year, month)[1]))


def horizon_target(day: date, months: int) -> date:
    return day + timedelta(days=14) if months == 0 else add_months(day, months)


def available_dates(expiries: Iterable[str], today: date) -> list[str]:
    dated = []
    for expiry in expiries:
        try:
            day = date.fromisoformat(str(expiry)[:10])
        except ValueError:
            continue
        if day >= today:
            dated.append((day, str(expiry)))
    return [key for _, key in sorted(dated)]


def closest_expiry(expiries: Iterable[str], target: date) -> str | None:
    dated = []
    for expiry in expiries:
        try:
            day = date.fromisoformat(str(expiry)[:10])
        except ValueError:
            continue
        dated.append((abs((day - target).days), day, str(expiry)))
    return min(dated)[2] if dated else None


def flow_expiries(expiries: Iterable[str], today: date) -> list[str]:
    """Keep this week's dates and one listed expiry near each horizon."""
    future = available_dates(expiries, today)
    week = [key for key in future if (date.fromisoformat(key[:10]) - today).days <= 7]
    chosen = set(week or future[:3])
    for _, months in HORIZONS:
        nearest = closest_expiry(future, horizon_target(today, months))
        if nearest:
            chosen.add(nearest)
    return sorted(chosen)
