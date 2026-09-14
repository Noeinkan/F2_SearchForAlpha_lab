"""Probabilistic and Deflated Sharpe — how much of a Sharpe ratio to believe.

A Sharpe ratio is an estimate from a finite, non-normal sample, picked out of
however many configurations were tried. Two corrections, both from Bailey and
López de Prado, turn it back into a probability:

**Probabilistic Sharpe Ratio (PSR)** answers "what is the chance the true Sharpe
exceeds a threshold, given this sample?" It folds in the sample length, the
skew and the kurtosis of the returns, so a Sharpe earned by selling tails —
negative skew, fat kurtosis — is discounted the way it should be. Against a
threshold of zero it is simply "the chance this edge is real at all".

**Deflated Sharpe Ratio (DSR)** is PSR against a threshold that is *not* zero:
the Sharpe the best of ``N`` trials would be expected to reach on noise alone.
Test 500 signal combinations on the same tape and the winner's Sharpe is a
maximum of 500 draws, not a measurement. The DSR is what survives that.

Read both as probabilities. Above 0.95 is the usual bar for calling a result
significant; below 0.5 the winner is not distinguishable from the best draw of
a coin-flipping strategy.

Units, in and out
-----------------
Sharpe ratios go in **annualised**, matching everything else in
:mod:`lib.metrics`; ``periods_per_year`` de-annualises internally, because the
PSR variance term is only correct on the per-bar ratio. The result is a
probability in ``[0, 1]``.

Reference: Bailey & López de Prado, *The Deflated Sharpe Ratio: Correcting for
Selection Bias, Backtest Overfitting and Non-Normality* (2014).
"""

from __future__ import annotations

import math
from statistics import NormalDist
from typing import Any, Optional

import numpy as np

from lib.metrics.core import _clean

# Euler–Mascheroni constant, from the Gumbel approximation to the expected
# maximum of N independent draws.
_EULER_MASCHERONI = 0.5772156649015329

_NORMAL = NormalDist()

# Kurtosis of a normal distribution, on the non-excess scale this module uses.
NORMAL_KURTOSIS = 3.0


def sample_moments(returns: Any) -> tuple[int, float, float]:
    """``(n_obs, skew, kurtosis)`` of a return series, kurtosis non-excess.

    Both moments are the plain (biased) sample estimators, which is what the
    PSR derivation assumes. A series too short to have a shape reports the
    normal values, so PSR degrades to the textbook Sharpe test rather than to
    a NaN.
    """
    r = _clean(returns)
    n = int(r.size)
    if n < 3:
        return n, 0.0, NORMAL_KURTOSIS
    std = float(r.std(ddof=0))
    if not np.isfinite(std) or std <= 0:
        return n, 0.0, NORMAL_KURTOSIS
    centred = (r - r.mean()) / std
    skew = float((centred**3).mean())
    kurtosis = float((centred**4).mean())
    if not np.isfinite(skew):
        skew = 0.0
    if not np.isfinite(kurtosis) or kurtosis <= 0:
        kurtosis = NORMAL_KURTOSIS
    return n, skew, kurtosis


def expected_max_sharpe(num_trials: int, sharpe_std: float) -> float:
    """Sharpe the best of *num_trials* independent trials reaches on noise alone.

    The Gumbel approximation to the expected maximum of ``N`` normal draws with
    standard deviation *sharpe_std* and zero mean. Scale-free: pass an
    annualised dispersion and the threshold comes back annualised.

    Returns ``0.0`` for a single trial — one draw has no selection bias — and
    for a set of trials that all scored the same, which carries no information
    about how wide the search was.
    """
    n = int(num_trials or 0)
    std = abs(float(sharpe_std or 0.0))
    if n <= 1 or not np.isfinite(std) or std <= 0:
        return 0.0
    high = _NORMAL.inv_cdf(1.0 - 1.0 / n)
    low = _NORMAL.inv_cdf(1.0 - 1.0 / (n * math.e))
    return float(std * ((1.0 - _EULER_MASCHERONI) * high + _EULER_MASCHERONI * low))


def probabilistic_sharpe_ratio(
    sharpe: float,
    *,
    n_obs: int,
    skew: float = 0.0,
    kurtosis: float = NORMAL_KURTOSIS,
    benchmark_sharpe: float = 0.0,
    periods_per_year: int = 1,
) -> float:
    """Probability the true Sharpe exceeds *benchmark_sharpe*.

    Args:
        sharpe: Annualised Sharpe of the strategy.
        n_obs: Number of return observations behind it.
        skew: Sample skew of the returns.
        kurtosis: Sample kurtosis, **non-excess** — 3.0 is normal.
        benchmark_sharpe: Annualised threshold to beat. Zero asks "is there any
            edge at all"; :func:`expected_max_sharpe` supplies the DSR's.
        periods_per_year: Annualisation factor, used to de-annualise both
            ratios before applying the estimator's variance term.

    Returns 0.0 when the sample is too short or the variance term collapses —
    an undefined probability, reported as "no confidence" rather than NaN.
    """
    n = int(n_obs or 0)
    if n < 2:
        return 0.0
    ppy = max(1, int(periods_per_year))
    scale = math.sqrt(ppy)
    sr = float(sharpe) / scale
    sr_star = float(benchmark_sharpe) / scale
    if not np.isfinite(sr) or not np.isfinite(sr_star):
        return 0.0

    variance = 1.0 - float(skew) * sr + ((float(kurtosis) - 1.0) / 4.0) * sr * sr
    if not np.isfinite(variance) or variance <= 0:
        return 0.0

    z = (sr - sr_star) * math.sqrt(n - 1) / math.sqrt(variance)
    if not np.isfinite(z):
        return 0.0
    return float(_NORMAL.cdf(z))


def deflated_sharpe_ratio(
    sharpe: float,
    *,
    n_obs: int,
    skew: float = 0.0,
    kurtosis: float = NORMAL_KURTOSIS,
    num_trials: int = 1,
    sharpe_std: Optional[float] = None,
    periods_per_year: int = 1,
) -> float:
    """PSR against the Sharpe the best of *num_trials* would reach by chance.

    *sharpe_std* is the dispersion of the annualised Sharpe ratios **across the
    trials** — the search's own spread, which is what says how much a maximum
    over it is worth. With one trial, or with no dispersion to measure, the
    threshold is zero and this equals the plain
    :func:`probabilistic_sharpe_ratio`.
    """
    threshold = expected_max_sharpe(num_trials, sharpe_std or 0.0)
    return probabilistic_sharpe_ratio(
        sharpe,
        n_obs=n_obs,
        skew=skew,
        kurtosis=kurtosis,
        benchmark_sharpe=threshold,
        periods_per_year=periods_per_year,
    )


def trial_sharpe_std(sharpes: Any) -> float:
    """Dispersion of a set of trial Sharpes, for :func:`deflated_sharpe_ratio`.

    Sample standard deviation (``ddof=1``), ``0.0`` for fewer than two trials.
    """
    values = _clean(sharpes)
    if values.size < 2:
        return 0.0
    std = float(values.std(ddof=1))
    return std if np.isfinite(std) and std > 0 else 0.0


__all__ = [
    "NORMAL_KURTOSIS",
    "deflated_sharpe_ratio",
    "expected_max_sharpe",
    "probabilistic_sharpe_ratio",
    "sample_moments",
    "trial_sharpe_std",
]
