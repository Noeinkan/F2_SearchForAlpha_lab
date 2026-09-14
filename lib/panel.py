"""One index for many symbols — the panel the portfolio engine trades (3.8.2).

The engine is single-symbol and positionally indexed: bar ``i`` of one frame,
and nothing else. A portfolio needs bar ``i`` to mean the *same instant* for
every symbol in the basket, which is not what a bag of independently fetched
frames gives you. AAPL and TSM do not share a holiday calendar; a halt punches
a hole in one tape and not the others; BTC-USD prints all weekend. Line those
frames up naively — by position, or by an outer join with its NaNs left where
they fall — and the portfolio silently trades a name on a day it never opened.

This module is the alignment layer, and it implements
[docs/portfolio-semantics.md](../docs/portfolio-semantics.md) §6:

    On a timestamp where a symbol printed no bar, its last close carries the
    mark and the symbol is skipped for execution.

That sentence is two different fills of the same hole, and keeping them apart
is the whole job:

* **Valuation is forward-filled.** ``Mark`` carries the last close across the
  gap. The position still exists, and §2 sizes every order off total portfolio
  value, so a halted name that vanished from the valuation would quietly shrink
  every other symbol's next trade.
* **Execution is not.** ``Open`` / ``High`` / ``Low`` / ``Close`` stay ``NaN``
  on a hole and ``Tradable`` is ``False``. Forward-filling those would let a
  resting stop fill against a bar that never happened, at a price nobody could
  have traded at.

Signal columns are the third case, and they fill with ``0``. A reindexed
``{INDICATOR}_{CONDITION}_Buy`` column would otherwise hold ``NaN`` on every
hole — and ``NaN`` is *truthy*, so an untradable bar would read as a live buy.
"No bar, no signal" is both the safe answer and the true one.

**Sessions are inferred once, on the merged index.** ``Session_Start`` is
written onto every aligned frame, so :func:`lib.sessions.resolve_session_starts`
finds it there and the engine — unchanged — uses the *panel's* boundaries rather
than re-inferring each symbol's own. A hole in one symbol is not a session
boundary for the basket, and the annualisation factor
(:meth:`Panel.periods_per_year`) describes the tape the portfolio actually
traded rather than any one member of it.

**Align after enriching, never before.** Indicators belong to a symbol's own
tape: an RSI computed across a forward-filled panel is an RSI of bars that never
printed, and one symbol's holiday would bleed into another's oscillator. Fetch,
enrich, *then* align.

The order symbols appear in carries no meaning anywhere in this module. That is
deliberate, and it is the same commitment ``CASH_ALLOCATION_RULE`` makes in
[docs/portfolio-semantics.md](../docs/portfolio-semantics.md) §4: nothing about
a basket may depend on where a ticker sits in the list.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping, Optional

import numpy as np
import pandas as pd

from lib.sessions import (
    SESSION_START_COLUMN,
    bars_per_session_from_starts,
    session_starts,
)
from lib.timeframes import SESSIONS_PER_YEAR, periods_per_year

# Column the aligned frame gains: True when this symbol printed a usable bar
# here, and may therefore trade. False on a hole.
TRADABLE_COLUMN = 'Tradable'

# Column the aligned frame gains: the price a held position is valued at,
# forward-filled across holes. NaN before the symbol's first bar — it does not
# exist yet, and a 0 there would be a price of zero rather than an absence.
MARK_COLUMN = 'Mark'

# Suffixes of the {INDICATOR}_{CONDITION}_{Buy|Sell} convention. Columns named
# this way fill with 0 on a hole whatever their dtype, because a NaN left in an
# int-coded signal column is truthy.
SIGNAL_SUFFIXES = ('_Buy', '_Sell')

# How the panel's index is built from its members'.
TRIM_MODES = ('none', 'common')

# Sessions the panel needs before its own bar count outranks the interval table:
# the first and last are cut mid-session by the fetch window and are dropped, so
# below three there is no complete session left to measure.
_MIN_SESSIONS_TO_MEASURE = 3


class PanelError(ValueError):
    """Raised when a set of frames cannot be aligned into a panel."""


def _is_signal_column(name: Any) -> bool:
    return isinstance(name, str) and name.endswith(SIGNAL_SUFFIXES)


def _normalise_index(symbol: str, df: pd.DataFrame) -> pd.DataFrame:
    """Return *df* with a sorted, de-duplicated DatetimeIndex."""
    if not isinstance(df, pd.DataFrame):
        raise PanelError(f"{symbol}: expected a DataFrame, got {type(df).__name__}")
    if df.empty:
        raise PanelError(
            f"{symbol}: no bars — a symbol with no data cannot join a basket"
        )
    if 'Close' not in df.columns:
        raise PanelError(f"{symbol}: no Close column, so the panel cannot mark it")

    if isinstance(df.index, pd.DatetimeIndex):
        index = df.index
    elif pd.api.types.is_numeric_dtype(df.index) or pd.api.types.is_bool_dtype(df.index):
        # pd.DatetimeIndex would happily read a RangeIndex as nanoseconds since
        # the epoch, park every bar in 1970 and align nothing — the loudest
        # possible bug wearing a silent disguise.
        raise PanelError(
            f"{symbol}: index is {df.index.dtype}, not datetime-like; a positional "
            "index cannot say which bar of another symbol it lines up with"
        )
    else:
        try:
            index = pd.DatetimeIndex(df.index)
        except (TypeError, ValueError) as exc:
            raise PanelError(
                f"{symbol}: index is not datetime-like, so bars cannot be matched "
                "across symbols"
            ) from exc

    out = df.copy()
    out.index = index
    if not out.index.is_monotonic_increasing:
        out = out.sort_index()
    if out.index.has_duplicates:
        # A re-fetch overlapping a cached window is the usual cause; the later
        # row is the fresher one.
        out = out[~out.index.duplicated(keep='last')]
    return out


def _harmonise_timezones(frames: dict[str, pd.DataFrame]) -> dict[str, pd.DataFrame]:
    """Put every frame on one clock, or refuse.

    ``fetch_data`` returns tz-naive exchange-local timestamps, which is what
    almost every caller has. Frames carrying a real timezone are converted to
    UTC first — the only way 09:30 in New York and 09:00 in London land in the
    right order. A mix of the two cannot be reconciled: a naive timestamp does
    not say which venue's clock it is on, and guessing would misalign the whole
    basket by hours with nothing looking wrong.
    """
    aware = {s: f for s, f in frames.items() if getattr(f.index, 'tz', None) is not None}
    if not aware:
        return frames
    if len(aware) != len(frames):
        naive = sorted(set(frames) - set(aware))
        raise PanelError(
            "cannot align tz-aware and tz-naive frames in one panel "
            f"(naive: {', '.join(naive)}); localize them or strip every timezone"
        )
    out: dict[str, pd.DataFrame] = {}
    for symbol, frame in frames.items():
        converted = frame.copy()
        converted.index = frame.index.tz_convert('UTC').tz_localize(None)
        out[symbol] = converted
    return out


def _tradable_stamps(df: pd.DataFrame) -> pd.DatetimeIndex:
    """Timestamps where this frame printed a bar with a usable Close."""
    return pd.DatetimeIndex(df.index[df['Close'].notna().to_numpy()])


def _merged_index(frames: Mapping[str, pd.DataFrame], trim: str) -> pd.DatetimeIndex:
    """The panel's index: the union of its members', optionally clipped.

    A union rather than an intersection. An intersection would delete a whole
    bar for the basket whenever a single member was halted — throwing away real
    trading in four symbols to avoid a hole in the fifth.
    """
    index = pd.DatetimeIndex([])
    for frame in frames.values():
        index = index.union(frame.index)
    index = pd.DatetimeIndex(index).sort_values()

    if trim == 'common':
        firsts, lasts = [], []
        for symbol, frame in frames.items():
            stamps = _tradable_stamps(frame)
            if stamps.empty:
                raise PanelError(
                    f"{symbol}: every Close is NaN, so it is never tradable"
                )
            firsts.append(stamps[0])
            lasts.append(stamps[-1])
        start, end = max(firsts), min(lasts)
        if start > end:
            raise PanelError(
                f"no overlapping window: the last symbol lists at {start}, "
                f"but the first stops at {end}"
            )
        index = index[(index >= start) & (index <= end)]
    return index


def _resolve_panel_sessions(
    index: pd.DatetimeIndex,
    supplied: Optional[Any],
) -> np.ndarray:
    """Session mask for the merged index, honouring a caller's override."""
    if supplied is None:
        return session_starts(index)

    if isinstance(supplied, pd.Series):
        mask = supplied.reindex(index).fillna(False).to_numpy().astype(bool)
    else:
        mask = np.asarray(supplied, dtype=bool)
        if mask.shape != (len(index),):
            raise PanelError(
                f"session_start has {mask.size} entries but the panel index "
                f"has {len(index)}"
            )
        mask = mask.copy()
    if mask.size:
        # The tape has to begin somewhere; same rule as resolve_session_starts.
        mask[0] = True
    return mask


