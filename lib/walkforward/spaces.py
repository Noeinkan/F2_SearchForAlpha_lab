"""
Search space resolution for agent strategies.

A bundle's search_space is a flat map of param name to a small descriptor:

    rsi_window: { type: int, low: 5, high: 30 }
    bb_std:     { type: float, low: 1.0, high: 3.0, log: false }
    foo:        { type: categorical, choices: [a, b, c] }

This module turns one trial of that space into a Python dict using either an
Optuna trial (TPE sampling) or a deterministic enumeration helper used by
tests. Reused by the Bayesian optimiser and the walk forward runner.
"""

from __future__ import annotations

from typing import Any

import optuna


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
            params[name] = trial.suggest_float(
                name,
                float(descriptor["low"]),
                float(descriptor["high"]),
                log=bool(descriptor.get("log", False)),
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
        elif kind == "categorical":
            if not descriptor.get("choices"):
                raise ValueError(f"search_space[{name}] categorical requires choices")
        else:
            raise ValueError(f"search_space[{name}] unknown type {kind!r}")
