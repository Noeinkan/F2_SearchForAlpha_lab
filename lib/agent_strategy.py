"""
Resolution of agent strategy bundles to executable backtests.

An agent strategy bundle (declared in config/strategy_config.yaml under the
``agent_strategies`` key) is a small descriptor: ticker, signal column names,
flat parameter map, mode. This module translates flat parameter keys into the
nested ``indicator_settings`` shape that ``lib.signals.indicators`` expects,
fetches data, runs the existing signal pipeline, and returns the prepared
DataFrame ready for ``lib.strategy.backtest``.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any

import pandas as pd

from lib.config_loader import get_agent_strategy
from lib.data_processing import fetch_data
from lib.signals.indicators import add_indicators, generate_signals

logger = logging.getLogger(__name__)


# Flat parameter key -> (indicator group, nested key). Extend as new tunable
# fields are exposed on agent strategies.
PARAM_KEY_MAP: dict[str, tuple[str, str]] = {
    "rsi_window": ("rsi", "period"),
    "rsi_overbought": ("rsi", "overbought"),
    "rsi_oversold": ("rsi", "oversold"),
    "bb_window": ("bollinger", "window"),
    "bb_std": ("bollinger", "window_dev"),
    "bb_double_lookback": ("bollinger", "lookback_window"),
    "cci_window": ("cci", "period"),
    "cci_upper": ("cci", "ceiling"),
    "cci_lower": ("cci", "floor"),
    "cci_extreme": ("cci", "extreme_threshold"),
    "macd_fast": ("macd", "fast"),
    "macd_slow": ("macd", "slow"),
    "macd_signal": ("macd", "signal"),
    "sma_short": ("sma", "short_window"),
    "sma_medium": ("sma", "medium_window"),
    "sma_long": ("sma", "long_window"),
    "ema_short": ("ema", "short_window"),
    "ema_medium": ("ema", "medium_window"),
    "ema_long": ("ema", "long_window"),
    "vwap_window": ("vwap", "window"),
}


class StrategyNotFoundError(KeyError):
    """Raised when a strategy name is not in agent_strategies."""


@dataclass(frozen=True)
class AgentStrategyBundle:
    name: str
    description: str
    ticker: str
    buy_signals: list[str]
    sell_signals: list[str]
    mode: str
    live_params: dict[str, Any]
    search_space: dict[str, dict[str, Any]]
    signal_logic: str = "or"
    signal_window: int = 0
    last_promoted: str | None = None


def load_bundle(name: str) -> AgentStrategyBundle:
    raw = get_agent_strategy(name)
    if not raw:
        raise StrategyNotFoundError(name)
    return AgentStrategyBundle(
        name=name,
        description=str(raw.get("description", "")),
        ticker=str(raw.get("ticker", "")),
        buy_signals=list(raw.get("buy_signals", []) or []),
        sell_signals=list(raw.get("sell_signals", []) or []),
        mode=str(raw.get("mode", "trading")),
        live_params=dict(raw.get("live_params", {}) or {}),
        search_space=dict(raw.get("search_space", {}) or {}),
        signal_logic=str(raw.get("signal_logic", "or")),
        signal_window=int(raw.get("signal_window", 0)),
        last_promoted=raw.get("last_promoted"),
    )


def params_to_indicator_settings(params: dict[str, Any]) -> dict[str, dict[str, Any]]:
    """Translate a flat agent param map to the nested indicator_settings shape."""
    settings: dict[str, dict[str, Any]] = {}
    for flat_key, value in (params or {}).items():
        if flat_key not in PARAM_KEY_MAP:
            logger.debug("Ignoring unknown agent param %s", flat_key)
            continue
        group, nested = PARAM_KEY_MAP[flat_key]
        settings.setdefault(group, {})[nested] = value
    return settings


def prepare_dataframe(
    bundle: AgentStrategyBundle,
    *,
    window_from: str,
    window_to: str,
    params: dict[str, Any] | None = None,
    ticker_override: str | None = None,
) -> pd.DataFrame:
    """Fetch OHLCV, apply indicator settings, generate signals."""
    ticker = ticker_override or bundle.ticker
    if not ticker:
        raise ValueError(f"Strategy {bundle.name} has no ticker configured")

    indicator_settings = params_to_indicator_settings(params or bundle.live_params)
    df = fetch_data(ticker, window_from, window_to)
    df = add_indicators(df, indicator_settings)
    df, _headers = generate_signals(df, indicator_settings)
    return df
