"""Black-Scholes Greeks and estimated Net GEX / DEX / Vanna Model ladders.

Educational estimates from Yahoo IV × open interest — not a vendor GEX product.
Dealer-sign convention: calls contribute positive GEX/DEX, puts negative.
OI Vanna Model uses short-customer delta notional (−Δ × OI × 100 × S').
"""

from __future__ import annotations

import math
from collections import defaultdict
from datetime import date, datetime
from typing import Any, Mapping, Protocol, Sequence

ALL_EXPIRIES_KEY = "__all__"

# Contract multiplier (US equity options) and 1% spot move scaling (SpotGamma-style).
_CONTRACT_MULT = 100.0
_PCT_MOVE = 0.01


class _OptionLike(Protocol):
    strike: float
    cp: str
    volume: int
    open_interest: int
    iv: float
    expiry: date


def _norm_pdf(x: float) -> float:
    return math.exp(-0.5 * x * x) / math.sqrt(2.0 * math.pi)


def _norm_cdf(x: float) -> float:
    return 0.5 * (1.0 + math.erf(x / math.sqrt(2.0)))


def _d1(S: float, K: float, T: float, sigma: float, r: float, q: float) -> float | None:
    if S <= 0 or K <= 0 or T <= 0 or sigma <= 0:
        return None
    return (math.log(S / K) + (r - q + 0.5 * sigma * sigma) * T) / (sigma * math.sqrt(T))


def bs_gamma(
    S: float,
    K: float,
    T: float,
    sigma: float,
    r: float = 0.05,
    q: float = 0.0,
) -> float:
    """Black-Scholes gamma (same for calls and puts)."""
    d1 = _d1(S, K, T, sigma, r, q)
    if d1 is None:
        return 0.0
    return math.exp(-q * T) * _norm_pdf(d1) / (S * sigma * math.sqrt(T))


def bs_delta(
    S: float,
    K: float,
    T: float,
    sigma: float,
    *,
    call: bool,
    r: float = 0.05,
    q: float = 0.0,
) -> float:
    """Black-Scholes delta for a call or put."""
    d1 = _d1(S, K, T, sigma, r, q)
    if d1 is None:
        return 0.0
    if call:
        return math.exp(-q * T) * _norm_cdf(d1)
    return math.exp(-q * T) * (_norm_cdf(d1) - 1.0)


def _years_to_expiry(expiry: date, as_of: date) -> float:
    days = (expiry - as_of).days
    if days <= 0:
        # Same-day / expired: treat as a few hours so ATM gamma is finite but small.
        return 1.0 / (365.0 * 8.0)
    return days / 365.0


def _gex_scale(S: float) -> float:
    return _CONTRACT_MULT * (S ** 2) * _PCT_MOVE


def _dex_scale(S: float) -> float:
    return _CONTRACT_MULT * S * _PCT_MOVE


def aggregate_gex_ladder(
    contracts: Sequence[_OptionLike],
    spot: float,
    as_of: date | None = None,
    *,
    r: float = 0.05,
    q: float = 0.0,
) -> list[dict[str, float | int]]:
    """Aggregate estimated GEX/DEX by strike for one expiry (or any contract list)."""
    as_of = as_of or date.today()
    S = float(spot or 0)
    if S <= 0 or not contracts:
        return []

    gex_s = _gex_scale(S)
    dex_s = _dex_scale(S)
    by_strike: dict[float, dict[str, float | int]] = {}

    for c in contracts:
        strike = float(c.strike)
        oi = int(c.open_interest or 0)
        vol = int(c.volume or 0)
        iv = float(c.iv or 0)
        T = _years_to_expiry(c.expiry, as_of)
        gamma = bs_gamma(S, strike, T, iv, r=r, q=q)
        is_call = str(c.cp).upper().startswith("C")
        delta = bs_delta(S, strike, T, iv, call=is_call, r=r, q=q)

        row = by_strike.setdefault(
            strike,
            {
                "strike": strike,
                "net_gex": 0.0,
                "call_gex": 0.0,
                "put_gex": 0.0,
                "net_dex": 0.0,
                "call_vol": 0,
                "put_vol": 0,
                "total_oi": 0,
            },
        )
        row["total_oi"] = int(row["total_oi"]) + oi

        if is_call:
            gex = gamma * oi * gex_s
            dex = abs(delta) * oi * dex_s
            row["call_gex"] = float(row["call_gex"]) + gex
            row["net_gex"] = float(row["net_gex"]) + gex
            row["net_dex"] = float(row["net_dex"]) + dex
            row["call_vol"] = int(row["call_vol"]) + vol
        else:
            gex = -gamma * oi * gex_s
            dex = -abs(delta) * oi * dex_s
            row["put_gex"] = float(row["put_gex"]) + gex
            row["net_gex"] = float(row["net_gex"]) + gex
            row["net_dex"] = float(row["net_dex"]) + dex
            row["put_vol"] = int(row["put_vol"]) + vol

    return sorted(
        (
            {
                "strike": float(r["strike"]),
                "net_gex": float(r["net_gex"]),
                "call_gex": float(r["call_gex"]),
                "put_gex": float(r["put_gex"]),
                "net_dex": float(r["net_dex"]),
                "call_vol": int(r["call_vol"]),
                "put_vol": int(r["put_vol"]),
                "total_oi": int(r["total_oi"]),
            }
            for r in by_strike.values()
        ),
        key=lambda r: float(r["strike"]),
    )


