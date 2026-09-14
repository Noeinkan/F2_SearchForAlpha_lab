"""Multi-symbol engine: per-symbol state, one account, phase-major bars (3.8.3 / 3.8.4).

The rules under test are decided in docs/portfolio-semantics.md; each test
names the section it holds the engine to.
"""

from __future__ import annotations

import itertools

import numpy as np
import pandas as pd
import pytest

from lib.engine.allocation import water_fill
from lib.metrics import compute_metrics
from lib.panel import MARK_COLUMN, TRADABLE_COLUMN, align_panel
from lib.portfolio import backtest_portfolio, equal_weight_benchmark
from lib.strategy import BacktestError, ValidationError, backtest


def _whole(value: float) -> float:
    return float(int(value)) if value > 0 else 0.0


def _fractional(value: float) -> float:
    return float(value) if value > 0 else 0.0


# --------------------------------------------------------------------------- #
# Tapes
# --------------------------------------------------------------------------- #

def _flat(price: float, days: int = 6, buy_on=(), sell_on=(), atr=None,
          start: str = '2024-01-01') -> pd.DataFrame:
    """A constant-price daily tape with signals on the listed bars."""
    index = pd.date_range(start, periods=days, freq='B')
    buy = np.zeros(days, dtype=int)
    sell = np.zeros(days, dtype=int)
    buy[list(buy_on)] = 1
    sell[list(sell_on)] = 1
    frame = pd.DataFrame(
        {
            'Open': price, 'High': price, 'Low': price, 'Close': price,
            'Volume': 1_000,
            'X_Buy': buy, 'X_Sell': sell,
        },
        index=index,
    )
    if atr is not None:
        frame['ATR'] = atr
    return frame


def _walk(seed: int, days: int = 250) -> pd.DataFrame:
    rng = np.random.default_rng(seed)
    index = pd.date_range('2021-01-01', periods=days, freq='B')
    close = 100 * np.exp(np.cumsum(rng.standard_normal(days) * 0.02))
    opn = close * (1 + rng.standard_normal(days) * 0.01)
    return pd.DataFrame(
        {
            'Open': opn,
            'High': np.maximum(opn, close) * (1 + rng.random(days) * 0.02),
            'Low': np.minimum(opn, close) * (1 - rng.random(days) * 0.02),
            'Close': close,
            'Volume': 1_000,
            'X_Buy': (rng.random(days) > 0.8).astype(int),
            'X_Sell': (rng.random(days) > 0.85).astype(int),
        },
        index=index,
    )


_NO_COSTS = dict(commission_per_trade=0.0, slippage_pct=0.0, fx_fee_pct=0.0)


def _run(panel, capital=10_000.0, sizer='percentage_of_portfolio',
         params=None, **options):
    return backtest_portfolio(
        panel, capital, sizer, params if params is not None else {'percent': 1.0},
        ['X_Buy'], ['X_Sell'], **options,
    )


# --------------------------------------------------------------------------- #
# §4 — CASH_ALLOCATION_RULE, in isolation
# --------------------------------------------------------------------------- #

_DOC_COSTS = (50 * 1.0005 * 1.0015, 200 * 1.0005 * 1.0015, 350 * 1.0005 * 1.0015)


