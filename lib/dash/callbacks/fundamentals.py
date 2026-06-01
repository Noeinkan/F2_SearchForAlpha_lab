"""Fundamentals page callbacks."""

from __future__ import annotations

import logging
from typing import Any, Sequence

from dash import callback_context, dash_table, dcc, html, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from lib.dash.dash_config import DEFAULT_THEME, DEFAULT_TICKER, FONT_MONO, FONT_SIZES, get_theme
from lib.fundamentals import fetch_fundamentals

logger = logging.getLogger(__name__)


def register_fundamentals_callbacks(app) -> None:
    @app.callback(
        Output('fundamentals-global-symbol', 'children'),
        Input('ticker-dropdown', 'value'),
    )
    def sync_fundamentals_global_symbol(ticker):
        return f"GLOBAL {str(ticker or DEFAULT_TICKER).upper()}"

    @app.callback(
        Output('fundamentals-ticker-input', 'value'),
        Input('open-fundamentals-button', 'n_clicks'),
        State('ticker-dropdown', 'value'),
        prevent_initial_call=True,
    )
    def seed_fundamentals_ticker(open_clicks, ticker):
        if not open_clicks:
            raise PreventUpdate
        return str(ticker or DEFAULT_TICKER).upper()

    @app.callback(
        Output('fundamentals-overlay-open-store', 'data'),
        [Input('open-fundamentals-button', 'n_clicks'),
         Input('close-fundamentals-button', 'n_clicks')],
        prevent_initial_call=True,
    )
    def set_fundamentals_open_state(open_clicks, close_clicks):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        return trigger_id != 'close-fundamentals-button'

    @app.callback(
        Output('fundamentals-overlay', 'style'),
        [Input('fundamentals-overlay-open-store', 'data'),
         Input('theme-store', 'data')],
        State('fundamentals-overlay', 'style'),
    )
    def render_fundamentals_overlay(open_state, theme_name, current_style):
        theme = get_theme(theme_name or DEFAULT_THEME)
        style = dict(current_style or {})
        style.update({
            'backgroundColor': theme['bg_primary'],
            'border': f'1px solid {theme["border_primary"]}',
            'display': 'block' if open_state else 'none',
        })
        return style

    @app.callback(
        [Output('fundamentals-store', 'data'),
         Output('fundamentals-title', 'children'),
         Output('fundamentals-status', 'children'),
         Output('ticker-dropdown', 'value', allow_duplicate=True)],
        [Input('open-fundamentals-button', 'n_clicks'),
         Input('refresh-fundamentals-button', 'n_clicks'),
         Input('load-fundamentals-ticker-button', 'n_clicks'),
         Input('fundamentals-ticker-input', 'n_submit')],
        [State('ticker-dropdown', 'value'),
         State('fundamentals-ticker-input', 'value')],
        prevent_initial_call=True,
    )
    def load_fundamentals(open_clicks, refresh_clicks, load_clicks, input_submit, ticker, overlay_ticker):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id == 'open-fundamentals-button':
            symbol = str(ticker or DEFAULT_TICKER).strip().upper()
        else:
            symbol = str(overlay_ticker or ticker or DEFAULT_TICKER).strip().upper()

        if not symbol:
            return None, 'Invalid ticker', 'ERROR: ticker is required', no_update

        try:
            payload = fetch_fundamentals(symbol)
        except Exception as exc:
            logger.exception("Error loading fundamentals for %s", symbol)
            return None, f'{symbol} fundamentals', f'ERROR: {exc}', no_update

        title = f"{payload['company_name']} ({payload['ticker']})"
        # Promote overlay ticker edits to global symbol only when user explicitly
        # loads/submits a ticker from fundamentals.
        update_global_ticker = symbol if trigger_id in {'load-fundamentals-ticker-button', 'fundamentals-ticker-input'} else no_update
        return payload, title, f"LOADED {payload['as_of']}", update_global_ticker

    @app.callback(
        Output('fundamentals-content', 'children'),
        [Input('fundamentals-store', 'data'),
         Input('theme-store', 'data')],
    )
    def render_fundamentals(payload, theme_name):
        theme = get_theme(theme_name or DEFAULT_THEME)
        if not payload:
            return _empty_state(theme, "Open fundamentals after selecting a stock.")
        return _render_payload(payload, theme)


