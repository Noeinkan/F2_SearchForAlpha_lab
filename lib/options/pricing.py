"""Pure European option pricing and exact expiry payoff for option strategies.

The only payoff/Greeks implementation: the Flow strategy panel and `sfa options price` both call it.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

from lib.options.greeks import bs_delta, bs_gamma, _norm_cdf, _norm_pdf

MULTIPLIER = 100


@dataclass(frozen=True)
class Leg:
    quantity: int
    kind: str
    strike: float
    premium: float
    iv: float = 0.2
    multiplier: int = MULTIPLIER


def _check(spot: float, strike: float, days: float, iv: float, rate: float, yield_rate: float) -> None:
    values = (spot, strike, days, iv, rate, yield_rate)
    if not all(math.isfinite(float(v)) for v in values):
        raise ValueError("Inputs must be finite numbers")
    if spot <= 0 or strike <= 0 or days < 0 or iv < 0:
        raise ValueError("Spot and strike must be positive; days and IV cannot be negative")


def price_option(*, spot: float, strike: float, days: float, iv: float,
                 kind: str = "call", rate: float = 0.05, yield_rate: float = 0.0) -> dict[str, float | None]:
    """Return per-share BSM value/Greeks; theta is per day, vega/rho per 1% point."""
    _check(spot, strike, days, iv, rate, yield_rate)
    call = kind.lower() in ("call", "c")
    if kind.lower() not in ("call", "c", "put", "p"):
        raise ValueError("kind must be call or put")
    t = days / 365.0
    if t == 0:
        return {"value": max(spot - strike if call else strike - spot, 0.0),
                "delta": None, "gamma": None, "theta": None, "vega": None, "rho": None}
    discounted_spot = spot * math.exp(-yield_rate * t)
    discounted_strike = strike * math.exp(-rate * t)
    if iv == 0:
        forward_edge = discounted_spot - discounted_strike
        return {"value": max(forward_edge if call else -forward_edge, 0.0),
                "delta": None, "gamma": None, "theta": None, "vega": None, "rho": None}
    root_t = math.sqrt(t)
    d1 = (math.log(spot / strike) + (rate - yield_rate + iv * iv / 2) * t) / (iv * root_t)
    d2 = d1 - iv * root_t
    if call:
        value = discounted_spot * _norm_cdf(d1) - discounted_strike * _norm_cdf(d2)
        theta_year = -(discounted_spot * _norm_pdf(d1) * iv / (2 * root_t)) \
            - rate * discounted_strike * _norm_cdf(d2) + yield_rate * discounted_spot * _norm_cdf(d1)
        rho = t * discounted_strike * _norm_cdf(d2)
    else:
        value = discounted_strike * _norm_cdf(-d2) - discounted_spot * _norm_cdf(-d1)
        theta_year = -(discounted_spot * _norm_pdf(d1) * iv / (2 * root_t)) \
            + rate * discounted_strike * _norm_cdf(-d2) - yield_rate * discounted_spot * _norm_cdf(-d1)
        rho = -t * discounted_strike * _norm_cdf(-d2)
    return {"value": value,
            "delta": bs_delta(spot, strike, t, iv, call=call, r=rate, q=yield_rate),
            "gamma": bs_gamma(spot, strike, t, iv, r=rate, q=yield_rate),
            "theta": theta_year / 365.0,
            "vega": discounted_spot * _norm_pdf(d1) * root_t / 100.0,
            "rho": rho / 100.0}


def payoff_at(underlying: float, legs: list[Leg]) -> float:
    if underlying < 0:
        raise ValueError("Underlying cannot be negative")
    return sum(
        leg.multiplier * leg.quantity * (
            (max(underlying - leg.strike, 0.0) if leg.kind.lower() in ("call", "c")
             else max(leg.strike - underlying, 0.0)) - leg.premium
        ) for leg in legs
    )


def payoff_summary(legs: list[Leg]) -> dict:
    if not legs:
        raise ValueError("At least one leg is required")
    for leg in legs:
        if (leg.quantity == 0 or not all(math.isfinite(float(v)) for v in
            (leg.quantity, leg.strike, leg.premium, leg.iv))
            or leg.strike <= 0 or leg.premium < 0 or leg.iv < 0):
            raise ValueError("Leg quantity must be nonzero; strike positive; premium and IV nonnegative")
        if leg.kind.lower() not in ("call", "c", "put", "p"):
            raise ValueError("Leg kind must be call or put")
    knots = sorted({0.0, *(leg.strike for leg in legs)})
    vals = [payoff_at(x, legs) for x in knots]
    roots = []
    for i in range(len(knots) - 1):
        a, b, ya, yb = knots[i], knots[i + 1], vals[i], vals[i + 1]
        if abs(ya) < 1e-8:
            roots.append(a)
        if ya * yb < 0:
            roots.append(a - ya * (b - a) / (yb - ya))
    if abs(vals[-1]) < 1e-8:
        roots.append(knots[-1])
    slope = sum(leg.multiplier * leg.quantity for leg in legs if leg.kind.lower() in ("call", "c"))
    if slope and vals[-1] * slope < 0:
        roots.append(knots[-1] - vals[-1] / slope)
    return {"break_evens": sorted({round(x, 8) for x in roots if x >= 0}),
            "max_profit": None if slope > 0 else max(vals),
            "max_loss": None if slope < 0 else min(vals)}


def net_premium(legs: list[Leg]) -> float:
    """Cash at entry: positive means the strategy costs money, negative means it collects a credit."""
    return sum(leg.multiplier * leg.quantity * leg.premium for leg in legs)


def implied_vol(price: float, *, spot: float, strike: float, days: float, kind: str = "call",
                rate: float = 0.05, yield_rate: float = 0.0) -> float | None:
    """Volatility at which the BSM value equals `price`, or None when no volatility can reach it."""
    if not (price > 0 and days > 0):
        return None
    low, high = 1e-4, 5.0

    def value(iv: float) -> float:
        return float(price_option(spot=spot, strike=strike, days=days, iv=iv, kind=kind,
                                  rate=rate, yield_rate=yield_rate)["value"])

    if not value(low) <= price <= value(high):
        return None
    for _ in range(100):
        mid = (low + high) / 2
        if value(mid) < price:
            low = mid
        else:
            high = mid
    return (low + high) / 2


def strategy_legs(preset: str, spot: float, premium: float = 0.0, iv: float = 0.2) -> list[Leg]:
    """Create editable example legs; premiums default to theoretical values in the UI."""
    if spot <= 0:
        raise ValueError("Spot must be positive")
    # Whole-dollar strikes above $10, like a listed chain; cents below.
    places = 0 if spot >= 10 else 2
    at = round(spot, places)
    width = max(round(spot * 0.05, places), 0.01)
    if preset == "long_call":
        return [Leg(1, "call", at, premium, iv)]
    if preset == "long_put":
        return [Leg(1, "put", at, premium, iv)]
    if preset == "bull_call_spread":
        return [Leg(1, "call", at, premium, iv), Leg(-1, "call", round(at + width, 2), premium, iv)]
    if preset == "iron_condor":
        return [Leg(1, "put", round(max(0.01, at - 2 * width), 2), premium, iv),
                Leg(-1, "put", round(max(0.01, at - width), 2), premium, iv),
                Leg(-1, "call", round(at + width, 2), premium, iv),
                Leg(1, "call", round(at + 2 * width, 2), premium, iv)]
    raise ValueError("Unknown preset")
