"""Historical option chains and replays for the Flow Scanner, built from ThetaData EOD.

Two things are kept on disk under ``state/flow-history/<TICKER>/``:

* ``chain-YYYY-MM-DD.json`` — every contract quoted on one past trading day.
  A past day never changes, so a cached chain is reused until **Load history**
  is asked again with a refresh.
* ``replays.json`` — one entry per strategy sent from a historical chain to
  paper trading: the legs, the entry observation and one snapshot per trading
  day from entry through expiry (or the last day the plan can return). The
  snapshots use the same shape as ``flow_paper`` snapshots, so the paper
  simulator and its replay controls work on them unchanged.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from datetime import date, datetime, timezone
from pathlib import Path
from typing import Any, Mapping

from lib.dash import flow_store
from lib.dash.flow_dates import display_date
from lib.fetch_errors import DataFetchError
from lib.options import theta_history

HISTORY_DIR = flow_store.FLOW_DIR.parent / "flow-history"
MAX_REPLAYS = 20

_lock = threading.RLock()


def _dir(ticker: str) -> Path:
    return HISTORY_DIR / flow_store._stem(ticker)


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_name(f".{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        temporary.write_text(json.dumps(payload, allow_nan=False), encoding="utf-8")
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def _read_json(path: Path) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def contract_key(expiry: str, cp: str, strike: float) -> str:
    # Same format as flow_paper.contract_key; kept here to avoid an import cycle.
    return f"{expiry}|{cp}|{strike:g}"


def parse_key(key: str) -> tuple[str, str, float]:
    expiry, cp, strike = str(key).split("|")
    date.fromisoformat(expiry)
    if cp not in ("C", "P"):
        raise ValueError("Option right must be C or P")
    return expiry, cp, float(strike)


def _as_date(value: date | str) -> date:
    return value if isinstance(value, date) else date.fromisoformat(str(value)[:10])


def check_trade_date(trade_date: date | str, *, today: date | None = None) -> date:
    """The date as a ``date``, refused when the configured plan cannot return it."""
    day = _as_date(trade_date)
    first, last = theta_history.history_window(today)
    if day > last:
        raise ValueError(f"Choose a date up to {last.strftime('%d/%m/%Y')}: ThetaData's free plan is one day delayed.")
    if day < first:
        raise ValueError(f"Choose a date from {first.strftime('%d/%m/%Y')}: the configured ThetaData plan "
                         f"returns {theta_history.HISTORY_DAYS} days of history.")
    if day.weekday() >= 5:
        raise ValueError(f"{day.strftime('%d/%m/%Y')} is a weekend. Choose a trading day.")
    return day


def _clean_quote(row: Mapping[str, Any]) -> dict:
    return {"key": contract_key(row["expiry"], row["cp"], row["strike"]),
            "expiry": row["expiry"], "cp": row["cp"], "strike": row["strike"],
            "bid": row.get("bid"), "ask": row.get("ask"), "volume": row.get("volume"),
            "open_interest": None, "multiplier": row.get("multiplier") or theta_history.STANDARD_MULTIPLIER,
            "observed_at": row["observed_at"]}


def _underlying(ticker: str, start: date, end: date) -> dict[str, float]:
    try:
        return theta_history.stock_eod(ticker, start, end)
    except theta_history.ThetaUnavailable:
        raise
    except DataFetchError:
        # The chain is still usable without the underlying close; the chart just has no "now" line.
        return {}


def load_chain(ticker: str, trade_date: date | str, *, refresh: bool = False,
               today: date | None = None) -> dict:
    """Every contract quoted on ``trade_date``, cached on disk once fetched."""
    symbol = flow_store.normalize_ticker(ticker)
    day = check_trade_date(trade_date, today=today)
    path = _dir(symbol) / f"chain-{day.isoformat()}.json"
    if not refresh:
        cached = _read_json(path)
        if isinstance(cached, dict) and cached.get("contracts"):
            return cached
    rows = theta_history.option_eod(symbol, day, day, expiration="*")
    contracts = [_clean_quote(r) for r in rows if r["date"] == day.isoformat()]
    if not contracts:
        raise ValueError(f"ThetaData has no option quotes for {symbol} on {day.strftime('%d/%m/%Y')}. "
                         "It may have been a market holiday, or the symbol had no listed options.")
    contracts.sort(key=lambda c: (c["expiry"], c["strike"], c["cp"]))
    record = {"ticker": symbol, "date": day.isoformat(),
              "observed_at": max(c["observed_at"] for c in contracts),
              "underlying": _underlying(symbol, day, day).get(day.isoformat()),
              "source": theta_history.SOURCE_LABEL, "contracts": contracts}
    with _lock:
        _write_json(path, record)
    return record


def cached_chain(ticker: str, trade_date: date | str) -> dict | None:
    record = _read_json(_dir(ticker) / f"chain-{_as_date(trade_date).isoformat()}.json")
    return record if isinstance(record, dict) and record.get("contracts") else None


def chain_report(record: Mapping[str, Any]) -> dict:
    """A historical chain in the report shape ``flow_chain`` renders."""
    chains: dict[str, dict[float, dict]] = {}
    for c in record.get("contracts") or []:
        row = chains.setdefault(c["expiry"], {}).setdefault(c["strike"], {"strike": c["strike"]})
        row["call" if c["cp"] == "C" else "put"] = {
            "bid": c.get("bid"), "ask": c.get("ask"), "volume": c.get("volume"),
            "open_interest": None, "multiplier": c.get("multiplier") or 100,
            "observed_at": c.get("observed_at"),
        }
    return {
        "ticker": record["ticker"], "spot": record.get("underlying"),
        "option_chains": {exp: [rows[k] for k in sorted(rows)] for exp, rows in sorted(chains.items())},
        "contracts": [],
        "historical": {"date": record["date"], "observed_at": record["observed_at"],
                       "source": record.get("source") or theta_history.SOURCE_LABEL},
    }


# --- replays --------------------------------------------------------------

def _replays_path(ticker: str) -> Path:
    return _dir(ticker) / "replays.json"


def list_replays(ticker: str) -> list[dict]:
    data = _read_json(_replays_path(ticker))
    return list(data.get("replays", [])) if isinstance(data, dict) else []


def load_replay(ticker: str, replay_id: str | None) -> dict | None:
    if not replay_id:
        return None
    return next((r for r in list_replays(ticker) if r.get("id") == replay_id), None)


def find_replay_by_nonce(ticker: str, nonce: Any) -> dict | None:
    if nonce in (None, ""):
        return None
    return next((r for r in list_replays(ticker) if r.get("nonce") == nonce), None)


def replay_label(replay: Mapping[str, Any]) -> str:
    legs = replay.get("legs") or []
    names = ", ".join(f"{'Buy' if leg['side'] == 'buy' else 'Sell'} {leg['qty']} "
                      f"{'Call' if leg['cp'] == 'C' else 'Put'} {leg['strike']:g}" for leg in legs)
    return f"{display_date(replay['trade_date'])} → {display_date(replay['last_available'])} · {names}"


def _normalise_legs(legs: list[Mapping[str, Any]]) -> list[dict]:
    if not isinstance(legs, list) or not 1 <= len(legs) <= 4:
        raise ValueError("Choose 1–4 option legs")
    out, seen, expiry = [], set(), None
    for leg in legs:
        key = str(leg.get("key") or "")
        leg_expiry, cp, strike = parse_key(key)
        side = str(leg.get("side") or "buy").lower()
        qty = leg.get("qty", 1)
        if key in seen or side not in ("buy", "sell") or not isinstance(qty, int) or isinstance(qty, bool) or not 1 <= qty <= 100:
            raise ValueError("Each leg needs a unique option, Buy or Sell, and 1–100 contracts")
        if expiry is not None and leg_expiry != expiry:
            raise ValueError("All strategy legs must have the same expiry")
        expiry = leg_expiry
        seen.add(key)
        out.append({"key": contract_key(leg_expiry, cp, strike), "expiry": leg_expiry, "cp": cp,
                    "strike": strike, "side": side, "qty": qty})
    return out


def build_replay(ticker: str, trade_date: date | str, legs: list[Mapping[str, Any]], *,
                 nonce: Any = None, today: date | None = None) -> dict:
    """Daily observations of the chosen legs from ``trade_date`` through expiry.

    History stops at the earlier of the contract expiry and the last day the plan
    returns; ``ended_early`` says the replay stops short of expiry. A trading day
    with no quote for a leg is kept and listed in that snapshot's ``missing``.
    """
    symbol = flow_store.normalize_ticker(ticker)
    entry = check_trade_date(trade_date, today=today)
    legs = _normalise_legs(legs)
    expiry = date.fromisoformat(legs[0]["expiry"])
    if expiry < entry:
        raise ValueError("This contract had already expired on the chosen date")
    _, window_end = theta_history.history_window(today)
    end = min(expiry, window_end)

    by_leg: dict[str, dict[str, dict]] = {}
    for leg in legs:
        rows = theta_history.option_eod(symbol, entry, end, expiration=leg["expiry"],
                                        strike=leg["strike"], right=leg["cp"])
        by_leg[leg["key"]] = {r["date"]: _clean_quote(r) for r in rows
                              if contract_key(r["expiry"], r["cp"], r["strike"]) == leg["key"]}
    chain = cached_chain(symbol, entry)
    if chain:
        for c in chain["contracts"]:
            if c["key"] in by_leg:
                by_leg[c["key"]][entry.isoformat()] = c
    if not any(entry.isoformat() in days for days in by_leg.values()):
        raise ValueError(f"No ThetaData quote for these options on {entry.strftime('%d/%m/%Y')}")

    quoted_days = {d for days in by_leg.values() for d in days}
    last_available = max(quoted_days)
    closes = _underlying(symbol, entry, end)
    calendar = sorted({d for d in closes if entry.isoformat() <= d <= last_available} | quoted_days)

    snapshots = []
    for day in calendar:
        contracts, missing = [], []
        for leg in legs:
            q = by_leg[leg["key"]].get(day)
            if q is None:
                missing.append({"key": leg["key"], "what": "no quote"})
                continue
            contracts.append(q)
            gaps = [side for side in ("bid", "ask") if not q.get(side)]
            if gaps:
                missing.append({"key": leg["key"], "what": "no " + " or ".join(gaps)})
        stamps = [c["observed_at"] for c in contracts]
        observed = max(stamps) if stamps else theta_history.observation_stamp(None, day)[1]
        snapshots.append({"ticker": symbol, "observed_at": observed, "date": day,
                          "underlying": closes.get(day), "contracts": contracts, "missing": missing})

    replay = {
        "id": uuid.uuid4().hex, "ticker": symbol, "nonce": nonce,
        "source": theta_history.SOURCE_LABEL,
        "trade_date": entry.isoformat(), "expiry": expiry.isoformat(),
        "last_available": last_available,
        "ended_early": date.fromisoformat(last_available) < expiry,
        "legs": legs, "snapshots": snapshots,
        "created_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
    }
    with _lock:
        replays = [r for r in list_replays(symbol) if r.get("id") != replay["id"]]
        replays.append(replay)
        _write_json(_replays_path(symbol), {"replays": replays[-MAX_REPLAYS:]})
    return replay
