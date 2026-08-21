"""Session model, session-anchored resampling, and overnight gap fills (3.9)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.sessions import (
    bars_per_session,
    resolve_session_starts,
    session_ids,
    session_starts,
)
from lib.strategy import backtest
from lib.timeframes import BARS_PER_SESSION, resample_ohlcv


# --------------------------------------------------------------------------- #
# Tapes
# --------------------------------------------------------------------------- #

_US_DAYS = ('2024-01-02', '2024-01-03', '2024-01-04')


def _us_hourly_index(days=_US_DAYS, bars_per_day: int = 7) -> pd.DatetimeIndex:
    """Yahoo's 1h US regular session: 09:30 ... 15:30, seven bars."""
    stamps: list[pd.Timestamp] = []
    for day in days:
        stamps += list(pd.date_range(f'{day} 09:30', periods=bars_per_day, freq='1h'))
    return pd.DatetimeIndex(stamps)


def _ohlcv(index: pd.DatetimeIndex) -> pd.DataFrame:
    step = np.arange(len(index), dtype=float)
    return pd.DataFrame(
        {
            'Open': 100.0 + step,
            'High': 101.0 + step,
            'Low': 99.0 + step,
            'Close': 100.5 + step,
            'Volume': 10,
        },
        index=index,
    )


# --------------------------------------------------------------------------- #
# 3.9.3 - where the boundaries are
# --------------------------------------------------------------------------- #

class TestSessionDetection:
    def test_an_hourly_tape_starts_a_session_each_morning(self):
        starts = session_starts(_us_hourly_index())
        assert list(np.flatnonzero(starts)) == [0, 7, 14]

    def test_every_bar_of_a_daily_tape_opens_a_session(self):
        """A daily bar's open is always separated from the last close by a gap."""
        starts = session_starts(pd.date_range('2024-01-01', periods=10, freq='B'))
        assert starts.all()

    def test_a_lunch_break_stays_inside_its_session(self):
        """Tokyo breaks 11:30-12:30. That is 1.5 bars, not a new session."""
        index = pd.DatetimeIndex([
            pd.Timestamp(f'{day} {clock}')
            for day in ('2024-01-04', '2024-01-05')
            for clock in ('09:00', '10:00', '11:00', '12:30', '13:30', '14:30')
        ])
        assert list(np.flatnonzero(session_starts(index))) == [0, 6]

    def test_a_four_hour_tape_is_not_fooled_by_its_own_bar_count(self):
        """Two bars a session means half the steps are overnight ones.

        Reading the spacing as the *mode* would tie here; the 25th percentile
        picks the intraday step, which is what makes this tape work.
        """
        index = pd.DatetimeIndex([
            pd.Timestamp(f'{day} {clock}')
            for day in _US_DAYS
            for clock in ('09:30', '13:30')
        ])
        assert list(np.flatnonzero(session_starts(index))) == [0, 2, 4]

    def test_an_index_with_no_time_information_is_one_session(self):
        """Degrade to the pre-3.9 positional behaviour, not to a break per bar."""
        starts = session_starts(pd.RangeIndex(5))
        assert list(np.flatnonzero(starts)) == [0]

    def test_an_empty_index_has_no_sessions(self):
        assert session_starts(pd.DatetimeIndex([])).size == 0
        assert session_ids(pd.DatetimeIndex([])).size == 0

    def test_session_ids_number_the_sessions_in_order(self):
        ids = session_ids(_us_hourly_index())
        assert list(ids[:8]) == [0] * 7 + [1]
        assert ids[-1] == 2

    def test_an_explicit_column_overrides_the_inference(self):
        """A caller with a real exchange calendar gets the last word."""
        df = _ohlcv(_us_hourly_index())
        df['Session_Start'] = False
        df.iloc[3, df.columns.get_loc('Session_Start')] = True
        starts = resolve_session_starts(df)
        # Bar 0 is forced on regardless: the tape has to begin somewhere.
        assert list(np.flatnonzero(starts)) == [0, 3]


# --------------------------------------------------------------------------- #
# 3.9.2 - the annualisation factor against the real bar count
# --------------------------------------------------------------------------- #

