"""
JSON contract tests for the sfa CLI.

The shapes asserted here are what an external agent (OpenClaw / Kimi K2.6)
parses. Breaking them breaks the agent. If a field name needs to change, also
update AGENTS.md and the contract dataclasses in lib.cli.contracts.
"""

from __future__ import annotations

import json
import os
import sys
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.cli.app import app
from lib.cli.commands.instructions_cmd import _build_briefing
from lib.cli.commands.list_cmd import build_strategy_list
from lib.cli.commands.sample_universe_cmd import build_sample_universe_contract


runner = CliRunner()


def _fake_fetch(
    symbol: str,
    start_date: str,
    end_date: str,
    validate: bool = True,
    interval: str = "1d",
) -> pd.DataFrame:
    """Synthetic OHLCV. Deterministic: no network, no yfinance."""
    rng = np.random.default_rng(2024)
    dates = pd.date_range(start_date, end_date, freq="D")
    if len(dates) == 0:
        dates = pd.date_range(start_date, periods=200, freq="D")
    n = len(dates)
    returns = rng.standard_normal(n) * 0.012
    close = 400.0 * np.exp(np.cumsum(returns))
    df = pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": rng.integers(1_000_000, 5_000_000, n),
        },
        index=dates,
    )
    return df


def test_list_contract_shape():
    result = runner.invoke(app, ["list", "--json"])
    assert result.exit_code == 0, result.output
    payload = json.loads(result.output)
    assert "strategies" in payload
    assert isinstance(payload["strategies"], list)
    assert payload["strategies"], "seed strategy missing from config"

    entry = payload["strategies"][0]
    for key in ("name", "description", "buy_signals", "sell_signals", "live_params", "status"):
        assert key in entry, f"missing key {key!r} in list entry"
    assert isinstance(entry["buy_signals"], list)
    assert isinstance(entry["sell_signals"], list)
    assert isinstance(entry["live_params"], dict)
    assert entry["status"] in {"idle", "running"}


def test_list_includes_seed_strategy():
    bundle = build_strategy_list()
    names = [s.name for s in bundle.strategies]
    assert "mean_reversion_rsi_bb" in names


