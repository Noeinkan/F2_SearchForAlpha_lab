"""sfa sweep-single: run every configured strategy against one ticker."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from lib.agent_strategy import StrategyNotFoundError, load_bundle
from lib.cli.commands.backtest_cmd import build_backtest_contract
from lib.cli.commands.list_cmd import build_strategy_list
from lib.cli.contracts import CliError, StrategySweep, StrategySweepFailure
from lib.timeframes import IntervalError, normalize_interval


def register(app: typer.Typer) -> None:
    @app.command("sweep-single")
    def sweep_single_cmd(
        ticker: Annotated[str, typer.Option("--ticker", help="Target symbol to test all strategies against.")],
        from_: Annotated[str, typer.Option("--from", help="Start date (YYYY-MM-DD).")],
        to: Annotated[str, typer.Option("--to", help="End date (YYYY-MM-DD).")],
        initial_capital: Annotated[float, typer.Option("--capital", help="Starting capital.")] = 10_000.0,
        seed: Annotated[int, typer.Option("--seed", help="RNG seed.")] = 42,
        interval: Annotated[str, typer.Option("--interval", help="Bar size: 1d, 1h, or 4h.")] = "1d",
        json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
    ) -> None:
        """Backtest every configured strategy bundle on one ticker and window."""
        try:
            canon = normalize_interval(interval)
        except IntervalError as exc:
            typer.echo(json.dumps(CliError("invalid_interval", str(exc)).as_dict()))
            raise typer.Exit(code=2) from exc

        strategy_entries = build_strategy_list().strategies
        if not strategy_entries:
            typer.echo(json.dumps(CliError("no_strategies", "No agent strategies configured.").as_dict()))
            raise typer.Exit(code=2)

        results: list[dict] = []
        failures: list[StrategySweepFailure] = []

        for entry in strategy_entries:
            try:
                bundle = load_bundle(entry.name)
                contract = build_backtest_contract(
                    bundle,
                    window_from=from_,
                    window_to=to,
                    params=bundle.live_params,
                    ticker_override=ticker,
                    initial_capital=initial_capital,
                    seed=seed,
                    interval=canon,
                )
                results.append(contract)
            except StrategyNotFoundError:
                failures.append(
                    StrategySweepFailure(
                        strategy=entry.name,
                        error="unknown_strategy",
                        message=f"No agent strategy named {entry.name!r}.",
                    )
                )
            except Exception as exc:
                failures.append(
                    StrategySweepFailure(
                        strategy=entry.name,
                        error="backtest_failed",
                        message=str(exc),
                    )
                )

        payload = StrategySweep(
            ticker=ticker,
            window_from=from_,
            window_to=to,
            strategy_count=len(strategy_entries),
            success_count=len(results),
            failure_count=len(failures),
            results=results,
            failures=failures,
            interval=canon,
        ).as_dict()

        if json_output:
            typer.echo(json.dumps(payload, indent=2, default=str))
            return

        typer.echo(f"sweep-single  {ticker}  {from_} -> {to}  [{canon}]")
        for contract in sorted(results, key=lambda item: item["metrics"]["sortino"], reverse=True):
            metrics = contract["metrics"]
            typer.echo(
                f"{contract['strategy']:<24s} "
                f"sortino {metrics['sortino']:+.3f}  "
                f"sharpe {metrics['sharpe']:+.3f}  "
                f"return {metrics['total_return']:+.4f}"
            )
        if failures:
            typer.echo("failures:")
            for failure in failures:
                typer.echo(f"  {failure.strategy}: {failure.error} - {failure.message}")
