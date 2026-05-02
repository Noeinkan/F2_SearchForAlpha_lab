"""
BacktestResult dataclass and a thin wrapper around lib.strategy.backtest.

Existing callers (Dash, optimisers, tests) keep using lib.strategy.backtest
directly and continue to receive a pd.DataFrame. New CLI and agent code uses
``run_backtest_result`` to get a structured, JSON friendly result.
"""

from __future__ import annotations

import time
from dataclasses import asdict, dataclass, field
from typing import Any

import numpy as np
import pandas as pd

from lib.data_processing import (
    calculate_max_drawdown,
    calculate_profit_factor,
    calculate_sharpe_ratio,
    calculate_win_rate,
)
from lib.seeds import DEFAULT_SEED, set_global_seed
from lib.strategy import backtest


@dataclass(frozen=True)
class BacktestMetrics:
    total_return: float
    sharpe: float
    sortino: float
    calmar: float
    max_drawdown: float
    num_trades: int
    win_rate: float
    profit_factor: float
    turnover: float

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


@dataclass(frozen=True)
class BacktestResult:
    strategy: str
    ticker: str
    window_from: str
    window_to: str
    params: dict[str, Any]
    metrics: BacktestMetrics
    seed: int = DEFAULT_SEED
    duration_seconds: float = 0.0
    df: pd.DataFrame | None = field(default=None, repr=False, compare=False)

    def to_contract(self) -> dict[str, Any]:
        """Produce the JSON contract documented in AGENTS.md / build prompt."""
        return {
            "strategy": self.strategy,
            "ticker": self.ticker,
            "window": {"from": self.window_from, "to": self.window_to},
            "params": self.params,
            "metrics": self.metrics.as_dict(),
            "seed": int(self.seed),
            "duration_seconds": float(self.duration_seconds),
        }


def _safe_float(value: Any, default: float = 0.0) -> float:
    try:
        out = float(value)
    except (TypeError, ValueError):
        return default
    if not np.isfinite(out):
        return default
    return out


def calculate_sortino_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252,
) -> float:
    """Annualised Sortino: like Sharpe but only penalises downside volatility."""
    if returns is None or len(returns) == 0:
        return 0.0
    excess = returns - risk_free_rate / periods_per_year
    downside = excess[excess < 0]
    downside_std = downside.std()
    if downside_std == 0 or np.isnan(downside_std):
        return 0.0
    return float(np.sqrt(periods_per_year) * excess.mean() / downside_std)


def calculate_calmar_ratio(
    returns: pd.Series,
    max_drawdown: float,
    periods_per_year: int = 252,
) -> float:
    """Annualised return divided by absolute max drawdown."""
    if returns is None or len(returns) == 0 or max_drawdown == 0:
        return 0.0
    annualised = (1.0 + returns.mean()) ** periods_per_year - 1.0
    return float(annualised / abs(max_drawdown))


def count_trades(df: pd.DataFrame) -> int:
    """Count completed buy + sell triggers from the result frame."""
    if "Buy_Trigger_Accepted" in df.columns and "Sell_Trigger_Accepted" in df.columns:
        return int(df["Buy_Trigger_Accepted"].sum() + df["Sell_Trigger_Accepted"].sum())
    if "Units" in df.columns:
        diffs = df["Units"].diff().fillna(0)
        return int((diffs != 0).sum())
    return 0


def calculate_turnover(df: pd.DataFrame) -> float:
    """Approximate turnover as gross traded notional divided by mean equity."""
    if "Units_to_buy" not in df.columns or "Units_to_sell" not in df.columns:
        return 0.0
    if "Close" not in df.columns or "Portfolio_Value" not in df.columns:
        return 0.0
    gross = ((df["Units_to_buy"] + df["Units_to_sell"]) * df["Close"]).sum()
    mean_equity = df["Portfolio_Value"].mean()
    if mean_equity <= 0:
        return 0.0
    return float(gross / mean_equity)


def metrics_from_result_df(df: pd.DataFrame, initial_capital: float) -> BacktestMetrics:
    """Compute the JSON contract metrics from a backtest result DataFrame."""
    if df is None or df.empty:
        return BacktestMetrics(0, 0, 0, 0, 0, 0, 0, 0, 0)

    final_value = _safe_float(df["Portfolio_Value"].iloc[-1], initial_capital)
    total_return = (final_value / initial_capital) - 1.0 if initial_capital else 0.0

    returns = df.get("Strategy_Returns", pd.Series(dtype=float))
    sharpe = _safe_float(calculate_sharpe_ratio(returns)) if len(returns) else 0.0
    max_dd_signed = _safe_float(calculate_max_drawdown(df))
    max_dd = abs(max_dd_signed)
    sortino = calculate_sortino_ratio(returns) if len(returns) else 0.0
    calmar = calculate_calmar_ratio(returns, max_dd_signed) if max_dd_signed else 0.0
    win_rate = _safe_float(calculate_win_rate(df))
    profit_factor = _safe_float(calculate_profit_factor(df))
    num_trades = count_trades(df)
    turnover = calculate_turnover(df)

    return BacktestMetrics(
        total_return=total_return,
        sharpe=sharpe,
        sortino=sortino,
        calmar=calmar,
        max_drawdown=max_dd,
        num_trades=int(num_trades),
        win_rate=win_rate,
        profit_factor=profit_factor,
        turnover=turnover,
    )


def run_backtest_result(
    df_with_signals: pd.DataFrame,
    *,
    strategy_name: str,
    ticker: str,
    window_from: str,
    window_to: str,
    params: dict[str, Any],
    buy_signals: list[str],
    sell_signals: list[str],
    initial_capital: float = 10_000.0,
    strategy_mode: str = "trading",
    signal_logic: str = "or",
    signal_window: int = 0,
    seed: int = DEFAULT_SEED,
    backtest_kwargs: dict[str, Any] | None = None,
) -> BacktestResult:
    """Run a backtest and wrap the result in a structured BacktestResult."""
    set_global_seed(seed)
    started = time.perf_counter()

    extra = dict(backtest_kwargs or {})
    extra.setdefault("position_sizing_strategy", "percentage_of_portfolio")
    extra.setdefault("position_sizing_params", {"percent": 0.1})
    extra.setdefault("strategy_mode", strategy_mode)
    extra.setdefault("signal_logic", signal_logic)
    extra.setdefault("signal_window", signal_window)

    result_df = backtest(
        df=df_with_signals,
        initial_capital=initial_capital,
        buy_indicators=buy_signals,
        sell_indicators=sell_signals,
        **extra,
    )

    duration = time.perf_counter() - started
    metrics = metrics_from_result_df(result_df, initial_capital)

    return BacktestResult(
        strategy=strategy_name,
        ticker=ticker,
        window_from=window_from,
        window_to=window_to,
        params=dict(params),
        metrics=metrics,
        seed=int(seed),
        duration_seconds=float(duration),
        df=result_df,
    )
