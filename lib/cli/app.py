"""
sfa CLI Typer app.

Every subcommand supports ``--json`` for machine readable output. Subcommand
implementations live under ``lib.cli.commands`` and register themselves on the
Typer app via ``register(app)``.
"""

from __future__ import annotations

import logging

import typer

from lib.cli.commands import (
    backtest_cmd,
    instructions_cmd,
    kill_cmd,
    list_cmd,
    optimise_cmd,
    promote_cmd,
    run_cmd,
    status_cmd,
    sweep_single_cmd,
    trials_cmd,
    walkforward_cmd,
)


def _configure_logging() -> None:
    logging.basicConfig(
        level=logging.WARNING,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )


def build_app() -> typer.Typer:
    """Construct and return the sfa Typer application."""
    _configure_logging()
    app = typer.Typer(
        name="sfa",
        help="SearchForAlpha CLI: backtest, optimise, walk forward, paper trade.",
        add_completion=False,
        no_args_is_help=True,
    )
    instructions_cmd.register(app)
    list_cmd.register(app)
    backtest_cmd.register(app)
    sweep_single_cmd.register(app)
    optimise_cmd.register(app)
    trials_cmd.register(app)
    walkforward_cmd.register(app)
    promote_cmd.register(app)
    run_cmd.register(app)
    status_cmd.register(app)
    kill_cmd.register(app)
    return app


app = build_app()


if __name__ == "__main__":
    app()
