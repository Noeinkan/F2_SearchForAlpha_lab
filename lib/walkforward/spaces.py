"""
Search space resolution for agent strategies.

A bundle's search_space is a flat map of param name to a small descriptor:

    rsi_window: { type: int, low: 5, high: 30 }
    bb_std:     { type: float, low: 1.0, high: 3.0, log: false, step: 0.5 }
    foo:        { type: categorical, choices: [a, b, c] }

This module turns one trial of that space into a Python dict using either an
Optuna trial (TPE sampling) or a deterministic grid enumeration. Reused by the
Bayesian optimiser, grid search, and the walk forward runner.
"""

from __future__ import annotations

import itertools
import math
from typing import Any

import optuna

_DEFAULT_FLOAT_GRID_POINTS = 5


def suggest_from_space(trial: optuna.trial.Trial, space: dict[str, dict[str, Any]]) -> dict[str, Any]:
    """Translate a search_space dict into one set of suggested params for ``trial``."""
    params: dict[str, Any] = {}
    for name, descriptor in (space or {}).items():
        kind = str(descriptor.get("type", "float")).lower()
        if kind == "int":
            params[name] = trial.suggest_int(
                name,
                int(descriptor["low"]),
                int(descriptor["high"]),
                step=int(descriptor.get("step", 1)),
            )
        elif kind == "float":
            step = descriptor.get("step")
            use_log = bool(descriptor.get("log", False))
            # Optuna forbids step+log together; step wins for grid-aligned spaces.
            if step is not None and not use_log:
                params[name] = trial.suggest_float(
                    name,
                    float(descriptor["low"]),
                    float(descriptor["high"]),
                    step=float(step),
                )
            else:
                params[name] = trial.suggest_float(
                    name,
                    float(descriptor["low"]),
                    float(descriptor["high"]),
                    log=use_log,
                )
        elif kind == "categorical":
            choices = list(descriptor.get("choices", []))
            if not choices:
                raise ValueError(f"categorical param {name!r} requires non empty choices")
            params[name] = trial.suggest_categorical(name, choices)
        else:
            raise ValueError(f"Unsupported search space type {kind!r} for param {name!r}")
    return params


def validate_space(space: dict[str, dict[str, Any]]) -> None:
    """Raise if the space dict is malformed. Cheap pre flight check."""
    for name, descriptor in (space or {}).items():
        if not isinstance(descriptor, dict):
            raise ValueError(f"search_space[{name}] must be a mapping")
        kind = str(descriptor.get("type", "float")).lower()
        if kind in {"int", "float"}:
            if "low" not in descriptor or "high" not in descriptor:
                raise ValueError(f"search_space[{name}] missing low/high")
            if float(descriptor["high"]) <= float(descriptor["low"]):
                raise ValueError(f"search_space[{name}] high must exceed low")
            if "step" in descriptor and float(descriptor["step"]) <= 0:
                raise ValueError(f"search_space[{name}] step must be positive")
        elif kind == "categorical":
            if not descriptor.get("choices"):
                raise ValueError(f"search_space[{name}] categorical requires choices")
        else:
            raise ValueError(f"search_space[{name}] unknown type {kind!r}")


def discretize_dimension(name: str, descriptor: dict[str, Any]) -> list[Any]:
    """Turn one search_space descriptor into an ordered list of grid values."""
    kind = str(descriptor.get("type", "float")).lower()
    if kind == "categorical":
        choices = list(descriptor.get("choices", []))
        if not choices:
            raise ValueError(f"categorical param {name!r} requires non empty choices")
        return choices
    if kind == "int":
        low = int(descriptor["low"])
        high = int(descriptor["high"])
        step = int(descriptor.get("step", 1))
        if step <= 0:
            raise ValueError(f"search_space[{name}] step must be positive")
        return list(range(low, high + 1, step))
    if kind == "float":
        low = float(descriptor["low"])
        high = float(descriptor["high"])
        step = descriptor.get("step")
        if step is not None:
            step_f = float(step)
            if step_f <= 0:
                raise ValueError(f"search_space[{name}] step must be positive")
            values: list[float] = []
            cur = low
            # Inclusive high with float tolerance.
            while cur <= high + step_f * 1e-9:
                values.append(round(cur, 10))
                cur += step_f
            return values
        n = int(descriptor.get("n_points", _DEFAULT_FLOAT_GRID_POINTS))
        if n < 2:
            raise ValueError(f"search_space[{name}] n_points must be >= 2 when step is omitted")
        if bool(descriptor.get("log", False)):
            if low <= 0:
                raise ValueError(f"search_space[{name}] log grid requires low > 0")
            log_low, log_high = math.log(low), math.log(high)
            return [
                round(math.exp(log_low + i * (log_high - log_low) / (n - 1)), 10)
                for i in range(n)
            ]
        return [round(low + i * (high - low) / (n - 1), 10) for i in range(n)]
    raise ValueError(f"Unsupported search space type {kind!r} for param {name!r}")


def estimate_grid_size(space: dict[str, dict[str, Any]]) -> int:
    """Return the cartesian product size without materialising combinations."""
    if not space:
        return 0
    size = 1
    for name, descriptor in space.items():
        size *= len(discretize_dimension(name, descriptor))
    return size


def enumerate_grid(
    space: dict[str, dict[str, Any]],
    *,
    max_combos: int = 250,
) -> list[dict[str, Any]]:
    """
    Materialise every combination in ``space``.

    Raises ``ValueError`` when the product exceeds ``max_combos`` so callers
    must narrow ``--params`` or raise the cap explicitly.
    """
    validate_space(space)
    if not space:
        return [{}]
    names = list(space.keys())
    axes = [discretize_dimension(name, space[name]) for name in names]
    total = 1
    for axis in axes:
        total *= len(axis)
    if total > int(max_combos):
        raise ValueError(
            f"Grid has {total} combinations (cap={max_combos}). "
            f"Narrow --params or raise --max-combos."
        )
    return [dict(zip(names, values)) for values in itertools.product(*axes)]


def resolve_search_space(
    bundle_space: dict[str, dict[str, Any]],
    *,
    include_execution: bool = False,
    only_keys: list[str] | None = None,
    execution_space: dict[str, dict[str, Any]] | None = None,
) -> dict[str, dict[str, Any]]:
    """
    Merge bundle indicator space with optional shared execution space.

    ``only_keys`` (if set) keeps only the named dimensions after the merge.
    """
    merged: dict[str, dict[str, Any]] = {
        str(k): dict(v) for k, v in (bundle_space or {}).items() if isinstance(v, dict)
    }
    if include_execution:
        if execution_space is None:
            from lib.execution_params import load_execution_search_space

            execution_space = load_execution_search_space()
        for key, descriptor in (execution_space or {}).items():
            # Bundle-local descriptors win over the shared execution template.
            merged.setdefault(str(key), dict(descriptor))
    if only_keys is not None:
        wanted = [k.strip() for k in only_keys if k and k.strip()]
        missing = [k for k in wanted if k not in merged]
        if missing:
            raise ValueError(
                f"Unknown search-space keys: {missing}. "
                f"Available: {sorted(merged)}"
            )
        merged = {k: merged[k] for k in wanted}
    validate_space(merged)
    return merged
