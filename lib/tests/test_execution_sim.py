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
    order_model_summary,
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

    def test_the_bars_are_a_tape_and_not_four_unrelated_series(self):
        """Low <= min(Open, Close) <= max(Open, Close) <= High, on every bar."""
        df = build_sandbox_frame()
        o, h, l, c = (df[k].to_numpy(dtype=float) for k in ('Open', 'High', 'Low', 'Close'))
        assert (h >= np.maximum(o, c)).all()
        assert (l <= np.minimum(o, c)).all()

    def test_bars_have_range_a_resting_order_could_actually_reach(self):
        """The old tape was High = close x 1.01: decoration, not a range."""
        df = build_sandbox_frame()
        close = df['Close'].to_numpy(dtype=float)
        low = df['Low'].to_numpy(dtype=float)
        high = df['High'].to_numpy(dtype=float)
        # At least a few bars have to dip meaningfully below their close, or a
        # buy limit resting under the close can never fill.
        dips = (close - low) / close
        assert (dips > 0.02).sum() >= 3, "no bar dips far enough for a limit to fill"
        assert ((high - low) / close > 0.02).sum() >= 5, "ranges are too narrow to teach with"


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


# --------------------------------------------------------------------------- #
# The order model on the fixed tape (roadmap 3.7.8)
# --------------------------------------------------------------------------- #

class TestOrderModelInTheSandbox:
    @pytest.mark.parametrize('mode', MODE_ORDER)
    def test_the_default_run_is_still_market_orders_at_the_close(self, mode):
        run = simulate(mode)
        assert run.order_type == 'market'
        assert run.exit_order_mode == 'close'
        assert run.resting_fills == 0
        traded = [r for r in run.rows if r.order_value]
        assert traded
        # Market fills land on the close, with the one documented exception the
        # rebuilt tape finally makes visible: a trailing stop the market
        # reopened through fills at the Open (3.9.4). It could never show up
        # while the sandbox's Open was a copy of its Close.
        opens = build_sandbox_frame()['Open'].to_numpy(dtype=float)
        for row in traded:
            assert (
                row.fill_price == pytest.approx(row.price)
                or row.fill_price == pytest.approx(opens[row.bar])
            )

    @pytest.mark.parametrize('kind', ['limit', 'stop', 'stop_limit'])
    def test_a_resting_order_type_actually_fills_away_from_the_close(self, kind):
        """This is what the rebuilt tape exists to make possible."""
        run = simulate('trading', order_type=kind, order_offset_pct=2.0)
        assert run.order_type == kind
        assert run.resting_fills > 0
        away = [r for r in run.rows if r.order_value and r.fill_price != r.price]
        assert away, f"{kind} never filled at a price other than the close"

    def test_a_limit_buy_fills_below_the_close_it_was_placed_from(self):
        run = simulate('trading', order_type='limit', order_offset_pct=2.0)
        closes = [r.price for r in run.rows]
        buys = [r for r in run.rows if r.order_value > 0 and r.order_type == 'limit']
        assert buys
        for row in buys:
            # It rested 2% below the *signal* bar's close, one bar earlier.
            assert row.fill_price <= closes[row.bar - 1] * 0.98 + 1e-9

    def test_the_ledger_names_a_bracket_target_a_target_and_not_a_stop(self):
        """The old heuristic called every unsignalled exit a stop."""
        run = simulate('trading', exit_order_mode='bracket', take_profit_pct=10.0)
        notes = {r.note for r in run.rows if r.order_value < 0}
        assert 'target' in notes
        assert run.exit_order_mode == 'bracket'

    def test_accumulation_reports_the_exit_mode_the_engine_actually_ran(self):
        """It has no exits, so asking for a bracket must not claim to have one."""
        run = simulate('accumulation', exit_order_mode='bracket')
        assert run.exit_order_mode == 'close'

    def test_the_order_model_summary_describes_the_run_it_measured(self):
        market = order_model_summary('trading')
        assert 'market' in market and 'close' in market

        limit = order_model_summary('trading', order_type='limit', order_offset_pct=2.0)
        assert 'limit' in limit
        assert 'off the close' in limit

    @pytest.mark.parametrize('tif', ['gtc', 'day', 'ioc'])
    def test_time_in_force_reaches_the_engine(self, tif):
        run = simulate('trading', order_type='limit', order_offset_pct=2.0, order_tif=tif)
        assert len(run.rows) == 24

    def test_a_more_patient_limit_fills_no_more_often_than_an_eager_one(self):
        eager = simulate('trading', order_type='limit', order_offset_pct=0.5)
        patient = simulate('trading', order_type='limit', order_offset_pct=6.0)
        assert patient.buy_count <= eager.buy_count