class TestWaterFill:
    def test_the_worked_example_in_the_semantics_doc(self):
        requests = list(zip((20, 40, 30), _DOC_COSTS))
        assert water_fill(10_000.0, requests, _whole) == [20, 22, 12]

    def test_the_answer_ignores_the_order_of_the_requests(self):
        requests = list(zip((20, 40, 30), _DOC_COSTS))
        expected = dict(zip('ABC', water_fill(10_000.0, requests, _whole)))
        for perm in itertools.permutations(range(3)):
            granted = water_fill(10_000.0, [requests[k] for k in perm], _whole)
            assert {'ABC'[k]: units for k, units in zip(perm, granted)} == expected

    def test_one_request_is_the_single_symbol_affordability_clamp(self):
        for cash, wanted, cost in [(10_000, 50, 199.9), (10_000, 500, 199.9), (0.0, 5, 10.0)]:
            assert water_fill(cash, [(wanted, cost)], _whole) == [
                min(wanted, _whole(cash / cost))
            ]

    def test_a_satisfied_request_releases_its_unused_share(self):
        # A needs 1,000 of a 5,000 share; B takes the other 9,000.
        assert water_fill(10_000.0, [(10, 100.0), (1_000, 10.0)], _whole) == [10, 900]

    def test_everyone_satisfied_leaves_the_rest_in_cash(self):
        assert water_fill(10_000.0, [(10, 100.0), (20, 100.0)], _whole) == [10, 20]

    def test_fractional_units_split_exactly(self):
        granted = water_fill(1_000.0, [(100.0, 10.0), (100.0, 40.0)], _fractional)
        assert granted == pytest.approx([50.0, 12.5])

    def test_empty_and_zero_requests_get_nothing(self):
        assert water_fill(1_000.0, [], _whole) == []
        assert water_fill(1_000.0, [(0, 10.0), (5, 0.0), (5, 10.0)], _whole) == [0, 0, 5]


# --------------------------------------------------------------------------- #
# §8 — the one-symbol case is today's engine, bit for bit
# --------------------------------------------------------------------------- #

_CONFIGS = [
    dict(),
    dict(order_type='limit', use_brackets=True, bracket_target_pct=0.06, take_profit=0.05),
    dict(order_type='stop_limit', trailing_stop_orders=True, time_in_force='day'),
    dict(strategy_mode='accumulation', amount_per_buy=1_500, allow_fractional=True),
    dict(strategy_mode='rebalancing', position_size_pct=40, consecutive_signal_mode='cooldown',
         cooldown_bars=2),
    dict(use_low_for_stops=True, min_holding_period=3, position_scaling=0.5),
]


class TestOneSymbolBasket:
    @pytest.mark.parametrize('options', _CONFIGS)
    def test_a_basket_of_one_reproduces_backtest(self, options):
        df = _walk(7)
        options = {'position_size_pct': 100, **options}
        expected = backtest(
            df, 25_000.0, 'percentage_of_portfolio', {'percent': 0.5},
            ['X_Buy'], ['X_Sell'], **options,
        )
        got = backtest_portfolio(
            align_panel({'ONLY': df}), 25_000.0, 'percentage_of_portfolio',
            {'percent': 0.5}, ['X_Buy'], ['X_Sell'], **options,
        )

        frame = got.frame('ONLY')
        pd.testing.assert_frame_equal(frame[expected.columns], expected, check_exact=True)
        pd.testing.assert_frame_equal(
            frame.attrs['trades'], expected.attrs['trades'], check_exact=True
        )
        pd.testing.assert_frame_equal(
            frame.attrs['fills'].drop(columns='order_id'),
            expected.attrs['fills'].drop(columns='order_id'),
            check_exact=True,
        )
        np.testing.assert_array_equal(
            got.portfolio['Portfolio_Value'].to_numpy(), expected['Portfolio_Value'].to_numpy()
        )
        assert len(expected.attrs['trades']) > 0, "the fixture must actually trade"

    def test_the_one_symbol_benchmark_is_that_symbols_buy_and_hold(self):
        df = _walk(3)
        got = _run(align_panel({'ONLY': df}))
        expected = backtest(df, 10_000.0, 'percentage_of_portfolio', {'percent': 1.0},
                            ['X_Buy'], ['X_Sell'])
        np.testing.assert_allclose(
            got.portfolio['Returns'].to_numpy(), expected['Returns'].to_numpy(),
            rtol=0, atol=1e-12,
        )


# --------------------------------------------------------------------------- #
# §3 / §4 — contention on one bar
# --------------------------------------------------------------------------- #

def _contended_panel(order=('A', 'B', 'C')):
    """The semantics doc's worked example, driven through the engine.

    ``atr_risk_based`` with 1% risk wants ``100 / ATR`` units, so the ATR column
    picks each symbol's request: 20, 40 and 30 units, all signalling on bar 0.
    """
    frames = {
        'A': _flat(50.0, buy_on=[0], atr=5.0),
        'B': _flat(200.0, buy_on=[0], atr=2.5),
        'C': _flat(350.0, buy_on=[0], atr=3.33),
    }
    return align_panel({symbol: frames[symbol] for symbol in order})


