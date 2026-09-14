"""
The order layer: fill rules, priority, time in force, and the engine wiring.

Two halves. The first exercises :mod:`lib.orders` on its own — it is pure, so
every rule in its docstring can be asserted against a hand-built bar. The second
runs :func:`lib.strategy.backtest` and checks that the order model actually
reaches the position: that ``order_type='market'`` still means "fill at the
close", that a resting order fills where the fill rules say it should, and that
a bracket's two legs cancel each other.

The one invariant that matters more than any single number is at the bottom:
the ledger has to reconcile with the equity curve on every configuration. An
order model that double-fills or loses a fill breaks that immediately.
"""

from __future__ import annotations

import os
import sys

import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from lib.orders import (  # noqa: E402
    ORDER_TYPES,
    Bar,
    Order,
    OrderBook,
    OrderError,
    bracket_orders,
    fill_price,
    fills_to_frame,
)
from lib.strategy import backtest  # noqa: E402


def _bar(index=1, open_=100.0, high=110.0, low=90.0, close=105.0, session_start=False, session=0):
    return Bar(
        index=index, open=open_, high=high, low=low, close=close,
        session_start=session_start, session_id=session,
    )


# --------------------------------------------------------------------------- #
# Fill rules
# --------------------------------------------------------------------------- #

class TestLimitFills:
    def test_buy_limit_inside_the_range_fills_at_the_limit(self):
        order = Order(side='buy', order_type='limit', qty=1, limit_price=95.0)
        assert fill_price(order, _bar()) == 95.0

    def test_buy_limit_below_the_range_does_not_fill(self):
        order = Order(side='buy', order_type='limit', qty=1, limit_price=80.0)
        assert fill_price(order, _bar()) is None

    def test_a_bar_that_opens_through_a_buy_limit_fills_at_the_open(self):
        """Price improvement is real: you cannot be filled worse than the open."""
        order = Order(side='buy', order_type='limit', qty=1, limit_price=105.0)
        assert fill_price(order, _bar(open_=100.0)) == 100.0

    def test_sell_limit_mirrors_against_the_high(self):
        order = Order(side='sell', order_type='limit', qty=1, limit_price=108.0)
        assert fill_price(order, _bar()) == 108.0
        far = Order(side='sell', order_type='limit', qty=1, limit_price=120.0)
        assert fill_price(far, _bar()) is None

    def test_a_bar_that_opens_through_a_sell_limit_fills_at_the_open(self):
        order = Order(side='sell', order_type='limit', qty=1, limit_price=95.0)
        assert fill_price(order, _bar(open_=100.0)) == 100.0


class TestStopFills:
    def test_sell_stop_touched_intrabar_fills_at_the_stop(self):
        order = Order(side='sell', order_type='stop', qty=1, stop_price=95.0)
        assert fill_price(order, _bar()) == 95.0

    def test_sell_stop_gapped_through_fills_at_the_open_not_the_stop(self):
        """The market reopened below the stop; the stop could not be worked."""
        order = Order(side='sell', order_type='stop', qty=1, stop_price=95.0)
        assert fill_price(order, _bar(open_=90.0, high=96.0, low=88.0, close=94.0)) == 90.0

    def test_sell_stop_the_bar_never_reaches_does_not_fill(self):
        order = Order(side='sell', order_type='stop', qty=1, stop_price=80.0)
        assert fill_price(order, _bar()) is None

    def test_buy_stop_mirrors_against_the_high(self):
        order = Order(side='buy', order_type='stop', qty=1, stop_price=108.0)
        assert fill_price(order, _bar()) == 108.0
        gapped = Order(side='buy', order_type='stop', qty=1, stop_price=95.0)
        assert fill_price(gapped, _bar(open_=100.0)) == 100.0


