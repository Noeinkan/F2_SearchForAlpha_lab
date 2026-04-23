"""sfa kill: stop a running paper strategy, optionally flattening positions."""

from __future__ import annotations

from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command("kill")
    def kill_cmd(
        name: Annotated[str, typer.Option("--name")],
        flatten: Annotated[bool, typer.Option("--flatten")] = False,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """Send SIGTERM to a running strategy. With --flatten, close positions first."""
        from lib.live.runner import kill_cli

        kill_cli(name=name, flatten=flatten, json_output=json_output)
