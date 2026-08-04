"""Unit tests for optimizer UI formatting helpers."""

from lib.dash.callbacks.optimization import (
    format_capital_label,
    format_optimizer_conditions,
    truncate_signal_names,
)


def test_format_capital_label_whole_dollars():
    assert format_capital_label(10000) == "$10,000"
    assert format_capital_label("25000") == "$25,000"


def test_format_capital_label_fractional_and_bad():
    assert format_capital_label(1000.5) == "$1,000.50"
    assert format_capital_label(None) == "—"
    assert format_capital_label("nope") == "—"


def test_truncate_signal_names():
    assert truncate_signal_names([]) == "—"
    assert truncate_signal_names(["A", "B"]) == "A, B"
    names = [f"S{i}" for i in range(8)]
    out = truncate_signal_names(names, limit=6)
    assert out.startswith("S0, S1, S2, S3, S4, S5")
    assert out.endswith("+2 more")


def test_format_optimizer_conditions():
    text = format_optimizer_conditions(
        interval_label="1D",
        capital_label="$10,000",
        window_label="2020-01-01 → 2024-12-31",
        buy_signals=["BB_Breakout_Buy", "RSI_Oversold_Buy"],
        sell_signals=["BB_Breakout_Sell"],
    )
    assert "1D · $10,000 · 2020-01-01 → 2024-12-31" in text
    assert "Buy: BB_Breakout_Buy, RSI_Oversold_Buy" in text
    assert "Sell: BB_Breakout_Sell" in text
