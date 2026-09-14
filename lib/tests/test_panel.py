"""Multi-symbol alignment onto a common session-aware index (3.8.2)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from lib.panel import (
    MARK_COLUMN,
    TRADABLE_COLUMN,
    PanelError,
    align_panel,
)
from lib.sessions import session_starts
from lib.strategy import backtest
from lib.timeframes import periods_per_year


# --------------------------------------------------------------------------- #
# Tapes
# --------------------------------------------------------------------------- #

_DAYS = ('2024-01-02', '2024-01-03', '2024-01-04')


def _hourly_index(days=_DAYS, bars_per_day: int = 7) -> pd.DatetimeIndex:
    """Yahoo's 1h US regular session: 09:30 ... 15:30, seven bars."""
    stamps: list[pd.Timestamp] = []
    for day in days:
        stamps += list(pd.date_range(f'{day} 09:30', periods=bars_per_day, freq='1h'))
    return pd.DatetimeIndex(stamps)


def _ohlcv(index: pd.DatetimeIndex, base: float = 100.0) -> pd.DataFrame:
    step = np.arange(len(index), dtype=float)
    return pd.DataFrame(
        {
            'Open': base + step,
            'High': base + 1.0 + step,
            'Low': base - 1.0 + step,
            'Close': base + 0.5 + step,
            'Volume': 10,
            'RSI': 50.0 + step,
            'RSI_Oversold_Buy': ([1] + [0] * (len(index) - 1)),
            'RSI_Overbought_Sell': [0] * len(index),
        },
        index=index,
    )


def _daily(days: int, start: str = '2024-01-01', base: float = 100.0) -> pd.DataFrame:
    return _ohlcv(pd.date_range(start, periods=days, freq='B'), base=base)


# --------------------------------------------------------------------------- #
# The index itself
# --------------------------------------------------------------------------- #

class TestMergedIndex:
    def test_the_panel_index_is_the_union_of_its_members(self):
        """A holiday in one name must not delete the bar for the others."""
        a = _daily(6)
        b = _daily(6).drop(index=_daily(6).index[3])  # B was shut that day

        panel = align_panel({'A': a, 'B': b})

        assert list(panel.index) == list(a.index)
        assert len(panel) == 6

    def test_a_symbol_trading_when_the_others_are_shut_adds_its_bars(self):
        """The weekend-trading member's bars survive; they are not intersected away."""
        equity = _daily(5)                                    # business days only
        crypto = _ohlcv(pd.date_range('2024-01-01', periods=7, freq='D'))

        panel = align_panel({'EQ': equity, 'BTC': crypto})

        assert len(panel) == 7
        weekend = pd.Timestamp('2024-01-06')
        assert panel.tradable.loc[weekend, 'BTC']
        assert not panel.tradable.loc[weekend, 'EQ']

    def test_every_frame_lands_on_the_same_index(self):
        panel = align_panel({'A': _daily(6), 'B': _daily(4), 'C': _daily(6)})
        for symbol in panel.symbols:
            assert panel.frame(symbol).index.equals(panel.index)

    def test_the_ticker_order_changes_nothing_but_the_symbol_tuple(self):
        """§4's commitment: no result may depend on where a ticker sits."""
        a, b = _daily(6), _daily(4, base=50.0)

        forward = align_panel({'A': a, 'B': b})
        reverse = align_panel({'B': b, 'A': a})

        assert forward.symbols == ('A', 'B')
        assert reverse.symbols == ('B', 'A')
        assert forward.index.equals(reverse.index)
        for symbol in ('A', 'B'):
            pd.testing.assert_frame_equal(
                forward.frame(symbol), reverse.frame(symbol)
            )

    def test_unsorted_and_duplicated_input_is_normalised(self):
        df = _daily(5)
        scrambled = pd.concat([df.iloc[[4, 0, 2]], df.iloc[[2]], df.iloc[[1, 3]]])

        panel = align_panel({'A': scrambled})

        assert panel.index.equals(df.index)
        assert panel.index.is_monotonic_increasing
        assert not panel.index.has_duplicates


# --------------------------------------------------------------------------- #
# §6 — a symbol with no bar is valued, not traded
# --------------------------------------------------------------------------- #

