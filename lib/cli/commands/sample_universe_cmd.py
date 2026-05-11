"""sfa sample-universe: materialize benchmark and seeded ETF exploration samples."""

from __future__ import annotations

import json
from typing import Annotated

import typer

from lib.cli.contracts import UniverseSamplePlan, UniverseSeedSample
from lib.cli.research_utils import (
    build_exploration_config,
    flatten_group_tickers,
    get_effective_exploration_groups,
    get_etf_group_roles,
    get_ticker_universe,
    materialize_seed_samples,
)
from lib.config_loader import get_agent_config


def build_sample_universe_contract(cfg: dict) -> dict:
    research = cfg.get("research", {})
    ticker_universe = get_ticker_universe(research)
    exploration = build_exploration_config(research)
    benchmark_groups, eligible_groups = get_effective_exploration_groups(ticker_universe, exploration)
    benchmark_tickers = flatten_group_tickers(ticker_universe, benchmark_groups)
    etf_group_roles = get_etf_group_roles(ticker_universe, benchmark_groups)
    seed_samples = materialize_seed_samples(
        ticker_universe=ticker_universe,
        benchmark_tickers=benchmark_tickers,
        eligible_groups=eligible_groups,
        exploration=exploration,
    )

    return UniverseSamplePlan(
        enabled=exploration["enabled"],
        mode=exploration["mode"],
        advisory_only=exploration["advisory_only"],
        benchmark_groups=benchmark_groups,
        benchmark_tickers=benchmark_tickers,
        eligible_groups=eligible_groups,
        excluded_groups=exploration["excluded_groups"],
        etf_group_roles=etf_group_roles,
        sample_per_group=exploration["sample_per_group"],
        max_random_tickers=exploration["max_random_tickers"],
        seeds=exploration["seeds"],
        seed_samples=[UniverseSeedSample(**sample) for sample in seed_samples],
    ).as_dict()


def register(app: typer.Typer) -> None:
    @app.command("sample-universe")
    def sample_universe_cmd(
        json_output: Annotated[bool, typer.Option("--json", help="Emit JSON.")] = False,
    ) -> None:
        """Materialize the benchmark ETF set and seeded exploratory ETF samples."""
        payload = build_sample_universe_contract(get_agent_config())

        if json_output:
            typer.echo(json.dumps(payload, indent=2, default=str))
            return

        status = "enabled" if payload["enabled"] else "disabled"
        typer.echo(f"sample-universe  {payload['mode']}  [{status}]")
        typer.echo(f"benchmark_groups: {', '.join(payload['benchmark_groups'])}")
        typer.echo(f"benchmark_tickers: {', '.join(payload['benchmark_tickers'])}")
        typer.echo(f"eligible_groups: {', '.join(payload['eligible_groups'])}")
        for sample in payload["seed_samples"]:
            typer.echo(f"seed {sample['seed']}: {', '.join(sample['random_tickers'])}")
            for group, tickers in sample["sampled_groups"].items():
                typer.echo(f"  {group}: {', '.join(tickers)}")