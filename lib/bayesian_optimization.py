"""
Optuna based parameter search for agent strategies.

This module is a fourth optimisation flavour that lives alongside the existing
params, signal combination, and weights optimisers. None of the older modules
are touched.

Workflow:
    1. Resolve the strategy bundle and its search_space.
    2. Fetch OHLCV once for the requested window (mockable in tests).
    3. For each trial: regenerate signals with the suggested params and run
       a single backtest. Score with the chosen objective (sharpe, sortino,
       calmar, composite). Persist the trial via lib.store.trials.

Optuna's RDB storage at state/optuna.db handles study state and resume; our
own sfa_trials table holds the agent visible record (full metric breakdown,
seed, wall time, git commit).
"""

from __future__ import annotations

import json
import logging
import time
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable

import optuna
import pandas as pd
import structlog
import typer
from optuna.pruners import MedianPruner
from optuna.samplers import TPESampler

from lib.agent_strategy import (
    AgentStrategyBundle,
    StrategyNotFoundError,
    load_bundle,
    params_to_indicator_settings,
)
from lib.backtest_result import BacktestMetrics, run_backtest_result
from lib.cli.contracts import CliError
from lib.config_loader import get_agent_config
from lib.data_processing import fetch_data
from lib.seeds import set_global_seed
from lib.signals.indicators import add_indicators, generate_signals
from lib.store import trials as trials_store
from lib.walkforward.spaces import suggest_from_space, validate_space

logger = structlog.get_logger(__name__)

DEFAULT_STORAGE_URL = "sqlite:///state/optuna.db"
DEFAULT_DB_PATH = Path("state/optuna.db")
DEFAULT_TPE_SEED = 42
DEFAULT_N_WARMUP_STEPS = 20

VALID_METRICS = ("sharpe", "sortino", "calmar", "composite")


# Silence Optuna's INFO chatter during CLI runs; keep WARNING+ visible.
optuna.logging.set_verbosity(optuna.logging.WARNING)


@dataclass(frozen=True)
class OptimisationResult:
    study_id: str
    trials_completed: int
    best_trial_id: int
    best_optuna_number: int
    best_params: dict[str, Any]
    best_metrics: dict[str, Any]
    best_value: float
    metric: str
    duration_seconds: float

    def to_contract(self) -> dict[str, Any]:
        return {
            "study_id": self.study_id,
            "trials_completed": int(self.trials_completed),
            "best_trial": {
                "trial_id": int(self.best_trial_id),
                "optuna_trial_number": int(self.best_optuna_number),
                "params": self.best_params,
                "value": float(self.best_value),
                "metric": self.metric,
                "metrics": self.best_metrics,
            },
            "duration_seconds": float(self.duration_seconds),
        }


def composite_weights() -> dict[str, float]:
    cfg = get_agent_config().get("optimiser", {}).get("composite_weights", {})
    return {
        "sortino": float(cfg.get("sortino", 1.0)),
        "max_drawdown": float(cfg.get("max_drawdown", 2.0)),
        "turnover": float(cfg.get("turnover", 0.5)),
    }


def score_metrics(metric: str, m: BacktestMetrics) -> float:
    """Compute the objective value for one backtest result."""
    if metric == "sharpe":
        return float(m.sharpe)
    if metric == "sortino":
        return float(m.sortino)
    if metric == "calmar":
        return float(m.calmar)
    if metric == "composite":
        w = composite_weights()
        return float(
            w["sortino"] * m.sortino
            - w["max_drawdown"] * m.max_drawdown
            - w["turnover"] * m.turnover
        )
    raise ValueError(f"Unknown metric {metric!r}; expected one of {VALID_METRICS}")


def _make_study_id(strategy_name: str) -> str:
    stamp = datetime.now(UTC).strftime("%Y%m%d_%H%M%S")
    return f"{strategy_name}_{stamp}"


def _build_objective(
    *,
    bundle: AgentStrategyBundle,
    base_df: pd.DataFrame,
    metric: str,
    seed: int,
    study_id: str,
    db_path: Path,
    window_from: str,
    window_to: str,
    search_to: str,
    held_out_to: str,
) -> Callable[[optuna.trial.Trial], float]:
    def objective(trial: optuna.trial.Trial) -> float:
        params = suggest_from_space(trial, bundle.search_space)
        started = time.perf_counter()
        indicator_settings = params_to_indicator_settings(params)
        df = add_indicators(base_df.copy(), indicator_settings)
        df, _ = generate_signals(df, indicator_settings)

        result = run_backtest_result(
            df,
            strategy_name=bundle.name,
            ticker=bundle.ticker,
            window_from=window_from,
            window_to=search_to,
            params=params,
            buy_signals=bundle.buy_signals,
            sell_signals=bundle.sell_signals,
            strategy_mode=bundle.mode,
            signal_logic=bundle.signal_logic,
            signal_window=bundle.signal_window,
            seed=seed,
        )
        score = score_metrics(metric, result.metrics)
        wall = time.perf_counter() - started

        trial_metrics = result.metrics.as_dict()
        trial_metrics["search_to"] = search_to
        trial_metrics["held_out_to"] = held_out_to

        trials_store.save_trial(
            study_id=study_id,
            strategy_name=bundle.name,
            optuna_trial_number=trial.number,
            metric=metric,
            objective_value=score,
            params=params,
            metrics=trial_metrics,
            seed=seed,
            wall_seconds=wall,
            db_path=db_path,
        )
        return score

    return objective


