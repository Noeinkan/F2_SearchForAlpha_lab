"""Test-window callbacks — the period the backtest and optimizer evaluate.

This is deliberately separate from `data_loading`. Fetching and evaluating used
to share one pair of sidebar date pickers, which is how the optimizer ended up
slicing to the picker range while the backtest ran on the whole fetched frame.
The two concerns are now split by module as well as by UI:

  data_loading  -> what data exists (always the widest window Yahoo will serve)
  test_window   -> what slice of it is measured, and where the chart is looking

Output ownership, which Dash 4 enforces rather than merely prefers:

  test-window-start/end .date   <- sync_test_window   (this file, only writer)
  test-window-series-store.data <- sync_test_window   (this file, only writer)
  test-window-pending-store     <- sync_test_window + stage_preset_test_window
  chart-focus-store.data        <- focus_chart_on_test_window (this file)
                                   + focus_chart_from_row (data_table.py)
"""

from __future__ import annotations

import logging

import pandas as pd
from dash import callback_context, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.callbacks.shared import slice_df_to_window
from lib.dash.state import dashboard_state

logger = logging.getLogger(__name__)


def _loaded_bounds() -> tuple[str, str] | None:
    """First and last bar dates of the loaded frame, or None if unusable."""
    df = dashboard_state.df
    if df is None or df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return None
    return (
        df.index.min().date().isoformat(),
        df.index.max().date().isoformat(),
    )


def resolve_preset(preset: str | None, first: str, last: str) -> tuple[str, str]:
    """Turn a MAX/5Y/2Y/1Y/YTD shortcut into concrete dates.

    Anchored to the loaded frame's *last bar* rather than today, so the window
    is the same whether it is resolved on a Monday morning or after a long
    weekend, and so a delisted or stale symbol still yields a usable range.
    Clamped to ``first`` — asking for 5Y of a 2-year-old listing gives 2 years,
    not an empty slice.
    """
    last_ts = pd.Timestamp(last)
    if preset == 'ytd':
        start_ts = pd.Timestamp(year=last_ts.year, month=1, day=1)
    elif preset in ('1y', '2y', '5y'):
        start_ts = last_ts - pd.DateOffset(years=int(preset[0]))
    else:  # 'max' and anything unrecognised
        return first, last

    first_ts = pd.Timestamp(first)
    return max(start_ts, first_ts).date().isoformat(), last


def _clamp_to_loaded(start, end, first: str, last: str) -> tuple[str, str]:
    """Pull a restored window back inside what is actually loaded."""
    try:
        start_iso = max(pd.Timestamp(str(start)[:10]), pd.Timestamp(first)).date().isoformat()
        end_iso = min(pd.Timestamp(str(end)[:10]), pd.Timestamp(last)).date().isoformat()
    except (TypeError, ValueError):
        return first, last
    return (first, last) if start_iso >= end_iso else (start_iso, end_iso)


def register_test_window_callbacks(app) -> None:
    @app.callback(
        [Output('test-window-start', 'date'),
         Output('test-window-end', 'date'),
         Output('test-window-series-store', 'data'),
         Output('test-window-pending-store', 'data')],
        [Input('data-loaded-store', 'data'),
         Input('test-window-preset', 'value')],
        [State('test-window-series-store', 'data'),
         State('test-window-pending-store', 'data')],
        prevent_initial_call=False,
    )
    def sync_test_window(_load_generation, preset, series_key, pending):
        """Keep the window valid against whatever data is currently loaded.

        Resets to the full loaded range only when the *series* changes (new
        symbol or new bar size) — the same rule the chart glue uses to decide
        whether the old viewport still means anything. A plain refresh of the
        same series must not throw away a window the user narrowed by hand.
        """
        bounds = _loaded_bounds()
        if bounds is None:
            raise PreventUpdate
        first, last = bounds

        ctx = callback_context
        trigger = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None

        if trigger == 'test-window-preset':
            start, end = resolve_preset(preset, first, last)
            return start, end, no_update, no_update

        current_key = f"{dashboard_state.ticker}|{dashboard_state.interval}"
        if series_key == current_key and not pending:
            raise PreventUpdate

        if pending:
            start, end = _clamp_to_loaded(pending.get('start'), pending.get('end'), first, last)
        else:
            start, end = first, last
        return start, end, current_key, None

    @app.callback(
        Output('test-window-pending-store', 'data', allow_duplicate=True),
        Input('preset-apply-store', 'data'),
        prevent_initial_call=True,
    )
    def stage_preset_test_window(preset_data):
        """Park a preset's saved window until its data has finished loading.

        Applying a preset changes the symbol, which triggers a fetch, which
        lands as a new series — and a new series resets the window. Writing the
        saved dates straight to the pickers would just get overwritten a layer
        later, so they wait here for ``sync_test_window`` to pick them up and
        clamp them to whatever actually loaded.
        """
        if not preset_data:
            raise PreventUpdate
        window = (preset_data.get("market_data") or {}).get("test_window") or {}
        if not window.get("start") or not window.get("end"):
            raise PreventUpdate
        return {"start": window["start"], "end": window["end"]}

    @app.callback(
        [Output('chart-focus-store', 'data', allow_duplicate=True),
         Output('summary-test-window', 'children')],
        [Input('test-window-start', 'date'),
         Input('test-window-end', 'date')],
        prevent_initial_call=True,
    )
    def focus_chart_on_test_window(start_date, end_date):
        """Scroll the chart to the evaluated window and label the accordion.

        The clientside half of this already exists for Data-tab row clicks
        (callbacks/chart.py) — it reads chart-focus-store and calls
        sfaChart.setVisibleRange, handling the sub-daily epoch conversion. This
        only has to write the store. Showing the resolved dates and bar count
        matters because the preset radio is a pure applicator: it does not
        deselect when the pickers are edited by hand, so the summary is what
        tells the truth about the window in force.
        """
        if not start_date or not end_date:
            raise PreventUpdate

        df = dashboard_state.df
        if df is None:
            return {'start': start_date, 'end': end_date}, no_update

        sliced, label = slice_df_to_window(df, start_date, end_date)
        return {'start': start_date, 'end': end_date}, f"{label} · {len(sliced):,} bars"
