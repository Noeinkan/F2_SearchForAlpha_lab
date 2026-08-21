"""Metric primitives — the only implementation of each formula in the repo.

Conventions, fixed here and relied on everywhere downstream:

* **Rates are fractions**, never percentages. ``0.2`` is +20%. Percent
  formatting happens in :mod:`lib.metrics.names`, at the point of display.
* **``max_drawdown`` is a positive magnitude.** A 15% peak-to-trough loss is
  ``0.15``, not ``-0.15``. Callers wanting the negative convention negate it
  themselves; the sign belongs to the display, not to the number.
* **Every ratio is annualised** at ``periods_per_year``, which comes from
  ``lib.timeframes.periods_per_year(interval)`` — never a hardcoded 252.
* **Standard deviations use ``ddof=1``.** These are sample estimates.
* **Undefined is 0.0, not NaN.** A ratio with no dispersion to divide by, or a
  statistic over zero trades, reports 0.0 so downstream sorting and JSON
  serialisation stay total.

The risk-free rate is a single convention (see :func:`resolve_risk_free_rate`),
not a per-call-site default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from functools import lru_cache
from typing import Any, Optional

import numpy as np
import pandas as pd

logger = logging.getLogger(__name__)

# Annual risk-free rate used as the excess-return hurdle for Sharpe and
# Sortino. Zero by default: it makes Sharpe the plain reward-to-variability
# ratio most backtest tooling reports, and it does not bake a rate that was
# current on the day it was typed into every historical number.
# Override with ``metrics.risk_free_rate`` in ``config/agent.yaml``.
DEFAULT_RISK_FREE_RATE = 0.0

# Profit factor with winners and no losers is mathematically infinite. The JSON
# contract and the Dash leaderboards both need a sortable, serialisable number,
# so it is reported as this sentinel instead.
PROFIT_FACTOR_SENTINEL = 999.0


@lru_cache(maxsize=1)
def _configured_risk_free_rate() -> float:
    """Read ``metrics.risk_free_rate`` from ``config/agent.yaml``, once."""
    try:
        from lib.config_loader import get_agent_config

        raw = (get_agent_config().get("metrics") or {}).get("risk_free_rate")
    except Exception:
        logger.debug("metrics.risk_free_rate lookup failed; using default", exc_info=True)
        return DEFAULT_RISK_FREE_RATE
    if raw is None:
        return DEFAULT_RISK_FREE_RATE
    try:
        return float(raw)
    except (TypeError, ValueError):
        logger.warning(
            "config/agent.yaml metrics.risk_free_rate is not a number (%r); using %s",
            raw,
            DEFAULT_RISK_FREE_RATE,
        )
        return DEFAULT_RISK_FREE_RATE


def resolve_risk_free_rate(explicit: Optional[float] = None) -> float:
    """The annual risk-free rate to use: *explicit* when given, else config."""
    if explicit is not None:
        return float(explicit)
    return _configured_risk_free_rate()


def _clean(values: Any) -> np.ndarray:
    """Coerce to a finite float array; non-finite entries become 0.0."""
    if values is None:
        return np.empty(0, dtype=float)
    arr = pd.to_numeric(pd.Series(values), errors="coerce").to_numpy(dtype=float)
    return np.nan_to_num(arr, nan=0.0, posinf=0.0, neginf=0.0)


def _excess(returns: Any, periods_per_year: int, risk_free_rate: float) -> np.ndarray:
    """Per-bar returns net of the per-bar share of the annual risk-free rate."""
    r = _clean(returns)
    if r.size == 0:
        return r
    return r - (risk_free_rate / max(1, int(periods_per_year)))


def sharpe_ratio(
    returns: Any,
    *,
    periods_per_year: int,
    risk_free_rate: Optional[float] = None,
) -> float:
    """Annualised Sharpe: mean excess return over its standard deviation."""
    ppy = max(1, int(periods_per_year))
    excess = _excess(returns, ppy, resolve_risk_free_rate(risk_free_rate))
    if excess.size < 2:
        return 0.0
    std = float(excess.std(ddof=1))
    if not np.isfinite(std) or std <= 0:
        return 0.0
    return float(np.sqrt(ppy) * excess.mean() / std)


def sortino_ratio(
    returns: Any,
    *,
    periods_per_year: int,
    risk_free_rate: Optional[float] = None,
) -> float:
    """Annualised Sortino: like Sharpe, but only downside deviation is penalised.

    The denominator is the standard deviation of the *negative* excess returns
    only — not a semi-deviation taken over the full-length series.
    """
    ppy = max(1, int(periods_per_year))
    excess = _excess(returns, ppy, resolve_risk_free_rate(risk_free_rate))
    if excess.size < 2:
        return 0.0
    downside = excess[excess < 0]
    if downside.size < 2:
        return 0.0
    downside_std = float(downside.std(ddof=1))
    if not np.isfinite(downside_std) or downside_std <= 0:
        return 0.0
    return float(np.sqrt(ppy) * excess.mean() / downside_std)


def max_drawdown(equity: Any) -> float:
    """Largest peak-to-trough decline of an equity curve, as a positive fraction."""
    curve = _clean(equity)
    if curve.size == 0:
        return 0.0
    peak = np.maximum.accumulate(curve)
    with np.errstate(divide="ignore", invalid="ignore"):
        drawdown = np.where(peak > 0, curve / np.where(peak > 0, peak, 1.0) - 1.0, 0.0)
    worst = float(np.nan_to_num(drawdown, nan=0.0, posinf=0.0, neginf=0.0).min())
    return abs(min(worst, 0.0))


def total_return(equity: Any, initial_capital: Optional[float] = None) -> float:
    """Fractional growth of an equity curve over the whole window."""
    curve = _clean(equity)
    if curve.size == 0:
        return 0.0
    start = float(initial_capital) if initial_capital else float(curve[0])
    if start <= 0:
        return 0.0
    return float(curve[-1] / start) - 1.0


def cagr(
    equity: Any,
    *,
    periods_per_year: int,
    initial_capital: Optional[float] = None,
) -> float:
    """Compound annual growth rate implied by the equity curve.

    The horizon is the number of bar *steps* (``len - 1``) over
    ``periods_per_year``, so 253 daily bars at 252 periods/year is exactly one
    year and CAGR equals total return.
    """
    curve = _clean(equity)
    if curve.size == 0:
        return 0.0
    start = float(initial_capital) if initial_capital else float(curve[0])
    if start <= 0:
        return 0.0
    growth = float(curve[-1]) / start
    if growth <= 0:
        return -1.0
    years = max(curve.size - 1, 1) / max(1, int(periods_per_year))
    return float(growth ** (1.0 / years) - 1.0)


def calmar_ratio(cagr_value: float, max_dd: float) -> float:
    """Compound annual growth rate divided by the drawdown that paid for it.

    ``max_dd`` follows the positive-magnitude convention of :func:`max_drawdown`.
    """
    if not max_dd:
        return 0.0
    value = float(cagr_value) / abs(float(max_dd))
    return float(value) if np.isfinite(value) else 0.0


def exposure(units: Any) -> float:
    """Fraction of bars spent holding a position."""
    held = _clean(units)
    if held.size == 0:
        return 0.0
    return float((held > 0).mean())


def turnover(units_bought: Any, units_sold: Any, price: Any, equity: Any) -> float:
    """Gross traded notional over mean equity — unitless, higher means busier."""
    bought = _clean(units_bought)
    sold = _clean(units_sold)
    px = _clean(price)
    eq = _clean(equity)
    if bought.size == 0 or px.size != bought.size or sold.size != bought.size:
        return 0.0
    if eq.size == 0:
        return 0.0
    gross = float(((bought + sold) * px).sum())
    mean_equity = float(eq.mean())
    if mean_equity <= 0:
        return 0.0
    return gross / mean_equity


def count_fills(units_bought: Any, units_sold: Any) -> int:
    """Number of individual executions — buys plus sells.

    Distinct from a round-trip count: one round trip is at least two fills, and
    a scale-in makes it more. See :class:`RoundTripStats.num_trades`.
    """
    bought = _clean(units_bought)
    sold = _clean(units_sold)
    return int((bought > 0).sum() + (sold > 0).sum())


@dataclass(frozen=True)
class RoundTripStats:
    """Realised trade statistics, read from the engine's round-trip ledger.

    Rows with ``exit_reason == 'open'`` are excluded from every realised figure
    and counted separately as :attr:`open_trades` — an unclosed position has no
    realised result to win or lose.
    """

    num_trades: int = 0
    open_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    avg_holding_bars: float = 0.0
    avg_holding_sessions: float = 0.0
    total_fees: float = 0.0


def round_trip_stats(ledger: Optional[pd.DataFrame]) -> RoundTripStats:
    """Summarise a trade ledger. See :mod:`lib.metrics.ledger` for its shape."""
    if ledger is None or not isinstance(ledger, pd.DataFrame) or ledger.empty:
        return RoundTripStats()

    if "exit_reason" not in ledger.columns:
        logger.warning(
            "Trade ledger has no 'exit_reason' column; treating every row as closed"
        )
        closed = ledger
        open_trades = 0
    else:
        open_trades = int((ledger["exit_reason"] == "open").sum())
        closed = ledger[ledger["exit_reason"] != "open"]

    total_fees = float(_clean(ledger["fees"]).sum()) if "fees" in ledger.columns else 0.0

    if closed.empty or "net_pnl" not in closed.columns:
        return RoundTripStats(open_trades=open_trades, total_fees=total_fees)

    pnl = _clean(closed["net_pnl"])
    wins = pnl[pnl > 0]
    losses = pnl[pnl < 0]

    gross_profit = float(wins.sum())
    gross_loss = float(-losses.sum())
    if gross_loss > 0:
        profit_factor = gross_profit / gross_loss
    else:
        profit_factor = PROFIT_FACTOR_SENTINEL if gross_profit > 0 else 0.0

    holding = _clean(closed["holding_bars"]) if "holding_bars" in closed.columns else np.empty(0)
    sessions = (
        _clean(closed["holding_sessions"])
        if "holding_sessions" in closed.columns
        else np.empty(0)
    )

    return RoundTripStats(
        num_trades=int(pnl.size),
        open_trades=open_trades,
        win_rate=float(wins.size / pnl.size),
        profit_factor=float(profit_factor),
        avg_win=float(wins.mean()) if wins.size else 0.0,
        avg_loss=float(losses.mean()) if losses.size else 0.0,
        expectancy=float(pnl.mean()),
        avg_holding_bars=float(holding.mean()) if holding.size else 0.0,
        avg_holding_sessions=float(sessions.mean()) if sessions.size else 0.0,
        total_fees=total_fees,
    )
