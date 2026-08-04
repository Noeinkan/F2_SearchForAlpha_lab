"""
Capped cartesian grid search over a unified (indicator + execution) space.

Companion to ``lib.bayesian_optimization``: use this when the space is small
enough to enumerate; use Optuna when it is not.
"""

from __future__ import annotations

import json
import logging
import threading
import time
from dataclasses import dataclass, field
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import pandas as pd
import typer

logger = logging.getLogger(__name__)

from lib.agent_strategy import (
    AgentStrategyBundle,
    StrategyNotFoundError,
    load_bundle,
    params_to_indicator_settings,
)
from lib.bayesian_optimization import VALID_METRICS, score_metrics
from lib.cli.contracts import CliError
from lib.execution_params import partition_params
from lib.backtest_result import run_backtest_result
from lib.data_processing import fetch_data
from lib.seeds import set_global_seed
from lib.signals.indicators import add_indicators, generate_signals
from lib.store import trials as trials_store
from lib.walkforward.spaces import (
    enumerate_grid,
    estimate_grid_size,
    resolve_search_space,
    validate_space,
)

DEFAULT_DB_PATH = Path("state/optuna.db")
DEFAULT_MAX_COMBOS = 250


@dataclass(frozen=True)
class GridSearchResult:
    study_id: str
    combinations_tested: int
    combinations_total: int
    best_trial_id: int
    best_params: dict[str, Any]
    best_metrics: dict[str, Any]
    best_value: float
    metric: str
    duration_seconds: float
    space_keys: list[str]
    trials: list[dict[str, Any]] = field(default_factory=list)
    cancelled: bool = False

    def to_contract(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "mode": "grid",
            "combinations_tested": int(self.combinations_tested),
            "combinations_total": int(self.combinations_total),
            "space_keys": list(self.space_keys),
            "best_trial": {
                "trial_id": int(self.best_trial_id),
                "params": self.best_params,
                "value": float(self.best_value),
                "metric": self.metric,
                "metrics": self.best_metrics,
            },
            "trials": list(self.trials),
            "cancelled": bool(self.cancelled),
            "duration_seconds": float(self.duration_seconds),
        }


