"""sfa kill: stop a running paper strategy, optionally flattening positions."""

from __future__ import annotations

from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command("kill")
    def kill_cmd(
        name: Annotated[str, typer.Option("--name")],
        flatten: Annotated[bool, typer.Option("--flatten")] = False,
        wait: Annotated[float, typer.Option("--wait", help="Seconds to wait for a clean stop.")] = 60.0,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """Ask a running strategy to stop cleanly. With --flatten, close its position first.

        A runner that does not answer is terminated, and the command says so.
        """
        from lib.live.runner import kill_cli

        kill_cli(name=name, flatten=flatten, json_output=json_output, wait_seconds=wait)
