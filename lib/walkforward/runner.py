"""
Rolling walk forward orchestrator.

For each of N windows: take a (train_months) IS slice and an immediately
following (test_months) OOS slice from the fetched OHLCV. Re run the signal
pipeline with the candidate params on the slice, backtest each segment, and
collect the metric breakdown for both. Defer the robust verdict to
verdict.aggregate.

Records persist to sqlite (sfa_walkforward) so the promotion gate can later
look up "is there a recent walk forward record for these exact params?"
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
from lib.signals.indicators import add_indicators, generate_signals
from lib.store import trials as trials_store
from lib.strategy import backtest

logger = structlog.get_logger(__name__)


@dataclass(frozen=True)
class WalkForwardOptions:
    n_windows: int = 5
    train_months: int = 12
    test_months: int = 3
    initial_capital: float = 10_000.0
    seed: int = 42


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


def _backtest_metrics(slice_df: pd.DataFrame, bundle: AgentStrategyBundle, capital: float) -> dict[str, Any]:
    if slice_df.empty:
        return {"sharpe": 0.0, "sortino": 0.0, "max_drawdown": 0.0, "num_trades": 0, "total_return": 0.0}
    result_df = backtest(
        df=slice_df,
        initial_capital=capital,
        position_sizing_strategy="percentage_of_portfolio",
        position_sizing_params={"percent": 0.1},
        buy_indicators=bundle.buy_signals,
        sell_indicators=bundle.sell_signals,
        strategy_mode=bundle.mode,
    )
    metrics = metrics_from_result_df(result_df, capital)
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

    # Total span: (n - 1) * test_months + train_months + test_months months.
    today = datetime.now(UTC).replace(tzinfo=None)
    total_months = (options.n_windows - 1) * options.test_months + options.train_months + options.test_months
    base_end = today
    base_start = base_end - relativedelta(months=total_months) - relativedelta(months=2)  # warmup buffer

    # Use a fixed window relative to today so tests can monkeypatch fetch_data.
    base_df = fetch_data(
        bundle.ticker,
        base_start.strftime("%Y-%m-%d"),
        base_end.strftime("%Y-%m-%d"),
    )

    indicator_settings = params_to_indicator_settings(params)
    enriched = add_indicators(base_df.copy(), indicator_settings)
    enriched, _ = generate_signals(enriched, indicator_settings)

    windows: list[dict[str, Any]] = []
    span_start = base_end - relativedelta(months=total_months)
    for k in range(options.n_windows):
        train_start = span_start + relativedelta(months=k * options.test_months)
        train_end = train_start + relativedelta(months=options.train_months)
        test_end = train_end + relativedelta(months=options.test_months)

        train_df = _slice(enriched, train_start, train_end)
        test_df = _slice(enriched, train_end, test_end)

        train_metrics = _backtest_metrics(train_df, bundle, options.initial_capital)
        test_metrics = _backtest_metrics(test_df, bundle, options.initial_capital)

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
                windows_json, robust, oos_sharpe_mean, degradation, recorded_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
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
            ),
        )


def find_recent_walkforward(
    strategy_name: str,
    params: dict[str, Any],
    *,
    db_path: Path | None = None,
) -> dict[str, Any] | None:
    """Return the most recent walk forward record for this strategy + exact params."""
    canon = json.dumps(params, sort_keys=True)
    with trials_store.connect(db_path) as conn:
        row = conn.execute(
            """
            SELECT walkforward_id, params_json, aggregate_json, windows_json,
                   robust, oos_sharpe_mean, degradation, recorded_at
            FROM sfa_walkforward
            WHERE strategy_name = ? AND params_json = ?
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
    seed: int,
    json_output: bool,
) -> None:
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
                seed=seed,
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
