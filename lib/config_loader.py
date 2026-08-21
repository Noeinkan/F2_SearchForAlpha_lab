# Configuration loader module
"""
Centralized configuration management for trading strategies.
Loads settings from YAML config files.
"""

import os
import logging
from pathlib import Path
from typing import Dict, Any, Optional

import yaml

logger = logging.getLogger(__name__)

# Default config file path (relative to project root)
DEFAULT_CONFIG_PATH = Path(__file__).parent.parent / "config" / "strategy_config.yaml"


class ConfigLoader:
    """Singleton configuration loader for strategy parameters."""
    
    _instance: Optional['ConfigLoader'] = None
    _config: Dict[str, Any] = {}
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not self._config:
            self.load_config()
    
    def load_config(self, config_path: Optional[Path] = None) -> Dict[str, Any]:
        """
        Load configuration from YAML file.
        
        Args:
            config_path: Optional path to config file. Uses default if not provided.
            
        Returns:
            Dictionary with configuration values.
        """
        path = config_path or DEFAULT_CONFIG_PATH
        
        if not path.exists():
            logger.warning(f"Config file not found at {path}. Using defaults.")
            return {}
        
        try:
            with open(path, 'r') as f:
                self._config = yaml.safe_load(f) or {}
            logger.info(f"Loaded configuration from {path}")
        except yaml.YAMLError as e:
            logger.error(f"Error parsing config file: {e}")
            self._config = {}
        except Exception as e:
            logger.error(f"Error loading config file: {e}")
            self._config = {}
        
        return self._config
    
    def get_strategy_config(self, strategy_name: str) -> Dict[str, Any]:
        """
        Get configuration for a specific strategy.
        
        Args:
            strategy_name: Name of the strategy (e.g., 'sma', 'rsi', 'bollinger_bands')
            
        Returns:
            Dictionary with strategy-specific configuration.
        """
        strategies = self._config.get('strategies', {})
        return strategies.get(strategy_name, {})
    
    def get_backtest_config(self) -> Dict[str, Any]:
        """Get backtest configuration."""
        return self._config.get('backtest', {})
    
    def get(self, key: str, default: Any = None) -> Any:
        """Get a top-level config value."""
        return self._config.get(key, default)
    
    def reload(self, config_path: Optional[Path] = None) -> Dict[str, Any]:
        """Force reload configuration from file."""
        self._config = {}
        return self.load_config(config_path)

    def get_agent_strategies(self) -> Dict[str, Dict[str, Any]]:
        """Return all agent strategy bundles keyed by name."""
        return self._config.get('agent_strategies', {}) or {}

    def get_agent_strategy(self, name: str) -> Dict[str, Any]:
        """Return a single agent strategy bundle by name (empty dict if missing)."""
        return self.get_agent_strategies().get(name, {})

    def get_agent_config(self) -> Dict[str, Any]:
        """Read config/agent.yaml if present (live trading + guard settings)."""
        agent_path = DEFAULT_CONFIG_PATH.parent / 'agent.yaml'
        if not agent_path.exists():
            return {}
        try:
            with open(agent_path, 'r') as f:
                return yaml.safe_load(f) or {}
        except Exception as e:
            logger.error(f"Error loading agent.yaml: {e}")
            return {}


# Convenience function for direct access
def get_config() -> ConfigLoader:
    """Get the singleton ConfigLoader instance."""
    return ConfigLoader()


def get_strategy_config(strategy_name: str) -> Dict[str, Any]:
    """
    Convenience function to get strategy configuration.

    Args:
        strategy_name: Name of the strategy.

    Returns:
        Strategy configuration dictionary.
    """
    return get_config().get_strategy_config(strategy_name)


def get_agent_strategies() -> Dict[str, Dict[str, Any]]:
    """Convenience accessor for agent strategy bundles."""
    return get_config().get_agent_strategies()


def get_agent_strategy(name: str) -> Dict[str, Any]:
    """Convenience accessor for a single agent strategy bundle."""
    return get_config().get_agent_strategy(name)


def get_agent_config() -> Dict[str, Any]:
    """Convenience accessor for config/agent.yaml content."""
    return get_config().get_agent_config()