class TestStopLimitFills:
    def test_trigger_inside_the_limit_fills_at_the_trigger(self):
        order = Order(
            side='sell', order_type='stop_limit', qty=1, stop_price=95.0, limit_price=93.0
        )
        assert fill_price(order, _bar()) == 95.0

    def test_gapping_past_the_limit_does_not_fill_at_a_worse_price(self):
        """The whole point of a stop-limit — and the reason it can strand you."""
        order = Order(
            side='sell', order_type='stop_limit', qty=1, stop_price=95.0, limit_price=94.0
        )
        gap = _bar(open_=90.0, high=92.0, low=85.0, close=91.0)
        assert fill_price(order, gap) is None

    def test_a_bar_that_comes_back_to_the_limit_after_gapping_fills_there(self):
        order = Order(
            side='sell', order_type='stop_limit', qty=1, stop_price=95.0, limit_price=94.0
        )
        recovering = _bar(open_=90.0, high=97.0, low=88.0, close=96.0)
        assert fill_price(order, recovering) == 94.0

    def test_a_triggered_stop_limit_is_a_plain_limit_from_then_on(self):
        order = Order(
            side='sell', order_type='stop_limit', qty=1, stop_price=95.0, limit_price=94.0
        )
        book = OrderBook()
        book.submit(order)
        book.arm_triggered(_bar(open_=90.0, high=92.0, low=85.0, close=91.0))
        assert order.triggered
        assert not order.is_stop
        # A later bar that trades back up through the limit fills it there, and
        # the stop at 95 is no longer consulted at all.
        recovered = _bar(open_=90.0, high=96.0, low=89.0, close=95.0)
        assert fill_price(order, recovered) == 94.0


class TestOrderValidation:
    @pytest.mark.parametrize('kind', ORDER_TYPES)
    def test_every_declared_order_type_is_constructible(self, kind):
        order = Order(side='buy', order_type=kind, qty=1, limit_price=10.0, stop_price=10.0)
        assert order.order_type == kind

    def test_a_limit_order_without_a_limit_price_is_refused(self):
        with pytest.raises(OrderError):
            Order(side='buy', order_type='limit', qty=1)

    def test_a_stop_order_without_a_stop_price_is_refused(self):
        with pytest.raises(OrderError):
            Order(side='sell', order_type='stop', qty=1)

    def test_unknown_side_type_and_tif_are_all_refused(self):
        with pytest.raises(OrderError):
            Order(side='short', order_type='market')
        with pytest.raises(OrderError):
            Order(side='buy', order_type='iceberg')
        with pytest.raises(OrderError):
            Order(side='buy', order_type='market', tif='fok')

    def test_market_orders_cannot_rest(self):
        with pytest.raises(OrderError):
            OrderBook().submit(Order(side='buy', order_type='market', qty=1))


# --------------------------------------------------------------------------- #
# Priority when a bar touches more than one order (3.7.3)
# --------------------------------------------------------------------------- #

class TestMultiTouchPriority:
    def test_a_bar_touching_both_bracket_legs_ranks_the_stop_first(self):
        """Ambiguous bars are scored against the position, on purpose."""
        book = OrderBook()
        for leg in bracket_orders('sell', stop_price=95.0, target_price=108.0,
                                  group='g', created_bar=0):
            book.submit(leg)
        ranked = book.candidates(_bar())
        assert [o.reason for o, _ in ranked] == ['bracket_stop', 'bracket_target']

    def test_an_order_marketable_at_the_open_outranks_a_nearer_one(self):
        book = OrderBook()
        far_but_at_open = book.submit(
            Order(side='sell', order_type='limit', limit_price=99.0, qty=1)
        )
        near_intrabar = book.submit(
            Order(side='sell', order_type='stop', stop_price=99.5, qty=1)
        )
        # Opens at 100: the limit at 99 is already marketable, the stop at 99.5
        # is only reached later in the bar.
        ranked = book.candidates(_bar(open_=100.0, high=101.0, low=98.0, close=100.5))
        assert ranked[0][0] is far_but_at_open
        assert ranked[1][0] is near_intrabar

    def test_ties_break_on_submission_order_so_runs_are_reproducible(self):
        book = OrderBook()
        first = book.submit(Order(side='sell', order_type='limit', limit_price=108.0, qty=1))
        second = book.submit(Order(side='sell', order_type='limit', limit_price=108.0, qty=1))
        assert [o for o, _ in book.candidates(_bar())] == [first, second]

    def test_filling_one_leg_cancels_the_other(self):
        book = OrderBook()
        stop, target = bracket_orders('sell', 95.0, 108.0, 'g', 0)
        book.submit(stop)
        book.submit(target)
        book.fill(stop, _bar(), qty=10, price=95.0)
        assert book.is_empty
        assert [why for _, why in book.cancelled] == ['oco', 'filled']