class TestHoles:
    @staticmethod
    def _panel_with_a_hole():
        """B is missing the fourth bar; A printed it."""
        a = _daily(6)
        b = _daily(6)
        return align_panel({'A': a, 'B': b.drop(index=b.index[3])}), b

    def test_the_execution_columns_stay_nan_on_a_hole(self):
        panel, _ = self._panel_with_a_hole()
        row = panel.frame('B').iloc[3]
        for column in ('Open', 'High', 'Low', 'Close', 'Volume'):
            assert pd.isna(row[column]), f"{column} was forward-filled into a hole"

    def test_a_hole_is_not_tradable(self):
        panel, _ = self._panel_with_a_hole()
        assert list(panel.frame('B')[TRADABLE_COLUMN]) == [
            True, True, True, False, True, True
        ]
        assert panel.frame('A')[TRADABLE_COLUMN].all()

    def test_the_mark_carries_the_last_close_across_the_hole(self):
        panel, raw = self._panel_with_a_hole()
        assert panel.frame('B')[MARK_COLUMN].iloc[3] == pytest.approx(
            raw['Close'].iloc[2]
        )

    def test_the_mark_never_backfills_before_the_first_bar(self):
        """A name that has not listed has no price, and 0 would be a lie."""
        panel = align_panel({'A': _daily(6), 'LATE': _daily(3, start='2024-01-04')})
        late = panel.frame('LATE')
        listed = panel.index.get_loc(_daily(3, start='2024-01-04').index[0])

        assert late[MARK_COLUMN].iloc[:listed].isna().all()
        assert not late[TRADABLE_COLUMN].iloc[:listed].any()
        assert late[MARK_COLUMN].iloc[listed:].notna().all()

    def test_the_mark_carries_on_after_the_last_bar(self):
        """A delisted or halted name is still worth its last print."""
        panel = align_panel({'A': _daily(6), 'GONE': _daily(3)})
        gone = panel.frame('GONE')

        assert gone[MARK_COLUMN].iloc[3:].eq(gone[MARK_COLUMN].iloc[2]).all()
        assert not gone[TRADABLE_COLUMN].iloc[3:].any()

    def test_a_bar_that_printed_without_a_close_is_not_tradable(self):
        b = _daily(6)
        b.iloc[2, b.columns.get_loc('Close')] = np.nan

        panel = align_panel({'A': _daily(6), 'B': b})

        assert not panel.frame('B')[TRADABLE_COLUMN].iloc[2]


class TestSignalColumnsOnAHole:
    def test_signals_fill_with_zero_not_nan(self):
        """NaN is truthy: a reindexed signal column would fire on a dead bar."""
        b = _daily(6)
        b.iloc[:, b.columns.get_loc('RSI_Oversold_Buy')] = 1
        panel = align_panel({'A': _daily(6), 'B': b.drop(index=b.index[3])})

        column = panel.frame('B')['RSI_Oversold_Buy']
        assert column.iloc[3] == 0
        assert not column.iloc[3]
        assert column.notna().all()

    def test_a_filled_signal_column_keeps_its_dtype(self):
        b = _daily(6)
        panel = align_panel({'A': _daily(6), 'B': b.drop(index=b.index[3])})
        assert panel.frame('B')['RSI_Oversold_Buy'].dtype == b['RSI_Oversold_Buy'].dtype

    def test_boolean_columns_fill_false(self):
        b = _daily(6)
        b['Regime_On'] = True
        panel = align_panel({'A': _daily(6), 'B': b.drop(index=b.index[3])})

        column = panel.frame('B')['Regime_On']
        assert column.dtype == bool
        assert not column.iloc[3]

    def test_indicator_columns_keep_their_nan(self):
        """An indicator has no value on a bar that never printed."""
        b = _daily(6)
        panel = align_panel({'A': _daily(6), 'B': b.drop(index=b.index[3])})
        assert pd.isna(panel.frame('B')['RSI'].iloc[3])


# --------------------------------------------------------------------------- #
# §6 — sessions come from the merged index
# --------------------------------------------------------------------------- #

