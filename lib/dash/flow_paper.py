"""Observed option quotes, one-contract paper positions, and causal replay."""

from __future__ import annotations

import json
import math
import os
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from lib.dash import flow_store

_lock = threading.RLock()


def _positive(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number > 0 else None


def _nonnegative(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) and number >= 0 else None


def _stamp(value: Any) -> str:
    stamp = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    if stamp.tzinfo is None:
        stamp = stamp.astimezone()
    return stamp.astimezone(timezone.utc).isoformat(timespec="seconds")


def contract_key(expiry: str, cp: str, strike: float) -> str:
    return f"{expiry}|{cp}|{strike:g}"


def snapshot_from_report(payload: Mapping[str, Any]) -> dict:
    """Keep only observed fields; zero or absent quotes remain unavailable."""
    reports = payload.get("reports") or []
    report = reports[0] if reports else {}
    ticker = flow_store.normalize_ticker(report.get("ticker"))
    if not ticker:
        raise ValueError("Snapshot needs a ticker")
    stamp = _stamp(payload.get("generated_at"))
    contracts = []
    for expiry, rows in (report.get("option_chains") or {}).items():
        date.fromisoformat(str(expiry))
        for row in rows:
            strike = _positive(row.get("strike"))
            if strike is None:
                continue
            for cp, side_name in (("C", "call"), ("P", "put")):
                side = row.get(side_name)
                if not isinstance(side, Mapping):
                    continue
                contracts.append({
                    "key": contract_key(str(expiry), cp, strike),
                    "expiry": str(expiry), "cp": cp, "strike": strike,
                    "bid": _positive(side.get("bid")),
                    "ask": _positive(side.get("ask")),
                    "volume": _nonnegative(side.get("volume")),
                    "open_interest": _nonnegative(side.get("open_interest")),
                })
    return {"ticker": ticker, "observed_at": stamp,
            "underlying": _positive(report.get("spot")), "contracts": contracts}


def _path(ticker: str) -> Path:
    return flow_store.FLOW_DIR.parent / "flow-paper" / f"{flow_store._stem(ticker)}.json"


def _read(ticker: str) -> dict:
    try:
        data = json.loads(_path(ticker).read_text(encoding="utf-8"))
    except (OSError, ValueError):
        data = {}
    return {"snapshots": data.get("snapshots", []), "positions": data.get("positions", [])}


def _write(ticker: str, data: dict) -> None:
    path = _path(ticker)
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(data, allow_nan=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def load(ticker: str) -> dict:
    with _lock:
        return _read(ticker)


def add_snapshot(snapshot: Mapping[str, Any]) -> bool:
    """Archive one scan/import; duplicate timestamps are idempotent."""
    ticker = flow_store.normalize_ticker(snapshot.get("ticker"))
    if not ticker:
        raise ValueError("Snapshot needs a ticker")
    stamp = _stamp(snapshot.get("observed_at"))
    clean = snapshot_from_report({"generated_at": stamp, "reports": [{
        "ticker": ticker, "spot": snapshot.get("underlying"),
        "option_chains": _chains_from_contracts(snapshot.get("contracts") or []),
    }]})
    with _lock:
        data = _read(ticker)
        if any(s.get("observed_at") == stamp for s in data["snapshots"]):
            return False
        data["snapshots"].append(clean)
        data["snapshots"].sort(key=lambda s: s["observed_at"])
        _write(ticker, data)
    return True


def _chains_from_contracts(contracts: list) -> dict:
    chains: dict[str, dict[float, dict]] = {}
    for contract in contracts:
        expiry = str(contract["expiry"])
        date.fromisoformat(expiry)
        cp = str(contract["cp"]).upper()
        strike = _positive(contract["strike"])
        if cp not in ("C", "P") or strike is None:
            raise ValueError("Invalid option contract")
        row = chains.setdefault(expiry, {}).setdefault(strike, {"strike": strike})
        row["call" if cp == "C" else "put"] = contract
    return {exp: list(rows.values()) for exp, rows in chains.items()}


def quote(snapshot: Mapping[str, Any], key: str) -> dict | None:
    return next((c for c in snapshot.get("contracts", []) if c.get("key") == key), None)


def buy(ticker: str, snapshot: Mapping[str, Any], key: str, *, fee: float = 0,
        multiplier: int = 100) -> dict:
    fee = _nonnegative(fee)
    if fee is None or not isinstance(multiplier, int) or multiplier <= 0:
        raise ValueError("Fee and multiplier must be nonnegative and positive")
    contract = quote(snapshot, key)
    if not contract or not _positive(contract.get("ask")):
        raise ValueError("Observed ask is missing; cannot simulate a purchase")
    if flow_store.normalize_ticker(snapshot.get("ticker")) != flow_store.normalize_ticker(ticker):
        raise ValueError("Snapshot ticker does not match")
    if datetime.fromisoformat(snapshot["observed_at"]).date() > date.fromisoformat(contract["expiry"]):
        raise ValueError("Cannot enter a contract after expiry")
    position = {"id": uuid.uuid4().hex, "ticker": flow_store.normalize_ticker(ticker),
                "contract": key, "expiry": contract["expiry"], "cp": contract["cp"],
                "strike": contract["strike"], "opened_at": snapshot["observed_at"],
                "entry_ask": contract["ask"], "multiplier": multiplier,
                "entry_fee": fee, "max_loss": contract["ask"] * multiplier + fee,
                "status": "open"}
    with _lock:
        data = _read(ticker)
        data["positions"].append(position)
        _write(ticker, data)
    return position


def record_historical_entry(ticker: str, snapshot: Mapping[str, Any], key: str,
                            premium: float, *, fee: float = 0, multiplier: int = 100) -> dict:
    """Record a known historical premium when the snapshot has no usable ask."""
    contract = quote(snapshot, key)
    price = _positive(premium)
    charge = _nonnegative(fee)
    if not contract or price is None or charge is None or multiplier <= 0:
        raise ValueError("A contract, positive entry premium, and nonnegative fee are required")
    if _positive(contract.get("ask")) is not None:
        raise ValueError("An observed ask exists; use the paper buy instead")
    if snapshot.get("ticker") != flow_store.normalize_ticker(ticker):
        raise ValueError("Snapshot ticker does not match")
    if datetime.fromisoformat(snapshot["observed_at"]).date() > date.fromisoformat(contract["expiry"]):
        raise ValueError("Cannot enter a contract after expiry")
    position = {"id": uuid.uuid4().hex, "ticker": snapshot["ticker"],
                "contract": key, "expiry": contract["expiry"], "cp": contract["cp"],
                "strike": contract["strike"], "opened_at": snapshot["observed_at"],
                "entry_ask": price, "entry_source": "imported historical premium",
                "multiplier": multiplier, "entry_fee": charge,
                "max_loss": price * multiplier + charge, "status": "open"}
    with _lock:
        data = _read(ticker)
        data["positions"].append(position)
        _write(ticker, data)
    return position


def valuation(position: Mapping[str, Any], bid: Any) -> float | None:
    price = _positive(bid)
    if price is None:
        return None
    return round((price - position["entry_ask"]) * position["multiplier"] - position["entry_fee"], 2)


def expiry_pnl(position: Mapping[str, Any], settlement: float) -> float:
    spot = _nonnegative(settlement)
    if spot is None:
        raise ValueError("Settlement price is required")
    intrinsic = max(spot - position["strike"], 0) if position["cp"] == "C" else max(position["strike"] - spot, 0)
    return round(intrinsic * position["multiplier"] - position["max_loss"], 2)


def break_even(position: Mapping[str, Any]) -> float:
    cost = position["max_loss"] / position["multiplier"]
    return position["strike"] + cost if position["cp"] == "C" else position["strike"] - cost


def close(ticker: str, position_id: str, snapshot: Mapping[str, Any], *, fee: float = 0) -> dict:
    fee = _nonnegative(fee)
    if fee is None:
        raise ValueError("Closing fee must be nonnegative")
    with _lock:
        data = _read(ticker)
        position = next((p for p in data["positions"] if p["id"] == position_id and p["status"] == "open"), None)
        if position is None:
            raise ValueError("Open position not found")
        if snapshot.get("ticker") != position["ticker"] or snapshot["observed_at"] <= position["opened_at"]:
            raise ValueError("A close needs a later observation for this ticker")
        contract = quote(snapshot, position["contract"])
        bid = _positive(contract.get("bid")) if contract else None
        if bid is None:
            raise ValueError("Observed bid is missing; cannot simulate a close")
        position.update(status="closed", closed_at=snapshot["observed_at"], exit_bid=bid,
                        exit_fee=fee, pnl=round((bid - position["entry_ask"]) * position["multiplier"] - position["entry_fee"] - fee, 2))
        _write(ticker, data)
        return position


def settle(ticker: str, position_id: str, price: float, source: str, verified_at: str) -> dict:
    """Record a user verified expiry settlement; never infer it from a spot bar."""
    if not source.strip():
        raise ValueError("Settlement source is required")
    stamp = _stamp(verified_at)
    with _lock:
        data = _read(ticker)
        position = next((p for p in data["positions"] if p["id"] == position_id and p["status"] == "open"), None)
        if position is None:
            raise ValueError("Open position not found")
        if datetime.fromisoformat(stamp).date() < date.fromisoformat(position["expiry"]):
            raise ValueError("Settlement observation predates expiry")
        pnl = expiry_pnl(position, price)
        position.update(status="expired", settlement_price=float(price), settlement_source=source.strip(),
                        settlement_verified_at=stamp, pnl=pnl)
        _write(ticker, data)
        return position