# --------------------------------------------------------------------------- #
# Time in force (3.7.4)
# --------------------------------------------------------------------------- #

class TestTimeInForce:
    def _rest(self, tif, expire_bars=None):
        book = OrderBook()
        book.submit(Order(
            side='buy', order_type='limit', qty=1, limit_price=1.0, tif=tif,
            expire_bars=expire_bars, created_bar=0, created_session=0,
        ))
        return book

    def test_an_order_is_never_killed_on_the_bar_that_placed_it(self):
        book = self._rest('ioc')
        book.expire(_bar(index=0))
        assert len(book) == 1

    def test_ioc_gets_exactly_one_bar_of_range(self):
        book = self._rest('ioc')
        book.expire(_bar(index=1))
        assert len(book) == 1, 'the first workable bar must not be skipped'
        book.expire(_bar(index=2))
        assert book.is_empty

    def test_gtc_survives_indefinitely(self):
        book = self._rest('gtc')
        for i in range(1, 50):
            book.expire(_bar(index=i))
        assert len(book) == 1

    def test_day_dies_at_the_next_session_boundary(self):
        book = self._rest('day')
        book.expire(_bar(index=1, session=3))   # first workable bar, session 3
        book.expire(_bar(index=2, session=3))   # same session, still working
        assert len(book) == 1
        book.expire(_bar(index=3, session=4))
        assert book.is_empty

    def test_expire_bars_caps_a_gtc_order(self):
        book = self._rest('gtc', expire_bars=2)
        book.expire(_bar(index=1))
        book.expire(_bar(index=2))
        assert len(book) == 1
        book.expire(_bar(index=3))
        assert book.is_empty


class TestFillLedgerFrame:
    def test_an_empty_fill_ledger_still_has_its_columns(self):
        frame = fills_to_frame([])
        assert list(frame.columns) == [
            'order_id', 'bar', 'date', 'side', 'qty', 'price', 'order_type', 'reason', 'group',
        ]
        assert frame.empty


# --------------------------------------------------------------------------- #
# Engine wiring
# --------------------------------------------------------------------------- #

def _tape(n=200, seed=4242):
    """A tape with real intrabar range, so limits and stops have something to hit."""
    rng = np.random.default_rng(seed)
    close = 100.0 * np.exp(np.cumsum(rng.standard_normal(n) * 0.015))
    open_ = close * (1 + rng.standard_normal(n) * 0.004)
    # High and Low must bracket both Open and Close or the tape is not a tape:
    # a fill at the Open would sit outside the bar's own range.
    high = np.maximum(open_, close) * (1 + np.abs(rng.standard_normal(n)) * 0.010)
    low = np.minimum(open_, close) * (1 - np.abs(rng.standard_normal(n)) * 0.010)
    return pd.DataFrame(
        {
            'Open': open_,
            'High': high,
            'Low': low,
            'Close': close,
            'Volume': np.full(n, 1_000_000),
            'RSI_Oversold_Buy': (rng.random(n) > 0.85).astype(int),
            'RSI_Overbought_Sell': (rng.random(n) > 0.88).astype(int),
        },
        index=pd.date_range('2021-01-01', periods=n, freq='B'),
    )


def _run(frame=None, **kwargs):
    return backtest(
        df=_tape() if frame is None else frame,
        initial_capital=25_000.0,
        position_sizing_strategy='percentage_of_portfolio',
        position_sizing_params={'percent': 0.35},
        buy_indicators=['RSI_Oversold_Buy'],
        sell_indicators=['RSI_Overbought_Sell'],
        **{
            'min_holding_period': 3,
            'trailing_stop_loss': 0.07,
            'take_profit': 0.12,
            'commission_per_trade': 0.001,
            **kwargs,
        },
    )


