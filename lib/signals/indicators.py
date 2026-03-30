# indicators module
"""
Technical indicators and signal aggregation module.
"""

import importlib
import inspect
import logging
import pkgutil
import numpy as np
import pandas as pd
from dataclasses import dataclass
from typing import Callable

from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange

from lib.signals.base_strategy import BaseTradingStrategy
from lib.config_loader import get_strategy_config, get_config

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class StrategyRegistration:
    """Discovered strategy registration metadata."""
    key: str
    class_ref: type[BaseTradingStrategy]
    module_name: str


STRATEGY_KEY_ALIASES = {
    'bb': 'bollinger',
    'bollinger_bands': 'bollinger',
}


def normalize_strategy_key(key: str) -> str:
    normalized = (key or '').strip().lower()
    return STRATEGY_KEY_ALIASES.get(normalized, normalized)


def _parse_registry_controls() -> tuple[set[str], set[str], list[str], dict[str, int]]:
    """Load optional registry controls from YAML config."""
    registry_cfg = get_config().get('signal_registry', {}) or {}

    allowlist = {
        normalize_strategy_key(item)
        for item in registry_cfg.get('allowlist', [])
        if isinstance(item, str)
    }
    denylist = {
        normalize_strategy_key(item)
        for item in registry_cfg.get('denylist', [])
        if isinstance(item, str)
    }
    order = [
        normalize_strategy_key(item)
        for item in registry_cfg.get('order', [])
        if isinstance(item, str)
    ]

    priority_overrides: dict[str, int] = {}
    raw_priorities = registry_cfg.get('priorities', {})
    if isinstance(raw_priorities, dict):
        for key, value in raw_priorities.items():
            if not isinstance(key, str):
                continue
            normalized_key = normalize_strategy_key(key)
            try:
                priority_overrides[normalized_key] = int(value)
            except (TypeError, ValueError):
                continue

    return allowlist, denylist, order, priority_overrides


def _discover_strategy_classes() -> dict[str, StrategyRegistration]:
    """Auto-discover strategy classes under lib.signals.signals_*."""
    discovered: dict[str, StrategyRegistration] = {}
    signals_pkg = importlib.import_module('lib.signals')

    for module_info in pkgutil.iter_modules(signals_pkg.__path__):
        if not module_info.name.startswith('signals_'):
            continue

        module_name = f'lib.signals.{module_info.name}'
        module = importlib.import_module(module_name)

        for _, cls in inspect.getmembers(module, inspect.isclass):
            if cls is BaseTradingStrategy:
                continue
            if not issubclass(cls, BaseTradingStrategy):
                continue
            if cls.__module__ != module_name:
                continue

            key = normalize_strategy_key(cls.get_strategy_key())
            discovered[key] = StrategyRegistration(
                key=key,
                class_ref=cls,
                module_name=module_name,
            )

    return discovered


def _sort_registrations(
    registrations: list[StrategyRegistration],
    preferred_order: list[str],
    priority_overrides: dict[str, int],
) -> list[StrategyRegistration]:
    def effective_priority(registration: StrategyRegistration) -> int:
        return priority_overrides.get(
            registration.key,
            registration.class_ref.get_strategy_priority(),
        )

    rank = {key: idx for idx, key in enumerate(preferred_order)}
    if preferred_order:
        return sorted(
            registrations,
            key=lambda registration: (
                rank.get(registration.key, 10_000),
                effective_priority(registration),
                registration.key,
            ),
        )
    return sorted(
        registrations,
        key=lambda registration: (
            effective_priority(registration),
            registration.key,
        ),
    )


def get_registered_strategies() -> list[StrategyRegistration]:
    """Return strategy registrations after applying hybrid allow/deny controls."""
    discovered = _discover_strategy_classes()
    allowlist, denylist, order, priority_overrides = _parse_registry_controls()

    enabled_keys = set(discovered.keys())
    if allowlist:
        enabled_keys &= allowlist
    if denylist:
        enabled_keys -= denylist

    enabled_registrations = [
        discovered[key]
        for key in enabled_keys
        if key in discovered
    ]
    return _sort_registrations(enabled_registrations, order, priority_overrides)


def get_registered_strategy_keys() -> list[str]:
    return [registration.key for registration in get_registered_strategies()]


def get_strategy_order_debug_info() -> list[dict[str, int | str]]:
    """Return effective ordered strategies with resolved priorities."""
    _, _, _, priority_overrides = _parse_registry_controls()
    debug_rows: list[dict[str, int | str]] = []
    for position, registration in enumerate(get_registered_strategies(), start=1):
        default_priority = registration.class_ref.get_strategy_priority()
        resolved_priority = priority_overrides.get(registration.key, default_priority)
        debug_rows.append({
            'position': position,
            'key': registration.key,
            'default_priority': default_priority,
            'resolved_priority': resolved_priority,
        })
    return debug_rows


