"""
Dashboard State Management
Encapsulates dashboard state to avoid global mutable variables.
"""

import logging
from typing import Any, Dict, List, Optional, Tuple
from collections import OrderedDict
from datetime import datetime
import pandas as pd

from lib.dash.dash_config import DEFAULT_THEME, get_theme

logger = logging.getLogger(__name__)

# Cache configuration
MAX_CACHE_SIZE = 50  # Maximum number of cached DataFrames


class DashboardState:
    """Encapsulates dashboard state to avoid global mutable variables."""

    def __init__(self, max_cache_size: int = MAX_CACHE_SIZE):
        self._df: Optional[pd.DataFrame] = None
        self._all_tickers_df: Optional[pd.DataFrame] = None
        self._ticker_dropdown_options: Optional[List[Dict[str, Any]]] = None
        self._backtest_results: Optional[Dict] = None
        self._data_cache: OrderedDict[str, pd.DataFrame] = OrderedDict()
        self._current_theme: str = DEFAULT_THEME
        self._max_cache_size = max_cache_size
        self._optimization_state: Dict[str, Any] = self._create_empty_optimization_state()
        self.flow_last_scan_at: datetime | None = None
        self.flow_last_scan_path: str | None = None

    @staticmethod
    def _create_empty_optimization_state() -> Dict[str, Any]:
        """Create empty optimization state dict."""
        return {
            'running': False,
            'current_index': 0,
            'total_combinations': 0,
            'combinations': [],
            'results': [],
            'initial_capital': 0,
            'completed': False,
            'error': None
        }

    @property
    def df(self) -> Optional[pd.DataFrame]:
        """Current working DataFrame with price data and indicators."""
        return self._df

    @df.setter
    def df(self, value: pd.DataFrame) -> None:
        self._df = value

    @property
    def all_tickers_df(self) -> Optional[pd.DataFrame]:
        """DataFrame containing all available tickers."""
        return self._all_tickers_df

    @all_tickers_df.setter
    def all_tickers_df(self, value: pd.DataFrame) -> None:
        self._all_tickers_df = value

    @property
    def ticker_dropdown_options(self) -> Optional[List[Dict[str, Any]]]:
        """Full ticker dropdown options including search index."""
        return self._ticker_dropdown_options

    @ticker_dropdown_options.setter
    def ticker_dropdown_options(self, value: List[Dict[str, Any]]) -> None:
        self._ticker_dropdown_options = value

    @property
    def backtest_results(self) -> Optional[Dict]:
        """Results from the most recent backtest."""
        return self._backtest_results

    @backtest_results.setter
    def backtest_results(self, value: Dict) -> None:
        self._backtest_results = value

    @property
    def theme(self) -> dict:
        """Current theme configuration."""
        return get_theme(self._current_theme)

    @property
    def theme_name(self) -> str:
        """Current theme name."""
        return self._current_theme

    def set_theme(self, theme_name: str) -> None:
        """Set the current theme."""
        self._current_theme = theme_name

    @property
    def optimization_state(self) -> Dict[str, Any]:
        """Current optimization state."""
        return self._optimization_state

    def update_optimization_state(self, **kwargs) -> None:
        """Update optimization state with provided values."""
        self._optimization_state.update(kwargs)

    def reset_optimization(self) -> None:
        """Reset optimization state for new run."""
        self._optimization_state = self._create_empty_optimization_state()
        logger.debug("Optimization state reset")

    def get_cached_data(self, key: str) -> Optional[pd.DataFrame]:
        """
        Get cached data by key.

        Args:
            key: Cache key (typically ticker_startdate_enddate)

        Returns:
            Cached DataFrame or None if not found
        """
        if key in self._data_cache:
            # Move to end to mark as recently used (LRU)
            self._data_cache.move_to_end(key)
            return self._data_cache[key]
        return None

    def set_cached_data(self, key: str, data: pd.DataFrame) -> None:
        """
        Cache data with LRU eviction.

        Args:
            key: Cache key
            data: DataFrame to cache
        """
        # If key exists, update and move to end
        if key in self._data_cache:
            self._data_cache.move_to_end(key)
            self._data_cache[key] = data
            return

        # Evict oldest if at capacity
        while len(self._data_cache) >= self._max_cache_size:
            evicted_key, _ = self._data_cache.popitem(last=False)
            logger.debug(f"Evicted cache entry: {evicted_key}")

        self._data_cache[key] = data

    def clear_cache(self) -> None:
        """Clear all cached data."""
        self._data_cache.clear()
        logger.info("Data cache cleared")

    def get_cache_info(self) -> Dict:
        """Get cache statistics."""
        return {
            'size': len(self._data_cache),
            'max_size': self._max_cache_size,
            'keys': list(self._data_cache.keys())
        }

    def reset(self) -> None:
        """Reset all state to initial values."""
        self._df = None
        self._all_tickers_df = None
        self._ticker_dropdown_options = None
        self._backtest_results = None
        self._data_cache.clear()
        self._current_theme = DEFAULT_THEME
        self._optimization_state = self._create_empty_optimization_state()
        from lib.dash.callbacks.shared import clear_enriched_cache
        clear_enriched_cache()
        logger.info("Dashboard state reset")


# Singleton instance
dashboard_state = DashboardState()
