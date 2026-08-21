"""
Execution-layer parameters for unified search spaces.

Indicator flat keys live in ``lib.agent_strategy.PARAM_KEY_MAP``. Execution
keys are orthogonal: they do not regenerate signals, they only change how
``lib.strategy.backtest`` sizes and exits trades.

Bundles may put these keys directly in ``search_space``, or callers can merge
the shared ``execution_search_space`` from ``strategy_config.yaml``.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from lib.agent_strategy import PARAM_KEY_MAP

# Flat keys that override run_backtest_result kwargs (not backtest() itself).
_BUNDLE_OVERRIDE_KEYS = frozenset({"signal_logic", "signal_window"})

# Flat key -> backtest() kwarg name (identity for most).
_EXECUTION_KWARG_MAP: dict[str, str] = {
    "min_holding_period": "min_holding_period",
    "trailing_stop_loss": "trailing_stop_loss",
    "stop_mode": "stop_mode",
    "position_scaling": "position_scaling",
    "take_profit": "take_profit",
    "consecutive_signal_mode": "consecutive_signal_mode",
    "cooldown_bars": "cooldown_bars",
    "commission_per_trade": "commission_per_trade",
    "slippage_pct": "slippage_pct",
    "fx_fee_pct": "fx_fee_pct",
    "amount_per_buy": "amount_per_buy",
    "position_size_pct": "position_size_pct",
    "use_low_for_stops": "use_low_for_stops",
    "gap_fills": "gap_fills",
    "allow_fractional": "allow_fractional",
}

_KELLY_KEYS = frozenset({"kelly_win_rate", "kelly_win_loss_ratio"})

EXECUTION_PARAM_KEYS: frozenset[str] = (
    frozenset(_EXECUTION_KWARG_MAP)
    | _KELLY_KEYS
    | _BUNDLE_OVERRIDE_KEYS
)

# Compact shared grid defaults (fractions, not UI percentages).
DEFAULT_EXECUTION_SEARCH_SPACE: dict[str, dict[str, Any]] = {
    "min_holding_period": {"type": "int", "low": 0, "high": 10, "step": 5},
    "trailing_stop_loss": {"type": "float", "low": 0.03, "high": 0.10, "step": 0.01},
    "take_profit": {"type": "float", "low": 0.0, "high": 0.15, "step": 0.05},
    "position_scaling": {"type": "float", "low": 0.25, "high": 1.0, "step": 0.25},
    "stop_mode": {"type": "categorical", "choices": ["percent", "atr"]},
    "consecutive_signal_mode": {
        "type": "categorical",
        "choices": ["scale_in", "edge", "cooldown"],
    },
    "cooldown_bars": {"type": "int", "low": 0, "high": 10, "step": 5},
}


@dataclass(frozen=True)
class PartitionedParams:
    """Split a flat trial/live param map into engine-ready pieces."""

    indicator_params: dict[str, Any]
    backtest_kwargs: dict[str, Any]
    signal_logic: str | None = None
    signal_window: int | None = None


def is_execution_key(key: str) -> bool:
    return key in EXECUTION_PARAM_KEYS


def is_indicator_key(key: str) -> bool:
    return key in PARAM_KEY_MAP


def partition_params(params: dict[str, Any] | None) -> PartitionedParams:
    """Split flat params into indicator settings input and backtest kwargs."""
    indicator: dict[str, Any] = {}
    kwargs: dict[str, Any] = {}
    signal_logic: str | None = None
    signal_window: int | None = None
    kelly_win_rate: float | None = None
    kelly_win_loss_ratio: float | None = None

    for key, value in (params or {}).items():
        if key in PARAM_KEY_MAP:
            indicator[key] = value
        elif key == "signal_logic":
            signal_logic = str(value)
        elif key == "signal_window":
            signal_window = int(value)
        elif key == "kelly_win_rate":
            kelly_win_rate = float(value)
        elif key == "kelly_win_loss_ratio":
            kelly_win_loss_ratio = float(value)
        elif key in _EXECUTION_KWARG_MAP:
            kwargs[_EXECUTION_KWARG_MAP[key]] = value

    if kelly_win_rate is not None or kelly_win_loss_ratio is not None:
        kwargs["position_sizing_strategy"] = "kelly_criterion"
        kwargs["position_sizing_params"] = {
            "win_rate": 0.5 if kelly_win_rate is None else float(kelly_win_rate),
            "win_loss_ratio": 1.5 if kelly_win_loss_ratio is None else float(kelly_win_loss_ratio),
        }

    return PartitionedParams(
        indicator_params=indicator,
        backtest_kwargs=kwargs,
        signal_logic=signal_logic,
        signal_window=signal_window,
    )


def load_execution_search_space() -> dict[str, dict[str, Any]]:
    """Return YAML ``execution_search_space`` or the built-in defaults."""
    try:
        from lib.config_loader import get_config

        raw = get_config().get("execution_search_space") or {}
        if isinstance(raw, dict) and raw:
            return {str(k): dict(v) for k, v in raw.items() if isinstance(v, dict)}
    except Exception:
        pass
    return dict(DEFAULT_EXECUTION_SEARCH_SPACE)