_CONTENDED = dict(
    sizer='atr_risk_based', params={'risk_percent': 0.01, 'atr_multiplier': 1.0},
    position_scaling=1.0, commission_per_trade=0.0, slippage_pct=0.0005, fx_fee_pct=0.0015,
)


class TestContention:
    def test_competing_buys_are_water_filled(self):
        result = _run(_contended_panel(), **_CONTENDED)
        units = {s: result.frame(s)['Units'].iloc[1] for s in 'ABC'}
        assert units == {'A': 20, 'B': 22, 'C': 12}
        assert result.portfolio['Cash_Value'].iloc[1] == pytest.approx(380.79, abs=0.01)

    def test_a_starved_buy_is_still_an_accepted_trigger(self):
        result = _run(_contended_panel(), **_CONTENDED)
        for symbol in 'ABC':
            assert result.frame(symbol)['Buy_Trigger_Accepted'].iloc[1]

    @pytest.mark.parametrize('order', list(itertools.permutations('ABC')))
    def test_the_ticker_order_changes_nothing(self, order):
        """Every unit and every balance, to the last bit, whatever the list order."""
        reference = _run(_contended_panel(), **_CONTENDED)
        permuted = _run(_contended_panel(order), **_CONTENDED)

        for column in ('Cash_Value', 'Stocks_Value', 'Portfolio_Value'):
            np.testing.assert_array_equal(
                permuted.portfolio[column].to_numpy(), reference.portfolio[column].to_numpy()
            )
        for symbol in 'ABC':
            np.testing.assert_array_equal(
                permuted.frame(symbol)['Units'].to_numpy(),
                reference.frame(symbol)['Units'].to_numpy(),
            )

    def test_order_independence_holds_on_a_busy_random_basket(self):
        frames = {s: _walk(seed) for s, seed in zip('PQRS', (11, 12, 13, 14))}
        options = dict(order_type='limit', use_brackets=True, take_profit=0.04)

        forward = _run(align_panel(frames), capital=20_000.0,
                       params={'percent': 0.6}, **options)
        backward = _run(align_panel(dict(reversed(list(frames.items())))),
                        capital=20_000.0, params={'percent': 0.6}, **options)

        np.testing.assert_array_equal(
            forward.portfolio['Portfolio_Value'].to_numpy(),
            backward.portfolio['Portfolio_Value'].to_numpy(),
        )
        pd.testing.assert_frame_equal(forward.trades, backward.trades, check_exact=True)
        assert len(forward.trades) > 20, "the fixture must actually contend"


# --------------------------------------------------------------------------- #
# §2 / §3 — sizing base and T+0 funding
# --------------------------------------------------------------------------- #

