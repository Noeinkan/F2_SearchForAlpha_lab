"""
Seed helpers for deterministic numerical work.

Use ``set_global_seed`` at the top of any pipeline that touches numpy or the
stdlib ``random`` module. The backtest engine itself is deterministic given
identical inputs; this module exists so callers (optimisers, fixtures, walk
forward orchestrators) can pin the entropy of their data generation.
"""

from __future__ import annotations

import os
import random

import numpy as np


DEFAULT_SEED = 42


def set_global_seed(seed: int = DEFAULT_SEED) -> int:
    """Seed numpy, stdlib random, and PYTHONHASHSEED for reproducibility."""
    seed = int(seed)
    random.seed(seed)
    np.random.seed(seed)
    os.environ.setdefault("PYTHONHASHSEED", str(seed))
    return seed


def numpy_rng(seed: int = DEFAULT_SEED) -> np.random.Generator:
    """Return a fresh seeded numpy Generator (preferred over the legacy state)."""
    return np.random.default_rng(int(seed))
