"""
Data tab callbacks — filter/slice the display store and rebuild the table.
"""

from __future__ import annotations

from datetime import datetime

import pandas as pd
from dash import callback_context, dcc, no_update
from dash.dependencies import Input, Output, State
from dash.dcc.express import send_string
from dash.exceptions import PreventUpdate

from lib.dash.dash_config import DATA_EXPORT_MAX_ROWS, get_theme
from lib.dash.callbacks.shared import (
    _create_data_table,
    _create_summary_strip,
    filter_data_display,
    records_to_csv,
)


def _should_seed_dates(trigger_id: str) -> bool:
    return trigger_id == 'data-display-store'


def register_data_table_callbacks(app) -> None:
    @app.callback(
        [
            Output('data-table-container', 'children'),
            Output('data-summary-strip', 'children'),
            Output('data-date-start', 'date', allow_duplicate=True),
            Output('data-date-end', 'date', allow_duplicate=True),
        ],
        [
            Input('data-display-store', 'data'),
            Input('data-rows', 'value'),
            Input('data-col-groups', 'value'),
            Input('data-date-start', 'date'),
            Input('data-date-end', 'date'),
        ],
        prevent_initial_call='initial_duplicate',
    )
    def rebuild_data_table(payload, row_count, col_groups, date_start, date_end):
        """Rebuild the Data tab table from the store and control widgets."""
        if not payload:
            return None, None, no_update, no_update

        ctx = callback_context
        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ''
        seed_dates = _should_seed_dates(trigger_id)
        effective_start = payload.get('range_start') if seed_dates else date_start
        effective_end = payload.get('range_end') if seed_dates else date_end

        records, columns, summary = filter_data_display(
            payload,
            row_count,
            col_groups,
            effective_start,
            effective_end,
        )
        theme = get_theme()
        if not records:
            empty = dcc.Markdown(
                '_No rows match the current filters._',
                style={'color': theme['text_tertiary'], 'fontSize': '12px'},
            )
            return empty, _create_summary_strip(summary, theme), effective_start, effective_end

        table = _create_data_table(records, columns, theme)
        return (
            table,
            _create_summary_strip(summary, theme),
            effective_start if seed_dates else no_update,
            effective_end if seed_dates else no_update,
        )

    @app.callback(
        Output('chart-focus-store', 'data'),
        Input('data-table', 'active_cell'),
        [
            State('data-display-store', 'data'),
            State('data-rows', 'value'),
            State('data-col-groups', 'value'),
            State('data-date-start', 'date'),
            State('data-date-end', 'date'),
        ],
        prevent_initial_call=True,
    )
    def focus_chart_from_row(active_cell, payload, row_count, col_groups, date_start, date_end):
        """Map a clicked table row to a chart focus window."""
        if not active_cell or not payload:
            raise PreventUpdate

        records, _, _ = filter_data_display(
            payload,
            row_count,
            col_groups,
            date_start,
            date_end,
        )
        row_idx = active_cell.get('row')
        if row_idx is None or row_idx < 0 or row_idx >= len(records):
            raise PreventUpdate

        date_col = payload.get('date_column', 'Date')
        focus_date = records[row_idx].get(date_col)
        if not focus_date:
            raise PreventUpdate

        focus_ts = pd.Timestamp(focus_date)
        all_dates = [
            pd.Timestamp(rec[date_col])
            for rec in payload.get('records', [])
            if rec.get(date_col)
        ]
        if not all_dates:
            raise PreventUpdate

        all_dates.sort()
        try:
            loc = all_dates.index(focus_ts)
        except ValueError:
            loc = max(0, min(len(all_dates) - 1, int(row_idx)))

        start_idx = max(0, loc - 30)
        end_idx = min(len(all_dates) - 1, loc + 10)
        start = all_dates[start_idx].strftime('%Y-%m-%d')
        end = all_dates[end_idx].strftime('%Y-%m-%d')
        return {'date': focus_ts.strftime('%Y-%m-%d'), 'start': start, 'end': end}

    @app.callback(
        Output('data-download', 'data'),
        Input('data-export-btn', 'n_clicks'),
        [
            State('data-display-store', 'data'),
            State('data-rows', 'value'),
            State('data-col-groups', 'value'),
            State('data-date-start', 'date'),
            State('data-date-end', 'date'),
            State('ticker-dropdown', 'value'),
        ],
        prevent_initial_call=True,
    )
    def export_data_csv(n_clicks, payload, row_count, col_groups, date_start, date_end, ticker):
        """Export the currently filtered data tab view as CSV."""
        if not n_clicks or not payload:
            raise PreventUpdate

        records, columns, _ = filter_data_display(
            payload,
            row_count,
            col_groups,
            date_start,
            date_end,
        )
        if not records:
            raise PreventUpdate

        csv_text = records_to_csv(records, columns)
        export_date = datetime.now().strftime('%Y%m%d')
        safe_ticker = (ticker or 'data').replace('/', '-')
        filename = f"{safe_ticker}_data_tab_{export_date}.csv"
        if len(records) > DATA_EXPORT_MAX_ROWS:
            csv_text = (
                f"# Export capped at {DATA_EXPORT_MAX_ROWS} rows "
                f"(filtered view had {len(records)} rows)\n"
                f"{csv_text}"
            )
        return send_string(csv_text, filename)