CONFIGURATIONS = {
    'market': {},
    'limit': dict(order_type='limit', limit_offset_pct=0.005),
    'stop': dict(order_type='stop', stop_offset_pct=0.005),
    'stop_limit': dict(order_type='stop_limit', stop_offset_pct=0.005, limit_offset_pct=0.003),
    'ioc': dict(order_type='limit', limit_offset_pct=0.005, time_in_force='ioc'),
    'day': dict(order_type='limit', limit_offset_pct=0.005, time_in_force='day'),
    'expiry': dict(order_type='limit', limit_offset_pct=0.005, order_expiry_bars=3),
    'trailing_orders': dict(trailing_stop_orders=True),
    'brackets': dict(use_brackets=True, bracket_stop_pct=0.05, bracket_target_pct=0.10),
    'brackets_trailing': dict(
        use_brackets=True, bracket_stop_pct=0.05, bracket_target_pct=0.10,
        trailing_stop_orders=True,
    ),
    'limit_brackets': dict(
        order_type='limit', limit_offset_pct=0.004, use_brackets=True,
        bracket_stop_pct=0.05, bracket_target_pct=0.10,
    ),
}


class TestMarketIsUnchanged:
    def test_the_default_is_market_and_records_it(self):
        result = _run()
        assert result.attrs['order_type'] == 'market'
        assert result.attrs['use_brackets'] is False
        assert result.attrs['trailing_stop_orders'] is False

    def test_every_market_fill_lands_on_a_bar_close(self):
        result = _run()
        fills = result.attrs['fills']
        assert not fills.empty
        bars = fills['bar'].to_numpy()
        closes = result['Close'].to_numpy(dtype=float)[bars]
        opens = result['Open'].to_numpy(dtype=float)[bars]
        price = fills['price'].to_numpy(dtype=float)
        # Every market fill is a bar close, with one documented exception: a
        # trailing stop the market reopened through fills at the Open (3.9.4).
        assert (np.isclose(price, closes) | np.isclose(price, opens)).all()
        assert set(fills['order_type']) == {'market'}

    def test_the_fill_ledger_agrees_with_the_per_bar_quantities(self):
        result = _run()
        fills = result.attrs['fills']
        bought = fills[fills['side'] == 'buy']['qty'].sum()
        sold = fills[fills['side'] == 'sell']['qty'].sum()
        assert bought == pytest.approx(result['Units_to_buy'].sum())
        assert sold == pytest.approx(result['Units_to_sell'].sum())

    def test_asking_for_an_order_type_the_engine_does_not_have_is_refused(self):
        from lib.strategy import ValidationError

        with pytest.raises(ValidationError):
            _run(order_type='iceberg')


class TestRestingOrdersReachThePosition:
    @pytest.mark.parametrize('kind', ['limit', 'stop', 'stop_limit'])
    def test_a_resting_entry_does_not_fill_at_the_signal_bar_close(self, kind):
        """If it filled at the close it would be a market order wearing a hat."""
        result = _run(**CONFIGURATIONS[kind])
        fills = result.attrs['fills']
        entries = fills[(fills['side'] == 'buy') & (fills['order_type'] == kind)]
        assert not entries.empty
        closes = result['Close'].to_numpy(dtype=float)
        at_close = np.isclose(entries['price'].to_numpy(dtype=float), closes[entries['bar'].to_numpy()])
        assert not at_close.all()

    def test_a_limit_buy_never_pays_more_than_its_limit(self):
        result = _run(**CONFIGURATIONS['limit'])
        fills = result.attrs['fills']
        entries = fills[(fills['side'] == 'buy') & (fills['order_type'] == 'limit')]
        closes = result['Close'].to_numpy(dtype=float)
        signal_closes = closes[entries['bar'].to_numpy() - 1]
        # The order rested 50 bps below the *previous* close at worst; it can
        # only ever have filled at or below that.
        assert (entries['price'].to_numpy(dtype=float) <= signal_closes * (1 - 0.005) + 1e-9).all()

    def test_every_fill_price_sits_inside_its_own_bar_range(self):
        for name, config in CONFIGURATIONS.items():
            result = _run(**config)
            fills = result.attrs['fills']
            if fills.empty:
                continue
            bars = fills['bar'].to_numpy()
            low = result['Low'].to_numpy(dtype=float)[bars]
            high = result['High'].to_numpy(dtype=float)[bars]
            price = fills['price'].to_numpy(dtype=float)
            assert (price >= low - 1e-9).all(), name
            assert (price <= high + 1e-9).all(), name

    def test_ioc_and_day_fill_less_often_than_gtc(self):
        gtc = len(_run(**CONFIGURATIONS['limit']).attrs['fills'])
        for tif in ('ioc', 'day'):
            assert len(_run(**CONFIGURATIONS[tif]).attrs['fills']) < gtc

    def test_a_bar_expiry_cap_sits_between_ioc_and_gtc(self):
        counts = {
            name: len(_run(**CONFIGURATIONS[name]).attrs['fills'])
            for name in ('ioc', 'expiry', 'limit')
        }
        assert counts['ioc'] <= counts['expiry'] <= counts['limit']


