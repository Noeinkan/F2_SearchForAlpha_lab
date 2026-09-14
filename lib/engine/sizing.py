"""Position sizers: how many units a buy or sell signal asks for.

A sizer answers one question — given a portfolio value and a price, how many
units? — and knows nothing about cash, fees or contention. The engine clamps
whatever it returns to what the account can actually afford.

In a portfolio run the ``portfolio_value`` every sizer receives is the **total**
across the basket, from the previous bar
([docs/portfolio-semantics.md](../../docs/portfolio-semantics.md) §2), so
``percentage_of_portfolio(2%)`` means 2% of everything, not of a notional slice.
"""

from typing import Callable

import numpy as np


def get_position_sizer(strategy: str, fractional: bool = False, **kwargs) -> Callable:
    """
    Get the position sizing function for the specified strategy.

    Args:
        strategy: Name of the position sizing strategy.
        fractional: Return the exact (unrounded) quantity instead of whole
            shares. The engine sets this from ``backtest(allow_fractional=...)``;
            the truncation otherwise happens inside the sizer, where the engine
            cannot undo it.
        **kwargs: Additional parameters for the strategy.

    Returns:
        Callable position sizing function.

    Raises:
        ValueError: If strategy is not recognized.
    """
    strategies = {
        "percentage_of_portfolio": lambda pv, cp: _size_percentage_of_portfolio(
            pv, cp, kwargs.get('percent', 0.01)
        ),
        "fixed_dollar_amount": lambda pv, cp: _size_fixed_dollar_amount(
            cp, kwargs.get('amount', 1000)
        ),
        "volatility_based": lambda pv, cp, vol: _size_volatility_based(
            pv, cp, vol, kwargs.get('target_volatility', 0.01)
        ),
        "kelly_criterion": lambda pv, cp: _size_kelly_criterion(
            kwargs['win_rate'], kwargs['win_loss_ratio'], pv, cp
        ),
        "risk_based": lambda pv, cp: _size_risk_based(
            pv, cp, kwargs['stop_loss_percent'], kwargs.get('risk_percent', 0.01)
        ),
        "atr_risk_based": lambda pv, cp, atr: _size_atr_risk_based(
            pv, cp, atr, kwargs.get('atr_multiplier', 1.5), kwargs.get('risk_percent', 0.01)
        )
    }

    if strategy not in strategies:
        available = ", ".join(strategies.keys())
        raise ValueError(f"Unknown position sizing strategy: '{strategy}'. Available: {available}")

    sizer = strategies[strategy]
    if fractional:
        return sizer
    return lambda *args: int(sizer(*args))


# The `_size_*` helpers return the exact, unrounded quantity. The public
# functions below wrap them with the whole-share truncation callers expect.

def _size_percentage_of_portfolio(portfolio_value: float, close_price: float, percent: float) -> float:
    if close_price <= 0:
        return 0.0
    return (portfolio_value * percent) / close_price


def _size_fixed_dollar_amount(close_price: float, amount: float) -> float:
    if close_price <= 0:
        return 0.0
    return amount / close_price


def _size_volatility_based(
    portfolio_value: float, close_price: float, volatility: float, target_volatility: float
) -> float:
    if close_price <= 0 or volatility <= 0:
        return 0.0
    return ((target_volatility / volatility) * portfolio_value) / close_price


def _size_kelly_criterion(
    win_rate: float, win_loss_ratio: float, portfolio_value: float, close_price: float
) -> float:
    if close_price <= 0 or win_loss_ratio <= 0:
        return 0.0
    kelly_percentage = win_rate - ((1 - win_rate) / win_loss_ratio)
    kelly_percentage = max(0, min(kelly_percentage, 1))
    return (kelly_percentage * portfolio_value) / close_price


def _size_risk_based(
    portfolio_value: float, close_price: float, stop_loss_percent: float, risk_percent: float
) -> float:
    if close_price <= 0 or stop_loss_percent <= 0:
        return 0.0
    return (portfolio_value * risk_percent) / (close_price * stop_loss_percent)


def _size_atr_risk_based(
    portfolio_value: float, close_price: float, atr: float,
    atr_multiplier: float, risk_percent: float
) -> float:
    if close_price <= 0 or not np.isfinite(atr) or atr <= 0 or atr_multiplier <= 0:
        return 0.0
    return (portfolio_value * risk_percent) / (atr * atr_multiplier)


def percentage_of_portfolio(portfolio_value: float, close_price: float, percent: float = 0.02) -> int:
    """Calculate position size as percentage of portfolio."""
    return int(_size_percentage_of_portfolio(portfolio_value, close_price, percent))

def fixed_dollar_amount(close_price: float, amount: float = 500) -> int:
    """Calculate position size based on fixed dollar amount."""
    return int(_size_fixed_dollar_amount(close_price, amount))


def volatility_based(
    portfolio_value: float,
    close_price: float,
    volatility: float,
    target_volatility: float = 0.01
) -> int:
    """Calculate position size based on asset volatility."""
    return int(_size_volatility_based(portfolio_value, close_price, volatility, target_volatility))


def kelly_criterion(
    win_rate: float,
    win_loss_ratio: float,
    portfolio_value: float,
    close_price: float
) -> int:
    """Calculate position size using Kelly Criterion."""
    return int(_size_kelly_criterion(win_rate, win_loss_ratio, portfolio_value, close_price))


def risk_based(
    portfolio_value: float,
    close_price: float,
    stop_loss_percent: float,
    risk_percent: float = 0.01
) -> int:
    """Calculate position size based on fixed risk per trade."""
    return int(_size_risk_based(portfolio_value, close_price, stop_loss_percent, risk_percent))


def atr_risk_based(
    portfolio_value: float,
    close_price: float,
    atr: float,
    atr_multiplier: float = 1.5,
    risk_percent: float = 0.01
) -> int:
    """
    Size a position so that ``atr_multiplier`` ATRs of adverse move costs
    ``risk_percent`` of the portfolio.

    This is ``risk_based`` with the fixed stop percentage replaced by the
    instrument's own volatility, so a low-vol utility gets a larger position
    than a high-beta name for the same dollar risk. ``atr_multiplier`` defaults
    to 1.5 to match ``ATR_TradingStrategy``'s stop multiplier, so sizing and
    ``stop_mode='atr'`` agree on the same risk unit.

    Returns 0 for a non-finite or non-positive ATR (warmup bars) — a position
    whose risk cannot be measured is not taken.
    """
    return int(_size_atr_risk_based(portfolio_value, close_price, atr, atr_multiplier, risk_percent))
