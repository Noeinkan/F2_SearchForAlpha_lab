"""
Promotion gate: refuses unless every check passes.

Checks (all must be true unless --force):
    1. A walk forward record exists for these exact params, run within
       walkforward_max_age_days.
    2. aggregate.robust == True
    3. aggregate.oos_sharpe_mean >= min_oos_sharpe_mean
    4. aggregate.degradation <= max_degradation
    5. Strategy is not currently running (no PID file in state/running).

--force bypasses (5) only.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

import typer
from dateutil.parser import isoparse

from lib.agent_strategy import StrategyNotFoundError, load_bundle
from lib.cli.contracts import CliError
from lib.config_loader import get_agent_config
from lib.promotion.registry import (
    append_history_yaml,
    diff_params,
    get_last_promoted,
    record_promotion,
    update_live_params,
)
from lib.store import trials as trials_store
from lib.walkforward.runner import find_recent_walkforward

DEFAULT_THRESHOLDS = {
    "min_oos_sharpe_mean": 1.0,
    "max_degradation": 0.4,
    "walkforward_max_age_days": 7,
}


@dataclass(frozen=True)
class GateRefusal:
    reason: str
    details: str

    def as_contract(self) -> dict[str, Any]:
        return {"promoted": False, "reason": self.reason, "details": self.details}


def _thresholds() -> dict[str, float]:
    cfg = get_agent_config().get("promotion", {}) or {}
    return {
        "min_oos_sharpe_mean": float(cfg.get("min_oos_sharpe_mean", DEFAULT_THRESHOLDS["min_oos_sharpe_mean"])),
        "max_degradation": float(cfg.get("max_degradation", DEFAULT_THRESHOLDS["max_degradation"])),
        "walkforward_max_age_days": float(
            cfg.get("walkforward_max_age_days", DEFAULT_THRESHOLDS["walkforward_max_age_days"])
        ),
    }


def _is_running(strategy_name: str) -> bool:
    pid_path = Path("state/running") / f"{strategy_name}.pid"
    return pid_path.exists()


def evaluate_gate(
    *,
    strategy_name: str,
    candidate_params: dict[str, Any],
    force: bool = False,
    db_path: Path | None = None,
) -> GateRefusal | dict[str, Any]:
    """Return a GateRefusal or a dict with the resolved walkforward record + gate stats."""
    thresholds = _thresholds()
    record = find_recent_walkforward(strategy_name, candidate_params, db_path=db_path)
    if record is None:
        return GateRefusal(
            "walkforward_missing",
            "No walkforward record found for these params. Run `sfa walkforward` first.",
        )

    recorded_at = isoparse(record["recorded_at"])
    age_days = (datetime.now(UTC) - recorded_at).total_seconds() / 86400.0
    if age_days > thresholds["walkforward_max_age_days"]:
        return GateRefusal(
            "walkforward_stale",
            f"Walkforward record is {age_days:.1f} days old; max allowed is "
            f"{thresholds['walkforward_max_age_days']:.0f} days.",
        )

    agg = record["aggregate"]
    if not agg.get("robust"):
        return GateRefusal(
            "not_robust",
            f"Walkforward verdict says not robust: {agg.get('robust_reason')}",
        )
    if float(agg.get("oos_sharpe_mean", 0.0)) < thresholds["min_oos_sharpe_mean"]:
        return GateRefusal(
            "oos_sharpe_below_threshold",
            f"OOS Sharpe mean {agg.get('oos_sharpe_mean'):.3f} below threshold "
            f"{thresholds['min_oos_sharpe_mean']:.2f}",
        )
    if float(agg.get("degradation", 1.0)) > thresholds["max_degradation"]:
        return GateRefusal(
            "degradation_too_high",
            f"Degradation {agg.get('degradation'):.3f} above threshold "
            f"{thresholds['max_degradation']:.2f}",
        )
    if _is_running(strategy_name) and not force:
        return GateRefusal(
            "strategy_running",
            f"Strategy {strategy_name!r} is currently running. "
            f"Stop it (sfa kill) or pass --force.",
        )

    return {
        "walkforward_id": record["walkforward_id"],
        "walkforward_age_days": round(age_days, 2),
        "oos_sharpe_mean": float(agg["oos_sharpe_mean"]),
        "degradation": float(agg["degradation"]),
        "thresholds": thresholds,
    }


def promote(
    *,
    strategy_name: str,
    candidate_params: dict[str, Any],
    force: bool = False,
    config_path: Path | None = None,
    history_path: Path | None = None,
    db_path: Path | None = None,
) -> dict[str, Any]:
    """Run the gate and, on pass, write the new live_params + history entry."""
    decision = evaluate_gate(
        strategy_name=strategy_name,
        candidate_params=candidate_params,
        force=force,
        db_path=db_path,
    )
    if isinstance(decision, GateRefusal):
        return decision.as_contract()

    prior_last_promoted = get_last_promoted(strategy_name, config_path=config_path)
    prior_params = update_live_params(strategy_name, candidate_params, config_path=config_path)
    diff = diff_params(prior_params, candidate_params)
    history_entry_id = f"promo_{datetime.now(UTC).strftime('%Y%m%d_%H%M%S_%f')}"
    promoted_at = datetime.now(UTC).isoformat()
    entry = {
        "history_entry_id": history_entry_id,
        "strategy": strategy_name,
        "walkforward_id": decision["walkforward_id"],
        "from_params": prior_params,
        "to_params": candidate_params,
        "diff": diff,
        "gate": {
            "walkforward_age_days": decision["walkforward_age_days"],
            "oos_sharpe_mean": decision["oos_sharpe_mean"],
            "degradation": decision["degradation"],
        },
        "promoted_at": promoted_at,
    }
    try:
        append_history_yaml(entry, path=history_path)
    except Exception as exc:
        update_live_params(
            strategy_name,
            prior_params,
            config_path=config_path,
            last_promoted=prior_last_promoted,
        )
        return GateRefusal(
            "history_write_failed",
            f"Could not append to param history ({exc!r}); live_params were rolled back. "
            "Fix permissions on config/param_history.yaml (see scripts/fix_openclaw_server_perms.sh).",
        ).as_contract()
    record_promotion(entry, db_path=db_path)
    return {
        "promoted": True,
        "strategy": strategy_name,
        "from_params": prior_params,
        "to_params": candidate_params,
        "diff": diff,
        "gate": entry["gate"],
        "history_entry_id": history_entry_id,
    }


def _resolve_trial_arg(trial_arg: str) -> dict[str, Any]:
    """Accept either a trial id (int) or a JSON object string for params."""
    raw = trial_arg.strip()
    if raw.isdigit():
        record = trials_store.get_trial(int(raw))
        if record is None:
            raise ValueError(f"No trial with id {raw}")
        return record.params
    parsed = json.loads(raw)
    if not isinstance(parsed, dict):
        raise ValueError("--trial must be a trial id or JSON object")
    return parsed


def run_promote_cli(*, name: str, trial: str, force: bool, json_output: bool) -> None:
    try:
        load_bundle(name)
    except StrategyNotFoundError:
        typer.echo(json.dumps(CliError("unknown_strategy", f"No agent strategy named {name!r}.").as_dict()))
        raise typer.Exit(code=2)

    try:
        params = _resolve_trial_arg(trial)
    except (ValueError, json.JSONDecodeError) as exc:
        typer.echo(json.dumps(CliError("invalid_trial", str(exc)).as_dict()))
        raise typer.Exit(code=2) from exc

    payload = promote(strategy_name=name, candidate_params=params, force=force)
    text = json.dumps(payload, indent=2, default=str)
    if json_output or not payload.get("promoted", False):
        typer.echo(text)
    else:
        typer.echo(
            f"Promoted {payload['strategy']}\n"
            f"  from {payload['from_params']}\n"
            f"  to   {payload['to_params']}\n"
            f"  history_entry_id {payload['history_entry_id']}"
        )
    if not payload.get("promoted", False):
        raise typer.Exit(code=2)