def format_strategy_order_debug_text() -> str:
    """Return compact strategy ordering text for status/diagnostics UI."""
    rows = get_strategy_order_debug_info()
    return " > ".join(
        f"{row['key']}({row['resolved_priority']})"
        for row in rows
    )


def get_signal_descriptions() -> dict[str, str]:
    """Aggregate signal descriptions from registered strategies."""
    merged: dict[str, str] = {}
    for registration in get_registered_strategies():
        metadata = registration.class_ref.get_signal_metadata()
        if not isinstance(metadata, dict):
            continue
        for key, value in metadata.items():
            if isinstance(key, str) and isinstance(value, str):
                merged[key] = value
    return merged


def get_signal_categories() -> list[str]:
    """Return signal category labels for dashboard filtering."""
    categories: list[str] = []
    for registration in get_registered_strategies():
        category = 'BB' if registration.key == 'bollinger' else registration.key.upper()
        if category not in categories:
            categories.append(category)
    return categories


def get_signal_category_map() -> dict[str, str]:
    """Return mapping of signal keys (and base keys) to category labels."""
    mapping: dict[str, str] = {}
    for registration in get_registered_strategies():
        category = 'BB' if registration.key == 'bollinger' else registration.key.upper()
        metadata = registration.class_ref.get_signal_metadata()
        if not isinstance(metadata, dict):
            continue

        for key, _ in metadata.items():
            if not isinstance(key, str):
                continue
            mapping[key] = category

            key_lower = key.lower()
            if key_lower.endswith('_buy') or key_lower.endswith('_sell'):
                base = key.rsplit('_', 1)[0]
                if base:
                    mapping.setdefault(base, category)

    return mapping


def classify_signal_columns(columns: list[str]) -> dict[str, list[str]]:
    """Classify signal columns by explicit side suffixes."""
    buy = [col for col in columns if col.lower().endswith('_buy')]
    sell = [col for col in columns if col.lower().endswith('_sell')]
    other = [col for col in columns if col not in buy and col not in sell]
    return {'buy': buy, 'sell': sell, 'other': other}


def _build_default_indicator_settings() -> dict:
    """Build default indicator settings from strategy YAML with safe fallbacks."""
    rsi_cfg = get_strategy_config('rsi')
    cci_cfg = get_strategy_config('cci')
    macd_cfg = get_strategy_config('macd')
    bb_cfg = get_strategy_config('bollinger_bands')
    sma_cfg = get_strategy_config('sma')
    ema_cfg = get_strategy_config('ema')
    vwap_cfg = get_strategy_config('vwap')

    return {
        'rsi': {
            'period': rsi_cfg.get('rsi', {}).get('window', 14),
            'overbought': rsi_cfg.get('overbought_oversold', {}).get('upper_threshold', 70),
            'oversold': rsi_cfg.get('overbought_oversold', {}).get('lower_threshold', 30)
        },
        'cci': {
            'period': cci_cfg.get('cci', {}).get('window', 20),
            'ceiling': cci_cfg.get('overbought_oversold', {}).get('upper_threshold', 100),
            'floor': cci_cfg.get('overbought_oversold', {}).get('lower_threshold', -100)
        },
        'macd': {
            'fast': macd_cfg.get('macd', {}).get('fast_period', 12),
            'slow': macd_cfg.get('macd', {}).get('slow_period', 26),
            'signal': macd_cfg.get('macd', {}).get('signal_period', 9)
        },
        'bollinger': {
            'window': bb_cfg.get('bollinger_bands', {}).get('window', 20),
            'window_dev': bb_cfg.get('bollinger_bands', {}).get('window_dev', 2),
            'squeeze_threshold': bb_cfg.get('squeeze_strategy', {}).get('squeeze_threshold', 0.1),
            'double_bottom_threshold': bb_cfg.get('double_bottom_top_strategy', {}).get('threshold', 0.02)
        },
        'sma': {
            'short_window': sma_cfg.get('sma', {}).get('short_window', 5),
            'medium_window': sma_cfg.get('sma', {}).get('medium_window', 20),
            'long_window': sma_cfg.get('sma', {}).get('long_window', 50),
            'trend_window': sma_cfg.get('sma', {}).get('trend_window', 200)
        },
        'ema': {
            'short_window': ema_cfg.get('ema', {}).get('short_window', 12),
            'medium_window': ema_cfg.get('ema', {}).get('medium_window', 26),
            'long_window': ema_cfg.get('ema', {}).get('long_window', 50),
            'atr_window': 14
        },
        'vwap': {
            'window': vwap_cfg.get('vwap', {}).get('window', 20)
        }
    }


def _merge_indicator_settings(indicator_settings: dict | None) -> dict:
    defaults = _build_default_indicator_settings()
    merged = {key: value.copy() for key, value in defaults.items()}
    user_settings = indicator_settings or {}
    for key, value in user_settings.items():
        if isinstance(value, dict):
            merged.setdefault(key, {}).update(value)
        else:
            merged[key] = value
    return merged