def _render_payload(payload: dict[str, Any], theme: dict) -> html.Div:
    years = [str(year) for year in payload.get('years', [])]
    return html.Div([
        _summary_strip(payload, theme),
        html.Div([
            html.Div([
                _panel_title('Financials', theme),
                _financial_table(payload.get('financials', []), years, theme),
            ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-main'),
            html.Div([
                _panel_title('Valuation', theme),
                _valuation_table(payload.get('valuation', []), theme),
            ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-side'),
        ], className='sfa-fundamentals-top'),
        html.Div([
            _panel_title('Big Five', theme),
            _big_five_note(payload.get('big_five_note', ''), theme),
            _big_five_table(payload.get('big_five', []), years, theme),
        ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-big-five'),
        html.Div([
            _chart_card(label, values, payload.get('years', []), theme)
            for label, values in payload.get('chart_series', {}).items()
        ], className='sfa-fundamentals-charts'),
        _quality_notes(payload.get('quality_notes', []), theme),
    ], style={'width': '100%', 'minWidth': 0}, className='sfa-fundamentals-root')


def _summary_strip(payload: dict[str, Any], theme: dict) -> html.Div:
    years = payload.get('years') or []
    last_year = years[-1] if years else '--'
    return html.Div([
        _summary_cell('Ticker', payload.get('ticker', '--'), theme),
        _summary_cell('Currency', payload.get('currency', '--'), theme),
        _summary_cell('Last FY', last_year, theme),
        _summary_cell('Updated', payload.get('as_of', '--'), theme),
    ], style={
        'display': 'grid',
    }, className='sfa-fundamentals-summary')


def _summary_cell(label: str, value: Any, theme: dict) -> html.Div:
    return html.Div([
        html.Div(label, style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'fontFamily': FONT_MONO}),
        html.Div(str(value), className='num', style={'fontSize': FONT_SIZES['sm'], 'color': theme['text_primary'], 'fontFamily': FONT_MONO}),
    ], style={
        'backgroundColor': theme['bg_tertiary'],
        'border': f'1px solid {theme["border_primary"]}',
        'padding': '5px 7px',
        'minWidth': 0,
    })


def _panel_title(title: str, theme: dict) -> html.Div:
    return html.Div(title, style={
        'fontFamily': FONT_MONO,
        'fontSize': FONT_SIZES['xs'],
        'fontWeight': 700,
        'color': theme['text_secondary'],
        'letterSpacing': '1.5px',
        'textTransform': 'uppercase',
        'marginBottom': '5px',
    })


def _panel_style(theme: dict) -> dict[str, Any]:
    return {
        'backgroundColor': theme['bg_panel'],
        'border': f'1px solid {theme["border_primary"]}',
        'padding': '6px',
        'minWidth': 0,
    }


def _financial_table(rows: list[dict[str, Any]], years: list[str], theme: dict) -> dash_table.DataTable:
    columns = [{'name': 'Metric', 'id': 'metric'}, {'name': 'Unit', 'id': 'unit'}] + [{'name': year, 'id': year} for year in years]
    props: dict[str, Any] = {
        'columns': columns,
        'data': rows,
        'fill_width': True,
        'style_table': {'overflowX': 'auto', 'width': '100%', 'minWidth': '100%'},
        'style_cell': _table_cell_style(theme),
        'style_cell_conditional': [
            {'if': {'column_id': 'metric'}, 'textAlign': 'left', 'fontWeight': 700, 'minWidth': '165px', 'width': '18%'},
            {'if': {'column_id': 'unit'}, 'textAlign': 'center', 'width': '52px', 'maxWidth': '58px'},
        ],
        'style_header': _table_header_style(theme),
        'style_data_conditional': _financial_conditionals(theme),
        'fixed_columns': {'headers': True, 'data': 1},
    }
    return dash_table.DataTable(**props)


def _big_five_table(rows: list[dict[str, Any]], years: list[str], theme: dict) -> dash_table.DataTable:
    rows = _decorate_big_five_rows(rows)
    columns = [{'name': 'Metric', 'id': 'metric'}, {'name': 'Unit', 'id': 'unit'}]
    columns += [{'name': year, 'id': year} for year in years]
    columns += [{'name': label, 'id': label} for label in ('10Y', '5Y', '1Y')]
    props: dict[str, Any] = {
        'columns': columns,
        'data': rows,
        'fill_width': True,
        'style_table': {'overflowX': 'auto', 'width': '100%', 'minWidth': '100%'},
        'style_cell': _table_cell_style(theme),
        'style_cell_conditional': [
            {'if': {'column_id': 'metric'}, 'textAlign': 'left', 'fontWeight': 700, 'minWidth': '150px', 'width': '16%'},
            {'if': {'column_id': 'unit'}, 'textAlign': 'center', 'width': '52px', 'maxWidth': '58px'},
            {'if': {'column_id': '10Y'}, 'borderLeft': f'2px solid {theme["accent_blue"]}'},
        ],
        'style_header': _table_header_style(theme),
        'style_data_conditional': _big_five_conditionals(theme, years + ['10Y', '5Y', '1Y']),
    }
    return dash_table.DataTable(**props)


def _decorate_big_five_rows(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    arrow_by_status = {
        'good': '↑',
        'warn': '→',
        'bad': '↓',
    }
    decorated: list[dict[str, Any]] = []
    for row in rows:
        new_row = dict(row)
        for summary_label in ('10Y', '5Y', '1Y'):
            status = str(new_row.get(f'status_{summary_label}', ''))
            value = str(new_row.get(summary_label, '--'))
            arrow = arrow_by_status.get(status)
            if arrow and value != '--':
                new_row[summary_label] = f'{arrow} {value}'
        decorated.append(new_row)
    return decorated


def _big_five_note(note: str, theme: dict) -> html.Div:
    if not note:
        return html.Div()
    return html.Div(note, style={
        'fontFamily': FONT_MONO,
        'fontSize': FONT_SIZES['xs'],
        'fontWeight': 700,
        'color': theme['accent_red'],
        'marginBottom': '4px',
        'lineHeight': '1.25',
    })


def _valuation_table(rows: list[dict[str, Any]], theme: dict) -> html.Div:
    midpoint = (len(rows) + 1) // 2
    paired_rows = list(zip(rows[:midpoint], rows[midpoint:] + [{}] * midpoint))
    return html.Div([
        html.Div([
            html.Div('Metric', style=_valuation_header_style(theme)),
            html.Div('Value', style={**_valuation_header_style(theme), 'textAlign': 'right'}),
            html.Div('Metric', style=_valuation_header_style(theme)),
            html.Div('Value', style={**_valuation_header_style(theme), 'textAlign': 'right'}),
        ], className='sfa-valuation-grid sfa-valuation-header'),
        *[
            html.Div([
                *_valuation_cells(left, theme),
                *_valuation_cells(right, theme),
            ], className='sfa-valuation-grid')
            for left, right in paired_rows
        ],
    ], className='sfa-valuation-table')


def _table_cell_style(theme: dict) -> dict[str, Any]:
    return {
        'textAlign': 'right',
        'padding': '5px 7px',
        'backgroundColor': theme['bg_tertiary'],
        'color': theme['text_primary'],
        'border': f'1px solid {theme["border_secondary"]}',
        'fontSize': '12px',
        'fontFamily': FONT_MONO,
        'fontVariantNumeric': 'tabular-nums',
        'whiteSpace': 'nowrap',
        'lineHeight': '18px',
        'height': '24px',
        'minHeight': '24px',
        'maxHeight': '24px',
        'overflow': 'hidden',
        'textOverflow': 'ellipsis',
    }


def _table_header_style(theme: dict) -> dict[str, Any]:
    return {
        'fontWeight': 700,
        'backgroundColor': theme['bg_secondary'],
        'color': theme['text_secondary'],
        'textTransform': 'uppercase',
        'fontSize': '12px',
        'border': f'1px solid {theme["border_primary"]}',
        'height': '24px',
        'minHeight': '24px',
        'maxHeight': '24px',
    }


def _valuation_header_style(theme: dict) -> dict[str, Any]:
    return {
        'fontWeight': 700,
        'backgroundColor': theme['bg_secondary'],
        'color': theme['text_secondary'],
        'textTransform': 'uppercase',
        'fontSize': '12px',
        'border': f'1px solid {theme["border_primary"]}',
        'padding': '5px 7px',
        'fontFamily': FONT_MONO,
        'lineHeight': '18px',
    }


def _valuation_cells(row: dict[str, Any], theme: dict) -> list[html.Div]:
    metric = row.get('metric') or ''
    value = row.get('value') or ''
    color_style = _valuation_metric_style(metric, theme)
    base_style = {
        'backgroundColor': theme['bg_tertiary'],
        'color': theme['text_primary'],
        'border': f'1px solid {theme["border_secondary"]}',
        'padding': '5px 7px',
        'fontSize': '12px',
        'fontFamily': FONT_MONO,
        'lineHeight': '18px',
        'whiteSpace': 'nowrap',
        'overflow': 'hidden',
        'textOverflow': 'ellipsis',
    }
    return [
        html.Div(metric, title=metric, style={**base_style, **color_style, 'fontWeight': 700}),
        html.Div(value, title=str(value), className='num', style={**base_style, **color_style, 'textAlign': 'right'}),
    ]


def _valuation_metric_style(metric: str, theme: dict) -> dict[str, Any]:
    if metric == 'Current Price':
        return {'backgroundColor': f'{theme["accent_red"]}25', 'color': theme['accent_red']}
    if metric == 'Entry Price':
        return {'backgroundColor': f'{theme["accent_green"]}22', 'color': theme['accent_green']}
    if metric == 'Fut. Market Price (10 Y)':
        return {'backgroundColor': f'{theme["accent_blue"]}18'}
    if metric == 'Sticker Price':
        return {'backgroundColor': f'{theme["accent_blue"]}12'}
    return {}


def _financial_conditionals(theme: dict) -> list[dict[str, Any]]:
    return [
        {'if': {'filter_query': '{metric} = "Sales (Rev)"'}, 'backgroundColor': f'{theme["accent_green"]}24'},
        {'if': {'filter_query': '{metric} = "Equity"'}, 'backgroundColor': f'{theme["accent_green"]}24'},
        {'if': {'filter_query': '{metric} = "EPS"'}, 'backgroundColor': f'{theme["accent_green"]}24'},
        {'if': {'filter_query': '{metric} = "FCF"'}, 'backgroundColor': f'{theme["accent_green"]}24'},
        {'if': {'filter_query': '{metric} = "NOPAT"'}, 'backgroundColor': f'{theme["accent_red"]}22'},
        {'if': {'filter_query': '{metric} contains "Debt"'}, 'backgroundColor': f'{theme["accent_cyan"]}24'},
        {'if': {'filter_query': '{metric} = "Debt Ratio"'}, 'backgroundColor': f'{theme["accent_cyan"]}28'},
        {'if': {'filter_query': '{metric} = "PE Ratio"'}, 'backgroundColor': f'{theme["accent_orange"]}24'},
        {'if': {'filter_query': '{metric} = "Avg. Invested Capital"'}, 'backgroundColor': f'{theme["accent_orange"]}22'},
        {'if': {'state': 'active'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
        {'if': {'state': 'selected'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
    ]


def _big_five_conditionals(theme: dict, value_columns: list[str]) -> list[dict[str, Any]]:
    conditionals = [{'if': {'filter_query': '{metric} = "ROIC"'}, 'backgroundColor': f'{theme["accent_green"]}24'}]
    for column in value_columns:
        conditionals.extend([
            {'if': {'column_id': column, 'filter_query': f'{{{column}}} contains "--"'}, 'color': theme['text_tertiary']},
            {'if': {'column_id': column, 'filter_query': f'{{{column}}} contains "-"'}, 'backgroundColor': f'{theme["accent_red"]}26', 'color': theme['accent_red'], 'fontWeight': 700},
            {'if': {'column_id': column, 'filter_query': f'{{{column}}} contains "0.00%"'}, 'backgroundColor': f'{theme["accent_red"]}26', 'color': theme['accent_red'], 'fontWeight': 700},
        ])
    for summary_label in ('10Y', '5Y', '1Y'):
        status_key = f'status_{summary_label}'
        conditionals.extend([
            {'if': {'column_id': summary_label, 'filter_query': f'{{{status_key}}} = "good"'}, 'backgroundColor': f'{theme["accent_green"]}30', 'color': theme['accent_green'], 'fontWeight': 700},
            {'if': {'column_id': summary_label, 'filter_query': f'{{{status_key}}} = "warn"'}, 'backgroundColor': f'{theme["accent_orange"]}30', 'color': theme['accent_orange'], 'fontWeight': 700},
            {'if': {'column_id': summary_label, 'filter_query': f'{{{status_key}}} = "bad"'}, 'backgroundColor': f'{theme["accent_red"]}30', 'color': theme['accent_red'], 'fontWeight': 700},
        ])
    conditionals.extend([
        {'if': {'state': 'active'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
        {'if': {'state': 'selected'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
    ])
    return conditionals


def _chart_card(label: str, values: list[float | None], years: list[int], theme: dict) -> html.Div:
    return html.Div([
        _panel_title(label, theme),
        dcc.Graph(figure=_metric_figure(label, values, years, theme), config={'displayModeBar': False}, style={'height': 'clamp(145px, 19vh, 190px)'}),
    ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-chart')


def _metric_figure(label: str, values: list[float | None], years: list[int], theme: dict) -> go.Figure:
    fig = go.Figure()
    y_values = [value * 100 if label == 'ROIC' and value is not None else value for value in values]
    fig.add_trace(go.Scatter(
        x=years,
        y=y_values,
        mode='lines+markers+text',
        line={'color': theme['accent_blue'], 'width': 2},
        marker={'size': 6, 'color': theme['accent_blue']},
        text=[_chart_text(value, label) for value in y_values],
        textposition='top center',
        textfont={'size': 9, 'color': theme['text_secondary']},
        hovertemplate='%{x}: %{y:,.2f}<extra></extra>',
    ))
    _add_trendline(fig, years, y_values, theme)
    fig.update_layout(
        paper_bgcolor=theme['bg_panel'],
        plot_bgcolor=theme['bg_primary'],
        margin={'l': 38, 'r': 8, 't': 4, 'b': 24},
        font={'family': FONT_MONO, 'size': 10, 'color': theme['text_secondary']},
        xaxis={'gridcolor': theme['chart_grid'], 'showline': True, 'linecolor': theme['border_primary']},
        yaxis={'gridcolor': theme['chart_grid'], 'showline': True, 'linecolor': theme['border_primary']},
        showlegend=False,
    )
    return fig


def _add_trendline(fig: go.Figure, years: list[int], values: list[float | None], theme: dict) -> None:
    pairs = [(year, value) for year, value in zip(years, values) if value is not None]
    if len(pairs) < 2:
        return
    x_values = [pair[0] for pair in pairs]
    y_values = [pair[1] for pair in pairs]
    slope, intercept = _linear_fit(x_values, y_values)
    fig.add_trace(go.Scatter(
        x=x_values,
        y=[slope * year + intercept for year in x_values],
        mode='lines',
        line={'color': theme['text_secondary'], 'width': 1.5, 'dash': 'dot'},
        hoverinfo='skip',
    ))


def _linear_fit(x_values: Sequence[float], y_values: Sequence[float]) -> tuple[float, float]:
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    if denominator == 0:
        return 0.0, y_mean
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / denominator
    return slope, y_mean - slope * x_mean


def _chart_text(value: float | None, label: str) -> str:
    if value is None:
        return ''
    if label == 'ROIC':
        return f'{value:.1f}%'
    return f'{value:,.0f}' if abs(value) >= 100 else f'{value:,.2f}'


def _quality_notes(notes: list[str], theme: dict) -> html.Div:
    return html.Div([
        html.Span('DATA QUALITY: ', style={'fontWeight': 700}),
        html.Span(' | '.join(notes or ['No notes'])),
    ], style={
        'marginTop': '0',
        'fontFamily': FONT_MONO,
        'fontSize': FONT_SIZES['xs'],
        'color': theme['text_secondary'],
    })


def _empty_state(theme: dict, message: str) -> html.Div:
    return html.Div(message, style={
        'fontFamily': FONT_MONO,
        'fontSize': FONT_SIZES['sm'],
        'color': theme['text_secondary'],
        'padding': '18px',
    })