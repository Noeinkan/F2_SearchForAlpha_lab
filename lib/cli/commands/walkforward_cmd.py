"""sfa walkforward: rolling out of sample validation."""

from __future__ import annotations

from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command("walkforward")
    def walkforward_cmd(
        name: Annotated[str, typer.Option("--name")],
        params: Annotated[str, typer.Option("--params", help="Trial id or JSON dict.")],
        windows: Annotated[int, typer.Option("--windows")] = 5,
        train_months: Annotated[int, typer.Option("--train-months")] = 12,
        test_months: Annotated[int, typer.Option("--test-months")] = 3,
        seed: Annotated[int, typer.Option("--seed")] = 42,
        interval: Annotated[str, typer.Option("--interval", help="Bar size: 1d, 1h, or 4h.")] = "1d",
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """Run rolling walk forward validation."""
        from lib.walkforward.runner import run_walkforward_cli

        run_walkforward_cli(
            name=name,
            params_arg=params,
            windows=windows,
            train_months=train_months,
            test_months=test_months,
            seed=seed,
            json_output=json_output,
            interval=interval,
        )
