"""sfa promote: gated promotion of trial params to live."""

from __future__ import annotations

from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command("promote")
    def promote_cmd(
        name: Annotated[str, typer.Option("--name")],
        trial: Annotated[str, typer.Option("--trial")],
        force: Annotated[bool, typer.Option("--force")] = False,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """Promote a trial's parameters to the live config (gated)."""
        from lib.promotion.gate import run_promote_cli

        run_promote_cli(name=name, trial=trial, force=force, json_output=json_output)
