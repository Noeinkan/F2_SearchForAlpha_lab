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
from lib.cli.commands.list_cmd import build_strategy_list


runner = CliRunner()


def _fake_fetch(symbol: str, start_date: str, end_date: str, validate: bool = True) -> pd.DataFrame:
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
    assert payload["window"] == {"from": "2024-01-01", "to": "2024-06-30"}
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
