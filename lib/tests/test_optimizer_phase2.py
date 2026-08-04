"""Unit tests for optimizer Phase 2 helpers (universe, constraints, mirrors, eval kwargs)."""

from dash import no_update
import pandas as pd

from lib.dash.callbacks.optimization import build_eval_kwargs
from lib.dash.callbacks.optimizer_sync import pick_mirror_write, values_differ
from lib.dash.helpers import (
    apply_optimizer_constraints,
    filter_signal_universe,
    generate_signal_combinations,
)


def test_values_differ_dates_and_numbers():
    assert not values_differ(None, None)
    assert values_differ(None, 1)
    assert not values_differ("2020-01-01", "2020-01-01T00:00:00")
    assert values_differ("2020-01-01", "2020-01-02")
    assert not values_differ(10, 10.0)
    assert values_differ(10, 11)


def test_pick_mirror_write_propagates_one_side():
    left, right = pick_mirror_write("opt-initial-capital", "opt-initial-capital", 12_000, "initial-capital", 10_000)
    assert left is no_update
    assert right == 12_000

    left, right = pick_mirror_write("initial-capital", "opt-initial-capital", 12_000, "initial-capital", 10_000)
    assert left == 10_000
    assert right is no_update

    left, right = pick_mirror_write("opt-initial-capital", "opt-initial-capital", 10_000, "initial-capital", 10_000)
    assert left is no_update
    assert right is no_update


def test_filter_signal_universe_empty_means_all():
    buy = ["A_Buy", "B_Buy"]
    sell = ["A_Sell"]
    assert filter_signal_universe(buy, sell, None, None) == (buy, sell)
    assert filter_signal_universe(buy, sell, [], []) == (buy, sell)


def test_filter_signal_universe_restricts():
    buy = ["A_Buy", "B_Buy", "C_Buy"]
    sell = ["A_Sell", "B_Sell"]
    out_b, out_s = filter_signal_universe(buy, sell, ["B_Buy"], ["A_Sell"])
    assert out_b == ["B_Buy"]
    assert out_s == ["A_Sell"]


def test_universe_filter_shrinks_combo_count():
    buy = [f"B{i}_Buy" for i in range(4)]
    sell = [f"S{i}_Sell" for i in range(4)]
    all_combos = generate_signal_combinations(buy, sell, max_signals=2)
    filtered_buy, filtered_sell = filter_signal_universe(buy, sell, buy[:2], sell[:2])
    subset = generate_signal_combinations(filtered_buy, filtered_sell, max_signals=2)
    assert len(subset) < len(all_combos)
    assert len(subset) > 0


def test_apply_optimizer_constraints_dd_and_sharpe():
    df = pd.DataFrame({
        "Max_Drawdown_%": [-10.0, -40.0, -20.0],
        "Sharpe_Ratio": [1.2, 0.8, 0.3],
        "Total_Return_%": [10.0, 50.0, 5.0],
    })
    out = apply_optimizer_constraints(df, max_dd_pct=25, min_sharpe=0.5)
    assert len(out) == 1
    assert float(out.iloc[0]["Sharpe_Ratio"]) == 1.2


def test_build_eval_kwargs_idealized_empty():
    assert build_eval_kwargs(False) == {}


def test_build_eval_kwargs_realistic_converts_pct():
    kwargs = build_eval_kwargs(
        True,
        strategy_mode="accumulation",
        min_holding_period=3,
        trailing_stop_pct=10,
        stop_mode="atr",
        fx_fee_pct=0.15,
        slippage_pct=0.05,
        commission_pct=0.1,
    )
    assert kwargs["strategy_mode"] == "accumulation"
    assert kwargs["min_holding_period"] == 3
    assert kwargs["trailing_stop_loss"] == 0.10
    assert kwargs["stop_mode"] == "atr"
    assert abs(kwargs["fx_fee_pct"] - 0.0015) < 1e-9
    assert abs(kwargs["slippage_pct"] - 0.0005) < 1e-9
    assert abs(kwargs["commission_per_trade"] - 0.001) < 1e-9
