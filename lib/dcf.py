"""Two-stage Free Cash Flow to Equity (FCFE) valuation.

Sibling of the Rule #1 sticker-price method in ``lib.fundamentals``.  Where
Rule #1 works forward from EPS and a capped P/E, this works forward from free
cash flow and discounts at the cost of equity.

Why FCFE and not FCFF: the repo's ``free_cash_flow`` series is
``operating_cash_flow + capex``.  Operating cash flow is reported after
interest paid, so the series is already levered.  Discounting it at the cost
of equity yields equity value directly, with no WACC and no net-debt bridge.

This module is deliberately free of network calls and of any import from
``lib.fundamentals`` (which imports *this* module).  Every function is pure so
the tests can pin exact numbers.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import numpy as np
import pandas as pd

# --- defaults -----------------------------------------------------------
# Overridable from config/strategy_config.yaml -> dcf:
DEFAULT_RISK_FREE = 0.04
DEFAULT_EQUITY_RISK_PREMIUM = 0.05
DEFAULT_TERMINAL_GROWTH = 0.025
DEFAULT_BETA = 1.0
BETA_FLOOR = 0.8
BETA_CAP = 2.0
STAGE1_YEARS = 10
MAX_STAGE1_GROWTH = 0.20
FCF_BASE_YEARS = 3

SENSITIVITY_R_DELTAS = (-0.01, 0.0, 0.01)
SENSITIVITY_G_DELTAS = (-0.01, 0.0, 0.01)


@dataclass(frozen=True)
class DcfAssumptions:
    risk_free: float = DEFAULT_RISK_FREE
    equity_risk_premium: float = DEFAULT_EQUITY_RISK_PREMIUM
    terminal_growth: float = DEFAULT_TERMINAL_GROWTH
    beta: float = DEFAULT_BETA
    beta_floor: float = BETA_FLOOR
    beta_cap: float = BETA_CAP
    stage1_years: int = STAGE1_YEARS
    max_stage1_growth: float = MAX_STAGE1_GROWTH
    fade_to_terminal: bool = True


@dataclass(frozen=True)
class DcfResult:
    fcfe_base: float
    stage1_growth: float
    terminal_growth: float
    discount_rate: float
    beta_used: float
    pv_stage1: float
    pv_terminal: float
    equity_value: float
    terminal_share: float
    shares_outstanding: float
    fair_value_per_share: float
    upside_vs_price: float
    projections: list[dict[str, float]] = field(default_factory=list)
    sensitivity: list[dict[str, Any]] = field(default_factory=list)
    notes: list[str] = field(default_factory=list)


def cost_of_equity(assumptions: DcfAssumptions) -> tuple[float, float]:
    """CAPM cost of equity.  Returns (rate, clamped_beta).

    r = risk_free + beta * equity_risk_premium
    """
    beta = assumptions.beta
    if not _is_number(beta) or beta <= 0:
        beta = DEFAULT_BETA
    beta = float(min(max(beta, assumptions.beta_floor), assumptions.beta_cap))
    return assumptions.risk_free + beta * assumptions.equity_risk_premium, beta


def growth_path(
    stage1_growth: float, terminal_growth: float, years: int, *, fade: bool = True
) -> list[float]:
    """Per-year growth rates for stage 1.

    With ``fade`` the rate declines linearly from ``stage1_growth`` in year 1 to
    ``terminal_growth`` in the final year, which stops a high near-term rate
    from compounding untouched for a decade.  Without it the rate is flat.
    """
    if not fade or years <= 1:
        return [stage1_growth] * years
    step = (stage1_growth - terminal_growth) / (years - 1)
    return [stage1_growth - step * i for i in range(years)]


def two_stage_fcfe(
    fcfe_base: float,
    stage1_growth: float,
    discount_rate: float,
    terminal_growth: float,
    *,
    years: int = STAGE1_YEARS,
    fade: bool = True,
) -> dict[str, Any]:
    """Discount an explicit FCFE path plus a Gordon terminal value.

    equity_value = sum(FCFE_t / (1+r)^t) + [FCFE_N (1+g2) / (r - g2)] / (1+r)^N
    """
    if not _is_number(fcfe_base):
        raise ValueError("fcfe_base is not a number")
    if discount_rate <= terminal_growth:
        raise ValueError(
            f"discount rate {discount_rate:.4f} must exceed terminal growth "
            f"{terminal_growth:.4f}; the Gordon denominator would be non-positive"
        )

    rates = growth_path(stage1_growth, terminal_growth, years, fade=fade)
    projections: list[dict[str, float]] = []
    cash_flow = float(fcfe_base)
    pv_stage1 = 0.0
    for year, rate in enumerate(rates, start=1):
        cash_flow *= 1 + rate
        discount_factor = 1 / ((1 + discount_rate) ** year)
        present_value = cash_flow * discount_factor
        pv_stage1 += present_value
        projections.append(
            {
                "year": year,
                "growth": rate,
                "fcfe": cash_flow,
                "discount_factor": discount_factor,
                "present_value": present_value,
            }
        )

    terminal_value = cash_flow * (1 + terminal_growth) / (discount_rate - terminal_growth)
    pv_terminal = terminal_value / ((1 + discount_rate) ** years)
    equity_value = pv_stage1 + pv_terminal

    return {
        "projections": projections,
        "pv_stage1": pv_stage1,
        "terminal_value": terminal_value,
        "pv_terminal": pv_terminal,
        "equity_value": equity_value,
        "terminal_share": pv_terminal / equity_value if equity_value else np.nan,
    }


def sensitivity_grid(
    fcfe_base: float,
    stage1_growth: float,
    discount_rate: float,
    terminal_growth: float,
    *,
    years: int = STAGE1_YEARS,
    fade: bool = True,
    shares: float = 1.0,
    r_deltas: tuple[float, ...] = SENSITIVITY_R_DELTAS,
    g_deltas: tuple[float, ...] = SENSITIVITY_G_DELTAS,
) -> list[dict[str, Any]]:
    """Fair value per share across a discount-rate x terminal-growth grid.

    The point of surfacing this is that the two softest inputs move the answer
    more than a decade of careful cash-flow forecasting does.  A single fair
    value hides that; the grid does not.
    """
    rows: list[dict[str, Any]] = []
    for r_delta in r_deltas:
        rate = discount_rate + r_delta
        cells: list[dict[str, Any]] = []
        for g_delta in g_deltas:
            growth = terminal_growth + g_delta
            try:
                result = two_stage_fcfe(
                    fcfe_base, stage1_growth, rate, growth, years=years, fade=fade
                )
                per_share = result["equity_value"] / shares if shares else np.nan
            except ValueError:
                per_share = np.nan
            cells.append({"terminal_growth": growth, "value_per_share": per_share})
        rows.append({"discount_rate": rate, "cells": cells})
    return rows


def build_dcf(
    info: dict[str, Any],
    financial_map: dict[str, dict[str, Any]],
    assumptions: DcfAssumptions | None = None,
) -> DcfResult:
    """Assemble a DCF from the same ``financial_map`` the Rule #1 model uses.

    ``financial_map['fcf']['values']`` is scaled to $mil by ``_metric``, so the
    equity value comes out in $mil and shares are converted to millions before
    the per-share divide.
    """
    assumptions = assumptions or DcfAssumptions()
    notes: list[str] = []

    beta_raw = _number(info.get("beta"))
    if not _is_number(beta_raw):
        notes.append("Beta unavailable; defaulted to 1.0")
    assumptions = _with_beta(assumptions, beta_raw)
    discount_rate, beta_used = cost_of_equity(assumptions)
    if _is_number(beta_raw) and not np.isclose(beta_raw, beta_used):
        notes.append(f"Beta clamped from {beta_raw:.2f} to {beta_used:.2f}")

    fcf = financial_map["fcf"]["values"].dropna()
    fcfe_base = _base_fcfe(fcf)
    if not _is_number(fcfe_base) or fcfe_base <= 0:
        raise ValueError("Base FCFE is not positive; DCF not meaningful for this company")
    if (fcf.tail(FCF_BASE_YEARS) <= 0).any():
        notes.append("Negative free cash flow in the base window; treat with caution")

    historical = _cagr(fcf, min(10, max(len(fcf) - 1, 1)))
    analysts = _growth_from_info(info)
    stage1_growth = _conservative_growth(
        analysts, historical, cap=assumptions.max_stage1_growth,
        floor=assumptions.terminal_growth,
    )

    core = two_stage_fcfe(
        fcfe_base,
        stage1_growth,
        discount_rate,
        assumptions.terminal_growth,
        years=assumptions.stage1_years,
        fade=assumptions.fade_to_terminal,
    )

    shares_millions = _number(info.get("sharesOutstanding")) / 1_000_000
    if not _is_number(shares_millions) or shares_millions <= 0:
        raise ValueError("sharesOutstanding unavailable; cannot express DCF per share")

    fair_value = core["equity_value"] / shares_millions
    price = _number(info.get("currentPrice")) or _latest(financial_map["stock_price"]["values"])
    upside = (fair_value / price - 1) if _is_number(price) and price else np.nan

    if core["terminal_share"] > 0.75:
        notes.append(
            f"{core['terminal_share']:.0%} of value sits in the terminal value; "
            "the answer is mostly an assumption about year 11 onward"
        )

    return DcfResult(
        fcfe_base=fcfe_base,
        stage1_growth=stage1_growth,
        terminal_growth=assumptions.terminal_growth,
        discount_rate=discount_rate,
        beta_used=beta_used,
        pv_stage1=core["pv_stage1"],
        pv_terminal=core["pv_terminal"],
        equity_value=core["equity_value"],
        terminal_share=core["terminal_share"],
        shares_outstanding=shares_millions,
        fair_value_per_share=fair_value,
        upside_vs_price=upside,
        projections=core["projections"],
        sensitivity=sensitivity_grid(
            fcfe_base,
            stage1_growth,
            discount_rate,
            assumptions.terminal_growth,
            years=assumptions.stage1_years,
            fade=assumptions.fade_to_terminal,
            shares=shares_millions,
        ),
        notes=notes,
    )


def dcf_rows(result: DcfResult) -> list[dict[str, str]]:
    """Rows in the {'metric', 'value'} shape used by the valuation table."""
    rows = [
        ("Base FCFE (3y avg)", _money_mil(result.fcfe_base)),
        ("Stage 1 FCFE GR", _pct(result.stage1_growth)),
        ("Terminal GR", _pct(result.terminal_growth)),
        ("Beta (clamped)", f"{result.beta_used:.2f}"),
        ("Cost of Equity", _pct(result.discount_rate)),
        ("PV Stage 1", _money_mil(result.pv_stage1)),
        ("PV Terminal Value", _money_mil(result.pv_terminal)),
        ("Terminal Value Share", _pct(result.terminal_share)),
        ("Equity Value", _money_mil(result.equity_value)),
        ("DCF Fair Value", _money(result.fair_value_per_share)),
        ("Upside vs Price", _pct(result.upside_vs_price)),
    ]
    return [{"metric": metric, "value": value} for metric, value in rows]


# --- internals ----------------------------------------------------------

def _with_beta(assumptions: DcfAssumptions, beta: float) -> DcfAssumptions:
    if not _is_number(beta):
        return assumptions
    return DcfAssumptions(
        risk_free=assumptions.risk_free,
        equity_risk_premium=assumptions.equity_risk_premium,
        terminal_growth=assumptions.terminal_growth,
        beta=beta,
        beta_floor=assumptions.beta_floor,
        beta_cap=assumptions.beta_cap,
        stage1_years=assumptions.stage1_years,
        max_stage1_growth=assumptions.max_stage1_growth,
        fade_to_terminal=assumptions.fade_to_terminal,
    )


def _base_fcfe(fcf: pd.Series, window: int = FCF_BASE_YEARS) -> float:
    """Average the last few years so one capex-heavy year does not set the base."""
    if fcf.empty:
        return float("nan")
    return float(fcf.tail(window).mean())


def _conservative_growth(*candidates: float, cap: float, floor: float) -> float:
    """Lowest positive candidate, capped, floored at terminal growth.

    Mirrors the Rule #1 philosophy already in ``_estimated_growth_rate``: when
    sources disagree, take the least optimistic one.
    """
    positives = [value for value in candidates if _is_number(value) and value > 0]
    if not positives:
        return floor
    return float(min(min(positives), cap))


def _growth_from_info(info: dict[str, Any]) -> float:
    for key in ("earningsGrowth", "revenueGrowth", "earningsQuarterlyGrowth"):
        value = _number(info.get(key))
        if _is_number(value):
            return value
    return float("nan")


def _cagr(values: pd.Series, periods: int) -> float:
    clean = values.dropna()
    if len(clean) < 2 or periods < 1:
        return float("nan")
    start, end = clean.iloc[-(periods + 1)], clean.iloc[-1]
    if start <= 0 or end <= 0:
        return float("nan")
    return float((end / start) ** (1 / periods) - 1)


def _latest(values: pd.Series) -> float:
    clean = values.dropna()
    return float(clean.iloc[-1]) if not clean.empty else float("nan")


def _number(value: Any) -> float:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return float("nan")
    return result if np.isfinite(result) else float("nan")


def _is_number(value: Any) -> bool:
    return isinstance(value, (int, float, np.floating)) and np.isfinite(value)


def _pct(value: float) -> str:
    return f"{value * 100:.1f}%" if _is_number(value) else "n/a"


def _money(value: float) -> str:
    return f"${value:,.2f}" if _is_number(value) else "n/a"


def _money_mil(value: float) -> str:
    return f"${value:,.0f}m" if _is_number(value) else "n/a"
