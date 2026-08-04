"""
Rolling walk forward orchestrator.

For each of N windows: take a (train_months) IS slice and an immediately
following (test_months) OOS slice from the fetched OHLCV. Indicators are
computed **per slice** (including a warmup prefix) to eliminate look-ahead
bias. Slice windows are non-overlapping by default.  Candidate params are
passed through to the backtest so position-sizing settings are honoured.

Records persist to sqlite (sfa_walkforward, schema_version=2) so the
promotion gate can later look up "is there a recent walk forward record for
these exact params?"
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

import pandas as pd
import structlog
import typer
from dateutil.relativedelta import relativedelta

from lib.agent_strategy import (
    AgentStrategyBundle,
    StrategyNotFoundError,
    load_bundle,
    params_to_indicator_settings,
)
from lib.backtest_result import metrics_from_result_df
from lib.cli.contracts import CliError
from lib.data_processing import fetch_data
from lib.seeds import set_global_seed
from lib.signals.indicators import add_indicators, generate_signals, longest_lookback
from lib.store import trials as trials_store
from lib.strategy import backtest

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class WalkForwardOptions:
    n_windows: int = 5
    train_months: int = 12
    test_months: int = 3
    step_months: int | None = None   # None → non-overlapping default (train + test)
    initial_capital: float = 10_000.0
    seed: int = 42
    interval: str = "1d"


def _slice(df: pd.DataFrame, start: datetime, end: datetime) -> pd.DataFrame:
    """Slice a dataframe by [start, end) regardless of whether the index holds
    pandas Timestamps (datetime64) or Python date objects.
    """
    if df.empty:
        return df
    idx_sample = df.index[0]
    if isinstance(idx_sample, pd.Timestamp) or hasattr(idx_sample, "tzinfo"):
        lo = pd.Timestamp(start)
        hi = pd.Timestamp(end)
    else:
        lo = start.date() if hasattr(start, "date") else start
        hi = end.date() if hasattr(end, "date") else end
    mask = (df.index >= lo) & (df.index < hi)
    return df[mask]


def _to_date(value: str | datetime) -> datetime:
    if isinstance(value, datetime):
        return value
    return datetime.strptime(value, "%Y-%m-%d")


def _backtest_metrics(
    slice_df: pd.DataFrame,
    bundle: AgentStrategyBundle,
    capital: float,
    params: dict[str, Any],
    *,
    interval: str = "1d",
) -> dict[str, Any]:
    if slice_df.empty:
        return {"sharpe": 0.0, "sortino": 0.0, "max_drawdown": 0.0, "num_trades": 0, "total_return": 0.0}
    from lib.execution_params import partition_params

    parted = partition_params(params)
    exec_kwargs = dict(parted.backtest_kwargs)
    pos_strategy = exec_kwargs.pop(
        "position_sizing_strategy",
        params.get("position_sizing_strategy", "percentage_of_portfolio"),
    )
    pos_params = exec_kwargs.pop(
        "position_sizing_params",
        params.get("position_sizing_params", {"percent": 0.1}),
    )
    result_df = backtest(
        df=slice_df,
        initial_capital=capital,
        position_sizing_strategy=pos_strategy,
        position_sizing_params=pos_params,
        buy_indicators=bundle.buy_signals,
        sell_indicators=bundle.sell_signals,
        strategy_mode=bundle.mode,
        signal_logic=parted.signal_logic or bundle.signal_logic,
        signal_window=(
            parted.signal_window
            if parted.signal_window is not None
            else bundle.signal_window
        ),
        **exec_kwargs,
    )
    metrics = metrics_from_result_df(result_df, capital, interval=interval)
    return metrics.as_dict()


def run_walkforward(
    *,
    strategy_name: str,
    params: dict[str, Any],
    options: WalkForwardOptions | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Run rolling walk forward and return the JSON contract record."""
    options = options or WalkForwardOptions()
    bundle = load_bundle(strategy_name)
    set_global_seed(options.seed)

    step = options.step_months or (options.train_months + options.test_months)
    total_months = (options.n_windows - 1) * step + options.train_months + options.test_months

    today = datetime.now(UTC).replace(tzinfo=None)
    base_end = today
    base_start = base_end - relativedelta(months=total_months) - relativedelta(months=2)

    base_df = fetch_data(
        bundle.ticker,
        base_start.strftime("%Y-%m-%d"),
        base_end.strftime("%Y-%m-%d"),
        interval=options.interval,
    )

    indicator_settings = params_to_indicator_settings(params)
    warmup_days = longest_lookback(indicator_settings)

    windows: list[dict[str, Any]] = []
    span_start = base_end - relativedelta(months=total_months)
    for k in range(options.n_windows):
        train_start = span_start + relativedelta(months=k * step)
        train_end = train_start + relativedelta(months=options.train_months)
        test_end = train_end + relativedelta(months=options.test_months)

        warmup_offset = relativedelta(days=warmup_days)
        raw = _slice(base_df, train_start - warmup_offset, test_end)
        if raw.empty:
            logger.warning("walkforward.empty_raw_slice", window=k)
            enriched = raw
        else:
            enriched = generate_signals(add_indicators(raw.copy(), indicator_settings), indicator_settings)[0]
            # Drop warmup prefix rows
            if isinstance(enriched.index[0], pd.Timestamp):
                cutoff = pd.Timestamp(train_start)
            else:
                cutoff = train_start.date() if hasattr(train_start, "date") else train_start
            enriched = enriched[enriched.index >= cutoff]

        train_df = _slice(enriched, train_start, train_end)
        test_df = _slice(enriched, train_end, test_end)

        train_metrics = _backtest_metrics(
            train_df, bundle, options.initial_capital, params, interval=options.interval
        )
        test_metrics = _backtest_metrics(
            test_df, bundle, options.initial_capital, params, interval=options.interval
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

    from lib.walkforward.verdict import aggregate

    verdict = aggregate(windows)
    walkforward_id = f"wf_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"
    recorded_at = datetime.now(UTC).isoformat()

    payload = {
        "strategy": strategy_name,
        "params": dict(params),
        "windows": windows,
        "aggregate": verdict.as_dict(),
        "walkforward_id": walkforward_id,
        "recorded_at": recorded_at,
    }

    _persist(payload, db_path=db_path)
    return payload


def _persist(payload: dict[str, Any], db_path: Path | None = None) -> None:
    with trials_store.connect(db_path) as conn:
        conn.execute(
            """
            INSERT INTO sfa_walkforward (
                walkforward_id, strategy_name, params_json, aggregate_json,
                windows_json, robust, oos_sharpe_mean, degradation, recorded_at,
                schema_version
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload["walkforward_id"],
                payload["strategy"],
                json.dumps(payload["params"], sort_keys=True),
                json.dumps(payload["aggregate"]),
                json.dumps(payload["windows"]),
                int(bool(payload["aggregate"]["robust"])),
                float(payload["aggregate"]["oos_sharpe_mean"]),
                float(payload["aggregate"]["degradation"]),
                payload["recorded_at"],
                2,
            ),
        )


def find_recent_walkforward(
    strategy_name: str,
    params: dict[str, Any],
    *,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """Return the most recent walk forward record (schema_version=2) for this strategy + exact params."""
    canon = json.dumps(params, sort_keys=True)
    with trials_store.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT walkforward_id, params_json, aggregate_json, windows_json,
                   robust, oos_sharpe_mean, degradation, recorded_at
            FROM sfa_walkforward
            WHERE strategy_name = ? AND params_json = ? AND schema_version = 2
            ORDER BY recorded_at DESC
            LIMIT 1
            """,
            (strategy_name, canon),
        ).fetchone()
    if not row:
        return None
    return {
        "walkforward_id": row["walkforward_id"],
        "strategy": strategy_name,
        "params": json.loads(row["params_json"]),
        "aggregate": json.loads(row["aggregate_json"]),
        "windows": json.loads(row["windows_json"]),
        "recorded_at": row["recorded_at"],
    }


def _resolve_params(params_arg: str) -> dict[str, Any]:
    """Accept either a trial id (int string) or a JSON object."""
    raw = params_arg.strip()
    if raw.isdigit():
        record = trials_store.get_trial(int(raw))
        if record is None:
            raise ValueError(f"No trial with id {raw}")
        return record.params
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--params must be a trial id or JSON object")
    return parsed


def run_walkforward_cli(
    *,
    name: str,
    params_arg: str,
    windows: int,
    train_months: int,
    test_months: int,
    step_months: int | None = None,
    seed: int,
    json_output: bool,
    interval: str = "1d",
) -> None:
    """CLI entry point for sfa walkforward.

    Uses non-overlapping windows by default (step = train + test months).
    Pass --step-months to override the stride between windows.
    """
    from lib.timeframes import IntervalError, normalize_interval

    try:
        canon = normalize_interval(interval)
    except IntervalError as exc:
        typer.echo(json.dumps(CliError("invalid_interval", str(exc)).as_dict()))
        raise typer.Exit(code=2) from exc

    try:
        params = _resolve_params(params_arg)
    except (ValueError, json.JSONDecodeError) as exc:
        typer.echo(json.dumps(CliError("invalid_params", str(exc)).as_dict()))
        raise typer.Exit(code=2) from exc

    try:
        payload = run_walkforward(
            strategy_name=name,
            params=params,
            options=WalkForwardOptions(
                n_windows=windows,
                train_months=train_months,
                test_months=test_months,
                step_months=step_months,
                seed=seed,
                interval=canon,
            ),
        )
    except StrategyNotFoundError:
        typer.echo(json.dumps(CliError("unknown_strategy", f"No agent strategy named {name!r}.").as_dict()))
        raise typer.Exit(code=2)
    except Exception as exc:
        typer.echo(json.dumps(CliError("walkforward_failed", str(exc)).as_dict()))
        raise typer.Exit(code=3) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, default=str))
        return
    agg = payload["aggregate"]
    typer.echo(
        f"{payload['strategy']}  walkforward_id={payload['walkforward_id']}\n"
        f"  is_sharpe_mean    {agg['is_sharpe_mean']:+.3f}\n"
        f"  oos_sharpe_mean   {agg['oos_sharpe_mean']:+.3f}\n"
        f"  degradation       {agg['degradation']:.3f}\n"
        f"  robust            {agg['robust']}  ({agg['robust_reason']})"
    )
