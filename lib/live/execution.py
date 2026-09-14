"""
How the paper runner executes a signal, read from the strategy's ``live_params``.

The order model is the backtest's (lib/orders.py, 3.7), carried over rather than
re-invented: the same ``order_type`` / ``limit_offset_pct`` / ``stop_offset_pct``
/ ``time_in_force`` / ``order_expiry_bars`` keys that ``sfa optimise`` sweeps and
``sfa promote`` writes, and the same price arithmetic (``signal_order_prices`` in
lib/engine/steps.py). What changes live is who enforces what:

    order type, limit and stop prices   sent to the broker (IB LMT / STP / STP LMT)
    gtc, day                            sent to the broker (IB GTC / DAY)
    ioc, order_expiry_bars              enforced by the runner, counting its own bars:
                                        an ``ioc`` order gets exactly one full bar of
                                        range and is then cancelled, as in the
                                        backtest. IB's native IOC would cancel a limit
                                        away from the market on arrival, which the
                                        backtest never does.

A "bar" is whatever the runner receives from the broker, which for IB is a
5-second bar. ROADMAP 8.15 records that this differs from research bars.

Settings the runner cannot honour — exits, sizing, signal gating — make
``sfa run`` refuse to start (:func:`unsupported_live_params`), so a paper track
record is never quietly produced by different rules from the backtest that
justified its promotion.
"""

from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

from lib.engine.steps import signal_order_prices
from lib.live.broker import Order
from lib.orders import ORDER_TYPES, TIME_IN_FORCE

# Backtest defaults (lib/strategy.py ``backtest``), so an absent key means the
# same thing live as it does in research.
DEFAULT_LIMIT_OFFSET = 0.002
DEFAULT_STOP_OFFSET = 0.002
DEFAULT_PRICE_TICK = 0.01

IB_ORDER_TYPES = {"market": "MKT", "limit": "LMT", "stop": "STP", "stop_limit": "STP LMT"}
# ioc goes to IB as DAY: the runner cancels it after one bar (see module docstring).
IB_TIME_IN_FORCE = {"gtc": "GTC", "day": "DAY", "ioc": "DAY"}

# Keys with no effect on a live order: the broker charges real costs in place of
# the simulated ones, and the rest only shape exits that are refused when on.
IGNORED_LIVE_KEYS = frozenset({
    "commission_per_trade",
    "slippage_pct",
    "fx_fee_pct",
    "stop_mode",
    "use_low_for_stops",
    "gap_fills",
    "bracket_stop_pct",
    "bracket_target_pct",
    "allow_fractional",
})


def _off(value: Any) -> bool:
    return value in (None, 0, 0.0, False, "", "0", "false", "False")


# key -> (is the value one the runner reproduces?, what the runner would do instead)
_REFUSED_UNLESS: dict[str, tuple[Any, str]] = {
    "trailing_stop_loss": (_off, "the runner places no trailing stop"),
    "take_profit": (_off, "the runner places no take-profit exit"),
    "trailing_stop_orders": (_off, "the runner places no resting trailing stop"),
    "use_brackets": (_off, "the runner places no bracket orders"),
    "min_holding_period": (_off, "the runner sells on the first sell signal"),
    "cooldown_bars": (_off, "the runner has no cooldown"),
    "consecutive_signal_mode": (lambda v: v in (None, "edge"), "the runner acts on signal edges only"),
    "position_scaling": (lambda v: False, "the runner trades a fixed quantity per signal"),
    "position_size_pct": (lambda v: False, "the runner trades a fixed quantity per signal"),
    "amount_per_buy": (lambda v: v is None, "the runner trades a fixed quantity per signal"),
    "kelly_win_rate": (lambda v: False, "the runner trades a fixed quantity per signal"),
    "kelly_win_loss_ratio": (lambda v: False, "the runner trades a fixed quantity per signal"),
    "signal_logic": (lambda v: v in (None, "or"), "the runner combines signals with OR on the last bar"),
    "signal_window": (_off, "the runner reads the last bar only"),
}


class UnsupportedLiveParams(ValueError):
    """``live_params`` ask for behaviour the paper runner does not reproduce."""

    def __init__(self, problems: dict[str, str]) -> None:
        self.problems = problems
        listed = "; ".join(f"{key}: {why}" for key, why in problems.items())
        super().__init__(f"live_params the paper runner cannot honour: {listed}")