def test_backtest_contract_shape():
    with patch("lib.agent_strategy.fetch_data", side_effect=_fake_fetch):
        result = runner.invoke(
            app,
            [
                "backtest",
                "--name", "mean_reversion_rsi_bb",
                "--from", "2024-01-01",
                "--to", "2024-06-30",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    assert payload["strategy"] == "mean_reversion_rsi_bb"
    assert payload["ticker"] == "SPY"
    assert payload["window"] == {"from": "2024-01-01", "to": "2024-06-30", "interval": "1d"}
    assert isinstance(payload["params"], dict)
    assert isinstance(payload["seed"], int)
    assert isinstance(payload["duration_seconds"], (int, float))

    metrics = payload["metrics"]
    for key in (
        "total_return",
        "sharpe",
        "sortino",
        "calmar",
        "max_drawdown",
        "num_trades",
        "win_rate",
        "profit_factor",
        "turnover",
    ):
        assert key in metrics, f"missing metric {key!r}"
    assert isinstance(metrics["num_trades"], int)


def test_backtest_unknown_strategy_returns_error():
    result = runner.invoke(
        app,
        ["backtest", "--name", "no_such_strategy", "--from", "2024-01-01", "--to", "2024-06-30", "--json"],
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["error"] == "unknown_strategy"


def test_run_live_mode_refused():
    result = runner.invoke(
        app,
        ["run", "--name", "mean_reversion_rsi_bb", "--mode", "live", "--json"],
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["error"] == "live_mode_disabled"


def test_backtest_invalid_params_json_returns_error():
    result = runner.invoke(
        app,
        [
            "backtest",
            "--name", "mean_reversion_rsi_bb",
            "--from", "2024-01-01",
            "--to", "2024-06-30",
            "--params", "not-json",
            "--json",
        ],
    )
    assert result.exit_code == 2
    payload = json.loads(result.output)
    assert payload["error"] == "invalid_params"


def test_sweep_single_contract_shape():
    with patch("lib.agent_strategy.fetch_data", side_effect=_fake_fetch):
        result = runner.invoke(
            app,
            [
                "sweep-single",
                "--ticker", "TSLA",
                "--from", "2024-01-01",
                "--to", "2024-10-01",
                "--json",
            ],
        )
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    expected_names = {entry.name for entry in build_strategy_list().strategies}
    result_names = {entry["strategy"] for entry in payload["results"]}

    assert payload["ticker"] == "TSLA"
    assert payload["window"] == {"from": "2024-01-01", "to": "2024-10-01", "interval": "1d"}
    assert payload["strategy_count"] == len(expected_names)
    assert payload["success_count"] == len(payload["results"])
    assert payload["failure_count"] == len(payload["failures"])
    assert payload["failure_count"] == 0
    assert result_names == expected_names
    assert all(entry["ticker"] == "TSLA" for entry in payload["results"])


def test_sample_universe_contract_shape():
    payload = build_sample_universe_contract(
        {
            "research": {
                "ticker_universe": {
                    "etf_broad": ["SPY", "QQQ"],
                    "etf_fixed_income": ["AGG"],
                    "etf_sector": ["XLK"],
                    "etf_style_factor": ["QUAL"],
                    "etf_commodity_futures": ["DBC"],
                },
                "exploration": {
                    "enabled": True,
                    "benchmark_groups": ["etf_broad", "etf_fixed_income"],
                    "eligible_groups": ["etf_sector", "etf_style_factor", "etf_commodity_futures"],
                    "excluded_groups": ["etf_commodity_futures"],
                    "seeds": [7, 19],
                    "sample_per_group": 1,
                    "max_random_tickers": 2,
                    "advisory_only": True,
                },
            }
        }
    )

    assert payload["enabled"] is True
    assert payload["mode"] == "seeded_stratified"
    assert payload["benchmark_groups"] == ["etf_broad", "etf_fixed_income"]
    assert payload["benchmark_tickers"] == ["SPY", "QQQ", "AGG"]
    assert payload["eligible_groups"] == ["etf_sector", "etf_style_factor"]
    assert payload["excluded_groups"] == ["etf_commodity_futures"]
    assert payload["etf_group_roles"] == {
        "etf_broad": "benchmark",
        "etf_fixed_income": "benchmark",
        "etf_sector": "specialist",
        "etf_style_factor": "specialist",
        "etf_commodity_futures": "specialist",
    }
    assert payload["sample_per_group"] == 1
    assert payload["max_random_tickers"] == 2
    assert payload["seeds"] == [7, 19]
    assert len(payload["seed_samples"]) == 2
    assert payload["seed_samples"][0]["sampled_groups"] == {
        "etf_sector": ["XLK"],
        "etf_style_factor": ["QUAL"],
    }
    assert payload["seed_samples"][0]["random_tickers"] == ["XLK", "QUAL"]
    assert payload["seed_samples"][0]["all_tickers"] == ["SPY", "QQQ", "AGG", "XLK", "QUAL"]


def test_sample_universe_command_contract_shape():
    result = runner.invoke(app, ["sample-universe", "--json"])
    assert result.exit_code == 0, result.output

    payload = json.loads(result.output)
    for key in (
        "enabled",
        "mode",
        "benchmark_groups",
        "benchmark_tickers",
        "eligible_groups",
        "excluded_groups",
        "etf_group_roles",
        "sample_per_group",
        "max_random_tickers",
        "seeds",
        "seed_samples",
    ):
        assert key in payload, f"missing key {key!r} in sample-universe payload"
    assert isinstance(payload["benchmark_tickers"], list)
    assert isinstance(payload["etf_group_roles"], dict)
    assert isinstance(payload["seed_samples"], list)
    assert payload["seed_samples"], "sample-universe should emit at least one seeded plan"


def test_instructions_single_target_backtest_syntax_uses_ticker_override():
    briefing = _build_briefing(
        {
            "research": {
                "single_target_mode": {
                    "enabled": True,
                    "ticker": "TSLA",
                    "window": "in_sample",
                },
                "backtest_windows": {
                    "in_sample": {
                        "from": "2020-01-01",
                        "to": "2023-12-31",
                    }
                },
            },
            "promotion": {},
        }
    )

    assert briefing["mode"] == "single_target"
    assert briefing["target"] == "TSLA"
    assert briefing["loop"][1].startswith("2:sweep-single")
    assert "--name NAME --ticker TSLA" in briefing["syntax"]["backtest"]
    assert "sweep-single" in briefing["syntax"]
    assert any("--name is always the strategy bundle name" in rule for rule in briefing["rules"])
    assert any("prefer `sfa sweep-single`" in rule for rule in briefing["rules"])


def test_instructions_sweep_mode_uses_etf_first_multi_asset_guidance():
    briefing = _build_briefing(
        {
            "research": {
                "ticker_universe": {
                    "etf_broad": ["SPY"],
                    "etf_sector": ["XLK"],
                    "sp500_energy": ["XOM"],
                    "etf_fixed_income": ["AGG"],
                },
                "exploration": {
                    "enabled": True,
                    "benchmark_groups": ["etf_broad", "etf_fixed_income"],
                    "eligible_groups": ["etf_sector", "etf_international"],
                    "excluded_groups": ["etf_commodity_futures"],
                    "seeds": [7, 19, 31],
                    "sample_per_group": 2,
                    "max_random_tickers": 5,
                    "advisory_only": True,
                },
            },
            "promotion": {},
        }
    )

    assert briefing["mode"] == "sweep"
    assert briefing["etf_universe_groups"] == ["etf_broad", "etf_sector", "etf_fixed_income"]
    assert briefing["etf_group_roles"] == {
        "etf_broad": "benchmark",
        "etf_sector": "specialist",
        "etf_fixed_income": "benchmark",
    }
    assert briefing["exploration"] == {
        "enabled": True,
        "mode": "seeded_stratified",
        "benchmark_groups": ["etf_broad", "etf_fixed_income"],
        "eligible_groups": ["etf_sector", "etf_international"],
        "excluded_groups": ["etf_commodity_futures"],
        "seeds": [7, 19, 31],
        "sample_per_group": 2,
        "max_random_tickers": 5,
        "advisory_only": True,
    }
    assert "sample-universe" in briefing["syntax"]
    assert "--ticker SYMBOL" in briefing["syntax"]["optimise"]
    assert "grid-search" in briefing["syntax"]
    assert "--max-combos" in briefing["syntax"]["grid-search"]
    assert any("liquid benchmark ETF groups" in rule for rule in briefing["rules"])
    assert any("futures-based commodity ETFs" in rule for rule in briefing["rules"])
    assert any("sample-universe --json" in rule for rule in briefing["rules"])
    assert not any("expand to sectors only" in rule for rule in briefing["rules"])