class TestPanelSessions:
    def test_every_frame_carries_the_panel_session_mask(self):
        panel = align_panel({'A': _ohlcv(_hourly_index()), 'B': _ohlcv(_hourly_index())})

        assert list(np.flatnonzero(panel.session_start)) == [0, 7, 14]
        for symbol in panel.symbols:
            assert list(
                panel.frame(symbol)['Session_Start'].to_numpy()
            ) == list(panel.session_start)

    def test_a_hole_in_one_symbol_is_not_a_session_boundary_for_the_basket(self):
        """B alone reads its missing 11:30 bar as a break. The basket does not."""
        full = _hourly_index()
        b = _ohlcv(full).drop(index=full[2])

        assert session_starts(b.index)[2], "the lone tape does see a break"

        panel = align_panel({'A': _ohlcv(full), 'B': b})

        assert list(np.flatnonzero(panel.session_start)) == [0, 7, 14]
        assert not panel.frame('B')['Session_Start'].iloc[2]

    def test_an_input_session_column_does_not_outrank_the_panel(self):
        """A member's own mask describes its tape, not the basket's."""
        full = _hourly_index()
        b = _ohlcv(full)
        b['Session_Start'] = True

        panel = align_panel({'A': _ohlcv(full), 'B': b})

        assert list(np.flatnonzero(panel.frame('B')['Session_Start'].to_numpy())) == [
            0, 7, 14
        ]

    def test_a_caller_with_a_calendar_can_override_the_inference(self):
        full = _hourly_index()
        supplied = np.zeros(len(full), dtype=bool)
        supplied[[4, 11]] = True

        panel = align_panel(
            {'A': _ohlcv(full), 'B': _ohlcv(full)}, session_start=supplied
        )

        assert list(np.flatnonzero(panel.session_start)) == [0, 4, 11]
        assert list(
            np.flatnonzero(panel.frame('A')['Session_Start'].to_numpy())
        ) == [0, 4, 11]

    def test_an_override_of_the_wrong_length_is_refused(self):
        with pytest.raises(PanelError, match='session_start'):
            align_panel({'A': _daily(6)}, session_start=np.ones(3, dtype=bool))

    def test_an_override_may_be_a_timestamp_indexed_series(self):
        full = _hourly_index()
        supplied = pd.Series(False, index=full)
        supplied.iloc[9] = True

        panel = align_panel({'A': _ohlcv(full)}, session_start=supplied)

        assert list(np.flatnonzero(panel.session_start)) == [0, 9]


class TestAnnualisation:
    def test_an_hourly_panel_annualises_at_the_bar_count_it_emits(self):
        panel = align_panel({'A': _ohlcv(_hourly_index()), 'B': _ohlcv(_hourly_index())})

        assert panel.bars_per_session == pytest.approx(7.0)
        assert panel.periods_per_year('1h') == periods_per_year('1h')

    def test_a_daily_panel_annualises_at_252(self):
        panel = align_panel({'A': _daily(20), 'B': _daily(20)})
        assert panel.periods_per_year('1d') == 252

    def test_a_basket_spanning_two_calendars_annualises_on_the_merged_tape(self):
        """Adding a member that trades an extra hour lengthens the panel's session."""
        us = _hourly_index()
        extended = pd.DatetimeIndex(
            sorted(set(us) | {stamp + pd.Timedelta(hours=7) for stamp in us[::7]})
        )

        panel = align_panel({'US': _ohlcv(us), 'EXT': _ohlcv(extended)})

        assert panel.bars_per_session == pytest.approx(8.0)
        assert panel.periods_per_year('1h') == 252 * 8

    def test_a_window_too_short_to_measure_falls_back_to_the_interval(self):
        panel = align_panel({'A': _daily(1)})
        assert panel.periods_per_year('1h') == periods_per_year('1h')


# --------------------------------------------------------------------------- #
# trim
# --------------------------------------------------------------------------- #