class TestAccount:
    def test_a_same_bar_sale_funds_a_same_bar_buy(self):
        """A sells everything on bar 3; B's bar-3 buy is paid for with the proceeds."""
        panel = align_panel({
            'A': _flat(100.0, buy_on=[0], sell_on=[2]),
            'B': _flat(100.0, buy_on=[2]),
        })
        result = _run(panel, capital=1_000.0, position_scaling=1.0, **_NO_COSTS)

        assert result.frame('A')['Units'].iloc[1] == 10
        assert result.portfolio['Cash_Value'].iloc[2] == 0.0
        assert result.frame('A')['Units'].iloc[3] == 0
        assert result.frame('B')['Units'].iloc[3] == 10

    def test_orders_are_sized_off_total_portfolio_value(self):
        """B's 30% is 30% of everything — including A's gain — not of cash."""
        a = _flat(100.0, buy_on=[0])
        a.loc[a.index[2:], ['Open', 'High', 'Low', 'Close']] = 200.0
        panel = align_panel({'A': a, 'B': _flat(100.0, buy_on=[2])})

        result = _run(panel, params={'percent': 0.3}, position_scaling=1.0,
                      trailing_stop_loss=0.5, **_NO_COSTS)

        assert result.frame('A')['Units'].iloc[1] == 30
        assert result.portfolio['Portfolio_Value'].iloc[2] == 13_000.0
        assert result.frame('B')['Units'].iloc[3] == 39  # 13,000 x 30% / 100

    def test_the_basket_starts_with_one_pool_of_cash(self):
        panel = align_panel({'A': _flat(100.0), 'B': _flat(50.0)})
        result = _run(panel, capital=5_000.0)
        assert (result.portfolio['Cash_Value'] == 5_000.0).all()
        for symbol in 'AB':
            assert (result.frame(symbol)['Cash_Value'] == 5_000.0).all()

    def test_rebalancing_defaults_to_equal_weight(self):
        """Three symbols, two signalling: the default target is a third each, not 100%."""
        panel = align_panel({
            'A': _flat(100.0, buy_on=[0]), 'B': _flat(50.0, buy_on=[0]), 'C': _flat(10.0),
        })
        default = _run(panel, strategy_mode='rebalancing', **_NO_COSTS)
        explicit = _run(panel, strategy_mode='rebalancing', position_size_pct=100, **_NO_COSTS)

        assert default.frame('A')['Units'].iloc[1] == 33
        assert default.frame('B')['Units'].iloc[1] == 66
        # Asked for 100% each, they contend and split the cash instead.
        assert explicit.frame('A')['Units'].iloc[1] == 50
        assert explicit.frame('B')['Units'].iloc[1] == 100

    def test_the_ledger_reconciles_with_the_equity_curve(self):
        frames = {s: _walk(seed) for s, seed in zip('XYZ', (21, 22, 23))}
        result = _run(align_panel(frames), params={'percent': 0.5})
        equity = result.portfolio['Portfolio_Value']
        assert result.trades['net_pnl'].sum() == pytest.approx(
            equity.iloc[-1] - equity.iloc[0], abs=1e-6
        )


# --------------------------------------------------------------------------- #
# §6 — a symbol with no bar is valued, not traded
# --------------------------------------------------------------------------- #

class TestHoles:
    def test_no_trade_on_a_bar_the_symbol_did_not_print(self):
        b = _flat(100.0, buy_on=[2])
        panel = align_panel({'A': _flat(100.0), 'B': b.drop(index=b.index[3])})

        frame = _run(panel, **_NO_COSTS).frame('B')

        assert not frame[TRADABLE_COLUMN].iloc[3]
        assert (frame['Units'] == 0).all()
        assert not frame['Buy_Trigger_Accepted'].any()

    def test_a_held_position_is_marked_across_the_hole(self):
        b = _flat(100.0, buy_on=[0])
        b.loc[b.index[2], 'Close'] = 120.0
        panel = align_panel({'A': _flat(50.0), 'B': b.drop(index=b.index[3])})

        result = _run(panel, capital=1_000.0, position_scaling=1.0,
                      trailing_stop_loss=0.5, **_NO_COSTS)
        frame = result.frame('B')

        assert frame['Units'].iloc[3] == 10
        assert frame[MARK_COLUMN].iloc[3] == 120.0
        assert frame['Stocks_Value'].iloc[3] == 1_200.0
        assert result.portfolio['Portfolio_Value'].iloc[3] == 1_200.0

    def test_a_symbol_that_has_not_listed_values_at_zero_not_nan(self):
        panel = align_panel({
            'A': _flat(100.0, days=6, buy_on=[0]),
            'LATE': _flat(20.0, days=3, start='2024-01-04', buy_on=[0]),
        })
        result = _run(panel, params={'percent': 0.3}, position_scaling=1.0)
        assert result.portfolio['Portfolio_Value'].notna().all()
        assert result.frame('LATE')['Units'].iloc[-1] > 0

    def test_a_stop_the_symbol_reopened_through_fills_at_the_open(self):
        """Intraday: a halt is not a session boundary, but it is a gap for that name."""
        days = ('2024-01-02', '2024-01-03')
        index = pd.DatetimeIndex([
            stamp for day in days
            for stamp in pd.date_range(f'{day} 09:30', periods=7, freq='1h')
        ])
        n = len(index)
        b = pd.DataFrame(
            {'Open': 100.0, 'High': 100.0, 'Low': 100.0, 'Close': 100.0, 'Volume': 1,
             'X_Buy': [1] + [0] * (n - 1), 'X_Sell': 0},
            index=index,
        )
        b.loc[index[3], ['Open', 'High', 'Low', 'Close']] = [90.0, 101.0, 89.0, 100.0]
        a = b.assign(X_Buy=0)
        panel = align_panel({'A': a, 'B': b.drop(index=index[2])})
        assert not panel.session_start[3]

        result = _run(panel, capital=1_000.0, position_scaling=1.0,
                      trailing_stop_loss=0.05, **_NO_COSTS)
        trade = result.frame('B').attrs['trades'].iloc[0]

        assert trade['exit_reason'] == 'trailing_stop'
        assert trade['exit_bar'] == 3
        assert trade['exit_price'] == 90.0


