"""
Merge Bayesian flat params into nested indicator-settings for Dash Apply.
"""

from __future__ import annotations

import copy
from typing import Any

from lib.agent_strategy import params_to_indicator_settings
from lib.dash.dash_config import merge_indicator_settings


def merge_indicator_settings_from_params(
    current: dict[str, Any] | None,
    flat_params: dict[str, Any] | None,
) -> dict[str, Any]:
    """Deep-merge params_to_indicator_settings(flat_params) into current settings."""
    base = merge_indicator_settings(current)
    patch = params_to_indicator_settings(flat_params or {})
    if not patch:
        return base
    out = copy.deepcopy(base)
    for group, nested in patch.items():
        out.setdefault(group, {})
        out[group].update(dict(nested))
    return out
