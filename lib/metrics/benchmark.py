"""Benchmark-relative metrics — the strategy measured against buy-and-hold.

The benchmark is the symbol's own per-bar return series, ``Returns``, which
``lib.strategy.backtest`` has always written onto the result frame and nothing
ever read. Holding the symbol over the same window, with the same bars, is the
only benchmark that needs no second fetch and no alignment step.

Conventions follow :mod:`lib.metrics.core`: rates are fractions, ratios
annualise at ``periods_per_year``, standard deviations use ``ddof=1``, and an
undefined quantity is ``0.0`` rather than NaN.

Two of these are easy to confuse, so they are named apart:

``excess_return``
    Strategy total return minus benchmark total return over the window. An
    arithmetic difference in percentage points — no risk adjustment at all.
    This is what the combo-search leaderboard used to call "alpha".
``alpha``
    Annualised **Jensen's alpha**: the part of the strategy's excess return
    that its beta to the benchmark does *not* explain. A strategy that is
    simply levered long earns excess return with zero alpha.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

import numpy as np

from lib.metrics.core import _clean, resolve_risk_free_rate


def _aligned(returns: Any, benchmark: Any) -> tuple[np.ndarray, np.ndarray]:
    """Two finite float arrays of equal length, truncated to the shorter one."""
    r = _clean(returns)
    b = _clean(benchmark)
    n = min(r.size, b.size)
    if n == 0:
        empty = np.empty(0, dtype=float)
        return empty, empty
    return r[:n], b[:n]


def compound_return(returns: Any) -> float:
    """Total fractional growth implied by a per-bar return series.

    Bars worse than -100% are clamped: an equity curve cannot go below zero,
    and without the clamp a single bad bar makes the product change sign.
    """
    r = _clean(returns)
    if r.size == 0:
        return 0.0
    growth = float(np.prod(np.maximum(1.0 + r, 0.0)))
    return growth - 1.0


def beta(returns: Any, benchmark: Any) -> float:
    """Sensitivity of strategy returns to benchmark returns, by OLS slope."""
    r, b = _aligned(returns, benchmark)
    if r.size < 2:
        return 0.0
    var = float(b.var(ddof=1))
    if not np.isfinite(var) or var <= 0:
        return 0.0
    cov = float(np.cov(r, b, ddof=1)[0, 1])
    return float(cov / var) if np.isfinite(cov) else 0.0


def alpha(
    returns: Any,
    benchmark: Any,
    *,
    periods_per_year: int,
    risk_free_rate: Optional[float] = None,
    beta_value: Optional[float] = None,
) -> float:
    """Annualised Jensen's alpha, as a fraction.

    ``mean(excess strategy) - beta * mean(excess benchmark)``, scaled by
    ``periods_per_year``. Arithmetic annualisation, which is the convention
    Jensen's alpha is quoted in — it is a per-bar intercept, not a growth rate.
    """
    r, b = _aligned(returns, benchmark)
    if r.size < 2:
        return 0.0
    ppy = max(1, int(periods_per_year))
    per_bar_rf = resolve_risk_free_rate(risk_free_rate) / ppy
    slope = beta(r, b) if beta_value is None else float(beta_value)
    intercept = float((r - per_bar_rf).mean() - slope * (b - per_bar_rf).mean())
    return float(intercept * ppy) if np.isfinite(intercept) else 0.0


def tracking_error(returns: Any, benchmark: Any, *, periods_per_year: int) -> float:
    """Annualised standard deviation of the active return, as a fraction."""
    r, b = _aligned(returns, benchmark)
    if r.size < 2:
        return 0.0
    std = float((r - b).std(ddof=1))
    if not np.isfinite(std) or std <= 0:
        return 0.0
    return float(np.sqrt(max(1, int(periods_per_year))) * std)


def information_ratio(returns: Any, benchmark: Any, *, periods_per_year: int) -> float:
    """Annualised mean active return over its tracking error."""
    r, b = _aligned(returns, benchmark)
    if r.size < 2:
        return 0.0
    active = r - b
    std = float(active.std(ddof=1))
    if not np.isfinite(std) or std <= 0:
        return 0.0
    ppy = max(1, int(periods_per_year))
    return float(np.sqrt(ppy) * active.mean() / std)


def _capture(r: np.ndarray, b: np.ndarray, mask: np.ndarray) -> float:
    """Geometric-mean return ratio over the bars *mask* selects."""
    k = int(mask.sum())
    if k < 1:
        return 0.0
    strat = float(np.prod(np.maximum(1.0 + r[mask], 0.0)) ** (1.0 / k) - 1.0)
    bench = float(np.prod(np.maximum(1.0 + b[mask], 0.0)) ** (1.0 / k) - 1.0)
    if not np.isfinite(strat) or not np.isfinite(bench) or bench == 0.0:
        return 0.0
    return float(strat / bench)


def up_capture(returns: Any, benchmark: Any) -> float:
    """Share of the benchmark's gain the strategy captured on its up bars.

    ``1.0`` means it matched the benchmark when the benchmark rose; below 1
    means it lagged. A strategy sitting in cash through the rally reports ``0``.
    """
    r, b = _aligned(returns, benchmark)
    if r.size == 0:
        return 0.0
    return _capture(r, b, b > 0)


def down_capture(returns: Any, benchmark: Any) -> float:
    """Share of the benchmark's loss the strategy took on its down bars.

    Both legs are negative, so the ratio is positive: below 1 means the
    strategy lost less than the benchmark did, which is the good direction.
    A negative value means the strategy *made* money while the benchmark fell.
    """
    r, b = _aligned(returns, benchmark)
    if r.size == 0:
        return 0.0
    return _capture(r, b, b < 0)


@dataclass(frozen=True)
class BenchmarkStats:
    """Everything :func:`benchmark_stats` computes, in canonical units."""

    benchmark_return: float = 0.0
    excess_return: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    information_ratio: float = 0.0
    tracking_error: float = 0.0
    up_capture: float = 0.0
    down_capture: float = 0.0


def benchmark_stats(
    returns: Any,
    benchmark: Any,
    *,
    periods_per_year: int,
    strategy_total_return: Optional[float] = None,
    risk_free_rate: Optional[float] = None,
) -> BenchmarkStats:
    """Summarise a strategy return series against a benchmark return series.

    Args:
        returns: Per-bar strategy returns (``Strategy_Returns``).
        benchmark: Per-bar benchmark returns (``Returns``).
        periods_per_year: Annualisation factor for the bar interval.
        strategy_total_return: The strategy's total return as the equity curve
            measured it. Given, ``excess_return`` uses it rather than
            recompounding ``returns`` — the equity curve is the authority, and
            the two differ once fees land on a bar with no position.
        risk_free_rate: Annual hurdle. Defaults to the configured convention.
    """
    r, b = _aligned(returns, benchmark)
    bench_total = compound_return(b)
    if r.size < 2:
        return BenchmarkStats(benchmark_return=bench_total)

    strat_total = (
        compound_return(r) if strategy_total_return is None else float(strategy_total_return)
    )
    slope = beta(r, b)
    return BenchmarkStats(
        benchmark_return=bench_total,
        excess_return=strat_total - bench_total,
        alpha=alpha(
            r,
            b,
            periods_per_year=periods_per_year,
            risk_free_rate=risk_free_rate,
            beta_value=slope,
        ),
        beta=slope,
        information_ratio=information_ratio(r, b, periods_per_year=periods_per_year),
        tracking_error=tracking_error(r, b, periods_per_year=periods_per_year),
        up_capture=up_capture(r, b),
        down_capture=down_capture(r, b),
    )


__all__ = [
    "BenchmarkStats",
    "alpha",
    "benchmark_stats",
    "beta",
    "compound_return",
    "down_capture",
    "information_ratio",
    "tracking_error",
    "up_capture",
]