class TestBarsPerSession:
    def test_an_hourly_us_tape_emits_the_documented_bar_count(self):
        """1638 assumed 6.5 bars a session. Yahoo sends seven."""
        index = _us_hourly_index(days=_US_DAYS + ('2024-01-05', '2024-01-08'))
        assert bars_per_session(index) == BARS_PER_SESSION['1h']

    def test_the_four_hour_resample_emits_the_documented_bar_count(self):
        index = _us_hourly_index(days=_US_DAYS + ('2024-01-05', '2024-01-08'))
        resampled = resample_ohlcv(_ohlcv(index), '4h')
        assert bars_per_session(resampled.index) == BARS_PER_SESSION['4h']


# --------------------------------------------------------------------------- #
# 3.9.1 - session-anchored resampling
# --------------------------------------------------------------------------- #

class TestSessionAnchoredResample:
    def test_buckets_are_labelled_with_a_real_bar_not_a_wall_clock_boundary(self):
        out = resample_ohlcv(_ohlcv(_us_hourly_index()), '4h')
        assert [str(t.time()) for t in out.index[:2]] == ['09:30:00', '13:30:00']

    def test_the_session_open_and_close_survive_the_bucketing(self):
        df = _ohlcv(_us_hourly_index())
        out = resample_ohlcv(df, '4h')
        first_day = out.loc['2024-01-02']
        assert first_day['Open'].iloc[0] == df['Open'].iloc[0]
        assert first_day['Close'].iloc[-1] == df['Close'].iloc[6]

    def test_no_bucket_holds_bars_from_two_sessions(self):
        """The bug: a wall-clock bucket straddling the overnight boundary.

        An overnight futures session (18:00 -> 16:00) puts the previous
        session's close and the next session's open in the same 16:00 bucket.
        """
        stamps: list[pd.Timestamp] = []
        for evening, morning in (
            ('2024-01-02', '2024-01-03'), ('2024-01-03', '2024-01-04')
        ):
            stamps += list(pd.date_range(f'{evening} 18:00', periods=6, freq='1h'))
            stamps += list(pd.date_range(f'{morning} 00:00', periods=17, freq='1h'))
        df = _ohlcv(pd.DatetimeIndex(stamps))
        ids = session_ids(df.index)

        def sessions_per_bucket(labels):
            """How many distinct sessions each output bar drew its bars from."""
            edges = list(labels) + [df.index[-1] + pd.Timedelta('1h')]
            return [
                len(set(ids[(df.index >= lo) & (df.index < hi)]))
                for lo, hi in zip(edges, edges[1:])
            ]

        anchored = resample_ohlcv(df, '4h')
        wall = resample_ohlcv(df, '4h', session_anchored=False)
        assert max(sessions_per_bucket(anchored.index)) == 1
        assert max(sessions_per_bucket(wall.index)) == 2

    def test_a_gapless_tape_matches_the_wall_clock_result(self):
        """One continuous session anchored at a clock boundary: nothing moves."""
        index = pd.date_range('2024-01-02 08:00', periods=8, freq='1h')
        df = _ohlcv(index)
        pd.testing.assert_frame_equal(
            resample_ohlcv(df, '4h'),
            resample_ohlcv(df, '4h', session_anchored=False),
            check_freq=False,  # only the anchored path infers a freq
        )


# --------------------------------------------------------------------------- #
# 3.9.4 / 3.9.5 - the engine
# --------------------------------------------------------------------------- #

def _gap_frame(day_two_open: float, day_two_close: float) -> pd.DataFrame:
    """A flat session, then a session that reopens somewhere else.

    The buy prints on bar 0 and fills at bar 1's close (delay=1), so the stop
    is armed and ratcheted well before the gap.
    """
    index = _us_hourly_index(days=('2024-01-02', '2024-01-03'))
    close = [100.0] * 7 + [day_two_close] * 7
    open_ = [100.0] * 7 + [day_two_open] + [day_two_close] * 6
    return pd.DataFrame(
        {
            'Open': open_,
            'High': [max(o, c) for o, c in zip(open_, close)],
            'Low': [min(o, c) for o, c in zip(open_, close)],
            'Close': close,
            'Volume': 10,
            'RSI_Oversold_Buy': [1] + [0] * 13,
            'RSI_Overbought_Sell': [0] * 14,
        },
        index=index,
    )