class TestTrim:
    def test_the_default_spans_every_members_history(self):
        panel = align_panel({'A': _daily(6), 'LATE': _daily(3, start='2024-01-04')})
        assert len(panel) == 6

    def test_common_clips_to_the_window_they_all_traded(self):
        panel = align_panel(
            {'A': _daily(6), 'LATE': _daily(3, start='2024-01-04')}, trim='common'
        )

        assert len(panel) == 3
        assert panel.tradable.to_numpy().all()
        assert panel.marks.notna().to_numpy().all()

    def test_common_clips_the_end_at_the_first_symbol_to_stop(self):
        panel = align_panel({'A': _daily(6), 'GONE': _daily(3)}, trim='common')

        assert len(panel) == 3
        assert panel.index[-1] == _daily(3).index[-1]

    def test_a_basket_with_no_overlapping_window_is_refused(self):
        with pytest.raises(PanelError, match='overlap'):
            align_panel(
                {'A': _daily(3), 'B': _daily(3, start='2024-06-03')}, trim='common'
            )

    def test_an_unknown_trim_mode_is_refused(self):
        with pytest.raises(PanelError, match='trim'):
            align_panel({'A': _daily(3)}, trim='intersect')


# --------------------------------------------------------------------------- #
# Timezones
# --------------------------------------------------------------------------- #

class TestTimezones:
    def test_two_venues_align_on_the_instant_not_the_wall_clock(self):
        ny = _daily(3).tz_localize('America/New_York')
        london = _daily(3).tz_localize('Europe/London')

        panel = align_panel({'NY': ny, 'LON': london})

        # Same local midnight, five hours apart in truth: six distinct bars.
        assert len(panel) == 6
        assert panel.index.tz is None

    def test_mixing_aware_and_naive_frames_is_refused(self):
        with pytest.raises(PanelError, match='tz-naive'):
            align_panel({'A': _daily(3).tz_localize('UTC'), 'B': _daily(3)})


# --------------------------------------------------------------------------- #
# Refusals
# --------------------------------------------------------------------------- #

class TestRefusals:
    def test_an_empty_basket_is_refused(self):
        with pytest.raises(PanelError, match='at least one symbol'):
            align_panel({})

    def test_a_symbol_with_no_bars_is_refused(self):
        with pytest.raises(PanelError, match='no bars'):
            align_panel({'A': _daily(3), 'B': _daily(3).iloc[0:0]})

    def test_a_frame_with_no_close_is_refused(self):
        with pytest.raises(PanelError, match='Close'):
            align_panel({'A': _daily(3).drop(columns=['Close'])})

    def test_a_non_datetime_index_is_refused(self):
        df = _daily(3).reset_index(drop=True)
        with pytest.raises(PanelError, match='datetime'):
            align_panel({'A': df})

    def test_asking_for_a_symbol_the_panel_does_not_hold(self):
        panel = align_panel({'A': _daily(3)})
        with pytest.raises(PanelError, match='TSLA'):
            panel.frame('TSLA')


# --------------------------------------------------------------------------- #
# §8 — the one-symbol case is today's engine, bit for bit
# --------------------------------------------------------------------------- #

def _run(df: pd.DataFrame) -> pd.DataFrame:
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
    )


class TestDegenerateCase:
    def test_a_one_symbol_panel_keeps_that_symbols_sessions(self):
        df = _ohlcv(_hourly_index())
        panel = align_panel({'A': df})
        assert list(panel.session_start) == list(session_starts(df.index))

    def test_a_gapless_panel_does_not_move_the_bars(self):
        df = _ohlcv(_hourly_index())
        aligned = align_panel({'A': df, 'B': _ohlcv(_hourly_index())}).frame('A')

        pd.testing.assert_frame_equal(aligned[df.columns], df)

    def test_a_gapless_aligned_frame_backtests_identically(self):
        """Alignment must be a no-op on a basket whose members share an index."""
        df = _ohlcv(_hourly_index())
        aligned = align_panel({'A': df, 'B': _ohlcv(_hourly_index())}).frame('A')

        expected = _run(df)
        got = _run(aligned.drop(columns=[TRADABLE_COLUMN, MARK_COLUMN]))

        pd.testing.assert_series_equal(
            got['Portfolio_Value'], expected['Portfolio_Value']
        )
        assert len(got.attrs['trades']) == len(expected.attrs['trades'])