def _make_study_id(strategy_name: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"grid_{strategy_name}_{stamp}"


def _evaluate_combo(
    *,
    bundle: AgentStrategyBundle,
    base_df: pd.DataFrame,
    params: dict[str, Any],
    metric: str,
    seed: int,
    study_id: str,
    db_path: Path,
    window_from: str,
    window_to: str,
    ticker: str,
    interval: str,
    trial_number: int,
) -> tuple[float, dict[str, Any], float]:
    started = time.perf_counter()
    parted = partition_params(params)
    # Keep full flat map for indicator regeneration (execution keys ignored there).
    indicator_settings = params_to_indicator_settings(params)
    df = add_indicators(base_df.copy(), indicator_settings)
    df, _ = generate_signals(df, indicator_settings)

    result = run_backtest_result(
        df,
        strategy_name=bundle.name,
        ticker=ticker,
        window_from=window_from,
        window_to=window_to,
        params=params,
        buy_signals=bundle.buy_signals,
        sell_signals=bundle.sell_signals,
        strategy_mode=bundle.mode,
        signal_logic=parted.signal_logic or bundle.signal_logic,
        signal_window=(
            parted.signal_window if parted.signal_window is not None else bundle.signal_window
        ),
        seed=seed,
        backtest_kwargs=parted.backtest_kwargs or None,
        interval=interval,
    )
    score = score_metrics(metric, result.metrics)
    wall = time.perf_counter() - started
    trial_metrics = result.metrics.as_dict()
    trials_store.save_trial(
        study_id=study_id,
        strategy_name=bundle.name,
        optuna_trial_number=trial_number,
        metric=metric,
        objective_value=score,
        params=params,
        metrics=trial_metrics,
        seed=seed,
        wall_seconds=wall,
        db_path=db_path,
    )
    return score, trial_metrics, wall


def run_grid_search(
    *,
    strategy_name: str,
    metric: str = "sortino",
    window_from: str | None = None,
    window_to: str | None = None,
    seed: int = 42,
    study_id: str | None = None,
    db_path: Path | None = None,
    ticker_override: str | None = None,
    interval: str = "1d",
    include_execution: bool = False,
    only_keys: list[str] | None = None,
    max_combos: int = DEFAULT_MAX_COMBOS,
    dry_run: bool = False,
    json_output: bool = False,
    cancel_event: threading.Event | None = None,
    progress_callback: Callable[[int, int], None] | None = None,
) -> GridSearchResult | dict[str, Any]:
    """Enumerate a capped grid and return the best combination."""
    from lib.timeframes import normalize_interval

    if metric not in VALID_METRICS:
        raise ValueError(f"Unknown metric {metric!r}; expected one of {VALID_METRICS}")
    if not window_from or not window_to:
        raise ValueError("window_from and window_to are required for grid search")

    canon = normalize_interval(interval)
    bundle = load_bundle(strategy_name)
    space = resolve_search_space(
        bundle.search_space,
        include_execution=include_execution,
        only_keys=only_keys,
    )
    if not space:
        raise ValueError(f"Strategy {strategy_name!r} resolved to an empty search space")
    validate_space(space)

    total = estimate_grid_size(space)
    if dry_run:
        return {
            "mode": "grid",
            "strategy": strategy_name,
            "combinations_total": total,
            "max_combos": int(max_combos),
            "within_cap": total <= int(max_combos),
            "space_keys": list(space.keys()),
            "space": space,
        }

    combos = enumerate_grid(space, max_combos=max_combos)
    ticker = ticker_override or bundle.ticker
    if not ticker:
        raise ValueError(f"Strategy {strategy_name!r} has no ticker configured")

    set_global_seed(seed)
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    base_df = fetch_data(ticker, window_from, window_to, interval=canon)
    sid = study_id or _make_study_id(
        f"{strategy_name}__{ticker}" if ticker_override else strategy_name
    )

    if not json_output:
        import sys

        print(
            f"Grid-search {strategy_name!r}  metric={metric}  combos={len(combos)}  "
            f"keys={list(space.keys())}  window={window_from}→{window_to}",
            file=sys.stderr,
            flush=True,
        )

    started = time.perf_counter()
    best_score = float("-inf")
    best_params: dict[str, Any] = {}
    best_metrics: dict[str, Any] = {}
    best_trial_number = -1
    trial_rows: list[dict[str, Any]] = []
    cancelled = False

    for idx, params in enumerate(combos):
        if cancel_event is not None and cancel_event.is_set():
            cancelled = True
            break
        # Overlay live_params so omitted dimensions stay at promoted defaults.
        full_params = dict(bundle.live_params)
        full_params.update(params)
        score, trial_metrics, _wall = _evaluate_combo(
            bundle=bundle,
            base_df=base_df,
            params=full_params,
            metric=metric,
            seed=seed,
            study_id=sid,
            db_path=db_path,
            window_from=window_from,
            window_to=window_to,
            ticker=ticker,
            interval=canon,
            trial_number=idx,
        )
        trial_rows.append({
            "index": idx,
            "params": dict(params),
            "full_params": dict(full_params),
            "value": float(score),
            "metrics": trial_metrics,
        })
        if progress_callback is not None:
            try:
                progress_callback(idx + 1, len(combos))
            except Exception:
                logger.debug("grid_search.progress_callback_failed", exc_info=True)
        if not json_output:
            import sys

            print(
                f"  combo {idx + 1:>3}/{len(combos)}  {metric}={score:+.4f}  "
                f"best={max(best_score, score):+.4f}  [{params}]",
                file=sys.stderr,
                flush=True,
            )
        if score > best_score:
            best_score = score
            best_params = dict(full_params)
            best_metrics = trial_metrics
            best_trial_number = idx

    duration = time.perf_counter() - started
    if best_trial_number < 0:
        raise RuntimeError("Grid search produced no completed combinations")

    persisted = trials_store.list_trials(
        strategy_name=strategy_name, study_id=sid, db_path=db_path
    )
    matching = next(
        (t for t in persisted if t.optuna_trial_number == best_trial_number), None
    )
    if matching is None:
        raise RuntimeError(f"Best grid combo {best_trial_number} not found in trial store")

    return GridSearchResult(
        study_id=sid,
        combinations_tested=len(trial_rows),
        combinations_total=total,
        best_trial_id=matching.trial_id,
        best_params=matching.params,
        best_metrics=matching.metrics,
        best_value=float(matching.objective_value),
        metric=metric,
        duration_seconds=duration,
        space_keys=list(space.keys()),
        trials=trial_rows,
        cancelled=cancelled,
    )


def run_grid_search_cli(
    *,
    name: str,
    metric: str,
    window_from: str | None,
    window_to: str | None,
    study_id: str | None,
    seed: int,
    json_output: bool,
    ticker: str | None,
    interval: str,
    include_execution: bool,
    params: str | None,
    max_combos: int,
    dry_run: bool,
) -> None:
    only_keys = None
    if params:
        only_keys = [p.strip() for p in params.split(",") if p.strip()]

    try:
        result = run_grid_search(
            strategy_name=name,
            metric=metric,
            window_from=window_from,
            window_to=window_to,
            seed=seed,
            study_id=study_id,
            ticker_override=ticker,
            interval=interval,
            include_execution=include_execution,
            only_keys=only_keys,
            max_combos=max_combos,
            dry_run=dry_run,
            json_output=json_output,
        )
    except StrategyNotFoundError:
        typer.echo(json.dumps(CliError("unknown_strategy", f"No agent strategy named {name!r}.").as_dict()))
        raise typer.Exit(code=2)
    except ValueError as exc:
        typer.echo(json.dumps(CliError("invalid_input", str(exc)).as_dict()))
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(json.dumps(CliError("grid_search_failed", str(exc)).as_dict()))
        raise typer.Exit(code=3) from exc

    if dry_run:
        payload = result if isinstance(result, dict) else result
        if json_output:
            typer.echo(json.dumps(payload, indent=2, default=str))
        else:
            typer.echo(
                f"grid dry-run  combos={payload['combinations_total']}  "
                f"cap={payload['max_combos']}  ok={payload['within_cap']}  "
                f"keys={payload['space_keys']}"
            )
        return

    assert isinstance(result, GridSearchResult)
    contract = result.to_contract()
    if json_output:
        typer.echo(json.dumps(contract, indent=2, default=str))
        return
    bt = contract["best_trial"]
    typer.echo(
        f"study {contract['study_id']}\n"
        f"  mode             grid\n"
        f"  combinations     {contract['combinations_tested']}\n"
        f"  duration         {contract['duration_seconds']:.1f}s\n"
        f"  best.trial_id    {bt['trial_id']}\n"
        f"  best.value       {bt['value']:.4f} ({bt['metric']})\n"
        f"  best.params      {bt['params']}"
    )
