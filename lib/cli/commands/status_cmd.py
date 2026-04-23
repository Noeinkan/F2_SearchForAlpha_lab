"""sfa status: snapshot of running strategies, positions, PnL, guards."""

from __future__ import annotations

from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command("status")
    def status_cmd(
        name: Annotated[str | None, typer.Option("--name")] = None,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """Show running strategies, open positions, PnL, guard states."""
        from lib.live.runner import status_cli

        status_cli(name=name, json_output=json_output)