def gex_levels(
    ladder: Sequence[Mapping[str, Any]],
    spot: float,
) -> dict[str, float | None]:
    """Derive call resistance, put support, and HVL from a GEX ladder."""
    rows = list(ladder or [])
    if not rows:
        return {"call_resistance": None, "put_support": None, "hvl": None}

    S = float(spot or 0)

    above = [r for r in rows if float(r["strike"]) >= S] if S > 0 else rows
    call_pool = above if above else rows
    call_resistance = max(call_pool, key=lambda r: float(r.get("call_gex") or 0))
    cr = float(call_resistance["strike"]) if float(call_resistance.get("call_gex") or 0) > 0 else None

    below = [r for r in rows if float(r["strike"]) <= S] if S > 0 else rows
    put_pool = below if below else rows
    put_support = max(put_pool, key=lambda r: abs(float(r.get("put_gex") or 0)))
    ps = float(put_support["strike"]) if abs(float(put_support.get("put_gex") or 0)) > 0 else None

    hvl_row = max(
        rows,
        key=lambda r: int(r.get("call_vol") or 0) + int(r.get("put_vol") or 0),
    )
    hvl_vol = int(hvl_row.get("call_vol") or 0) + int(hvl_row.get("put_vol") or 0)
    hvl = float(hvl_row["strike"]) if hvl_vol > 0 else None

    return {"call_resistance": cr, "put_support": ps, "hvl": hvl}


def merge_gex_ladders(
    per_expiry: Mapping[str, Sequence[Mapping[str, Any]]],
) -> list[dict[str, float | int]]:
    """Sum GEX/DEX/volume by strike across expiries (All Expirations)."""
    by_strike: dict[float, dict[str, float | int]] = {}
    for ladder in per_expiry.values():
        for r in ladder or []:
            strike = float(r["strike"])
            row = by_strike.setdefault(
                strike,
                {
                    "strike": strike,
                    "net_gex": 0.0,
                    "call_gex": 0.0,
                    "put_gex": 0.0,
                    "net_dex": 0.0,
                    "call_vol": 0,
                    "put_vol": 0,
                    "total_oi": 0,
                },
            )
            row["net_gex"] = float(row["net_gex"]) + float(r.get("net_gex") or 0)
            row["call_gex"] = float(row["call_gex"]) + float(r.get("call_gex") or 0)
            row["put_gex"] = float(row["put_gex"]) + float(r.get("put_gex") or 0)
            row["net_dex"] = float(row["net_dex"]) + float(r.get("net_dex") or 0)
            row["call_vol"] = int(row["call_vol"]) + int(r.get("call_vol") or 0)
            row["put_vol"] = int(row["put_vol"]) + int(r.get("put_vol") or 0)
            row["total_oi"] = int(row["total_oi"]) + int(r.get("total_oi") or 0)

    return sorted(
        (
            {
                "strike": float(r["strike"]),
                "net_gex": float(r["net_gex"]),
                "call_gex": float(r["call_gex"]),
                "put_gex": float(r["put_gex"]),
                "net_dex": float(r["net_dex"]),
                "call_vol": int(r["call_vol"]),
                "put_vol": int(r["put_vol"]),
                "total_oi": int(r["total_oi"]),
            }
            for r in by_strike.values()
        ),
        key=lambda r: float(r["strike"]),
    )


