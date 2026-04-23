"""sfa trials: list Optuna trials sorted by objective value."""

from __future__ import annotations

from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command("trials")
    def trials_cmd(
        name: Annotated[str, typer.Option("--name", help="Strategy bundle name.")],
        study: Annotated[str | None, typer.Option("--study")] = None,
        top: Annotated[int, typer.Option("--top")] = 10,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """List trials sorted by objective value descending."""
        from lib.bayesian_optimization import list_trials_cli

        list_trials_cli(name=name, study_id=study, top=top, json_output=json_output)