class TestTrailingStopAsARestingOrder:
    def test_it_is_recorded_and_still_exits_on_the_stop_reason(self):
        result = _run(**CONFIGURATIONS['trailing_orders'])
        assert result.attrs['trailing_stop_orders'] is True
        trades = result.attrs['trades']
        stops = trades[trades['exit_reason'] == 'trailing_stop']
        assert not stops.empty
        assert set(stops['exit_order_type']) == {'stop'}

    def test_a_stop_order_exit_never_fills_above_the_level_it_was_working_at(self):
        """A stop fills at the stop, or worse on a gap — never better."""
        result = _run(**CONFIGURATIONS['trailing_orders'])
        fills = result.attrs['fills']
        stops = fills[fills['reason'] == 'trailing_stop']
        assert not stops.empty
        trail = result['Trailing_Stop'].to_numpy(dtype=float)
        # The level the order was working at is the one written on the bar
        # before it filled; sync_exit_orders runs at the end of each bar.
        working = trail[stops['bar'].to_numpy() - 1]
        assert (stops['price'].to_numpy(dtype=float) <= working + 1e-9).all()

    def test_it_is_stricter_than_the_close_only_check_it_replaces(self):
        """Testing against Low instead of Close can only trip more often."""
        as_orders = _run(**CONFIGURATIONS['trailing_orders']).attrs['trades']
        default = _run().attrs['trades']
        stops = lambda t: int((t['exit_reason'] == 'trailing_stop').sum())  # noqa: E731
        assert stops(as_orders) >= stops(default)

    def test_a_short_time_in_force_never_expires_the_protective_stop(self):
        """A stop that goes away overnight is not a stop.

        ``time_in_force`` is about how patient an entry is. Letting it expire the
        exit orders too would leave the position naked on the bar after every
        expiry, because the exits can only be re-posted once a bar has been
        worked — so exits are pinned to GTC and this must not change with tif.
        """
        gtc = _run(trailing_stop_orders=True, time_in_force='gtc').attrs['trades']
        ioc = _run(trailing_stop_orders=True, time_in_force='ioc').attrs['trades']
        stops = lambda t: int((t['exit_reason'] == 'trailing_stop').sum())  # noqa: E731
        assert stops(ioc) == stops(gtc)

    def test_accumulation_mode_refuses_exit_orders_rather_than_pretending(self):
        result = _run(strategy_mode='accumulation', trailing_stop_orders=True, use_brackets=True)
        assert result.attrs['trailing_stop_orders'] is False
        assert result.attrs['use_brackets'] is False


