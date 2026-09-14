"""Demo limits. Every one is an environment variable with a default.

The container itself is also capped (``cpus`` and ``mem_limit`` in
``.deploy/compose.yml``), so these are about fairness between visitors: no one
visitor's optimiser run should stop the next visitor's backtest from starting.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, fields


def _int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


@dataclass(frozen=True)
class DemoSettings:
    # Visitors
    max_sessions: int = 60                 # DEMO_MAX_SESSIONS: dashboards held in memory at once
    session_idle_minutes: int = 30         # DEMO_SESSION_IDLE_MINUTES: idle visitor state is dropped after this
    # Per-run size caps
    max_combos: int = 150                  # DEMO_MAX_COMBOS: signal-combination search, combinations per run
    max_signals_per_side: int = 2          # DEMO_MAX_SIGNALS_PER_SIDE: signals stacked per side in that search
    max_grid_combos: int = 250             # DEMO_MAX_GRID_COMBOS: parameter grid search, combinations per run (~35 s on one core)
    max_bayes_trials: int = 30             # DEMO_MAX_BAYES_TRIALS: Bayesian sweep, trials per run
    optimizer_workers: int = 2             # DEMO_OPTIMIZER_WORKERS: threads the combination search shares
    # Concurrency
    max_concurrent_jobs: int = 2           # DEMO_MAX_CONCURRENT_JOBS: optimiser runs in flight, all visitors together
    job_timeout_seconds: int = 120         # DEMO_JOB_TIMEOUT_SECONDS: a run still going after this is stopped
    # Per-IP rate limits
    actions_per_ip_per_minute: int = 30    # DEMO_ACTIONS_PER_IP_PER_MINUTE: backtests, data and fundamentals loads
    jobs_per_ip_per_hour: int = 20         # DEMO_JOBS_PER_IP_PER_HOUR: optimiser runs started

    @classmethod
    def from_env(cls) -> "DemoSettings":
        values = {}
        for field in fields(cls):
            values[field.name] = _int(f"DEMO_{field.name.upper()}", field.default)
        return cls(**values)

    def as_manifest_limits(self) -> dict[str, int]:
        return {field.name: getattr(self, field.name) for field in fields(self)}