def run_study(
    *,
    strategy_name: str,
    n_trials: int,
    metric: str = "sortino",
    window_from: str | None = None,
    window_to: str | None = None,
    held_out_months: int = 6,
    seed: int = DEFAULT_TPE_SEED,
    study_id: str | None = None,
    storage_url: str | None = None,
    db_path: Path | None = None,
) -> OptimisationResult:
    """Run an Optuna TPE study end to end and return the best trial.

    The last *held_out_months* of data are withheld from the parameter search
    so that walk-forward validation has genuinely unseen out-of-sample evidence.
    """
    if metric not in VALID_METRICS:
        raise ValueError(f"Unknown metric {metric!r}; expected one of {VALID_METRICS}")

    bundle = load_bundle(strategy_name)
    if not bundle.search_space:
        raise ValueError(f"Strategy {strategy_name!r} has no search_space configured")
    validate_space(bundle.search_space)

    if not window_from or not window_to:
        raise ValueError("window_from and window_to are required for optimisation")

    set_global_seed(seed)
    if storage_url is None:
        storage_url = DEFAULT_STORAGE_URL
    if db_path is None:
        db_path = DEFAULT_DB_PATH
    db_path.parent.mkdir(parents=True, exist_ok=True)

    base_df = fetch_data(bundle.ticker, window_from, window_to)
    search_to_dt = pd.to_datetime(window_to) - pd.DateOffset(months=held_out_months)
    search_to = search_to_dt.strftime("%Y-%m-%d")
    search_df = base_df[base_df.index < search_to_dt]
    sid = study_id or _make_study_id(strategy_name)

    sampler = TPESampler(seed=seed, n_startup_trials=10)
    pruner = MedianPruner(n_warmup_steps=DEFAULT_N_WARMUP_STEPS)
    study = optuna.create_study(
        study_name=sid,
        direction="maximize",
        sampler=sampler,
        pruner=pruner,
        storage=storage_url,
        load_if_exists=True,
    )

    objective = _build_objective(
        bundle=bundle,
        base_df=search_df,
        metric=metric,
        seed=seed,
        study_id=sid,
        db_path=db_path,
        window_from=window_from,
        window_to=window_to,
        search_to=search_to,
        held_out_to=window_to,
    )

    started = time.perf_counter()
    study.optimize(objective, n_trials=int(n_trials), show_progress_bar=False)
    duration = time.perf_counter() - started

    best = study.best_trial
    persisted = trials_store.list_trials(strategy_name=strategy_name, study_id=sid, db_path=db_path)
    matching = next((t for t in persisted if t.optuna_trial_number == best.number), None)
    if matching is None:
        raise RuntimeError(f"Optuna best trial {best.number} not found in persisted store")

    return OptimisationResult(
        study_id=sid,
        trials_completed=len(study.trials),
        best_trial_id=matching.trial_id,
        best_optuna_number=int(best.number),
        best_params=matching.params,
        best_metrics=matching.metrics,
        best_value=float(matching.objective_value),
        metric=metric,
        duration_seconds=duration,
    )


def run_optimise_cli(
    *,
    name: str,
    trials: int,
    metric: str,
    window_from: str | None,
    window_to: str | None,
    study_id: str | None,
    seed: int,
    json_output: bool,
) -> None:
    try:
        result = run_study(
            strategy_name=name,
            n_trials=trials,
            metric=metric,
            window_from=window_from,
            window_to=window_to,
            seed=seed,
            study_id=study_id,
        )
    except StrategyNotFoundError:
        typer.echo(json.dumps(CliError("unknown_strategy", f"No agent strategy named {name!r}.").as_dict()))
        raise typer.Exit(code=2)
    except ValueError as exc:
        typer.echo(json.dumps(CliError("invalid_input", str(exc)).as_dict()))
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(json.dumps(CliError("optimise_failed", str(exc)).as_dict()))
        raise typer.Exit(code=3) from exc

    contract = result.to_contract()
    if json_output:
        typer.echo(json.dumps(contract, indent=2, default=str))
        return
    bt = contract["best_trial"]
    typer.echo(
        f"study {contract['study_id']}\n"
        f"  trials_completed {contract['trials_completed']}\n"
        f"  duration         {contract['duration_seconds']:.1f}s\n"
        f"  best.trial_id    {bt['trial_id']}\n"
        f"  best.value       {bt['value']:.4f} ({bt['metric']})\n"
        f"  best.params      {bt['params']}"
    )


def list_trials_cli(*, name: str, study_id: str | None, top: int, json_output: bool) -> None:
    rows = trials_store.list_trials(strategy_name=name, study_id=study_id, limit=top)
    payload = {"strategy": name, "study_id": study_id, "trials": [r.as_dict() for r in rows]}
    if json_output:
        typer.echo(json.dumps(payload, indent=2, default=str))
        return
    if not rows:
        typer.echo(f"No persisted trials for strategy {name!r}.")
        return
    for r in rows:
        typer.echo(
            f"#{r.trial_id}  {r.metric}={r.objective_value:+.4f}  params={r.params}  "
            f"sharpe={r.metrics.get('sharpe'):.3f}  max_dd={r.metrics.get('max_drawdown'):.4f}"
        )