class TestBrackets:
    def test_both_legs_appear_in_the_ledger_with_their_own_reasons(self):
        trades = _run(**CONFIGURATIONS['brackets']).attrs['trades']
        reasons = set(trades['exit_reason'])
        assert 'bracket_stop' in reasons
        assert 'bracket_target' in reasons

    def test_a_bracket_target_exit_is_a_limit_and_a_bracket_stop_is_a_stop(self):
        trades = _run(**CONFIGURATIONS['brackets']).attrs['trades']
        for reason, expected in (('bracket_stop', 'stop'), ('bracket_target', 'limit')):
            rows = trades[trades['exit_reason'] == reason]
            if not rows.empty:
                assert set(rows['exit_order_type']) == {expected}

    def test_only_one_leg_of_a_group_ever_fills(self):
        fills = _run(**CONFIGURATIONS['brackets']).attrs['fills']
        legs = fills[fills['group'].notna()]
        assert not legs.empty
        assert legs['group'].value_counts().max() == 1

    def test_a_working_bracket_suppresses_the_builtin_stop_and_take_profit(self):
        trades = _run(**CONFIGURATIONS['brackets']).attrs['trades']
        assert 'trailing_stop' not in set(trades['exit_reason'])
        assert 'take_profit' not in set(trades['exit_reason'])

    def test_a_bracket_with_no_legs_at_all_turns_itself_off(self):
        result = _run(
            use_brackets=True, bracket_stop_pct=0.0, bracket_target_pct=0.0,
            trailing_stop_loss=0.0, take_profit=0.0,
        )
        assert result.attrs['use_brackets'] is False

    def test_bracket_legs_default_to_the_trailing_stop_and_take_profit_distances(self):
        """Turning brackets on without sizing them must not silently drop the exits."""
        explicit = _run(use_brackets=True, bracket_stop_pct=0.07, bracket_target_pct=0.12)
        implied = _run(use_brackets=True)
        pd.testing.assert_frame_equal(
            explicit.attrs['trades'], implied.attrs['trades'], check_like=True
        )

    def test_trailing_ratchets_the_protective_leg_without_loosening_it(self):
        plain = _run(**CONFIGURATIONS['brackets']).attrs['trades']
        trailed = _run(**CONFIGURATIONS['brackets_trailing']).attrs['trades']
        count = lambda t: int((t['exit_reason'] == 'bracket_stop').sum())  # noqa: E731
        assert count(trailed) >= count(plain)


class TestLedgerAndReconciliation:
    @pytest.mark.parametrize('name', sorted(CONFIGURATIONS))
    def test_the_ledger_reconciles_with_the_equity_curve(self, name):
        """The invariant every order-model bug breaks first."""
        result = _run(**CONFIGURATIONS[name])
        trades = result.attrs['trades']
        equity_change = result['Portfolio_Value'].iloc[-1] - result['Portfolio_Value'].iloc[0]
        assert trades['net_pnl'].sum() == pytest.approx(equity_change, abs=1e-6)

    @pytest.mark.parametrize('name', sorted(CONFIGURATIONS))
    def test_cash_never_goes_negative(self, name):
        assert (_run(**CONFIGURATIONS[name])['Cash_Value'] >= -1e-6).all()

    @pytest.mark.parametrize('name', sorted(CONFIGURATIONS))
    def test_units_never_go_negative(self, name):
        assert (_run(**CONFIGURATIONS[name])['Units'] >= -1e-9).all()

    @pytest.mark.parametrize('name', sorted(CONFIGURATIONS))
    def test_every_run_is_repeatable(self, name):
        first = _run(**CONFIGURATIONS[name])
        second = _run(**CONFIGURATIONS[name])
        pd.testing.assert_frame_equal(first, second)

    @pytest.mark.parametrize('name', sorted(CONFIGURATIONS))
    def test_the_ledger_names_the_order_type_on_both_sides(self, name):
        trades = _run(**CONFIGURATIONS[name]).attrs['trades']
        assert 'entry_order_type' in trades.columns
        assert 'exit_order_type' in trades.columns
        assert set(trades['entry_order_type']) <= set(ORDER_TYPES)
        # 'none' is the marked-to-market open position: nothing executed it.
        assert set(trades['exit_order_type']) <= set(ORDER_TYPES) | {'none'}

    def test_a_frame_without_high_and_low_still_runs(self):
        """Degrade to the open-to-close span rather than raising mid-backtest."""
        frame = _tape().drop(columns=['High', 'Low'])
        result = _run(frame=frame, order_type='limit', limit_offset_pct=0.005)
        assert len(result) == len(frame)