def unsupported_live_params(params: dict[str, Any] | None) -> dict[str, str]:
    """``{key: reason}`` for every setting the runner would silently not apply."""
    problems: dict[str, str] = {}
    for key, value in (params or {}).items():
        rule = _REFUSED_UNLESS.get(key)
        if rule is None:
            continue
        reproduces, instead = rule
        if not reproduces(value):
            problems[key] = f"{value!r} is set, but {instead}"
    return problems


@dataclass(frozen=True)
class LiveOrderModel:
    """The order model of one strategy. Attribute names match ``EngineConfig``
    so ``signal_order_prices`` reads it exactly as it reads a backtest's."""

    order_type: str = "market"
    limit_offset: float = DEFAULT_LIMIT_OFFSET
    stop_offset: float = DEFAULT_STOP_OFFSET
    time_in_force: str = "gtc"
    order_expiry_bars: int = 0
    price_tick: float = DEFAULT_PRICE_TICK

    @classmethod
    def from_live_params(
        cls, params: dict[str, Any] | None, *, price_tick: float = DEFAULT_PRICE_TICK
    ) -> LiveOrderModel:
        """Read and validate the order keys. Raises ``UnsupportedLiveParams``
        for the settings the runner cannot honour, ``ValueError`` for bad values."""
        params = params or {}
        problems = unsupported_live_params(params)
        if problems:
            raise UnsupportedLiveParams(problems)
        order_type = str(params.get("order_type") or "market")
        if order_type not in ORDER_TYPES:
            raise ValueError(f"order_type {order_type!r} is not one of {', '.join(ORDER_TYPES)}")
        tif = str(params.get("time_in_force") or "gtc")
        if tif not in TIME_IN_FORCE:
            raise ValueError(f"time_in_force {tif!r} is not one of {', '.join(TIME_IN_FORCE)}")
        return cls(
            order_type=order_type,
            limit_offset=max(0.0, float(params.get("limit_offset_pct", DEFAULT_LIMIT_OFFSET) or 0)),
            stop_offset=max(0.0, float(params.get("stop_offset_pct", DEFAULT_STOP_OFFSET) or 0)),
            time_in_force=tif,
            order_expiry_bars=max(0, int(params.get("order_expiry_bars") or 0)),
            price_tick=float(price_tick),
        )

    @property
    def rests(self) -> bool:
        return self.order_type != "market"

    @property
    def cancel_after_bars(self) -> int | None:
        """Bars a resting order may stay unfilled before the runner cancels it."""
        limits = [n for n in (1 if self.time_in_force == "ioc" else 0, self.order_expiry_bars) if n > 0]
        return min(limits) if limits else None

    def prices(self, side: str, close: float) -> dict[str, float | None]:
        """Limit / stop / sizing reference for a signal on a bar closing at ``close``,
        rounded to the tick in the direction that never asks for a worse price."""
        raw = signal_order_prices(self, side.lower(), float(close))  # type: ignore[arg-type]
        buy = side.upper() == "BUY"
        limit = raw["limit_price"]
        stop = raw["stop_price"]
        out: dict[str, float | None] = {
            # A buy limit never rounds up (pay more), a sell limit never down.
            "limit_price": None if limit is None else _to_tick(limit, self.price_tick, up=not buy),
            # A buy stop never triggers nearer the market than asked, nor a sell stop.
            "stop_price": None if stop is None else _to_tick(stop, self.price_tick, up=buy),
        }
        out["reference"] = out["limit_price"] if out["limit_price"] is not None else (
            out["stop_price"] if out["stop_price"] is not None else float(close)
        )
        return out

    def broker_order(self, *, symbol: str, side: str, quantity: float, close: float, client_order_id: str) -> Order:
        prices = self.prices(side, close)
        return Order(
            symbol=symbol,
            side=side.upper(),
            quantity=quantity,
            order_type=IB_ORDER_TYPES[self.order_type],
            limit_price=prices["limit_price"],
            stop_price=prices["stop_price"],
            time_in_force=IB_TIME_IN_FORCE[self.time_in_force],
            client_order_id=client_order_id,
        )


def _to_tick(price: float, tick: float, *, up: bool) -> float:
    if tick <= 0:
        return float(price)
    steps = price / tick
    # The epsilon keeps a price already on the tick (100.00 as 99.99999999) put.
    steps = math.ceil(steps - 1e-9) if up else math.floor(steps + 1e-9)
    return round(steps * tick, 10)
