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
class UniverseSeedSample:
    seed: int
    sampled_groups: dict[str, list[str]] = field(default_factory=dict)
    random_tickers: list[str] = field(default_factory=list)
    all_tickers: list[str] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class UniverseSamplePlan:
    enabled: bool
    mode: str
    advisory_only: bool
    benchmark_groups: list[str]
    benchmark_tickers: list[str]
    eligible_groups: list[str]
    excluded_groups: list[str]
    etf_group_roles: dict[str, str]
    sample_per_group: int
    max_random_tickers: int
    seeds: list[int] = field(default_factory=list)
    seed_samples: list[UniverseSeedSample] = field(default_factory=list)

    def as_dict(self) -> dict[str, Any]:
        return {
            "enabled": self.enabled,
            "mode": self.mode,
            "advisory_only": self.advisory_only,
            "benchmark_groups": self.benchmark_groups,
            "benchmark_tickers": self.benchmark_tickers,
            "eligible_groups": self.eligible_groups,
            "excluded_groups": self.excluded_groups,
            "etf_group_roles": self.etf_group_roles,
            "sample_per_group": self.sample_per_group,
            "max_random_tickers": self.max_random_tickers,
            "seeds": self.seeds,
            "seed_samples": [sample.as_dict() for sample in self.seed_samples],
        }


@dataclass(frozen=True)
class CliError:
    error: str
    message: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)