def _align_one(
    frame: pd.DataFrame,
    index: pd.DatetimeIndex,
    session_start: np.ndarray,
) -> pd.DataFrame:
    """Reindex one symbol onto the panel index and fill each column's holes."""
    aligned = frame.reindex(index)

    for column in frame.columns:
        source = frame[column]
        if pd.api.types.is_bool_dtype(source):
            aligned[column] = aligned[column].fillna(False).astype(bool)
        elif _is_signal_column(column):
            aligned[column] = aligned[column].fillna(0).astype(source.dtype)
        # Everything else — prices, volume, indicators — keeps its NaN. A hole
        # is an absence of trading, and the columns execution reads must say so.

    aligned[TRADABLE_COLUMN] = aligned['Close'].notna().to_numpy()
    # ffill only: the mark carries a held position across a hole, but there is
    # nothing to carry before the symbol's first bar, and a backfill would
    # invent a price for a name that had not listed.
    aligned[MARK_COLUMN] = aligned['Close'].ffill()
    aligned[SESSION_START_COLUMN] = session_start
    return aligned


# eq=False: the generated __eq__ would compare a DataFrame and an ndarray with
# ==, which raises rather than answering. Compare the parts you mean.
@dataclass(frozen=True, eq=False)
class Panel:
    """Many symbols' bars on one index, with the holes labelled.

    ``frames[symbol]`` is that symbol's frame reindexed onto :attr:`index`,
    carrying its original columns plus ``Tradable``, ``Mark`` and
    ``Session_Start``. Every frame has the same index in the same order, so
    position ``i`` is one instant across the whole basket — the property the
    portfolio engine (3.8.3) is built on and the reason this class exists.
    """

    symbols: tuple[str, ...]
    index: pd.DatetimeIndex
    frames: dict[str, pd.DataFrame] = field(repr=False)
    session_start: np.ndarray = field(repr=False)

    def __len__(self) -> int:
        return len(self.index)

    def frame(self, symbol: str) -> pd.DataFrame:
        """The aligned frame for *symbol*."""
        try:
            return self.frames[symbol]
        except KeyError:
            raise PanelError(
                f"{symbol!r} is not in this panel ({', '.join(self.symbols)})"
            ) from None

    def _wide(self, column: str) -> pd.DataFrame:
        return pd.DataFrame(
            {symbol: self.frames[symbol][column] for symbol in self.symbols},
            index=self.index,
        )

    @property
    def tradable(self) -> pd.DataFrame:
        """Bars × symbols: True where the symbol may be traded on that bar."""
        return self._wide(TRADABLE_COLUMN)

    @property
    def marks(self) -> pd.DataFrame:
        """Bars × symbols: the price a held position is valued at.

        Forward-filled across holes, and ``NaN`` before a symbol's first bar.
        Value a basket with ``(units * marks).sum()``, which skips NaN, or by
        skipping zero-unit symbols — ``0 * NaN`` is ``NaN``, and one unlisted
        name would otherwise poison the whole portfolio value.
        """
        return self._wide(MARK_COLUMN)

    @property
    def bars_per_session(self) -> Optional[float]:
        """Mean bars a complete session emits *on the merged tape*.

        Higher than any single member's when the basket spans venues that do
        not keep the same hours — but that is the tape the panel was traded on,
        so it is the honest divisor.
        """
        return bars_per_session_from_starts(self.session_start)

    def periods_per_year(self, interval: str | None = None) -> int:
        """Annualisation factor for this panel.

        Measured from the panel's own sessions where it can be — the point of
        inferring sessions on the merged index — and falling back to
        :data:`lib.timeframes.PERIODS_PER_YEAR` for *interval* otherwise.

        The measurement needs **three** sessions to be worth anything: a fetch
        window cuts its first and last session mid-session, so those two are
        dropped, and a panel with only two of them would report the length of
        whichever partial session it had rather than a full one.
        """
        if int(np.count_nonzero(self.session_start)) < _MIN_SESSIONS_TO_MEASURE:
            return periods_per_year(interval)
        measured = self.bars_per_session
        if measured is None or measured <= 0:
            return periods_per_year(interval)
        return int(round(SESSIONS_PER_YEAR * measured))


