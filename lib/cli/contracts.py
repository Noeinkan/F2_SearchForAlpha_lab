"""
JSON response contracts emitted by the sfa CLI.

These dataclasses are the source of truth for the shapes documented in
AGENTS.md. External agents parse them; do not change a field name without
updating AGENTS.md and the contract tests.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from typing import Any


@dataclass(frozen=True)
class StrategyEntry:
    name: str
    description: str
    buy_signals: list[str]
    sell_signals: list[str]
    live_params: dict[str, Any]
    last_promoted: str | None = None
    status: str = "idle"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategyList:
    strategies: list[StrategyEntry] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {"strategies": [s.as_dict() for s in self.strategies]}


@dataclass(frozen=True)
class StrategySweepFailure:
    strategy: str
    error: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class StrategySweep:
    ticker: str
    window_from: str
    window_to: str
    strategy_count: int
    success_count: int
    failure_count: int
    results: list[dict[str, Any]] = field(default_factory=list)
    failures: list[StrategySweepFailure] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "window": {"from": self.window_from, "to": self.window_to},
            "strategy_count": self.strategy_count,
            "success_count": self.success_count,
            "failure_count": self.failure_count,
            "results": self.results,
            "failures": [failure.as_dict() for failure in self.failures],
        }


@dataclass(frozen=True)
class CliError:
    error: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
