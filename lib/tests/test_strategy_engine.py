"""
Correctness tests for the backtest engine in ``lib.strategy``.

Everything here runs on deterministic synthetic price series — no network, no
RNG that isn't explicitly seeded — so a failure always points at the engine and
never at the data. Each test names the invariant it protects rather than the
line of code it happens to touch.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.strategy import (  # noqa: E402
    ATR_STOP_COLUMN,
    ValidationError,
    backtest,
    calculate_metrics,
    calculate_returns,
)

FEE = 0.001          # commission, % of notional
FX = 0.002           # fx fee, % of notional
SLIP = 0.0005        # slippage, % of price


# --------------------------------------------------------------------------- #
# Fixtures: deterministic price series
# --------------------------------------------------------------------------- #

def _frame(close, buy=None, sell=None, high=None, low=None) -> pd.DataFrame:
    """Wrap a close series in the OHLCV + signal frame the engine expects."""
    close = np.asarray(close, dtype=float)
    n = len(close)
    idx = pd.date_range('2022-01-03', periods=n, freq='B')
    return pd.DataFrame(
        {
            'Open': close,
            'High': close * 1.01 if high is None else np.asarray(high, dtype=float),
            'Low': close * 0.99 if low is None else np.asarray(low, dtype=float),
            'Close': close,
            'Volume': np.full(n, 1_000_000),
            'Buy_Signal': np.zeros(n, dtype=int) if buy is None else np.asarray(buy, dtype=int),
            'Sell_Signal': np.zeros(n, dtype=int) if sell is None else np.asarray(sell, dtype=int),
        },
        index=idx,
    )


@pytest.fixture
def trend_up() -> np.ndarray:
    """Monotonic 40-bar rally, 100 -> 139."""
    return np.arange(100.0, 140.0, 1.0)


@pytest.fixture
def trend_down() -> np.ndarray:
    """Monotonic 40-bar decline, 100 -> 61."""
    return np.arange(100.0, 60.0, -1.0)


@pytest.fixture
def whipsaw() -> np.ndarray:
    """40 bars alternating +5%/-5% around 100 — no drift, plenty of stop hits."""
    steps = np.where(np.arange(40) % 2 == 0, 1.05, 1.0 / 1.05)
    return 100.0 * np.cumprod(steps)


def _run(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    params = dict(
        initial_capital=10_000.0,
        position_sizing_strategy='percentage_of_portfolio',
        position_sizing_params={'percent': 0.5},
        buy_indicators=['Buy_Signal'],
        sell_indicators=['Sell_Signal'],
        position_scaling=1.0,
        min_holding_period=0,
        commission_per_trade=0.0,
        slippage_pct=0.0,
        fx_fee_pct=0.0,
    )
    params.update(kwargs)
    return backtest(df=df, **params)


def _run_all_in(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    """``_run`` with a sizer far larger than the account.

    Every buy then clamps to available cash and every sell clamps to the whole
    position, which turns each signal pair into one unambiguous round trip.
    The default 50%-of-portfolio sizer deliberately produces *partial* exits
    (the sell is sized independently of the position), which is correct but
    makes ledger arithmetic hard to state.
    """
    kwargs.setdefault('position_sizing_params', {'percent': 5.0})
    kwargs.setdefault('trailing_stop_loss', 0.9)
    return _run(df, **kwargs)


# --------------------------------------------------------------------------- #
# P0.1 — signal execution must actually be lagged by `delay`
# --------------------------------------------------------------------------- #

class TestSignalDelay:
    def test_delay_one_fills_on_the_next_bar(self, trend_up):
        """A signal on bar t fills on bar t+1's close, never on bar t."""
        buy = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        result = _run(_frame(trend_up, buy=buy), delay=1)

        fills = np.flatnonzero(result['Units_to_buy'].to_numpy() > 0)
        assert fills.tolist() == [6]
        assert result['Units'].iloc[5] == 0

    def test_fill_price_is_the_next_bars_close(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        result = _run(_frame(trend_up, buy=buy), delay=1)

        qty = result['Units_to_buy'].iloc[6]
        spent = 10_000.0 - result['Cash_Value'].iloc[6]
        assert spent == pytest.approx(qty * trend_up[6])
        assert spent != pytest.approx(qty * trend_up[5])

    def test_delay_zero_fills_on_the_signal_bar(self, trend_up):
        """delay=0 is the look-ahead diagnostic mode; it must still be honoured."""
        buy = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        result = _run(_frame(trend_up, buy=buy), delay=0)
        assert np.flatnonzero(result['Units_to_buy'].to_numpy() > 0).tolist() == [5]

    def test_larger_delay_shifts_the_fill_further(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        result = _run(_frame(trend_up, buy=buy), delay=3)
        assert np.flatnonzero(result['Units_to_buy'].to_numpy() > 0).tolist() == [8]

    def test_edge_detection_compares_lagged_bars(self, trend_up):
        """'edge' mode fires once per signal *run*, still shifted by the delay."""
        buy = np.zeros(len(trend_up), dtype=int)
        buy[5:9] = 1  # a four-bar run
        result = _run(
            _frame(trend_up, buy=buy), delay=1,
            consecutive_signal_mode='edge',
        )
        assert np.flatnonzero(result['Buy_Trigger_Accepted'].to_numpy()).tolist() == [6]

    def test_sell_signal_is_lagged_too(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        sell = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        sell[10] = 1
        result = _run(_frame(trend_up, buy=buy, sell=sell), delay=1)
        assert np.flatnonzero(result['Units_to_sell'].to_numpy() > 0).tolist() == [11]


# --------------------------------------------------------------------------- #
# P0.2 — the trailing stop must never loosen
# --------------------------------------------------------------------------- #

class TestTrailingStopRatchet:
    def test_scale_in_after_a_pullback_does_not_lower_the_stop(self):
        """Rally, pull back, buy again: the stop must hold its ratcheted level."""
        close = np.concatenate([
            np.full(3, 100.0),          # 0-2  flat
            np.linspace(105, 140, 8),   # 3-10 rally
            np.full(4, 128.0),          # 11-14 pullback
            np.full(10, 130.0),         # 15-24 flat
        ])
        buy = np.zeros(len(close), dtype=int)
        buy[1] = 1    # fill on bar 2 at 100
        buy[11] = 1   # scale in on bar 12 at 128, well below the ratcheted stop

        result = _run(
            _frame(close, buy=buy),
            trailing_stop_loss=0.20, stop_mode='percent', position_scaling=0.5,
        )

        held = result[result['Units'] > 0]['Trailing_Stop'].to_numpy()
        assert len(held) > 1
        assert (np.diff(held) >= -1e-9).all(), "stop moved down while a position was open"

    def test_scale_in_keeps_the_high_water_stop_exactly(self):
        close = np.concatenate([
            np.full(3, 100.0),
            np.linspace(105, 140, 8),
            np.full(4, 128.0),
            np.full(10, 130.0),
        ])
        buy = np.zeros(len(close), dtype=int)
        buy[1] = 1
        buy[11] = 1
        result = _run(
            _frame(close, buy=buy),
            trailing_stop_loss=0.20, stop_mode='percent', position_scaling=0.5,
        )

        scale_in = np.flatnonzero(result['Units_to_buy'].to_numpy() > 0)[1]
        # The peak close before the scale-in sets the high-water stop.
        peak = result['Close'].iloc[:scale_in].max()
        assert result['Trailing_Stop'].iloc[scale_in] == pytest.approx(peak * 0.80)
        assert result['Trailing_Stop'].iloc[scale_in] > close[scale_in] * 0.80

    def test_stop_never_decreases_in_a_whipsaw(self, whipsaw):
        buy = np.zeros(len(whipsaw), dtype=int)
        buy[1::4] = 1  # repeated scale-in attempts
        result = _run(_frame(whipsaw, buy=buy), trailing_stop_loss=0.15, position_scaling=0.25)

        stops = result['Trailing_Stop'].to_numpy()
        units = result['Units'].to_numpy()
        for i in range(1, len(stops)):
            if units[i] > 0 and units[i - 1] > 0:
                assert stops[i] >= stops[i - 1] - 1e-9


# --------------------------------------------------------------------------- #
# P0.3 — cooldown_bars=N blocks exactly N bars
# --------------------------------------------------------------------------- #

class TestCooldown:
    @staticmethod
    def _run_cooldown(bars: int, mode: str = 'cooldown') -> pd.DataFrame:
        """Flat market, a buy signal on every bar, $100 per fill.

        Sizing is deliberately tiny so cash never runs out — an unfilled buy
        arms no cooldown, which would confound the interval being measured.
        """
        close = np.full(30, 100.0)
        buy = np.ones(30, dtype=int)
        return _run(
            _frame(close, buy=buy),
            delay=1, cooldown_bars=bars, consecutive_signal_mode=mode,
            position_sizing_strategy='fixed_dollar_amount',
            position_sizing_params={'amount': 100},
            position_scaling=1.0,
        )

    def test_cooldown_two_blocks_exactly_two_bars(self):
        result = self._run_cooldown(2)
        accepted = np.flatnonzero(result['Buy_Trigger_Accepted'].to_numpy())
        # First fill is bar 1 (delay=1 over a signal on bar 0), then every 3rd bar.
        assert accepted[0] == 1
        assert np.diff(accepted).tolist() == [3] * (len(accepted) - 1)

    def test_the_two_bars_after_a_fill_are_rejected(self):
        result = self._run_cooldown(2)
        first = np.flatnonzero(result['Buy_Trigger_Accepted'].to_numpy())[0]
        rejected = result['Buy_Trigger_Rejected'].to_numpy()
        assert rejected[first + 1] and rejected[first + 2]
        assert not rejected[first + 3]

    @pytest.mark.parametrize('bars', [1, 2, 3, 5])
    def test_gap_between_fills_is_bars_plus_one(self, bars):
        result = self._run_cooldown(bars)
        accepted = np.flatnonzero(result['Buy_Trigger_Accepted'].to_numpy())
        assert np.diff(accepted).tolist() == [bars + 1] * (len(accepted) - 1)

    def test_zero_cooldown_accepts_every_bar(self):
        result = self._run_cooldown(0)
        accepted = np.flatnonzero(result['Buy_Trigger_Accepted'].to_numpy())
        assert np.diff(accepted).tolist() == [1] * (len(accepted) - 1)


# --------------------------------------------------------------------------- #
# P1.4 — Buy_Position / Sell_Position mirror the simulated signals
# --------------------------------------------------------------------------- #

class TestPositionColumns:
    def test_columns_match_the_raw_signals_without_strength(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        sell = np.zeros(len(trend_up), dtype=int)
        buy[[3, 9]] = 1
        sell[[15]] = 1
        result = _run(_frame(trend_up, buy=buy, sell=sell))

        np.testing.assert_array_equal(result['Buy_Position'].to_numpy(), buy.astype(bool))
        np.testing.assert_array_equal(result['Sell_Position'].to_numpy(), sell.astype(bool))

    def test_default_threshold_no_longer_swallows_single_signals(self, trend_up):
        """A lone 0/1 signal used to fail the 0.5 threshold used for reporting."""
        buy = np.zeros(len(trend_up), dtype=int)
        buy[3] = 1
        result = _run(_frame(trend_up, buy=buy), buy_threshold=0.5, use_signal_strength=False)
        assert bool(result['Buy_Position'].iloc[3])

    def test_strength_mode_applies_the_threshold(self, trend_up):
        df = _frame(trend_up)
        df['Buy_A'] = 0
        df['Buy_B'] = 0
        df.iloc[4, df.columns.get_loc('Buy_A')] = 1        # strength 1
        df.iloc[8, df.columns.get_loc('Buy_A')] = 1
        df.iloc[8, df.columns.get_loc('Buy_B')] = 1        # strength 2
        result = _run(
            df, buy_indicators=['Buy_A', 'Buy_B'],
            use_signal_strength=True, buy_threshold=1.5,
        )
        assert not bool(result['Buy_Position'].iloc[4])
        assert bool(result['Buy_Position'].iloc[8])


# --------------------------------------------------------------------------- #
# P1.5 — trade ledger
# --------------------------------------------------------------------------- #

class TestTradeLedger:
    def test_round_trip_is_recorded(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        sell = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        sell[15] = 1
        result = _run_all_in(_frame(trend_up, buy=buy, sell=sell))
        trades = result.attrs['trades']

        closed = trades[trades['exit_reason'] != 'open']
        assert len(closed) == 1
        row = closed.iloc[0]
        assert row['entry_bar'] == 6
        assert row['exit_bar'] == 16
        assert row['holding_bars'] == 10
        assert row['entry_date'] == result.index[6]
        assert row['exit_date'] == result.index[16]
        assert row['exit_reason'] == 'signal'
        assert row['net_pnl'] > 0  # bought at 106, sold at 116

    def test_pnl_reconciles_with_the_equity_curve(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        sell = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        sell[15] = 1
        result = _run_all_in(
            _frame(trend_up, buy=buy, sell=sell),
            commission_per_trade=FEE, fx_fee_pct=FX, slippage_pct=SLIP,
        )
        trade = result.attrs['trades'].iloc[0]
        # Flat again at bar 16, so equity change == the trade's net PnL.
        equity_change = result['Portfolio_Value'].iloc[16] - 10_000.0
        assert trade['net_pnl'] == pytest.approx(equity_change)
        assert trade['gross_pnl'] - trade['fees'] == pytest.approx(trade['net_pnl'])

    def test_entry_price_excludes_fees_and_cost_basis_includes_them(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        result = _run_all_in(
            _frame(trend_up, buy=buy),
            commission_per_trade=FEE, fx_fee_pct=FX, slippage_pct=SLIP,
        )
        trade = result.attrs['trades'].iloc[0]
        expected_entry = trend_up[6] * (1 + SLIP)
        assert trade['avg_entry_price'] == pytest.approx(expected_entry)
        assert trade['avg_cost_basis'] == pytest.approx(expected_entry * (1 + FEE + FX))
        assert trade['avg_cost_basis'] > trade['avg_entry_price']

    def test_exit_reason_trailing_stop(self, trend_down):
        buy = np.zeros(len(trend_down), dtype=int)
        buy[1] = 1
        result = _run(_frame(trend_down, buy=buy), trailing_stop_loss=0.05)
        trades = result.attrs['trades']
        assert (trades['exit_reason'] == 'trailing_stop').any()

    def test_exit_reason_take_profit(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        buy[1] = 1
        result = _run(_frame(trend_up, buy=buy), take_profit=0.10, trailing_stop_loss=0.5)
        trades = result.attrs['trades']
        closed = trades[trades['exit_reason'] != 'open']
        assert (closed['exit_reason'] == 'take_profit').any()

    def test_take_profit_fires_on_the_nominal_price_move(self, trend_up):
        """TP is measured against the fee-exclusive entry, so 10% means 10%."""
        buy = np.zeros(len(trend_up), dtype=int)
        buy[1] = 1
        result = _run(
            _frame(trend_up, buy=buy), take_profit=0.10, trailing_stop_loss=0.5,
            commission_per_trade=FEE, fx_fee_pct=FX, slippage_pct=SLIP,
        )
        trade = result.attrs['trades'].iloc[0]
        exit_close = result['Close'].iloc[int(trade['exit_bar'])]
        prev_close = result['Close'].iloc[int(trade['exit_bar']) - 1]
        assert exit_close >= trade['avg_entry_price'] * 1.10
        assert prev_close < trade['avg_entry_price'] * 1.10

    def test_scale_in_collapses_into_one_round_trip(self):
        """Two entries then a stop-out: one ledger row spanning both fills."""
        close = np.concatenate([
            np.linspace(100, 130, 16),   # 0-15 rally, two entries land here
            np.linspace(128, 100, 14),   # 16-29 crash, takes out the stop
        ])
        buy = np.zeros(len(close), dtype=int)
        buy[[3, 6]] = 1
        result = _run(
            _frame(close, buy=buy),
            position_scaling=0.5, trailing_stop_loss=0.10,
        )
        assert (result['Units_to_buy'] > 0).sum() == 2

        closed = result.attrs['trades'].query("exit_reason != 'open'")
        assert len(closed) == 1
        assert closed.iloc[0]['entry_bar'] == 4  # first of the two fills
        assert closed.iloc[0]['units'] == result['Units_to_buy'].sum()
        assert closed.iloc[0]['exit_reason'] == 'trailing_stop'

    def test_position_open_at_the_end_is_marked_to_market(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        result = _run(_frame(trend_up, buy=buy), trailing_stop_loss=0.9)
        trades = result.attrs['trades']
        assert len(trades) == 1
        row = trades.iloc[0]
        assert row['exit_reason'] == 'open'
        assert bool(row['is_open'])
        assert row['exit_price'] == pytest.approx(trend_up[-1])

    def test_empty_ledger_has_stable_columns(self, trend_up):
        result = _run(_frame(trend_up))
        trades = result.attrs['trades']
        assert trades.empty
        assert 'net_pnl' in trades.columns and 'exit_reason' in trades.columns


# --------------------------------------------------------------------------- #
# P1.6 — calculate_metrics
# --------------------------------------------------------------------------- #

class TestCalculateMetrics:
    def test_reports_every_documented_key(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        sell = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        sell[15] = 1
        result = _run_all_in(_frame(trend_up, buy=buy, sell=sell))
        metrics = calculate_metrics(result, periods_per_year=252)

        for key in (
            'total_return', 'cagr', 'sharpe', 'sortino', 'max_drawdown',
            'exposure', 'num_trades', 'win_rate', 'profit_factor',
            'avg_win', 'avg_loss', 'expectancy',
        ):
            assert key in metrics

    def test_exposure_is_the_fraction_of_bars_in_market(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        sell = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        sell[15] = 1
        result = _run_all_in(_frame(trend_up, buy=buy, sell=sell))
        metrics = calculate_metrics(result)
        expected = (result['Units'] > 0).mean()
        assert metrics['exposure'] == pytest.approx(expected)

    def test_win_rate_and_profit_factor_from_closed_trades(self):
        """Two round trips, one winner one loser, with known magnitudes."""
        close = np.array(
            [100, 100, 100, 110, 110, 110, 110, 100, 100, 95, 95, 95, 95, 95],
            dtype=float,
        )
        buy = np.zeros(len(close), dtype=int)
        sell = np.zeros(len(close), dtype=int)
        buy[1] = 1     # fill bar 2 @100
        sell[2] = 1    # fill bar 3 @110  -> winner
        buy[7] = 1     # fill bar 8 @100
        sell[8] = 1    # fill bar 9 @95   -> loser
        result = _run_all_in(_frame(close, buy=buy, sell=sell))

        metrics = calculate_metrics(result)
        assert metrics['num_trades'] == 2
        assert metrics['win_rate'] == pytest.approx(0.5)
        assert metrics['avg_win'] > 0 > metrics['avg_loss']
        assert metrics['profit_factor'] == pytest.approx(
            metrics['avg_win'] / abs(metrics['avg_loss'])
        )

    def test_open_trade_is_excluded_from_realised_stats(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        buy[5] = 1
        result = _run(_frame(trend_up, buy=buy), trailing_stop_loss=0.9)
        metrics = calculate_metrics(result)
        assert metrics['num_trades'] == 0
        assert metrics['open_trades'] == 1
        assert metrics['win_rate'] == 0.0

    def test_cagr_matches_total_return_over_exactly_one_year(self):
        close = np.linspace(100.0, 200.0, 253)
        buy = np.zeros(len(close), dtype=int)
        buy[0] = 1
        result = _run(_frame(close, buy=buy), trailing_stop_loss=0.9, position_scaling=1.0)
        metrics = calculate_metrics(result, periods_per_year=252)
        # 252 bar-steps at 252 periods/year == 1 year, so CAGR == total return.
        assert metrics['cagr'] == pytest.approx(metrics['total_return'], rel=1e-9)

    def test_annualisation_factor_is_honoured(self, whipsaw):
        buy = np.zeros(len(whipsaw), dtype=int)
        buy[1::6] = 1
        result = _run(_frame(whipsaw, buy=buy))
        daily = calculate_metrics(result, periods_per_year=252)['sharpe']
        weekly = calculate_metrics(result, periods_per_year=52)['sharpe']
        if daily != 0:
            assert daily == pytest.approx(weekly * np.sqrt(252 / 52))

    def test_empty_frame_returns_zeroed_metrics(self):
        metrics = calculate_metrics(pd.DataFrame())
        assert metrics['total_return'] == 0.0
        assert metrics['num_trades'] == 0


# --------------------------------------------------------------------------- #
# P1.7 — division guards
# --------------------------------------------------------------------------- #

class TestReturnGuards:
    def test_zero_portfolio_value_does_not_produce_inf_or_nan(self):
        pv = np.array([100.0, 50.0, 0.0, 0.0, 0.0])
        market = np.zeros(5)
        strategy, cumulative, _ = calculate_returns(pv, market)
        assert np.isfinite(strategy).all()
        assert np.isfinite(cumulative).all()
        assert strategy[3] == 0.0
        assert cumulative[-1] == pytest.approx(0.0)

    def test_zero_close_price_does_not_poison_market_returns(self):
        close = np.array([100.0, 0.0, 0.0, 110.0, 121.0])
        result = _run(_frame(close))
        assert np.isfinite(result['Returns']).all()
        assert np.isfinite(result['Cumulative_Market_Returns']).all()

    def test_single_row_series_is_handled(self):
        strategy, cumulative, market = calculate_returns(np.array([100.0]), np.array([0.0]))
        assert strategy.tolist() == [0.0]
        assert cumulative.tolist() == [1.0]
        assert market.tolist() == [1.0]


# --------------------------------------------------------------------------- #
# Fees, cash accounting and accumulation mode
# --------------------------------------------------------------------------- #

class TestFeesAndCash:
    def test_buy_then_sell_round_trip_is_exact_to_the_penny(self):
        """Flat price, known fees: cash must land on the analytic value."""
        close = np.full(10, 50.0)
        buy = np.zeros(10, dtype=int)
        sell = np.zeros(10, dtype=int)
        buy[0] = 1
        sell[1] = 1
        result = _run_all_in(
            _frame(close, buy=buy, sell=sell),
            commission_per_trade=FEE, fx_fee_pct=FX, slippage_pct=SLIP,
            position_scaling=1.0,
        )

        fee_rate = FEE + FX
        qty = result['Units_to_buy'].iloc[1]
        assert qty > 0
        buy_price = 50.0 * (1 + SLIP)
        sell_price = 50.0 * (1 - SLIP)
        expected = (
            10_000.0
            - qty * buy_price * (1 + fee_rate)
            + qty * sell_price * (1 - fee_rate)
        )
        assert result['Cash_Value'].iloc[2] == pytest.approx(expected, abs=1e-9)
        assert result['Portfolio_Value'].iloc[2] == pytest.approx(expected, abs=1e-9)
        assert result['Units'].iloc[2] == 0

    def test_fees_are_the_only_thing_lost_on_a_flat_round_trip(self):
        close = np.full(10, 50.0)
        buy = np.zeros(10, dtype=int)
        sell = np.zeros(10, dtype=int)
        buy[0] = 1
        sell[1] = 1
        result = _run_all_in(
            _frame(close, buy=buy, sell=sell),
            commission_per_trade=FEE, fx_fee_pct=FX, slippage_pct=0.0,
            position_scaling=1.0,
        )
        trade = result.attrs['trades'].iloc[0]
        assert trade['gross_pnl'] == pytest.approx(0.0, abs=1e-9)
        assert trade['net_pnl'] == pytest.approx(-trade['fees'])

    def test_cash_never_goes_negative(self, whipsaw):
        buy = np.ones(len(whipsaw), dtype=int)
        result = _run(
            _frame(whipsaw, buy=buy),
            commission_per_trade=FEE, fx_fee_pct=FX, slippage_pct=SLIP,
            position_sizing_params={'percent': 5.0}, position_scaling=1.0,
        )
        assert (result['Cash_Value'] >= -1e-9).all()


class TestAccumulationMode:
    def test_cash_exhaustion_buys_the_remainder_then_stops(self):
        """DCA into a flat market: the last buy takes what's left, then zero."""
        close = np.full(20, 100.0)
        buy = np.ones(20, dtype=int)
        result = _run(
            _frame(close, buy=buy),
            strategy_mode='accumulation', amount_per_buy=3_000.0,
            initial_capital=10_000.0,
        )

        filled = result['Units_to_buy'].to_numpy()
        # 30 + 30 + 30 units at $100, leaving $1000 -> 10 units, then nothing.
        assert filled[filled > 0].tolist() == [30.0, 30.0, 30.0, 10.0]
        assert result['Cash_Value'].iloc[-1] == pytest.approx(0.0)
        assert result['Units'].iloc[-1] == 100.0

    def test_accumulation_never_sells_and_never_stops_out(self, trend_down):
        buy = np.ones(len(trend_down), dtype=int)
        sell = np.ones(len(trend_down), dtype=int)
        result = _run(
            _frame(trend_down, buy=buy, sell=sell),
            strategy_mode='accumulation', amount_per_buy=500.0,
        )
        assert (result['Units_to_sell'] == 0).all()
        assert np.isinf(result['Trailing_Stop']).all()


class TestRebalancingMode:
    """Rebalancing is a *target weight* mode: both sides size off portfolio value.

    Sizing off cash (buys) or off units held (sells) was the old behaviour; it
    made repeated buys decay geometrically and contradicted the mode's own name,
    its UI label and its docstring.
    """

    def test_buy_sizes_off_portfolio_value_not_cash(self):
        close = np.full(10, 100.0)
        buy = np.zeros(10, dtype=int)
        buy[0] = 1
        result = _run(
            _frame(close, buy=buy),
            strategy_mode='rebalancing', position_size_pct=25.0,
            initial_capital=10_000.0, trailing_stop_loss=0.9,
        )
        # 25% of the $10,000 portfolio at $100 = 25 units. Identical to 25% of
        # cash here only because no position is open yet — the next test is the
        # one that actually separates the two rules.
        assert result['Units_to_buy'].iloc[1] == pytest.approx(25.0)

    def test_repeated_buys_stay_equal_weight_instead_of_decaying(self):
        """Three buys in a flat market must each be the same size.

        Under the old ``pct * cash`` rule these were 25 / 18.75 / 14.06 units.
        """
        close = np.full(12, 100.0)
        buy = np.zeros(12, dtype=int)
        buy[0] = buy[2] = buy[4] = 1
        result = _run(
            _frame(close, buy=buy),
            strategy_mode='rebalancing', position_size_pct=25.0,
            initial_capital=10_000.0, trailing_stop_loss=0.9,
        )
        filled = result['Units_to_buy'].to_numpy()
        assert filled[filled > 0].tolist() == pytest.approx([25.0, 25.0, 25.0])

    def test_sell_sizes_off_portfolio_value_not_units_held(self):
        close = np.full(12, 100.0)
        buy = np.zeros(12, dtype=int)
        sell = np.zeros(12, dtype=int)
        buy[0] = 1          # -> 25 units held
        sell[2] = 1
        result = _run(
            _frame(close, buy=buy, sell=sell),
            strategy_mode='rebalancing', position_size_pct=25.0,
            initial_capital=10_000.0, trailing_stop_loss=0.9,
        )
        # 25% of the $10,000 portfolio = 25 units, and 25 units are held, so the
        # whole position goes. The old ``pct * units`` rule sold 6.25 units.
        assert result['Units_to_sell'].iloc[3] == pytest.approx(25.0)
        assert result['Units'].iloc[3] == pytest.approx(0.0)

    def test_sell_is_capped_at_units_actually_held(self):
        """A target weight above the open position liquidates, never goes short."""
        close = np.full(12, 100.0)
        buy = np.zeros(12, dtype=int)
        sell = np.zeros(12, dtype=int)
        buy[0] = 1
        sell[2] = 1
        result = _run(
            _frame(close, buy=buy, sell=sell),
            strategy_mode='rebalancing', position_size_pct=10.0,
            initial_capital=10_000.0, trailing_stop_loss=0.9,
        )
        held = result['Units'].iloc[2]
        assert result['Units_to_sell'].iloc[3] == pytest.approx(held)
        assert (result['Units'] >= -1e-9).all()

    def test_buy_still_clamps_to_available_cash(self):
        """An over-weight request degrades to 'spend what's left', not an error."""
        close = np.full(10, 100.0)
        buy = np.ones(10, dtype=int)
        result = _run(
            _frame(close, buy=buy),
            strategy_mode='rebalancing', position_size_pct=100.0,
            initial_capital=10_000.0, trailing_stop_loss=0.9,
            commission_per_trade=FEE, fx_fee_pct=FX, slippage_pct=SLIP,
        )
        assert (result['Cash_Value'] >= -1e-9).all()


KELLY_PARAMS = {'win_rate': 0.5, 'win_loss_ratio': 1.5}
KELLY_FRACTION = 0.5 - (0.5 / 1.5)          # 0.16666...


class TestTradingModeScaling:
    """``position_scaling`` ramps *each order*, it is not a target weight.

    Pinning this down matters because the UI describes the mode to the user: the
    first entry is ``kelly x position_scaling`` of portfolio value, and repeated
    buys keep stacking without converging on any cap.
    """

    def test_full_scaling_buys_the_whole_kelly_size_on_the_first_signal(self):
        close = np.full(10, 100.0)
        buy = np.zeros(10, dtype=int)
        buy[0] = 1
        result = _run(
            _frame(close, buy=buy), allow_fractional=True,
            position_sizing_strategy='kelly_criterion',
            position_sizing_params=KELLY_PARAMS,
            position_scaling=1.0, initial_capital=10_000.0,
            trailing_stop_loss=0.9,
        )
        expected_units = (KELLY_FRACTION * 10_000.0) / 100.0
        assert result['Units_to_buy'].iloc[1] == pytest.approx(expected_units)

    def test_quarter_scaling_quarters_the_first_entry(self):
        """The old dashboard default: a 16.7% Kelly size became a 4.2% entry."""
        close = np.full(14, 100.0)
        buy = np.zeros(14, dtype=int)
        buy[0] = 1
        result = _run(
            _frame(close, buy=buy), allow_fractional=True,
            position_sizing_strategy='kelly_criterion',
            position_sizing_params=KELLY_PARAMS,
            position_scaling=0.25, initial_capital=10_000.0,
            trailing_stop_loss=0.9,
        )
        kelly_units = (KELLY_FRACTION * 10_000.0) / 100.0
        assert result['Units_to_buy'].iloc[1] == pytest.approx(kelly_units * 0.25)
        # 4.17 units at $100 out of a $10,000 account.
        assert result['Units'].iloc[1] * 100.0 / 10_000.0 == pytest.approx(0.0417, abs=1e-4)

    def test_scale_in_ramps_order_size_and_never_caps(self):
        """Consecutive buys are sized 0.25, 0.50, 0.75, 1.00 x Kelly and stack.

        There is no target weight the position converges to — by the 3rd buy the
        holding is already 1.5x one Kelly size. Any UI copy that calls this
        'scaling up to full size' would be wrong.
        """
        close = np.full(14, 100.0)
        buy = np.ones(14, dtype=int)
        result = _run(
            _frame(close, buy=buy), allow_fractional=True,
            position_sizing_strategy='kelly_criterion',
            position_sizing_params=KELLY_PARAMS,
            position_scaling=0.25, initial_capital=10_000.0,
            trailing_stop_loss=0.9,
        )
        kelly_units = (KELLY_FRACTION * 10_000.0) / 100.0
        filled = result['Units_to_buy'].to_numpy()
        first_four = filled[filled > 0][:4] / kelly_units
        assert first_four == pytest.approx([0.25, 0.50, 0.75, 1.00], rel=1e-3)
        # Cumulative, not convergent (buys land one bar after their signal):
        # 0.25 Kelly held, then 0.75, then straight past 1.0 to 1.5.
        assert result['Units'].iloc[1] / kelly_units == pytest.approx(0.25, rel=1e-3)
        assert result['Units'].iloc[2] / kelly_units == pytest.approx(0.75, rel=1e-3)
        assert result['Units'].iloc[3] / kelly_units == pytest.approx(1.50, rel=1e-3)


# --------------------------------------------------------------------------- #
# ATR fallback
# --------------------------------------------------------------------------- #

class TestAtrStopFallback:
    def test_missing_atr_column_warns_and_matches_a_percent_run(self, caplog, trend_down):
        buy = np.zeros(len(trend_down), dtype=int)
        buy[1] = 1
        df = _frame(trend_down, buy=buy)

        with caplog.at_level('WARNING', logger='lib.strategy'):
            atr_run = _run(df.copy(), stop_mode='atr', trailing_stop_loss=0.05)
        assert any(ATR_STOP_COLUMN in rec.getMessage() for rec in caplog.records)

        percent_run = _run(df.copy(), stop_mode='percent', trailing_stop_loss=0.05)

        assert atr_run.attrs['stop_mode'] == 'percent'
        pd.testing.assert_series_equal(atr_run['Portfolio_Value'], percent_run['Portfolio_Value'])
        pd.testing.assert_series_equal(atr_run['Trailing_Stop'], percent_run['Trailing_Stop'])
        pd.testing.assert_series_equal(atr_run['Units'], percent_run['Units'])

    def test_present_atr_column_diverges_from_the_percent_run(self):
        """Rally then crash, so the Chandelier stop sits below price while held."""
        close = np.concatenate([np.linspace(100, 130, 20), np.linspace(128, 90, 20)])
        buy = np.zeros(len(close), dtype=int)
        buy[1] = 1
        df = _frame(close, buy=buy)
        df[ATR_STOP_COLUMN] = df['High'].rolling(14, min_periods=1).max() - 3.0

        atr_run = _run(df.copy(), stop_mode='atr', trailing_stop_loss=0.05)
        percent_run = _run(df.copy(), stop_mode='percent', trailing_stop_loss=0.05)
        assert atr_run.attrs['stop_mode'] == 'atr'
        assert not atr_run['Trailing_Stop'].equals(percent_run['Trailing_Stop'])


# --------------------------------------------------------------------------- #
# P2.9 / P2.10 / P2.11 — documented policies, validation, fractional shares
# --------------------------------------------------------------------------- #

class TestDocumentedPolicies:
    def test_buy_wins_when_both_signals_fire(self, trend_up):
        both = np.ones(len(trend_up), dtype=int)
        result = _run(_frame(trend_up, buy=both, sell=both), position_scaling=0.25)
        assert (result['Units_to_sell'] == 0).all()
        assert result['Buy_Trigger_Accepted'].any()

    def test_trailing_stop_ignores_min_holding_period(self, trend_down):
        buy = np.zeros(len(trend_down), dtype=int)
        buy[1] = 1
        result = _run(
            _frame(trend_down, buy=buy),
            trailing_stop_loss=0.02, min_holding_period=50,
        )
        exits = np.flatnonzero(result['Units_to_sell'].to_numpy() > 0)
        assert len(exits) == 1
        assert result['Holding_Period'].iloc[exits[0]] < 50

    def test_take_profit_respects_min_holding_period(self, trend_up):
        buy = np.zeros(len(trend_up), dtype=int)
        buy[1] = 1
        result = _run(
            _frame(trend_up, buy=buy),
            take_profit=0.05, trailing_stop_loss=0.9, min_holding_period=20,
        )
        exits = np.flatnonzero(result['Units_to_sell'].to_numpy() > 0)
        assert len(exits) == 1
        assert result['Holding_Period'].iloc[exits[0]] >= 20

    def test_close_only_stops_miss_an_intrabar_breach(self):
        """A wick through the stop that closes back above is ignored by default."""
        close = np.concatenate([np.full(4, 100.0), np.full(8, 99.0)])
        low = close.copy()
        low[6] = 80.0  # deep wick, recovers by the close
        buy = np.zeros(len(close), dtype=int)
        buy[0] = 1

        df = _frame(close, buy=buy, low=low)
        lenient = _run(df.copy(), trailing_stop_loss=0.10)
        assert (lenient['Units_to_sell'] == 0).all()

    def test_use_low_for_stops_catches_the_intrabar_breach(self):
        close = np.concatenate([np.full(4, 100.0), np.full(8, 99.0)])
        low = close.copy()
        low[6] = 80.0
        buy = np.zeros(len(close), dtype=int)
        buy[0] = 1

        df = _frame(close, buy=buy, low=low)
        strict = _run(df.copy(), trailing_stop_loss=0.10, use_low_for_stops=True)
        exits = np.flatnonzero(strict['Units_to_sell'].to_numpy() > 0)
        assert exits.tolist() == [6]
        # Filled at the stop (90), not at the 99 close and not at the 80 low.
        trade = strict.attrs['trades'].iloc[0]
        assert trade['exit_price'] == pytest.approx(90.0)
        assert trade['exit_reason'] == 'trailing_stop'

    def test_use_low_for_stops_without_a_low_column_warns_and_degrades(self, caplog, trend_down):
        buy = np.zeros(len(trend_down), dtype=int)
        buy[1] = 1
        df = _frame(trend_down, buy=buy).drop(columns=['Low'])
        with caplog.at_level('WARNING', logger='lib.strategy'):
            strict = _run(df.copy(), use_low_for_stops=True, trailing_stop_loss=0.05)
        assert any('Low' in rec.getMessage() for rec in caplog.records)

        lenient = _run(_frame(trend_down, buy=buy), use_low_for_stops=False, trailing_stop_loss=0.05)
        pd.testing.assert_series_equal(
            strict['Portfolio_Value'], lenient['Portfolio_Value'], check_names=False
        )


class TestModeValidation:
    def test_unknown_strategy_mode_raises(self, trend_up):
        with pytest.raises(ValidationError, match='strategy_mode'):
            _run(_frame(trend_up), strategy_mode='martingale')

    def test_unknown_consecutive_signal_mode_raises(self, trend_up):
        with pytest.raises(ValidationError, match='consecutive_signal_mode'):
            _run(_frame(trend_up), consecutive_signal_mode='pyramid')

    def test_unknown_stop_mode_raises(self, trend_up):
        with pytest.raises(ValidationError, match='stop_mode'):
            _run(_frame(trend_up), stop_mode='chandelier')

    @pytest.mark.parametrize('mode', ['TRADING', 'Accumulation', 'ReBalancing'])
    def test_mode_matching_is_case_insensitive(self, mode, trend_up):
        _run(_frame(trend_up), strategy_mode=mode, amount_per_buy=100.0)


class TestFractionalShares:
    def test_default_truncates_to_whole_shares(self):
        close = np.full(10, 300.0)  # $10k * 50% = $5000 -> 16.67 shares
        buy = np.zeros(10, dtype=int)
        buy[0] = 1
        result = _run(_frame(close, buy=buy), allow_fractional=False, position_scaling=1.0)
        qty = result['Units_to_buy'].max()
        assert qty == 16.0

    def test_fractional_keeps_the_exact_quantity(self):
        close = np.full(10, 300.0)
        buy = np.zeros(10, dtype=int)
        buy[0] = 1
        result = _run(_frame(close, buy=buy), allow_fractional=True, position_scaling=1.0)
        qty = result['Units_to_buy'].max()
        assert qty > 16.0
        assert qty != int(qty)

    def test_fractional_accumulation_spends_the_cash_exactly(self):
        close = np.full(20, 333.0)
        buy = np.ones(20, dtype=int)
        result = _run(
            _frame(close, buy=buy),
            strategy_mode='accumulation', amount_per_buy=2_500.0,
            allow_fractional=True,
        )
        assert result['Cash_Value'].iloc[-1] == pytest.approx(0.0, abs=1e-9)
        assert result['Portfolio_Value'].iloc[-1] == pytest.approx(10_000.0, abs=1e-6)

    def test_fractional_still_respects_affordability(self):
        close = np.full(10, 300.0)
        buy = np.ones(10, dtype=int)
        result = _run(
            _frame(close, buy=buy), allow_fractional=True, position_scaling=1.0,
            position_sizing_params={'percent': 5.0},
            commission_per_trade=FEE, fx_fee_pct=FX, slippage_pct=SLIP,
        )
        assert (result['Cash_Value'] >= -1e-9).all()