def _run(df: pd.DataFrame, **kwargs) -> pd.DataFrame:
    return backtest(
        df=df,
        initial_capital=10_000.0,
        position_sizing_strategy='percentage_of_portfolio',
        position_sizing_params={'percent': 1.0},
        buy_indicators=['RSI_Oversold_Buy'],
        sell_indicators=['RSI_Overbought_Sell'],
        trailing_stop_loss=0.05,
        commission_per_trade=0.0,
        slippage_pct=0.0,
        fx_fee_pct=0.0,
        allow_fractional=True,
        **kwargs,
    )


class TestOvernightGapFills:
    def test_a_gap_down_through_the_stop_fills_at_the_open(self):
        """The stop sits at 95. The market reopens at 80 and recovers to 90."""
        trades = _run(_gap_frame(day_two_open=80.0, day_two_close=90.0)).attrs['trades']
        assert list(trades['exit_reason']) == ['trailing_stop']
        assert trades['exit_price'].iloc[0] == pytest.approx(80.0)

    def test_turning_gap_fills_off_restores_the_close_fill(self):
        trades = _run(
            _gap_frame(day_two_open=80.0, day_two_close=90.0), gap_fills=False
        ).attrs['trades']
        assert trades['exit_price'].iloc[0] == pytest.approx(90.0)

    def test_a_reopen_above_the_stop_is_not_a_gap_exit(self):
        """96 is above the 95 stop, so the position survives the boundary."""
        result = _run(_gap_frame(day_two_open=96.0, day_two_close=97.0))
        assert list(result.attrs['trades']['exit_reason']) == ['open']

    def test_an_intrabar_dip_below_the_stop_is_not_a_gap(self):
        """The same shape mid-session. Only a session's first bar can gap."""
        df = _gap_frame(day_two_open=100.0, day_two_close=100.0)
        df.iloc[4, df.columns.get_loc('Open')] = 80.0
        df.iloc[4, df.columns.get_loc('Low')] = 80.0
        assert list(_run(df).attrs['trades']['exit_reason']) == ['open']

    def test_a_frame_without_an_open_column_still_runs(self):
        df = _gap_frame(day_two_open=80.0, day_two_close=90.0).drop(columns=['Open'])
        trades = _run(df).attrs['trades']
        assert trades['exit_price'].iloc[0] == pytest.approx(90.0)


class TestHoldingSessions:
    def test_the_result_frame_states_where_the_sessions_were(self):
        result = _run(_gap_frame(day_two_open=96.0, day_two_close=97.0))
        assert list(np.flatnonzero(result['Session_Start'].to_numpy())) == [0, 7]

    def test_a_trade_held_overnight_reports_the_boundary_it_crossed(self):
        row = _run(
            _gap_frame(day_two_open=80.0, day_two_close=90.0)
        ).attrs['trades'].iloc[0]
        assert row['holding_bars'] == 6      # six 1h bars of tape
        assert row['holding_sessions'] == 1  # ...spanning one overnight break

    def test_a_trade_closed_inside_its_session_crosses_nothing(self):
        df = _gap_frame(day_two_open=100.0, day_two_close=100.0)
        df.iloc[3, df.columns.get_loc('RSI_Overbought_Sell')] = 1
        row = _run(df).attrs['trades'].iloc[0]
        assert row['exit_reason'] == 'signal'
        assert row['holding_sessions'] == 0

    def test_holding_sessions_is_zero_while_flat(self):
        result = _run(_gap_frame(day_two_open=96.0, day_two_close=97.0))
        assert result['Holding_Sessions'].iloc[0] == 0

    def test_the_metrics_engine_reports_the_session_average(self):
        from lib.metrics import compute_metrics

        result = _run(_gap_frame(day_two_open=80.0, day_two_close=90.0))
        assert compute_metrics(result, interval='1h').avg_holding_sessions == 1.0
