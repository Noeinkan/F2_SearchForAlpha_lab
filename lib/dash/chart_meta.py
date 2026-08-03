"""Bar-interval inference and toolbar summary strings.

Split out of the old Plotly ``chart_builder`` — these describe the *data*, not
the rendering, so they outlived the figure factory. The chart itself is now
drawn client-side by ``assets/10-sfa-chart.js`` from a payload built in
``chart_payload.py``.
"""

from __future__ import annotations

import pandas as pd


def infer_bar_interval(index: pd.Index) -> str:
    """Best-effort bar-interval label ('1D', '1W', '1H', '15m', …).

    Uses the *median* consecutive gap so weekend/holiday jumps in daily equity
    data still resolve to '1D' rather than being skewed by Fri→Mon gaps.
    """
    if index is None or len(index) < 3:
        return '—'
    try:
        deltas = pd.Series(index[1:]) - pd.Series(index[:-1])
        secs = deltas.median().total_seconds()
    except (TypeError, ValueError, AttributeError):
        return '—'
    if not secs or secs <= 0:
        return '—'

    minute, hour, day = 60, 3600, 86400
    if secs < hour:
        return f"{int(round(secs / minute))}m"
    if secs < day:
        return f"{int(round(secs / hour))}H"
    if secs < 6 * day:
        return f"{int(round(secs / day))}D"
    if secs < 20 * day:
        return "1W"
    return "1M"


def is_subdaily(index: pd.Index) -> bool:
    """True when median bar spacing is under one calendar day."""
    label = infer_bar_interval(index)
    return bool(label.endswith('H') or (len(label) > 1 and label.endswith('m')))


def bar_count_summary(
    df: pd.DataFrame,
    view_range: dict | None = None,
    interval: str | None = None,
) -> str:
    """Toolbar string like ``1,247 bars · 1D · 2018-01-02 → 2024-12-31``.

    Reflects the visible window when a ``view_range`` is supplied, otherwise the
    full series. Python builds this only for the bootstrap first paint; once the
    chart is live the glue recomputes it locally on every pan, because routing
    that through a callback would put the server back in the interaction loop.

    ``interval`` is the bar size the data was actually fetched at. Prefer it
    over ``infer_bar_interval``: a 4h series has only two bars per regular
    session, so half its gaps are the 20h overnight jump and the median lands
    on ``20H``. Inference stays the fallback for callers without that context.
    """
    if df is None or len(df) == 0:
        return ''
    interval = interval.upper() if interval else infer_bar_interval(df.index)
    visible = df
    if view_range:
        start, end = view_range.get('start'), view_range.get('end')
        if start and end:
            try:
                s, e = pd.to_datetime(start), pd.to_datetime(end)
                windowed = df.loc[(df.index >= s) & (df.index <= e)]
                if len(windowed) > 0:
                    visible = windowed
            except (ValueError, TypeError):
                pass
    bars_label = f"{len(visible):,} bars"
    try:
        start_ts = pd.to_datetime(visible.index[0])
        end_ts = pd.to_datetime(visible.index[-1])
        fmt = '%Y-%m-%d %H:%M' if is_subdaily(df.index) else '%Y-%m-%d'
        start_s, end_s = start_ts.strftime(fmt), end_ts.strftime(fmt)
    except (ValueError, TypeError, IndexError):
        return f"{bars_label} · {interval}"
    return f"{bars_label} · {interval} · {start_s} → {end_s}"
