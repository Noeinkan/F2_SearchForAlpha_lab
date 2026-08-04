"""sfa grid-search: capped cartesian search over a unified param space."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from lib.cli.contracts import CliError


def register(app: typer.Typer) -> None:
    @app.command("grid-search")
    def grid_search_cmd(
        name: Annotated[str, typer.Option("--name", help="Strategy bundle name.")],
        from_: Annotated[str | None, typer.Option("--from")] = None,
        to: Annotated[str | None, typer.Option("--to")] = None,
        metric: Annotated[str, typer.Option("--metric")] = "sortino",
        ticker: Annotated[str | None, typer.Option("--ticker", help="Override the bundle ticker.")] = None,
        params: Annotated[
            str | None,
            typer.Option(
                "--params",
                help="Comma-separated search-space keys to include (required for large spaces).",
            ),
        ] = None,
        include_execution: Annotated[
            bool,
            typer.Option(
                "--include-execution/--no-include-execution",
                help="Merge shared execution_search_space (stops, scaling, cooldown, …).",
            ),
        ] = False,
        max_combos: Annotated[
            int,
            typer.Option("--max-combos", help="Hard cap on cartesian product size."),
        ] = 250,
        dry_run: Annotated[
            bool,
            typer.Option("--dry-run", help="Print combo count / space and exit."),
        ] = False,
        study: Annotated[str | None, typer.Option("--study")] = None,
        seed: Annotated[int, typer.Option("--seed")] = 42,
        interval: Annotated[str, typer.Option("--interval", help="Bar size: 1d, 1h, or 4h.")] = "1d",
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """Enumerate a capped grid of indicator and/or execution parameters."""
        from lib.grid_search import run_grid_search_cli
        from lib.timeframes import IntervalError, normalize_interval

        try:
            canon = normalize_interval(interval)
        except IntervalError as exc:
            typer.echo(json.dumps(CliError("invalid_interval", str(exc)).as_dict()))
            raise typer.Exit(code=2) from exc

        run_grid_search_cli(
            name=name,
            metric=metric,
            window_from=from_,
            window_to=to,
            study_id=study,
            seed=seed,
            json_output=json_output,
            ticker=ticker,
            interval=canon,
            include_execution=include_execution,
            params=params,
            max_combos=max_combos,
            dry_run=dry_run,
        )
