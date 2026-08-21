"""
Regression snapshot for the backtest engine.

``backtest()`` is a stateful bar loop split across ``_check_exits`` /
``_execute_buy`` / ``_execute_sell``. Any future rearrangement of those steps is
supposed to be behaviour-preserving, and the only cheap way to prove that is to
pin the output of a fixed-seed synthetic run.

If this test fails you have changed engine *behaviour*. That is allowed — but it
must be deliberate: confirm the new numbers are the ones you intended, then
regenerate the constants below with

    python -m lib.tests.test_strategy_snapshot
"""

from __future__ import annotations

import hashlib
import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.strategy import backtest, calculate_metrics  # noqa: E402

# Columns whose bar-by-bar values define "same behaviour".
SNAPSHOT_COLUMNS = (
    'Units', 'Units_to_buy', 'Units_to_sell', 'Cash_Value', 'Portfolio_Value',
    'Trailing_Stop', 'Holding_Period', 'Holding_Sessions',
    'Avg_Entry_Price', 'Avg_Cost_Basis',
)

# Last deliberate change: 3.9.4 gap fills (2026-08-21). On this daily fixture
# every bar opens a session, so eight of the twenty-one round trips now exit at
# the bar's Open instead of its Close. `gap_fills=False` still reproduces the
# pre-3.9 numbers exactly, which is how that change was confirmed to be the
# only one.

# --- pinned expectations ---------------------------------------------------
EXPECTED_DIGEST = 'e124c42c8096958d3d8c12f9c130940518f96858bc6367175a64134f60816bd8'
EXPECTED_FINAL_VALUE = 29355.045253426455
EXPECTED_TRADE_COUNT = 21
EXPECTED_NET_PNL = 4355.045253426444


def _fixture(seed: int = 20240817, n_rows: int = 400) -> pd.DataFrame:
    """A seeded random walk with sparse, uncorrelated buy/sell flags."""
    rng = np.random.default_rng(seed)
    dates = pd.date_range('2020-01-01', periods=n_rows, freq='B')
    prices = 100.0 * np.exp(np.cumsum(rng.standard_normal(n_rows) * 0.015))
    return pd.DataFrame(
        {
            'Open': prices * 1.001,
            'High': prices * 1.02,
            'Low': prices * 0.98,
            'Close': prices,
            'Volume': rng.integers(1_000_000, 10_000_000, n_rows),
            'RSI_Oversold_Buy': (rng.random(n_rows) > 0.82).astype(int),
            'RSI_Overbought_Sell': (rng.random(n_rows) > 0.86).astype(int),
        },
        index=dates,
    )


def _run_reference() -> pd.DataFrame:
    """One run that exercises scaling, cooldowns, stops, take profit and fees."""
    return backtest(
        df=_fixture(),
        initial_capital=25_000.0,
        position_sizing_strategy='percentage_of_portfolio',
        position_sizing_params={'percent': 0.35},
        buy_indicators=['RSI_Oversold_Buy'],
        sell_indicators=['RSI_Overbought_Sell'],
        delay=1,
        min_holding_period=3,
        position_scaling=0.4,
        trailing_stop_loss=0.07,
        take_profit=0.12,
        consecutive_signal_mode='cooldown',
        cooldown_bars=2,
        commission_per_trade=0.001,
        slippage_pct=0.0005,
        fx_fee_pct=0.0015,
    )


def _digest(result: pd.DataFrame) -> str:
    """Stable hash of the snapshot columns, rounded to sub-cent precision.

    Rounding keeps the digest immune to the last-bit float noise that a pure
    reassociation of the same arithmetic can produce, while still catching any
    change a human would call a different result.
    """
    block = np.column_stack([
        np.nan_to_num(result[col].to_numpy(dtype=float), posinf=-1.0, neginf=-2.0)
        for col in SNAPSHOT_COLUMNS
    ])
    return hashlib.sha256(np.round(block, 6).tobytes()).hexdigest()


class TestEngineSnapshot:
    def test_reference_run_matches_the_pinned_snapshot(self):
        result = _run_reference()
        assert _digest(result) == EXPECTED_DIGEST, (
            'engine behaviour changed — see this module\'s docstring before '
            'regenerating the constants'
        )

    def test_headline_numbers_match(self):
        """Human-readable anchors, so a digest failure is diagnosable."""
        result = _run_reference()
        trades = result.attrs['trades']
        assert result['Portfolio_Value'].iloc[-1] == pytest.approx(EXPECTED_FINAL_VALUE, abs=1e-6)
        assert len(trades) == EXPECTED_TRADE_COUNT
        assert trades['net_pnl'].sum() == pytest.approx(EXPECTED_NET_PNL, abs=1e-6)

    def test_the_run_actually_exercises_every_exit_path(self):
        """A snapshot over a trivial run would guard nothing."""
        reasons = set(_run_reference().attrs['trades']['exit_reason'])
        assert {'trailing_stop', 'take_profit', 'signal'} <= reasons

    def test_ledger_reconciles_with_the_equity_curve(self):
        """Net PnL across all round trips must equal the change in equity."""
        result = _run_reference()
        trades = result.attrs['trades']
        equity_change = result['Portfolio_Value'].iloc[-1] - result['Portfolio_Value'].iloc[0]
        assert trades['net_pnl'].sum() == pytest.approx(equity_change, abs=1e-6)

    def test_run_is_repeatable(self):
        first, second = _run_reference(), _run_reference()
        pd.testing.assert_frame_equal(first[list(SNAPSHOT_COLUMNS)], second[list(SNAPSHOT_COLUMNS)])

    def test_metrics_are_all_finite(self):
        metrics = calculate_metrics(_run_reference(), periods_per_year=252)
        for key, value in metrics.items():
            assert np.isfinite(value), f'{key} is not finite: {value}'


if __name__ == '__main__':  # pragma: no cover - snapshot regeneration helper
    run = _run_reference()
    ledger = run.attrs['trades']
    print(f"EXPECTED_DIGEST = {_digest(run)!r}")
    print(f"EXPECTED_FINAL_VALUE = {run['Portfolio_Value'].iloc[-1]!r}")
    print(f"EXPECTED_TRADE_COUNT = {len(ledger)}")
    print(f"EXPECTED_NET_PNL = {float(ledger['net_pnl'].sum())!r}")
    print(f"exit reasons: {sorted(set(ledger['exit_reason']))}")