def align_panel(
    frames: Mapping[str, pd.DataFrame],
    *,
    trim: str = 'none',
    session_start: Optional[Any] = None,
) -> Panel:
    """Align *frames* onto one session-aware index.

    Args:
        frames: ``{symbol: OHLCV frame}``, each on its own DatetimeIndex and
            already carrying whatever indicator and signal columns it needs.
            Enrich before aligning, never after. Iteration order sets
            :attr:`Panel.symbols` and nothing else.
        trim: ``'none'`` (default) spans the union of every member's history, so
            a late-listing symbol simply has ``NaN`` marks and no tradable bars
            until it lists. ``'common'`` clips to the window in which every
            symbol was tradable — the fair-comparison basket, and the window
            §7's equal-weight benchmark wants.
        session_start: Optional boolean mask, or a timestamp-indexed Series,
            overriding the inference for a caller holding a real exchange
            calendar. The same escape hatch as the ``Session_Start`` column in
            :mod:`lib.sessions`, moved up to the panel because a basket's
            sessions are a property of the merged index, not of any member.

    Returns:
        A :class:`Panel`.

    Raises:
        PanelError: On an empty basket, a frame with no bars or no ``Close``, a
            non-datetime index, a mix of tz-aware and tz-naive frames, or a
            ``trim='common'`` request with no overlapping window.
    """
    if trim not in TRIM_MODES:
        raise PanelError(f"trim must be one of {TRIM_MODES}, got {trim!r}")
    if not frames:
        raise PanelError("a panel needs at least one symbol")

    prepared = {
        str(symbol): _normalise_index(str(symbol), frame)
        for symbol, frame in frames.items()
    }
    prepared = _harmonise_timezones(prepared)

    index = _merged_index(prepared, trim)
    if len(index) == 0:
        raise PanelError("the merged index is empty")

    sessions = _resolve_panel_sessions(index, session_start)
    aligned = {
        symbol: _align_one(frame, index, sessions)
        for symbol, frame in prepared.items()
    }
    return Panel(
        symbols=tuple(prepared),
        index=index,
        frames=aligned,
        session_start=sessions,
    )


__all__ = [
    'MARK_COLUMN',
    'Panel',
    'PanelError',
    'SIGNAL_SUFFIXES',
    'TRADABLE_COLUMN',
    'TRIM_MODES',
    'align_panel',
]
