"""
Regime slicing — score one strategy separately in each historical market regime.

The calendar lives in ``config/regimes.yaml`` (twin of the RESEARCH.md table);
:mod:`lib.regimes.slicer` does the slicing and the pass/fail/inconclusive
verdict; :mod:`lib.regimes.runner` fetches data and scores an agent bundle.
"""

from lib.regimes.calendar import (
    DEFAULT_CALENDAR_PATH,
    Regime,
    RegimeCalendar,
    RegimeCalendarError,
    RegimeRule,
    load_calendar,
    parse_calendar,
)
from lib.regimes.slicer import (
    COVERAGE_FULL,
    COVERAGE_NONE,
    COVERAGE_PARTIAL,
    STATUS_FAIL,
    STATUS_INCONCLUSIVE,
    STATUS_PASS,
    RegimeVerdict,
    judge,
    score_regimes,
)

__all__ = [
    "COVERAGE_FULL",
    "COVERAGE_NONE",
    "COVERAGE_PARTIAL",
    "DEFAULT_CALENDAR_PATH",
    "STATUS_FAIL",
    "STATUS_INCONCLUSIVE",
    "STATUS_PASS",
    "Regime",
    "RegimeCalendar",
    "RegimeCalendarError",
    "RegimeRule",
    "RegimeVerdict",
    "judge",
    "load_calendar",
    "parse_calendar",
    "score_regimes",
]