# --------------------------------------------------------------------------- #
# §7 — the result, and what reads it
# --------------------------------------------------------------------------- #

class TestResult:
    def test_equal_weight_benchmark(self):
        a = _flat(100.0, days=3)
        a.loc[a.index[2], 'Close'] = 200.0
        panel = align_panel({'UP': a, 'FLAT': _flat(40.0, days=3)})

        growth = np.cumprod(1 + equal_weight_benchmark(panel))
        assert growth[-1] == pytest.approx(1.5)

    def test_the_benchmark_buys_a_late_lister_when_it_lists(self):
        late = _flat(10.0, days=3, start='2024-01-04')
        late.loc[late.index[2], 'Close'] = 20.0
        panel = align_panel({'EARLY': _flat(100.0, days=6), 'LATE': late})

        growth = np.cumprod(1 + equal_weight_benchmark(panel))
        assert growth[2] == pytest.approx(1.0)   # LATE's half waited in cash
        assert growth[-1] == pytest.approx(1.5)

    def test_metrics_read_the_portfolio_frame(self):
        frames = {s: _walk(seed) for s, seed in zip('XY', (31, 32))}
        result = _run(align_panel(frames), params={'percent': 0.5})

        metrics = compute_metrics(result.portfolio, 10_000.0)

        closed = int((~result.trades['is_open'].astype(bool)).sum())
        assert metrics.num_trades == closed
        assert np.isfinite(metrics.sharpe)
        assert np.isfinite(metrics.beta)

    def test_combined_ledgers_name_the_symbol(self):
        frames = {s: _walk(seed) for s, seed in zip('XY', (41, 42))}
        result = _run(align_panel(frames), params={'percent': 0.5})

        assert list(result.trades.columns[:2]) == ['symbol', 'entry_bar']
        assert set(result.trades['symbol']) == {'X', 'Y'}
        assert len(result.trades) == sum(
            len(result.frame(s).attrs['trades']) for s in 'XY'
        )
        assert result.fills['bar'].is_monotonic_increasing

    def test_a_dict_of_frames_is_aligned_for_you(self):
        frames = {'A': _flat(100.0, buy_on=[0]), 'B': _flat(50.0)}
        assert _run(frames).symbols == ('A', 'B')


class TestRefusals:
    def test_an_unknown_option_is_refused(self):
        with pytest.raises(ValidationError, match='order_typ'):
            _run(align_panel({'A': _flat(100.0)}), order_typ='limit')

    def test_a_member_missing_a_signal_column_is_named(self):
        panel = align_panel({'A': _flat(100.0), 'B': _flat(50.0).drop(columns='X_Buy')})
        with pytest.raises(ValidationError, match='B:'):
            _run(panel)

    def test_a_bad_mode_is_a_validation_error(self):
        with pytest.raises(ValidationError, match='strategy_mode'):
            _run(align_panel({'A': _flat(100.0)}), strategy_mode='yolo')

    def test_a_panel_that_is_not_a_panel(self):
        with pytest.raises(ValidationError, match='Panel'):
            _run([_flat(100.0)])

    def test_an_unknown_sizer_is_a_backtest_error(self):
        with pytest.raises(BacktestError):
            _run(align_panel({'A': _flat(100.0)}), sizer='astrology')
