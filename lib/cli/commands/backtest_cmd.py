"""sfa backtest: run the existing engine and emit the contract JSON."""

from __future__ import annotations

import json
import sys
from typing import Annotated

import typer

from lib.agent_strategy import AgentStrategyBundle, StrategyNotFoundError, load_bundle, prepare_dataframe
from lib.backtest_result import run_backtest_result
from lib.cli.contracts import CliError


def _parse_params(raw: str | None) -> dict | None:
    if not raw:
        return None
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError as exc:
        typer.echo(json.dumps(CliError("invalid_params", f"--params is not valid JSON: {exc}").as_dict()))
        raise typer.Exit(code=2) from exc
    if not isinstance(parsed, dict):
        typer.echo(json.dumps(CliError("invalid_params", "--params must be a JSON object").as_dict()))
        raise typer.Exit(code=2)
    return parsed


def build_backtest_contract(
    bundle: AgentStrategyBundle,
    *,
    window_from: str,
    window_to: str,
    params: dict | None,
    ticker_override: str | None,
    initial_capital: float,
    seed: int,
) -> dict:
    df = prepare_dataframe(
        bundle,
        window_from=window_from,
        window_to=window_to,
        params=params,
        ticker_override=ticker_override,
    )

    result = run_backtest_result(
        df,
        strategy_name=bundle.name,
        ticker=ticker_override or bundle.ticker,
        window_from=window_from,
        window_to=window_to,
        params=params,
        buy_signals=bundle.buy_signals,
        sell_signals=bundle.sell_signals,
        initial_capital=initial_capital,
        strategy_mode=bundle.mode,
        signal_logic=bundle.signal_logic,
        signal_window=bundle.signal_window,
        seed=seed,
    )
    return result.to_contract()


def register(app: typer.Typer) -> None:
    @app.command("backtest")
    def backtest_cmd(
        name: Annotated[str, typer.Option("--name", help="Strategy bundle name.")],
        from_: Annotated[str, typer.Option("--from", help="Start date (YYYY-MM-DD).")],
        to: Annotated[str, typer.Option("--to", help="End date (YYYY-MM-DD).")],
        params: Annotated[str | None, typer.Option("--params", help="JSON params override.")] = None,
        ticker: Annotated[str | None, typer.Option("--ticker", help="Override the bundle ticker.")] = None,
        initial_capital: Annotated[float, typer.Option("--capital", help="Starting capital.")] = 10_000.0,
        seed: Annotated[int, typer.Option("--seed", help="RNG seed.")] = 42,
        json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
    ) -> None:
        """Backtest a strategy on a date window."""
        try:
            bundle = load_bundle(name)
        except StrategyNotFoundError:
            typer.echo(json.dumps(CliError("unknown_strategy", f"No agent strategy named {name!r}.").as_dict()))
            raise typer.Exit(code=2)

        param_override = _parse_params(params)
        effective_params = param_override if param_override is not None else bundle.live_params

        try:
            contract = build_backtest_contract(
                bundle,
                window_from=from_,
                window_to=to,
                params=effective_params,
                ticker_override=ticker,
                initial_capital=initial_capital,
                seed=seed,
            )
        except Exception as exc:
            typer.echo(json.dumps(CliError("data_preparation_failed", str(exc)).as_dict()))
            raise typer.Exit(code=3) from exc
        if json_output:
            typer.echo(json.dumps(contract, indent=2, default=str))
            return
        m = contract["metrics"]
        typer.echo(
            f"{contract['strategy']}  {contract['ticker']}  "
            f"{contract['window']['from']} -> {contract['window']['to']}\n"
            f"  total_return    {m['total_return']:+.4f}\n"
            f"  sharpe          {m['sharpe']:.3f}\n"
            f"  sortino         {m['sortino']:.3f}\n"
            f"  calmar          {m['calmar']:.3f}\n"
            f"  max_drawdown    {m['max_drawdown']:.4f}\n"
            f"  num_trades      {m['num_trades']}\n"
            f"  win_rate        {m['win_rate']:.3f}\n"
            f"  profit_factor   {m['profit_factor']:.3f}\n"
            f"  duration_seconds {contract['duration_seconds']:.2f}",
            file=sys.stderr if json_output else sys.stdout,
        )
