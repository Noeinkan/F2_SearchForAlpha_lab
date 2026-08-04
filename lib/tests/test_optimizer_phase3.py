"""Tests for Optimizer workspace Phase 3 (history, landscape, combo walk-forward, layout)."""

from __future__ import annotations

from unittest.mock import patch

import numpy as np
import pandas as pd

from lib.dash.combo_walkforward import ComboSpec, run_combo_walkforward
from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS, get_theme
from lib.dash.optimizer_history import append_history, history_for_ticker, summarize_run
from lib.dash.optimizer_landscape import build_return_sharpe_figure
from lib.walkforward.runner import WalkForwardOptions


def _fake_long_fetch(symbol: str, start_date: str, end_date: str, validate: bool = True, interval: str = "1d") -> pd.DataFrame:
    rng = np.random.default_rng(42)
    dates = pd.date_range(start_date, end_date, freq="D")
    if len(dates) < 30:
        dates = pd.date_range(start_date, periods=2000, freq="D")
    n = len(dates)
    returns = rng.standard_normal(n) * 0.012 + 0.0003
    close = 400.0 * np.exp(np.cumsum(returns))
    return pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": rng.integers(1_000_000, 5_000_000, n),
        },
        index=dates,
    )


def test_summarize_and_append_history():
    results = [{
        "Buy_Signals": "RSI_Oversold_Buy",
        "Sell_Signals": "RSI_Overbought_Sell",
        "Total_Return_%": 12.5,
        "Sharpe_Ratio": 1.1,
        "Max_Drawdown_%": -8.0,
        "Trades": 24,
    }]
    entry = summarize_run(
        ticker="TSLA",
        results=results,
        total_combos=100,
        sort_by="Sharpe_Ratio",
        realistic=True,
        max_signals=2,
    )
    assert entry["ticker"] == "TSLA"
    assert entry["total_combos"] == 100
    assert entry["top"]["Buy_Signals"] == "RSI_Oversold_Buy"

    history = append_history([], entry)
    assert len(history) == 1
    assert history[0]["id"] == entry["id"]

    filtered = history_for_ticker(history + [{"ticker": "SPY"}], "TSLA")
    assert len(filtered) == 1


def test_build_return_sharpe_figure_empty_and_points():
    theme = get_theme()
    empty = build_return_sharpe_figure([], theme)
    assert empty.layout.annotations[0].text

    records = [
        {"Total_Return_%": 5.0, "Sharpe_Ratio": 0.8, "Buy_Signals": "A", "Sell_Signals": "B",
         "Max_Drawdown_%": -10, "Trades": 5},
        {"Total_Return_%": 12.0, "Sharpe_Ratio": 1.4, "Buy_Signals": "C", "Sell_Signals": "D",
         "Max_Drawdown_%": -6, "Trades": 12},
    ]
    fig = build_return_sharpe_figure(records, theme)
    assert len(fig.data) == 2
    assert fig.layout.xaxis.title.text == "Sharpe"


def test_run_combo_walkforward_mocked_fetch():
    combo = ComboSpec(
        buy_signals=("RSI_Oversold_Buy",),
        sell_signals=("RSI_Overbought_Sell",),
        ticker="TSLA",
        indicator_settings=DEFAULT_INDICATOR_SETTINGS,
        backtest_kwargs=None,
    )
    options = WalkForwardOptions(n_windows=5, train_months=12, test_months=3, initial_capital=10_000)

    with patch("lib.dash.combo_walkforward.fetch_data", side_effect=_fake_long_fetch):
        payload = run_combo_walkforward(combo=combo, options=options)

    assert len(payload["windows"]) == 5
    assert "aggregate" in payload
    assert "is_sharpe_mean" in payload["aggregate"]
    assert "oos_sharpe_mean" in payload["aggregate"]
    assert payload["strategy"].startswith("combo:")
