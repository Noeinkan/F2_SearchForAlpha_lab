"""sfa optimise: Bayesian (Optuna) parameter search."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from lib.cli.contracts import CliError


def register(app: typer.Typer) -> None:
    @app.command("optimise")
    def optimise_cmd(
        name: Annotated[str, typer.Option("--name", help="Strategy bundle name.")],
        trials: Annotated[int, typer.Option("--trials")] = 50,
        metric: Annotated[str, typer.Option("--metric")] = "sortino",
        from_: Annotated[str | None, typer.Option("--from")] = None,
        to: Annotated[str | None, typer.Option("--to")] = None,
        study: Annotated[str | None, typer.Option("--study")] = None,
        seed: Annotated[int, typer.Option("--seed")] = 42,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """Run a Bayesian (TPE) parameter search. Implemented in Phase 2."""
        from lib.bayesian_optimization import run_optimise_cli

        run_optimise_cli(
            name=name,
            trials=trials,
            metric=metric,
            window_from=from_,
            window_to=to,
            study_id=study,
            seed=seed,
            json_output=json_output,
        )
