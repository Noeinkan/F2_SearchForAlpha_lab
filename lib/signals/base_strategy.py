# Base Trading Strategy module
"""
Abstract base class for all trading strategies.
Provides common configuration handling and defines the interface for signal generation.
"""

import copy
import logging
from abc import ABC, abstractmethod
from typing import Dict, Any, List, Optional
import pandas as pd

logger = logging.getLogger(__name__)


class BaseTradingStrategy(ABC):
    """
    Abstract base class for trading strategies.
    
    All trading strategy classes (BB, RSI, MACD, etc.) should inherit from this class
    and implement the required abstract methods.
    
    Attributes:
        config: Dictionary containing strategy-specific configuration parameters.
        name: Human-readable name of the strategy.
    """
    
    DEFAULT_CONFIG: Dict[str, Any] = {}
    STRATEGY_KEY: str | None = None
    STRATEGY_PRIORITY: int = 100
    SIGNAL_METADATA: Dict[str, str] = {}
    
    def __init__(self, config: Optional[Dict[str, Any]] = None, name: str = "BaseStrategy"):
        """
        Initialize the trading strategy.
        
        Args:
            config: Optional configuration dictionary to override defaults.
            name: Name identifier for this strategy.
        """
        self.name = name
        # Deep copy: DEFAULT_CONFIG is nested, and a shallow copy would let
        # update_config() mutate the class-level defaults for every later
        # instance in the process.
        self.config = copy.deepcopy(self._get_default_config())
        if config:
            self.update_config(config)
        logger.debug(f"Initialized {self.name} with config: {self.config}")
    
    def _get_default_config(self) -> Dict[str, Any]:
        """
        Get the default configuration for this strategy.
        Subclasses should override this method to provide their default config.
        
        Returns:
            Dictionary with default configuration values.
        """
        return self.DEFAULT_CONFIG.copy()

    @classmethod
    def get_strategy_key(cls) -> str:
        """Return canonical strategy key used by registry/discovery."""
        if cls.STRATEGY_KEY:
            return cls.STRATEGY_KEY
        name = cls.__name__.replace("_TradingStrategy", "").replace("TradingStrategy", "")
        return name.strip("_").lower()

    @classmethod
    def get_signal_metadata(cls) -> Dict[str, str]:
        """Return strategy signal metadata."""
        return cls.SIGNAL_METADATA.copy()

    @classmethod
    def get_strategy_priority(cls) -> int:
        """Return strategy display/execution priority (lower comes first)."""
        return int(cls.STRATEGY_PRIORITY)
    
    def update_config(self, new_config: Dict[str, Any]) -> None:
        """
        Update the configuration with new values.
        Performs deep update for nested dictionaries.
        
        Args:
            new_config: Dictionary with new configuration values.
        """
        for key, value in new_config.items():
            if key in self.config:
                if isinstance(self.config[key], dict) and isinstance(value, dict):
                    self.config[key].update(value)
                else:
                    self.config[key] = value
            else:
                self.config[key] = value
        logger.debug(f"Updated {self.name} config: {self.config}")
    
    def get_config(self) -> Dict[str, Any]:
        """
        Get the current configuration.
        
        Returns:
            Copy of the current configuration dictionary.
        """
        return self.config.copy()
    
    def validate_dataframe(self, df: pd.DataFrame, required_columns: List[str]) -> None:
        """
        Validate that the DataFrame has required columns.
        
        Args:
            df: DataFrame to validate.
            required_columns: List of column names that must be present.
            
        Raises:
            ValueError: If any required columns are missing.
        """
        missing_columns = [col for col in required_columns if col not in df.columns]
        if missing_columns:
            raise ValueError(
                f"{self.name}: Missing required columns: {missing_columns}. "
                f"Available columns: {list(df.columns)}"
            )
    
    @abstractmethod
    def add_indicators(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Add technical indicators to the DataFrame.
        
        This method should add any technical indicator columns that are 
        prerequisites for signal generation.
        
        Args:
            df: DataFrame with OHLCV data.
            
        Returns:
            DataFrame with added indicator columns.
        """
        pass
    
    @abstractmethod
    def generate_signals(self, df: pd.DataFrame) -> pd.DataFrame:
        """
        Generate trading signals.
        
        This method should call add_indicators and then generate buy/sell signals
        based on the strategy logic.
        
        Args:
            df: DataFrame with OHLCV data.
            
        Returns:
            DataFrame with added signal columns.
        """
        pass
    
    def get_signal_columns(self, df: pd.DataFrame) -> Dict[str, List[str]]:
        """
        Get the names of buy and sell signal columns generated by this strategy.
        
        Args:
            df: DataFrame that has been processed by generate_signals.
            
        Returns:
            Dictionary with 'buy' and 'sell' keys containing lists of column names.
        """
        strategy_prefix = self.name.replace("_TradingStrategy", "").replace("TradingStrategy", "")
        buy_signals = [
            col for col in df.columns
            if strategy_prefix in col and col.lower().endswith('_buy')
        ]
        sell_signals = [
            col for col in df.columns
            if strategy_prefix in col and col.lower().endswith('_sell')
        ]
        other_signals = [
            col for col in df.columns
            if strategy_prefix in col and col not in buy_signals and col not in sell_signals
        ]
        return {'buy': buy_signals, 'sell': sell_signals, 'other': other_signals}
