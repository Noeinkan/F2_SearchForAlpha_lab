"""Exceptions raised by the backtest engine.

Defined here rather than in :mod:`lib.strategy` so every engine module can raise
them without importing the public entry point back. ``lib.strategy`` re-exports
both, and ``except lib.strategy.ValidationError`` catches the same class.
"""


class BacktestError(Exception):
    """Custom exception for backtest-related errors."""
    pass


class ValidationError(Exception):
    """Custom exception for input validation errors."""
    pass
