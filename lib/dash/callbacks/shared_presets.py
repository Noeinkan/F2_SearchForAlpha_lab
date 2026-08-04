"""UI preset payload builders and status helpers."""

from __future__ import annotations

import copy
import re
from typing import Any, Dict, List

from dash import html

from lib.dash.dash_config import FONT_SIZES
from lib.dash.preset_storage import normalize_preset

from .shared_signals import _extract_selected_plots


def _sanitize_preset_name(name: Any) -> str:
    """Normalize preset names for consistent storage."""
    if not name:
        return ""
    normalized = re.sub(r"\s+", " ", str(name)).strip()
    return normalized


def _preset_status(message: str, level: str = "info") -> html.Span:
    """Simple status message with theme color."""
    from lib.dash.dash_config import get_theme

    theme = get_theme()
    color_map = {
        "success": theme["accent_green"],
        "error": theme["accent_red"],
        "warning": theme["accent_orange"]
    }
    return html.Span(message, style={"color": color_map.get(level, theme["text_secondary"])})


def _format_preset_options(presets: Dict[str, Any]) -> List[Dict[str, str]]:
    names = sorted(presets.keys(), key=lambda name: str(name).lower())
    return [{"label": name, "value": name} for name in names]


def _build_preset_payload(
    ticker: str,
    test_window_start: str,
    test_window_end: str,
    initial_capital: Any,
    plot_values: List[List[str]],
    chart_elements: List[str],
    signal_checklist: List[str],
    indicator_settings: Dict[str, Any],
    chart_library: str,
    strategy_mode: str,
    strategy_preset: str,
    min_holding_period: Any,
    trailing_stop_pct: Any,
    position_scaling_pct: Any,
    take_profit_pct: Any,
    amount_per_buy: Any,
    position_size_pct: Any,
    kelly_win_rate: Any,
    kelly_win_loss_ratio: Any,
    consecutive_signal_mode: str,
    signal_cooldown_bars: Any,
    signal_logic_mode: str,
    signal_window: Any,
    buy_signals: List[str],
    sell_signals: List[str],
    fx_fee_pct: Any,
    slippage_pct: Any,
    commission_pct: Any,
    interval: str = "1d",
) -> Dict[str, Any]:
    payload = {
        "market_data": {
            "ticker": ticker,
            # No fetch window is saved: the fetch always takes maximum history,
            # so there is nothing about it worth restoring. `test_window` is the
            # period the preset evaluates, re-clamped to whatever data actually
            # loads (callbacks/test_window.py). Presets written before this
            # change carry start_date/end_date instead; those keys are simply
            # ignored on load rather than migrated, since they described a fetch
            # bound that no longer exists.
            "test_window": {
                "start": test_window_start,
                "end": test_window_end,
            },
            "initial_capital": initial_capital,
            "interval": interval or "1d",
        },
        "chart": {
            "plot_toggles": _extract_selected_plots(plot_values),
            "chart_elements": chart_elements or [],
            "signal_checklist": signal_checklist or [],
            "indicator_settings": copy.deepcopy(indicator_settings or {}),
            "chart_library": chart_library
        },
        "execution": {
            "strategy_mode": strategy_mode
        },
        "trade_setup": {
            "strategy_preset": strategy_preset,
            "min_holding_period": min_holding_period,
            "trailing_stop_pct": trailing_stop_pct,
            "position_scaling_pct": position_scaling_pct,
            "take_profit_pct": take_profit_pct,
            "amount_per_buy": amount_per_buy,
            "position_size_pct": position_size_pct,
            "kelly_win_rate": kelly_win_rate,
            "kelly_win_loss_ratio": kelly_win_loss_ratio,
            "consecutive_signal_mode": consecutive_signal_mode,
            "signal_cooldown_bars": signal_cooldown_bars
        },
        "signals": {
            "signal_logic_mode": signal_logic_mode,
            "signal_window": signal_window,
            "buy_signals": list(buy_signals or []),
            "sell_signals": list(sell_signals or [])
        },
        "costs": {
            "fx_fee_pct": fx_fee_pct,
            "slippage_pct": slippage_pct,
            "commission_pct": commission_pct
        }
    }
    return normalize_preset(payload)


