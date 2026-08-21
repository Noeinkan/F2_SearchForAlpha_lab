"""BacktestResult dataclass and a thin wrapper around lib.strategy.backtest.

Existing callers (Dash, optimisers, tests) keep using lib.strategy.backtest
directly and continue to receive a pd.DataFrame. New CLI and agent code uses
``run_backtest_result`` to get a structured, JSON friendly result.

The metrics themselves live in :mod:`lib.metrics`. This module only runs the
backtest and wraps what comes back — it does not define a single formula.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Any

import pandas as pd

from lib.metrics import BacktestMetrics, compute_metrics
from lib.seeds import DEFAULT_SEED, set_global_seed
from lib.strategy import backtest


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
    interval: str = "1d"
    df: pd.DataFrame | None = field(default=None, repr=False, compare=False)

    def to_contract(self) -> dict[str, Any]:
        """Produce the JSON contract documented in AGENTS.md / build prompt."""
        return {
            "strategy": self.strategy,
            "ticker": self.ticker,
            "window": {
                "from": self.window_from,
                "to": self.window_to,
                "interval": self.interval,
            },
            "params": self.params,
            "metrics": self.metrics.as_dict(),
            "seed": int(self.seed),
            "duration_seconds": float(self.duration_seconds),
        }


def metrics_from_result_df(
    df: pd.DataFrame,
    initial_capital: float,
    *,
    interval: str = "1d",
    periods_per_year: int | None = None,
) -> BacktestMetrics:
    """Compute the JSON contract metrics from a backtest result DataFrame.

    Kept as the name most callers import; :func:`lib.metrics.compute_metrics`
    is the implementation.
    """
    return compute_metrics(
        df,
        initial_capital,
        interval=interval,
        periods_per_year=periods_per_year,
        context="lib.backtest_result.metrics_from_result_df",
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
    interval: str = "1d",
) -> BacktestResult:
    """Run a backtest and wrap the result in a structured BacktestResult."""
    set_global_seed(seed)
    started = time.perf_counter()

    extra = dict(backtest_kwargs or {})
    extra.setdefault("position_sizing_strategy", "percentage_of_portfolio")
    extra.setdefault("position_sizing_params", {"percent": 0.1})
    extra.setdefault("position_scaling", 1.0)
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
    metrics = compute_metrics(
        result_df,
        initial_capital,
        interval=interval,
        context="lib.backtest_result.run_backtest_result",
    )

    # Record the risk machinery that was *actually* applied. backtest() downgrades
    # an ATR stop or ATR sizer to its percentage equivalent when the ATR columns
    # are absent, so reading the request back would misdescribe the run.
    recorded_params = dict(params)
    for key in ("stop_mode", "position_sizing_strategy"):
        if key in result_df.attrs:
            recorded_params[key] = result_df.attrs[key]

    return BacktestResult(
        strategy=strategy_name,
        ticker=ticker,
        window_from=window_from,
        window_to=window_to,
        params=recorded_params,
        metrics=metrics,
        seed=int(seed),
        duration_seconds=float(duration),
        interval=interval,
        df=result_df,
    )


__all__ = ["BacktestMetrics", "BacktestResult", "metrics_from_result_df", "run_backtest_result"]
