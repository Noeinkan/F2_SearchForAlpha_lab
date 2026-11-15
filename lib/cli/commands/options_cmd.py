"""Manual, offline European option pricing command."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from lib.cli.contracts import CliError
from lib.options.pricing import price_option


def register(app: typer.Typer) -> None:
    options = typer.Typer(help="Educational option pricing estimates.", no_args_is_help=True)

    @options.command("price")
    def price(
        spot: Annotated[float, typer.Option("--spot", "--S")],
        strike: Annotated[float, typer.Option("--strike", "--K")],
        days: Annotated[float, typer.Option("--days")],
        iv: Annotated[float, typer.Option("--iv")],
        kind: Annotated[str, typer.Option("--kind")] = "call",
        rate: Annotated[float, typer.Option("--rate")] = 0.05,
        yield_rate: Annotated[float, typer.Option("--yield")] = 0.0,
        json_output: Annotated[bool, typer.Option("--json")] = False,
    ) -> None:
        """Price one European call or put; rates and IV are fractions."""
        try:
            result = price_option(spot=spot, strike=strike, days=days, iv=iv,
                                  kind=kind, rate=rate, yield_rate=yield_rate)
        except ValueError as exc:
            typer.echo(json.dumps(CliError("invalid_options_input", str(exc)).as_dict()))
            raise typer.Exit(code=2) from exc
        payload = {"model": "black_scholes_merton", "kind": kind.lower(),
                   "inputs": {"spot": spot, "strike": strike, "days": days,
                              "iv": iv, "rate": rate, "yield": yield_rate}, **result}
        if json_output:
            typer.echo(json.dumps(payload))
        else:
            for key, value in payload.items():
                typer.echo(f"{key}: {value}")

    app.add_typer(options, name="options")