def build_gex_ladders(
    contracts: Sequence[_OptionLike],
    spot: float,
    as_of: date | None = None,
    *,
    r: float = 0.05,
    q: float = 0.0,
) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """Group contracts by expiry → GEX ladders + levels; include ``__all__``."""
    as_of = as_of or date.today()
    by_expiry: dict[date, list[_OptionLike]] = defaultdict(list)
    for c in contracts:
        by_expiry[c.expiry].append(c)

    ladders: dict[str, list[dict]] = {}
    meta: dict[str, dict] = {}
    for expiry in sorted(by_expiry):
        key = expiry.isoformat()
        ladder = aggregate_gex_ladder(by_expiry[expiry], spot, as_of, r=r, q=q)
        ladders[key] = ladder
        levels = gex_levels(ladder, spot)
        meta[key] = {
            **levels,
            "net_gex_total": sum(float(r["net_gex"]) for r in ladder),
            "net_dex_total": sum(float(r["net_dex"]) for r in ladder),
        }

    if ladders:
        merged = merge_gex_ladders(ladders)
        ladders[ALL_EXPIRIES_KEY] = merged
        levels = gex_levels(merged, spot)
        meta[ALL_EXPIRIES_KEY] = {
            **levels,
            "net_gex_total": sum(float(r["net_gex"]) for r in merged),
            "net_dex_total": sum(float(r["net_dex"]) for r in merged),
        }

    return ladders, meta


# Default strike window for OI Vanna Model (matches Flow inventory).
VANNA_WINDOW_PCT = 0.12


def _vanna_eval_strikes(
    contracts: Sequence[_OptionLike],
    spot: float,
    window_pct: float = VANNA_WINDOW_PCT,
) -> list[float]:
    """Unique contract strikes within ±window of spot (fallback: all strikes)."""
    strikes = sorted({float(c.strike) for c in contracts if float(c.strike) > 0})
    if not strikes or spot <= 0:
        return strikes
    lo = spot * (1.0 - window_pct)
    hi = spot * (1.0 + window_pct)
    filtered = [s for s in strikes if lo <= s <= hi]
    return filtered if filtered else strikes


def _delta_notional_curve(
    contracts: Sequence[_OptionLike],
    eval_strikes: Sequence[float],
    as_of: date,
    *,
    r: float,
    q: float,
) -> tuple[list[float], list[float]]:
    """Dealer delta notional at each hypothetical spot S' (short-customer sign).

    DN(S') = Σ_i [ -Δ_BS(S', K_i, T, r, σ_i) × OI_i × 100 × S' ]
    """
    usable = [
        c
        for c in contracts
        if int(c.open_interest or 0) > 0 and float(c.iv or 0) > 0 and float(c.strike) > 0
    ]
    if not usable or not eval_strikes:
        return list(eval_strikes), [0.0] * len(eval_strikes)

    strikes_out: list[float] = []
    notionals: list[float] = []
    for s_prime in eval_strikes:
        S = float(s_prime)
        total = 0.0
        for c in usable:
            T = _years_to_expiry(c.expiry, as_of)
            is_call = str(c.cp).upper().startswith("C")
            delta = bs_delta(S, float(c.strike), T, float(c.iv), call=is_call, r=r, q=q)
            # Dealers short customer OI → flip customer delta.
            total += -delta * int(c.open_interest) * _CONTRACT_MULT * S
        strikes_out.append(S)
        notionals.append(total)
    return strikes_out, notionals


def build_vanna_model(
    contracts: Sequence[_OptionLike],
    spot: float,
    as_of: date | None = None,
    *,
    r: float = 0.05,
    q: float = 0.0,
    window_pct: float = VANNA_WINDOW_PCT,
) -> dict[str, dict[str, list[float]]]:
    """Per-expiry OI Vanna Model curves: Delta Notional vs hypothetical spot.

    Returns ``{ "YYYY-MM-DD": { "strikes": [...], "delta_notional": [...] } }``.
    """
    as_of = as_of or date.today()
    S = float(spot or 0)
    if S <= 0 or not contracts:
        return {}

    by_expiry: dict[date, list[_OptionLike]] = defaultdict(list)
    for c in contracts:
        by_expiry[c.expiry].append(c)

    out: dict[str, dict[str, list[float]]] = {}
    for expiry in sorted(by_expiry):
        group = by_expiry[expiry]
        levels = _vanna_eval_strikes(group, S, window_pct=window_pct)
        strikes, dn = _delta_notional_curve(group, levels, as_of, r=r, q=q)
        if not strikes:
            continue
        out[expiry.isoformat()] = {
            "strikes": strikes,
            "delta_notional": dn,
        }
    return out


def parse_as_of(value: str | date | datetime | None) -> date:
    """Best-effort parse of as-of date for GEX rebuilds."""
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value:
        try:
            return date.fromisoformat(value[:10])
        except ValueError:
            pass
    return date.today()
