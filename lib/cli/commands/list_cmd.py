"""sfa list: enumerate agent strategy bundles."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Annotated

import typer

from lib.cli.contracts import StrategyEntry, StrategyList
from lib.config_loader import get_agent_strategies


def _running_status(name: str) -> str:
    """Return 'running' if a PID file exists, else 'idle'."""
    pid_path = Path("state/running") / f"{name}.pid"
    return "running" if pid_path.exists() else "idle"


def build_strategy_list() -> StrategyList:
    raw = get_agent_strategies()
    entries = []
    for name, body in sorted(raw.items()):
        body = body or {}
        entries.append(
            StrategyEntry(
                name=name,
                description=str(body.get("description", "")),
                buy_signals=list(body.get("buy_signals", []) or []),
                sell_signals=list(body.get("sell_signals", []) or []),
                live_params=dict(body.get("live_params", {}) or {}),
                last_promoted=body.get("last_promoted"),
                status=_running_status(name),
            )
        )
    return StrategyList(strategies=entries)


def register(app: typer.Typer) -> None:
    @app.command("list")
    def list_strategies(
        json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
    ) -> None:
        """List configured agent strategy bundles."""
        payload = build_strategy_list().as_dict()
        if json_output:
            typer.echo(json.dumps(payload, indent=2, default=str))
            return
        if not payload["strategies"]:
            typer.echo("No agent strategies configured (config/strategy_config.yaml: agent_strategies).")
            return
        for entry in payload["strategies"]:
            typer.echo(
                f"{entry['name']}  [{entry['status']}]\n"
                f"  description: {entry['description']}\n"
                f"  buy_signals: {', '.join(entry['buy_signals'])}\n"
                f"  sell_signals: {', '.join(entry['sell_signals'])}\n"
                f"  live_params: {entry['live_params']}"
            )
