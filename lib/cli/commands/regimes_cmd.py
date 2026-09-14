"""sfa regimes: score a strategy separately in each market regime of the calendar."""

from __future__ import annotations

from typing import Annotated

import typer


def register(app: typer.Typer) -> None:
    @app.command("regimes")
    def regimes_cmd(
        name: Annotated[str, typer.Option("--name", help="Strategy bundle name.")],
        params: Annotated[
            str | None,
            typer.Option("--params", help="Trial id or JSON dict. Defaults to the bundle's live params."),
        ] = None,
        ticker: Annotated[str | None, typer.Option("--ticker", help="Override the bundle ticker.")] = None,
        interval: Annotated[str, typer.Option("--interval", help="Bar size: 1d, 1h, or 4h.")] = "1d",
        initial_capital: Annotated[float, typer.Option("--capital", help="Starting capital per regime.")] = 10_000.0,
        seed: Annotated[int, typer.Option("--seed", help="RNG seed.")] = 42,
        json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
    ) -> None:
        """Backtest a strategy in each regime of config/regimes.yaml and apply the regime rule."""
        from lib.regimes.runner import run_regimes_cli

        run_regimes_cli(
            name=name,
            params_arg=params,
            ticker=ticker,
            interval=interval,
            initial_capital=initial_capital,
            seed=seed,
            json_output=json_output,
        )
