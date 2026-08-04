"""
Tests for the Execution Type sandbox.

The contract these protect: the explainer's numbers come from the real engine,
so they cannot drift from it. If someone reimplements sizing inside the
explainer for speed, the cross-checks against ``lib.strategy`` here fail.
"""

from __future__ import annotations

import numpy as np
import pytest

from lib.dash.execution_sim import (
    BUY_COLUMN,
    SANDBOX_CAPITAL,
    SELL_COLUMN,
    build_sandbox_frame,
    default_params,
    first_entry_summary,
    simulate,
)
from lib.dash.execution_glossary import MODE_ORDER

KELLY_FRACTION = 0.5 - (0.5 / 1.5)          # 0.16666...


class TestSandboxTape:
    def test_frame_has_the_columns_the_engine_needs(self):
        df = build_sandbox_frame()
        for column in ('Open', 'High', 'Low', 'Close', 'Volume', BUY_COLUMN, SELL_COLUMN):
            assert column in df.columns
        assert len(df) == 24
        assert df['Close'].gt(0).all()

    def test_tape_is_identical_every_call(self):
        first, second = build_sandbox_frame(), build_sandbox_frame()
        assert first.equals(second)

    def test_tape_exercises_every_mechanic(self):
        """A tape with no drawdown would never show a stop firing."""
        df = build_sandbox_frame()
        close = df['Close'].to_numpy()
        assert df[BUY_COLUMN].sum() >= 3
        assert df[SELL_COLUMN].sum() >= 2
        peak_to_trough = close.max() / close[np.argmax(close):].min() - 1
        assert peak_to_trough > 0.20, "need a drawdown deep enough to trip a stop"


class TestDeterminism:
    @pytest.mark.parametrize('mode', MODE_ORDER)
    def test_same_params_give_the_same_run(self, mode):
        a, b = simulate(mode), simulate(mode)
        assert a.equity == b.equity
        assert a.first_entry_value == b.first_entry_value

    @pytest.mark.parametrize('mode', MODE_ORDER)
    def test_every_mode_produces_a_full_ledger(self, mode):
        run = simulate(mode)
        assert len(run.rows) == 24
        assert run.buy_count > 0
        assert run.capital == SANDBOX_CAPITAL


class TestModeBehaviourMatchesTheEngine:
    """Cross-checks tying the explainer's headline numbers to engine rules."""

    def test_trading_first_entry_is_the_kelly_fraction(self):
        run = simulate('trading', position_scaling_pct=100.0,
                       kelly_win_rate=0.5, kelly_win_loss_ratio=1.5)
        assert run.first_entry_pct == pytest.approx(KELLY_FRACTION, rel=1e-3)
        # The number the old caption claimed was 100%.
        assert run.first_entry_pct < 0.20

    def test_trading_scale_in_shrinks_the_first_entry_proportionally(self):
        full = simulate('trading', position_scaling_pct=100.0)
        quarter = simulate('trading', position_scaling_pct=25.0)
        assert quarter.first_entry_value == pytest.approx(full.first_entry_value * 0.25, rel=1e-3)

    def test_accumulation_never_sells(self):
        run = simulate('accumulation')
        assert run.sell_count == 0
        assert run.stop_exits == 0

    def test_accumulation_spends_exactly_the_configured_amount(self):
        run = simulate('accumulation', amount_per_buy=1_500.0)
        assert run.first_entry_value == pytest.approx(1_500.0)

    def test_accumulation_stops_when_cash_runs_out(self):
        run = simulate('accumulation', amount_per_buy=3_000.0)
        assert run.rows[-1].cash < 3_000.0
        assert run.rows[-1].cash >= -1e-9

    def test_rebalancing_first_entry_is_the_configured_weight(self):
        run = simulate('rebalancing', position_size_pct=25.0)
        assert run.first_entry_pct == pytest.approx(0.25, rel=1e-3)

    def test_rebalancing_buys_are_equal_weight_not_decaying(self):
        """The regression that motivated the engine fix.

        Sizing off leftover cash made the second buy 75% of the first.
        """
        run = simulate('rebalancing', position_size_pct=25.0, trailing_stop_pct=40.0)
        buys = [r.order_value for r in run.rows if r.order_value > 0]
        assert len(buys) >= 2
        assert buys[1] / buys[0] > 0.85

    @pytest.mark.parametrize('mode', ('trading', 'rebalancing'))
    def test_stops_are_active_outside_accumulation(self, mode):
        run = simulate(mode, trailing_stop_pct=10.0)
        assert run.stop_exits >= 1


class TestCapital:
    def test_previews_scale_with_the_users_own_capital(self):
        small = simulate('rebalancing', capital=5_000.0, position_size_pct=25.0)
        assert small.capital == 5_000.0
        assert small.first_entry_value == pytest.approx(1_250.0)
        assert small.first_entry_pct == pytest.approx(0.25, rel=1e-3)

    def test_missing_capital_falls_back_rather_than_dividing_by_zero(self):
        run = simulate('trading', capital=None)
        assert run.capital == SANDBOX_CAPITAL


class TestSummaryStrings:
    def test_trading_summary_quotes_dollars_and_percent(self):
        text = first_entry_summary('trading', position_scaling_pct=100.0)
        assert 'first entry' in text and '$' in text and '%' in text

    def test_accumulation_summary_counts_the_buys_it_can_afford(self):
        text = first_entry_summary('accumulation', amount_per_buy=1_000.0, capital=10_000.0)
        assert '$1,000 per buy' in text
        assert '10 buys' in text

    @pytest.mark.parametrize('mode', MODE_ORDER)
    def test_summary_never_claims_a_full_buy(self, mode):
        """Guards the exact wording that caused the original confusion."""
        text = first_entry_summary(mode).lower()
        assert '100%' not in text


class TestDefaults:
    @pytest.mark.parametrize('mode', MODE_ORDER)
    def test_defaults_are_complete_enough_to_run(self, mode):
        params = default_params(mode)
        assert 'capital' in params
        assert simulate(mode, **params).buy_count > 0
