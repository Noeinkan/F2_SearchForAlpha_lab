"""Flow strategy panel: legs picked from the option chain or typed by hand, priced by lib.options.pricing.

A row is one leg as the panel's table holds it. Rows added from the chain also carry the quote they
came from (`key`, `bid`, `ask`), which is what lets them go to paper trading; editing a row's strike
or call/put turns it into a hypothetical leg, and only legs that still match a quote can be traded.
"""

from __future__ import annotations

import math
from datetime import date
from typing import Any, Mapping

from lib.options.pricing import (
    MULTIPLIER, Leg, implied_vol, net_premium, payoff_at, payoff_summary, price_option, strategy_legs,
)

MAX_CHAIN_LEGS = 4
DEFAULT_IV_PCT = 20.0
GREEKS = ("delta", "gamma", "theta", "vega", "rho")
PRESETS = (("Long call", "long_call"), ("Long put", "long_put"),
           ("Bull call spread", "bull_call_spread"), ("Iron condor", "iron_condor"))


def _num(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def iv_percent(raw: Any) -> float | None:
    """Chain IV as a percentage; Yahoo sends a fraction (0.315), so anything up to 2 is scaled."""
    iv = _num(raw)
    if iv is None or iv <= 0:
        return None
    return round(iv * 100 if iv <= 2 else iv, 2)


def days_between(expiry: str | None, as_of: date) -> int:
    try:
        return max((date.fromisoformat(str(expiry)[:10]) - as_of).days, 0)
    except ValueError:
        return 0


def chain_row(leg: Mapping[str, Any]) -> dict:
    """Table row for a quote clicked in the chain: one bought contract at the ask."""
    return {"quantity": 1, "kind": "call" if leg.get("cp") == "C" else "put",
            "strike": _num(leg.get("strike")), "premium": _num(leg.get("ask")),
            "iv": iv_percent(leg.get("iv")), "key": leg.get("key"),
            "bid": _num(leg.get("bid")), "ask": _num(leg.get("ask")),
            "multiplier": int(_num(leg.get("multiplier")) or MULTIPLIER)}


def add_chain_leg(rows: list[dict] | None, context: Mapping[str, Any] | None,
                  leg: Mapping[str, Any]) -> tuple[list[dict], dict, bool]:
    """Append a chain quote. Returns (rows, context, started_over); raises ValueError on a rule break.

    Another ticker, or a table with no chain leg left, starts a new strategy from this quote.
    """
    rows = list(rows or [])
    context = dict(context or {})
    if not (_num(leg.get("strike")) or 0) > 0 or not (_num(leg.get("ask")) or 0) > 0 or not leg.get("expiry"):
        raise ValueError("This quote needs a valid ask, strike and expiry.")
    chain_rows = [row for row in rows if row.get("key")]
    observed = leg.get("observed") or ""
    fresh = context.get("ticker") != leg.get("ticker") or not chain_rows
    if not fresh:
        if (context.get("observed") or "") != observed:
            raise ValueError("Keep every option on the same observation: remove the current chain legs "
                             "to start from " + ("that historical date." if observed else "current quotes."))
        if context.get("expiry") != leg.get("expiry"):
            raise ValueError("Choose options with the same expiry, or remove the current chain legs first.")
        if any(row.get("key") == leg.get("key") for row in rows):
            raise ValueError("That option is already in the strategy. Change its quantity in the table.")
        if len(chain_rows) >= MAX_CHAIN_LEGS:
            raise ValueError(f"A chain strategy holds up to {MAX_CHAIN_LEGS} options. Remove one to add another.")
    context = {"ticker": leg.get("ticker"), "expiry": leg.get("expiry"), "observed": observed,
               "trade_date": leg.get("trade_date") or "", "spot": _num(leg.get("spot"))}
    return ([] if fresh else rows) + [chain_row(leg)], context, fresh


def apply_edit(rows: list[dict] | None, previous: list[dict] | None) -> list[dict]:
    """Keep chain rows honest after a table edit.

    Flipping a chain leg between long and short re-prices it at the other side of the quote
    (buy at ask, sell at bid). Changing its strike or call/put detaches it from the quote.
    """
    rows = [dict(row) for row in rows or []]
    if not previous or len(previous) != len(rows):
        return rows
    for row, before in zip(rows, previous):
        if not row.get("key"):
            continue
        if row.get("strike") != before.get("strike") or row.get("kind") != before.get("kind"):
            row.update(key=None, bid=None, ask=None)
            continue
        qty, old_qty = _num(row.get("quantity")) or 0, _num(before.get("quantity")) or 0
        if qty * old_qty < 0 and row.get("premium") == before.get("premium"):
            quote = row.get("ask") if qty > 0 else row.get("bid")
            if quote:
                row["premium"] = quote
    return rows


def preset_rows(preset: str, *, spot: float, days: float, rate_pct: float, yield_pct: float) -> list[dict]:
    """Template legs around spot, priced at the theoretical value with a 20% IV."""
    rows = []
    for leg in strategy_legs(preset, spot, iv=DEFAULT_IV_PCT / 100):
        value = price_option(spot=spot, strike=leg.strike, days=days, iv=leg.iv, kind=leg.kind,
                             rate=rate_pct / 100, yield_rate=yield_pct / 100)["value"]
        rows.append({"quantity": leg.quantity, "kind": leg.kind, "strike": leg.strike,
                     "premium": round(float(value), 2), "iv": DEFAULT_IV_PCT, "key": None,
                     "bid": None, "ask": None, "multiplier": MULTIPLIER})
    return rows


def blank_row(spot: float | None) -> dict:
    return {"quantity": 1, "kind": "call", "strike": round(spot, 2) if spot else None, "premium": 0,
            "iv": DEFAULT_IV_PCT, "key": None, "bid": None, "ask": None, "multiplier": MULTIPLIER}


def _legs(rows: list[dict]) -> list[Leg]:
    legs = []
    for number, row in enumerate(rows, start=1):
        qty, strike, premium = _num(row.get("quantity")), _num(row.get("strike")), _num(row.get("premium"))
        if qty is None or not qty.is_integer() or qty == 0:
            raise ValueError(f"Leg {number}: quantity must be a whole number, + to buy or − to sell.")
        if strike is None or strike <= 0 or premium is None or premium < 0:
            raise ValueError(f"Leg {number}: enter a positive strike and a premium of 0 or more.")
        if row.get("kind") not in ("call", "put"):
            raise ValueError(f"Leg {number}: choose call or put.")
        legs.append(Leg(int(qty), row["kind"], strike, premium, 0.0,
                        int(_num(row.get("multiplier")) or MULTIPLIER)))
    return legs


def analyze(rows: list[dict] | None, *, spot: Any, days: Any, rate_pct: Any, yield_pct: Any) -> dict:
    """Expiry payoff, entry cash and Greeks for the table. Raises ValueError with a readable message."""
    if not rows:
        raise ValueError("No legs yet. Add a quote from the option chain, pick a template, or add a leg.")
    spot, days, rate, q = _num(spot), _num(days), _num(rate_pct), _num(yield_pct)
    if spot is None or spot <= 0 or days is None or days < 0 or rate is None or q is None:
        raise ValueError("Enter a positive spot, days to expiry (0 or more), rate and dividend yield.")
    legs = _legs(rows)
    summary = payoff_summary(legs)
    notes, priced = [], []
    for row, leg in zip(rows, legs):
        iv_pct = _num(row.get("iv"))
        solved = False
        if iv_pct is None or iv_pct <= 0:
            iv = implied_vol(leg.premium, spot=spot, strike=leg.strike, days=days, kind=leg.kind,
                             rate=rate / 100, yield_rate=q / 100)
            solved = iv is not None
        else:
            iv = iv_pct / 100
        greeks = price_option(spot=spot, strike=leg.strike, days=days, iv=iv, kind=leg.kind,
                              rate=rate / 100, yield_rate=q / 100) if iv is not None else None
        priced.append({"leg": leg, "iv": iv, "solved": solved, "greeks": greeks})
    if any(p["solved"] for p in priced):
        notes.append("IV marked * was solved from the premium, because the quote carried none.")
    if any(p["iv"] is None for p in priced):
        notes.append("Greeks need an IV: type one for the legs showing —.")
    if any((row.get("bid") or 0) > (row.get("ask") or math.inf) for row in rows):
        notes.append("One or more quotes are crossed (bid above ask): those prices may not be executable.")
    complete = all(p["greeks"] and p["greeks"]["delta"] is not None for p in priced)
    totals = {name: sum(p["greeks"][name] * p["leg"].multiplier * p["leg"].quantity for p in priced)
              for name in GREEKS} if complete else None
    return {"legs": legs, "summary": summary, "net_premium": net_premium(legs), "priced": priced,
            "totals": totals, "notes": notes, "spot": spot}


def curve(legs: list[Leg], spot: float, break_evens: list[float]) -> tuple[list[float], list[float]]:
    """Exact expiry P/L at the kinks plus an even grid, from below the lowest strike to above the highest."""
    strikes = sorted({leg.strike for leg in legs})
    pad = max((strikes[-1] - strikes[0]) * 0.5, spot * 0.15, max(leg.premium for leg in legs) * 3, 1.0)
    low = max(0.0, min(strikes[0], spot) - pad)
    high = max(strikes[-1], spot) + pad
    grid = [low + (high - low) * i / 120 for i in range(121)]
    xs = sorted({*grid, *(x for x in strikes + list(break_evens) if low <= x <= high)})
    return xs, [payoff_at(x, legs) for x in xs]


def paper_selection(rows: list[dict] | None, context: Mapping[str, Any] | None, nonce: int) -> dict:
    """Payload for flow-paper-strategy-selection. Raises ValueError when the table is not tradable."""
    rows = rows or []
    context = context or {}
    if not rows:
        raise ValueError("Add legs from the option chain first.")
    if any(not row.get("key") for row in rows):
        raise ValueError("Only legs taken from the option chain can go to paper trading. "
                         "Remove the typed or edited legs first.")
    legs = []
    for row in rows:
        qty = _num(row.get("quantity"))
        if qty is None or not qty.is_integer() or qty == 0 or abs(qty) > 100:
            raise ValueError("Paper trading needs 1 to 100 contracts per leg.")
        legs.append({"key": row["key"], "side": "buy" if qty > 0 else "sell", "qty": int(abs(qty))})
    historical = bool(context.get("observed"))
    return {"ticker": context.get("ticker"), "expiry": context.get("expiry"), "legs": legs, "nonce": nonce,
            "source": "historical" if historical else "current",
            "trade_date": context.get("trade_date") if historical else None,
            "observed_at": context.get("observed") if historical else None}
