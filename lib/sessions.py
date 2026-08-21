"""Where one trading session ends and the next begins.

The backtest engine is positionally indexed: bar ``i`` follows bar ``i - 1`` and
nothing in the loop knows whether the step between them was one hour of trading
or a weekend. That is fine until it isn't — a trailing stop set on Friday's
close is not "breached intrabar" when the market reopens 4% lower on Monday, it
is *gapped through*, and the fill belongs at the open.

This module is the one place that decides where those boundaries are. It infers
them from the timestamps alone, so it needs no exchange calendar and works for
any venue Yahoo serves:

* **Daily bars and coarser.** Every bar is its own session. A daily bar's open
  is always separated from the previous close by a non-trading gap.
* **Intraday bars.** A session starts wherever the step from the previous bar
  is more than :data:`SESSION_BREAK_RATIO` times the tape's own bar spacing.
  The overnight step on a 1h US equity tape is 18 hours against a 1h spacing,
  and CME's hour-long maintenance break shows up as a 2× step. Tokyo's
  90-minute lunch break is exactly 1.5× and the comparison is strict, so it
  stays *inside* the session — which is what an exchange calendar would say.
  A hole in the tape reads as a boundary, and that is the intended answer:
  a missing bar is a real discontinuity, not an hour of trading.

Bar spacing is read as the 25th percentile of the positive steps rather than
the minimum or the mode. The minimum would be hostage to a single duplicated
timestamp, and the mode ties on a tape that emits two bars per session (4h),
where exactly half the steps are overnight ones.

Everything here treats the index as already sorted and tz-naive exchange-local
time, which is what ``lib.data_processing.fetch_data`` returns.
"""

from __future__ import annotations

from typing import Any, Optional

import numpy as np
import pandas as pd

# A step larger than this multiple of the bar spacing is a session break. The
# discriminating band is narrow and the comparison is strict: Tokyo's lunch
# break is exactly 1.5 steps and stays inside the session, CME's hour-long
# maintenance break is 2 and does not.
SESSION_BREAK_RATIO = 1.5

# Quantile of the positive steps taken as "the bar spacing". See module docstring.
_SPACING_QUANTILE = 25

_ONE_DAY_NS = 24 * 60 * 60 * 1_000_000_000

# Boolean column a caller may put on the input frame to override inference.
SESSION_START_COLUMN = 'Session_Start'


def _as_datetime_index(index: Any) -> Optional[pd.DatetimeIndex]:
    """Return *index* as a tz-naive DatetimeIndex, or None if it isn't one."""
    if isinstance(index, pd.DatetimeIndex):
        idx = index
    elif isinstance(index, pd.Index) or isinstance(index, np.ndarray):
        try:
            idx = pd.DatetimeIndex(index)
        except (TypeError, ValueError):
            return None
    else:
        return None
    if idx.tz is not None:
        idx = idx.tz_localize(None)
    # pandas 2 keeps whatever resolution the source had (us for date_range,
    # ns for a Yahoo fetch), and ``asi8`` is expressed in *that* unit. Pin it
    # to nanoseconds so every comparison below is against the same clock.
    as_unit = getattr(idx, 'as_unit', None)
    if as_unit is not None:
        try:
            idx = as_unit('ns')
        except (ValueError, OverflowError):
            return None
    return idx


def bar_spacing_ns(index: Any) -> Optional[int]:
    """Nanoseconds between consecutive bars on this tape, or None.

    None means the question has no answer: a non-datetime index, or fewer than
    two distinct timestamps.
    """
    idx = _as_datetime_index(index)
    if idx is None or len(idx) < 2:
        return None
    steps = np.diff(idx.asi8)
    steps = steps[steps > 0]
    if steps.size == 0:
        return None
    return int(np.percentile(steps, _SPACING_QUANTILE, method='lower'))


def session_starts(index: Any) -> np.ndarray:
    """Boolean mask: True on the first bar of each trading session.

    Bar 0 is always a session start — the tape has to begin somewhere. When the
    index carries no usable time information the whole tape is treated as one
    session, so callers degrade to the positional behaviour they had before
    sessions existed rather than seeing a boundary on every bar.
    """
    n = len(index)
    out = np.zeros(n, dtype=bool)
    if n == 0:
        return out
    out[0] = True
    if n == 1:
        return out

    spacing = bar_spacing_ns(index)
    if spacing is None or spacing <= 0:
        return out

    if spacing >= _ONE_DAY_NS:
        # Daily or coarser: every bar opens after a non-trading gap.
        out[1:] = True
        return out

    idx = _as_datetime_index(index)
    assert idx is not None  # bar_spacing_ns returned a value, so this holds
    out[1:] = np.diff(idx.asi8) > spacing * SESSION_BREAK_RATIO
    return out


def session_ids(index: Any) -> np.ndarray:
    """Zero-based session number for each bar, monotonically non-decreasing."""
    starts = session_starts(index)
    if starts.size == 0:
        return np.zeros(0, dtype=int)
    return np.cumsum(starts) - 1


def resolve_session_starts(df: pd.DataFrame) -> np.ndarray:
    """Session mask for *df*, honouring an explicit ``Session_Start`` column.

    A caller holding a real exchange calendar can write the column itself and
    the inference is skipped. Everyone else gets it inferred from the index.
    """
    if SESSION_START_COLUMN in df.columns:
        supplied = df[SESSION_START_COLUMN].to_numpy()
        mask = np.zeros(len(df), dtype=bool)
        if mask.size:
            mask[:] = supplied.astype(bool)
            mask[0] = True
        return mask
    return session_starts(df.index)


def bars_per_session(index: Any) -> Optional[float]:
    """Mean number of bars a complete session emits on this tape.

    Used to check :data:`lib.timeframes.PERIODS_PER_YEAR` against what the tape
    actually contains. The first and last sessions are dropped because a fetch
    window almost always cuts them mid-session.
    """
    ids = session_ids(index)
    if ids.size == 0:
        return None
    counts = np.bincount(ids)
    if counts.size > 2:
        counts = counts[1:-1]
    if counts.size == 0:
        return None
    return float(counts.mean())


__all__ = [
    'SESSION_BREAK_RATIO',
    'SESSION_START_COLUMN',
    'bar_spacing_ns',
    'bars_per_session',
    'resolve_session_starts',
    'session_ids',
    'session_starts',
]
