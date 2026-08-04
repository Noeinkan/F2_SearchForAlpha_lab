"""
Signal-combo walk-forward for the Dash Optimizer.

Mirrors ``lib.walkforward.runner`` window geometry and ``aggregate()`` verdict,
but evaluates an arbitrary buy/sell column list via ``run_backtest`` (the
combinatorial optimizer winner) instead of an agent bundle.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

import pandas as pd
from dateutil.relativedelta import relativedelta

from lib.backtest_result import metrics_from_result_df
from lib.data_processing import fetch_data
from lib.signals.indicators import add_indicators, generate_signals, longest_lookback
from lib.strategy import run_backtest
from lib.walkforward.runner import WalkForwardOptions, _slice
from lib.walkforward.verdict import aggregate


@dataclass(frozen=True)
class ComboSpec:
    buy_signals: tuple[str, ...]
    sell_signals: tuple[str, ...]
    ticker: str
    indicator_settings: dict[str, Any]
    backtest_kwargs: dict[str, Any] | None = None


def _metrics_for_slice(
    slice_df: pd.DataFrame,
    *,
    capital: float,
    buy: list[str],
    sell: list[str],
    interval: str,
    backtest_kwargs: dict[str, Any] | None,
) -> dict[str, Any]:
    if slice_df.empty:
        return {
            "sharpe": 0.0,
            "sortino": 0.0,
            "max_drawdown": 0.0,
            "num_trades": 0,
            "total_return": 0.0,
        }
    result_df = run_backtest(
        df=slice_df,
        initial_capital=capital,
        buy_indicators=buy,
        sell_indicators=sell,
        **(backtest_kwargs or {}),
    )
    return metrics_from_result_df(result_df, capital, interval=interval).as_dict()


def run_combo_walkforward(
    *,
    combo: ComboSpec,
    options: WalkForwardOptions | None = None,
) -> dict[str, Any]:
    """Rolling IS/OOS validation for a signal combination.

    Returns the same shape as ``run_walkforward`` (windows + aggregate), with
    ``strategy`` set to a synthetic ``combo:<buy>|<sell>`` label. Does **not**
    write to ``sfa_walkforward`` (agent promotion gate stays CLI-only).
    """
    options = options or WalkForwardOptions()
    buy = list(combo.buy_signals)
    sell = list(combo.sell_signals)
    settings = combo.indicator_settings or {}
    kwargs = dict(combo.backtest_kwargs or {})

    step = options.step_months or (options.train_months + options.test_months)
    total_months = (options.n_windows - 1) * step + options.train_months + options.test_months

    today = datetime.now(UTC).replace(tzinfo=None)
    base_end = today
    base_start = base_end - relativedelta(months=total_months) - relativedelta(months=2)

    base_df = fetch_data(
        combo.ticker,
        base_start.strftime("%Y-%m-%d"),
        base_end.strftime("%Y-%m-%d"),
        interval=options.interval,
    )

    warmup_days = longest_lookback(settings)
    windows: list[dict[str, Any]] = []
    span_start = base_end - relativedelta(months=total_months)

    for k in range(options.n_windows):
        train_start = span_start + relativedelta(months=k * step)
        train_end = train_start + relativedelta(months=options.train_months)
        test_end = train_end + relativedelta(months=options.test_months)

        warmup_offset = relativedelta(days=warmup_days)
        raw = _slice(base_df, train_start - warmup_offset, test_end)
        if raw.empty:
            enriched = raw
        else:
            enriched = generate_signals(add_indicators(raw.copy(), settings), settings)[0]
            if len(enriched.index) > 0:
                if isinstance(enriched.index[0], pd.Timestamp):
                    cutoff = pd.Timestamp(train_start)
                else:
                    cutoff = train_start.date() if hasattr(train_start, "date") else train_start
                enriched = enriched[enriched.index >= cutoff]

        train_df = _slice(enriched, train_start, train_end)
        test_df = _slice(enriched, train_end, test_end)

        train_metrics = _metrics_for_slice(
            train_df,
            capital=options.initial_capital,
            buy=buy,
            sell=sell,
            interval=options.interval,
            backtest_kwargs=kwargs,
        )
        test_metrics = _metrics_for_slice(
            test_df,
            capital=options.initial_capital,
            buy=buy,
            sell=sell,
            interval=options.interval,
            backtest_kwargs=kwargs,
        )

        windows.append(
            {
                "index": k,
                "train": {
                    "from": train_start.strftime("%Y-%m-%d"),
                    "to": train_end.strftime("%Y-%m-%d"),
                    "sharpe": train_metrics["sharpe"],
                    "sortino": train_metrics["sortino"],
                    "max_drawdown": train_metrics["max_drawdown"],
                    "num_trades": train_metrics["num_trades"],
                    "total_return": train_metrics["total_return"],
                    "oos_sharpe_flag": "is",
                },
                "test": {
                    "from": train_end.strftime("%Y-%m-%d"),
                    "to": test_end.strftime("%Y-%m-%d"),
                    "sharpe": test_metrics["sharpe"],
                    "sortino": test_metrics["sortino"],
                    "max_drawdown": test_metrics["max_drawdown"],
                    "num_trades": test_metrics["num_trades"],
                    "total_return": test_metrics["total_return"],
                    "oos_sharpe_flag": "oos",
                },
            }
        )

    verdict = aggregate(windows)
    label = f"combo:{','.join(buy)}|{','.join(sell)}"
    return {
        "strategy": label,
        "params": {"buy_signals": buy, "sell_signals": sell},
        "windows": windows,
        "aggregate": verdict.as_dict(),
        "walkforward_id": f"combo_wf_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}",
        "recorded_at": datetime.now(UTC).isoformat(),
    }
