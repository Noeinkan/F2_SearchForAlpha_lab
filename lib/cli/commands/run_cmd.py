"""sfa run: paper trading entry point. Live mode is always refused."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from lib.cli.contracts import CliError


def register(app: typer.Typer) -> None:
    @app.command("run")
    def run_cmd(
        name: Annotated[str, typer.Option("--name")],
        mode: Annotated[str, typer.Option("--mode")] = "paper",
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """Start the async paper trading runner."""
        if mode != "paper":
            payload = CliError(
                "live_mode_disabled",
                "Live mode is not supported in this build. Use --mode paper.",
            ).as_dict()
            typer.echo(json.dumps(payload) if json_output else payload["message"])
            raise typer.Exit(code=2)

        from lib.live.runner import run_paper_cli

        run_paper_cli(name=name, json_output=json_output)