def _build_strategy_config_mappers() -> dict[str, Callable[[dict], dict]]:
    return {
        'rsi': lambda settings: {
            'rsi': {'window': settings.get('period', 14)},
            'overbought_oversold': {
                'upper_threshold': settings.get('overbought', 70),
                'lower_threshold': settings.get('oversold', 30),
            },
        },
        'cci': lambda settings: {
            'cci': {'window': settings.get('period', 20)},
            'overbought_oversold': {
                'upper_threshold': settings.get('ceiling', 100),
                'lower_threshold': settings.get('floor', -100),
            },
            'trend_reversal': {
                'extreme_threshold': settings.get('extreme_threshold', 180),
            },
        },
        'macd': lambda settings: {
            'macd': {
                'fast_period': settings.get('fast', 12),
                'slow_period': settings.get('slow', 26),
                'signal_period': settings.get('signal', 9),
            }
        },
        'bollinger': lambda settings: {
            'bollinger_bands': {
                'window': settings.get('window', 20),
                'window_dev': settings.get('window_dev', 2),
            },
            'squeeze_strategy': {
                'squeeze_threshold': settings.get('squeeze_threshold', 0.1),
            },
            'double_bottom_top_strategy': {
                'threshold': settings.get('double_bottom_threshold', 0.02),
            },
        },
        'sma': lambda settings: {
            'sma': {
                'short_window': settings.get('short_window', 5),
                'medium_window': settings.get('medium_window', 20),
                'long_window': settings.get('long_window', 50),
                'trend_window': settings.get('trend_window', 200),
            }
        },
        'ema': lambda settings: {
            'ema': {
                'short_window': settings.get('short_window', 12),
                'medium_window': settings.get('medium_window', 26),
                'long_window': settings.get('long_window', 50),
                'atr_window': settings.get('atr_window', 14),
                'distance_threshold': settings.get('distance_threshold', 0.01),
                'divergence_window': settings.get('divergence_window', 14),
                'atr_multiplier': settings.get('atr_multiplier', 1.5),
            }
        },
        'vwap': lambda settings: {
            'vwap': {
                'window': settings.get('window', 20),
            }
        },
    }


def _resolve_strategy_runtime_config(strategy_key: str, indicator_settings: dict) -> dict:
    mappers = _build_strategy_config_mappers()
    if strategy_key in mappers:
        return mappers[strategy_key](indicator_settings.get(strategy_key, {}))

    if strategy_key == 'bollinger':
        return mappers[strategy_key](indicator_settings.get('bollinger', {}))

    # Fallback to YAML strategy config if no runtime mapper exists.
    yaml_key = 'bollinger_bands' if strategy_key == 'bollinger' else strategy_key
    return get_strategy_config(yaml_key)


def _instantiate_strategy(registration: StrategyRegistration, indicator_settings: dict) -> BaseTradingStrategy:
    strategy_config = _resolve_strategy_runtime_config(registration.key, indicator_settings)
    try:
        return registration.class_ref(strategy_config)
    except TypeError:
        logger.warning(
            "Unable to initialize %s with runtime config, falling back to defaults",
            registration.class_ref.__name__,
        )
        return registration.class_ref()


def add_indicators(df: pd.DataFrame, indicator_settings: dict | None = None) -> pd.DataFrame:
    """
    Add technical indicators to the DataFrame.
    
    Args:
        df: DataFrame with OHLCV data.
        
    Returns:
        DataFrame with added indicator columns.
    """
    logger.debug("Adding technical indicators")
    indicator_settings = indicator_settings or {}
    
    # ADX (Average Directional Index)
    adx_period = indicator_settings.get('adx', {}).get('period', 14)
    adx = ADXIndicator(df['High'], df['Low'], df['Close'], window=adx_period)
    df['ADX'] = adx.adx()
    
    # ATR (Average True Range)
    atr_period = indicator_settings.get('atr', {}).get('period', 14)
    atr = AverageTrueRange(df['High'], df['Low'], df['Close'], window=atr_period)
    df['ATR'] = atr.average_true_range()
    
    # OBV (On-Balance Volume)
    df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
   
    return df


def generate_signals(df: pd.DataFrame, indicator_settings: dict | None = None) -> tuple:
    """
    Generate trading signals from all strategy classes.
    
    Args:
        df: DataFrame with OHLCV data and indicators.
        
    Returns:
        Tuple of (DataFrame with signals, list of signal column headers).
    """
    logger.info("Generating trading signals")
    indicator_settings = _merge_indicator_settings(indicator_settings)
    registrations = get_registered_strategies()
    strategies = [
        _instantiate_strategy(registration, indicator_settings)
        for registration in registrations
    ]
    logger.debug("Loaded strategy registry order: %s", [s.name for s in strategies])
    
    for strategy in strategies:
        try:
            df = strategy.generate_signals(df)
            logger.debug(f"Generated signals for {strategy.name}")
        except Exception as e:
            logger.error(f"Error generating signals for {strategy.name}: {e}")
            raise
    
    signal_headers = df.columns.tolist()
    
    return df, signal_headers

