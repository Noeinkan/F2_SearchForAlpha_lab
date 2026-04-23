"""
Aggregation and robustness verdict for walk forward windows.

robust == True iff:
    - OOS Sharpe > 1.0 in at least 80 percent of windows, AND
    - mean per window degradation < 0.4

Per window degradation is the relative drop from in sample to out of sample
Sharpe, clipped at zero for windows where OOS exceeds IS:
    degradation = max(0, (is_sharpe - oos_sharpe) / max(|is_sharpe|, 1e-9))
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

import numpy as np

OOS_SHARPE_THRESHOLD = 1.0
ROBUST_FRACTION = 0.8
DEGRADATION_LIMIT = 0.4


@dataclass(frozen=True)
class WindowVerdict:
    is_sharpe_mean: float
    oos_sharpe_mean: float
    degradation: float
    robust: bool
    robust_reason: str
    fraction_oos_above_threshold: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def _per_window_degradation(is_sharpe: float, oos_sharpe: float) -> float:
    denom = max(abs(is_sharpe), 1e-9)
    return float(max(0.0, (is_sharpe - oos_sharpe) / denom))


def aggregate(windows: list[dict[str, Any]]) -> WindowVerdict:
    """Compute aggregate metrics and the robust verdict from per window records."""
    if not windows:
        return WindowVerdict(
            is_sharpe_mean=0.0,
            oos_sharpe_mean=0.0,
            degradation=0.0,
            robust=False,
            robust_reason="No windows",
            fraction_oos_above_threshold=0.0,
        )

    is_sharpes = [float(w["train"]["sharpe"]) for w in windows]
    oos_sharpes = [float(w["test"]["sharpe"]) for w in windows]
    is_mean = float(np.mean(is_sharpes))
    oos_mean = float(np.mean(oos_sharpes))
    degradations = [_per_window_degradation(i, o) for i, o in zip(is_sharpes, oos_sharpes)]
    deg_mean = float(np.mean(degradations))
    above = sum(1 for o in oos_sharpes if o > OOS_SHARPE_THRESHOLD)
    fraction = above / len(oos_sharpes)
    robust = fraction >= ROBUST_FRACTION and deg_mean < DEGRADATION_LIMIT
    if robust:
        reason = (
            f"OOS Sharpe > {OOS_SHARPE_THRESHOLD} in {above}/{len(oos_sharpes)} windows, "
            f"mean degradation {deg_mean:.2f} < {DEGRADATION_LIMIT}"
        )
    else:
        bits = []
        if fraction < ROBUST_FRACTION:
            bits.append(
                f"only {above}/{len(oos_sharpes)} windows above OOS Sharpe {OOS_SHARPE_THRESHOLD}"
            )
        if deg_mean >= DEGRADATION_LIMIT:
            bits.append(f"mean degradation {deg_mean:.2f} >= {DEGRADATION_LIMIT}")
        reason = "; ".join(bits) or "Failed robustness check"
    return WindowVerdict(
        is_sharpe_mean=is_mean,
        oos_sharpe_mean=oos_mean,
        degradation=deg_mean,
        robust=robust,
        robust_reason=reason,
        fraction_oos_above_threshold=fraction,
    )
