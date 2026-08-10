"""Fundamentals page layout builders (tables, charts, summary)."""

from __future__ import annotations

from typing import Any, Sequence

from dash import dash_table, dcc, html
import plotly.graph_objects as go

from lib.dash.dash_config import (
    DEFAULT_FUNDAMENTALS_PERIOD,
    FONT_FAMILY,
    FONT_SIZES,
)

from .fundamentals_formulas import (
    _VALUATION_EXPLAIN_MAP,
    _canonical_metric,
    _escape_filter,
    _fmt_money,
    _split_valuation_rows,
    _valuation_explain_style,
)

def _resolve_payload_blocks(payload: dict[str, Any], period: str) -> tuple[dict[str, Any], dict[str, Any], str]:
    annual = payload.get('annual') if isinstance(payload.get('annual'), dict) else payload
    quarterly = payload.get('quarterly') if isinstance(payload.get('quarterly'), dict) else {}
    active_period = period if period in {'annual', 'quarterly'} else DEFAULT_FUNDAMENTALS_PERIOD
    active = annual if active_period == 'annual' else quarterly
    return annual or {}, active or {}, active_period


def _period_column_labels(years: list[Any]) -> list[str]:
    return [str(year) for year in years]


def _render_payload(payload: dict[str, Any], period: str, theme: dict) -> html.Div:
    annual, active, active_period = _resolve_payload_blocks(payload, period)
    if not annual:
        return _empty_state(theme, "No fundamentals data available.")

    period_labels = _period_column_labels(active.get('years', []))
    valuation_rows = annual.get('valuation', [])
    dcf_rows = annual.get('dcf', [])
    dcf_sensitivity = annual.get('dcf_sensitivity', [])
    chart_years = active.get('years', [])
    chart_labels = _period_column_labels(chart_years)

    if active_period == 'quarterly' and not active.get('financials'):
        quarterly_notice = html.Div(
            'Quarterly financials are unavailable for this symbol.',
            style={
                'fontFamily': FONT_FAMILY,
                'fontSize': FONT_SIZES['xs'],
                'color': theme['accent_orange'],
                'marginBottom': '6px',
            },
        )
    else:
        quarterly_notice = None

    financials_panel = html.Div([
        _panel_title('Financials', theme),
        quarterly_notice,
        _financial_table(
            active.get('financials', []),
            period_labels,
            theme,
            last_price=payload.get('last_price'),
        ),
    ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-main')

    return html.Div([
        _summary_strip(payload, active, active_period, theme),
        html.Div([
            financials_panel,
            html.Div([
                _panel_title('Valuation', theme, size='sm'),
                _valuation_assumptions(valuation_rows, theme),
                _valuation_tables(valuation_rows, theme),
                _panel_title('DCF (FCFE)', theme, size='sm'),
                _dcf_assumptions(dcf_rows, theme),
                _valuation_table(dcf_rows, theme, table_id='fundamentals-dcf-table'),
                _dcf_sensitivity_grid(dcf_sensitivity, theme),
                html.Div(
                    id='fundamentals-valuation-explain',
                    className='sfa-valuation-explain',
                    style=_valuation_explain_style(theme, visible=False),
                ),
            ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-side sfa-fundamentals-valuation'),
        ], className='sfa-fundamentals-top'),
        html.Div([
            _panel_title('Big Five', theme),
            _big_five_note(annual.get('big_five_note', ''), theme),
            _big_five_table(
                annual.get('big_five', []),
                _period_column_labels(annual.get('years', [])),
                theme,
            ),
        ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-big-five'),
        html.Div([
            _chart_card(label, values, chart_labels, theme)
            for label, values in active.get('chart_series', {}).items()
        ], className='sfa-fundamentals-charts'),
        _quality_notes(payload.get('quality_notes', []), theme),
    ], style={'width': '100%', 'minWidth': 0}, className='sfa-fundamentals-root')


def _summary_strip(
    payload: dict[str, Any],
    active: dict[str, Any],
    period: str,
    theme: dict,
) -> html.Div:
    periods = active.get('years') or []
    last_period = periods[-1] if periods else '--'
    last_label = 'Last FY' if period == 'annual' else 'Last period'
    return html.Div([
        _price_hero_cell(payload, theme),
        _summary_cell('Ticker', payload.get('ticker', '--'), theme),
        _summary_cell('Currency', payload.get('currency', '--'), theme),
        _summary_cell(last_label, last_period, theme),
        _summary_cell('Updated', payload.get('as_of', '--'), theme),
    ], style={
        'display': 'grid',
    }, className='sfa-fundamentals-summary')


def _summary_cell(label: str, value: Any, theme: dict) -> html.Div:
    return html.Div([
        html.Div(label, style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'fontFamily': FONT_FAMILY}),
        html.Div(str(value), className='num', style={'fontSize': FONT_SIZES['sm'], 'color': theme['text_primary']}),
    ], style={
        'backgroundColor': theme['bg_tertiary'],
        'border': f'1px solid {theme["border_primary"]}',
        'padding': '5px 7px',
        'minWidth': 0,
    })


def _price_hero_cell(payload: dict[str, Any], theme: dict) -> html.Div:
    """Hero cell showing the live last price and daily change.

    Falls back to '--' rather than fabricating a value when yfinance does
    not expose the live quote, so the user can immediately tell that the
    data provider did not return it (rather than masking the gap with 0).
    """
    last_price = payload.get('last_price')
    change = payload.get('last_change')
    change_pct = payload.get('last_change_pct')
    market_state = str(payload.get('market_state') or '').strip().upper()
    currency = payload.get('price_currency') or payload.get('currency') or 'USD'

    price_text = _fmt_money(last_price)
    change_text, change_class = _format_change(change, change_pct)
    state_text = _market_state_label(market_state)

    return html.Div([
        html.Div('LAST PRICE', className='sfa-fundamentals-hero-label'),
        html.Div(price_text, className='num sfa-fundamentals-hero-value'),
        html.Div([
            html.Span(change_text, className=f'sfa-fundamentals-hero-change {change_class}'),
            html.Span(f' {currency}', className='sfa-fundamentals-hero-state'),
        ]),
        html.Div(state_text, className='sfa-fundamentals-hero-state'),
    ], className='sfa-fundamentals-hero')


def _format_change(change: float | None, change_pct: float | None) -> tuple[str, str]:
    if change is None and change_pct is None:
        return '--', 'flat'
    sign = ''
    cls = 'flat'
    if isinstance(change, (int, float)) and change > 0:
        sign = '+'
        cls = 'up'
    elif isinstance(change, (int, float)) and change < 0:
        cls = 'down'
    change_part = f'{sign}{change:,.2f}' if isinstance(change, (int, float)) else '--'
    pct_part = (
        f' ({sign}{(change_pct * 100):.2f}%)'
        if isinstance(change_pct, (int, float))
        else ''
    )
    return f'{change_part}{pct_part}', cls


def _market_state_label(state: str) -> str:
    return {
        'REGULAR': 'Market · Regular session',
        'PRE': 'Pre-market',
        'POST': 'After-hours',
        'CLOSED': 'Market closed',
        'PREPRE': 'Pre-pre-market',
    }.get(state, '' if not state else f'Market · {state.title()}')


def _panel_title(title: str, theme: dict, *, size: str = 'xs') -> html.Div:
    return html.Div(title, style={
        'fontFamily': FONT_FAMILY,
        'fontSize': FONT_SIZES.get(size, FONT_SIZES['xs']),
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


def _financial_table(
    rows: list[dict[str, Any]],
    years: list[str],
    theme: dict,
    *,
    last_price: float | None = None,
) -> dash_table.DataTable:
    columns = [{'name': 'Metric', 'id': 'metric'}, {'name': 'Unit', 'id': 'unit'}] + [{'name': year, 'id': year} for year in years]
    enriched_rows = _decorate_financial_rows_with_last(rows, last_price)
    columns.append({'name': 'Last', 'id': 'Last'})
    props: dict[str, Any] = {
        'id': 'fundamentals-financial-table',
        'columns': columns,
        'data': enriched_rows,
        'fill_width': True,
        'style_table': {'overflowX': 'auto', 'width': '100%', 'minWidth': '100%'},
        'style_cell': _table_cell_style(theme),
        'style_cell_conditional': [
            {'if': {'column_id': 'metric'}, 'textAlign': 'left', 'fontWeight': 700, 'minWidth': '165px', 'width': '18%'},
            {'if': {'column_id': 'unit'}, 'textAlign': 'center', 'width': '52px', 'maxWidth': '58px'},
            {'if': {'column_id': 'Last'}, 'textAlign': 'right', 'width': '78px', 'maxWidth': '90px', 'fontFamily': 'IBM Plex Mono, monospace', 'fontVariantNumeric': 'tabular-nums'},
        ],
        'style_header': _table_header_style(theme),
        'style_data_conditional': _financial_conditionals(theme),
        'fixed_columns': {'headers': True, 'data': 1},
    }
    return dash_table.DataTable(**props)


def _decorate_financial_rows_with_last(
    rows: list[dict[str, Any]],
    last_price: float | None,
) -> list[dict[str, Any]]:
    """Inject a 'Last' column. Only the Stock Price (31/12) row shows the live
    value; the rest stay at '--' so the column semantics are unambiguous."""
    enriched: list[dict[str, Any]] = []
    for row in rows:
        new_row = dict(row)
        metric = str(new_row.get('metric', '')).strip()
        if metric == 'Stock Price (31/12)' and last_price is not None:
            new_row['Last'] = f'${float(last_price):,.2f}'
        else:
            new_row['Last'] = '--'
        enriched.append(new_row)
    return enriched


def _big_five_table(rows: list[dict[str, Any]], years: list[str], theme: dict) -> dash_table.DataTable:
    rows = _decorate_big_five_rows(rows)
    columns = [{'name': 'Metric', 'id': 'metric'}, {'name': 'Unit', 'id': 'unit'}]
    columns += [{'name': year, 'id': year} for year in years]
    columns += [{'name': label, 'id': label} for label in ('10Y', '5Y', '1Y')]
    props: dict[str, Any] = {
        'id': 'fundamentals-big-five-table',
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
        'fontFamily': FONT_FAMILY,
        'fontSize': FONT_SIZES['xs'],
        'fontWeight': 700,
        'color': theme['accent_red'],
        'marginBottom': '4px',
        'lineHeight': '1.25',
    })


def _valuation_tables(rows: list[dict[str, Any]], theme: dict) -> html.Div:
    rows_a, rows_b = _split_valuation_rows(rows)
    return html.Div([
        _valuation_table(rows_a, theme, table_id='fundamentals-valuation-table-a'),
        _valuation_table(rows_b, theme, table_id='fundamentals-valuation-table-b'),
    ], className='sfa-valuation-grid')


def _valuation_table(rows: list[dict[str, Any]], theme: dict, *, table_id: str) -> dash_table.DataTable:
    columns = [{'name': 'Metric', 'id': 'metric'}, {'name': 'Value', 'id': 'value'}]
    props: dict[str, Any] = {
        'id': table_id,
        'columns': columns,
        'data': rows,
        'fill_width': True,
        'style_table': {'overflowX': 'auto', 'width': '100%', 'minWidth': '100%'},
        'style_cell': _valuation_table_cell_style(theme),
        'style_cell_conditional': [
            {'if': {'column_id': 'metric'}, 'textAlign': 'left', 'fontWeight': 700, 'minWidth': '128px', 'width': '58%'},
            {'if': {'column_id': 'value'}, 'textAlign': 'right', 'width': '42%', 'fontWeight': 600},
        ],
        'style_header': _valuation_table_header_style(theme),
        'style_data_conditional': _valuation_conditionals(theme),
        'tooltip_data': _valuation_tooltips(rows),
        'tooltip_duration': None,
    }
    return dash_table.DataTable(**props)


def _valuation_table_cell_style(theme: dict) -> dict[str, Any]:
    return {
        'textAlign': 'right',
        'padding': '6px 9px',
        'backgroundColor': theme['bg_tertiary'],
        'color': theme['text_primary'],
        'border': f'1px solid {theme["border_secondary"]}',
        'fontSize': FONT_SIZES['base'],
        'fontFamily': FONT_FAMILY,
        'fontVariantNumeric': 'tabular-nums',
        'whiteSpace': 'nowrap',
        'lineHeight': '20px',
        'height': '30px',
        'minHeight': '30px',
        'maxHeight': '30px',
        'overflow': 'hidden',
        'textOverflow': 'ellipsis',
    }


def _valuation_table_header_style(theme: dict) -> dict[str, Any]:
    return {
        'fontWeight': 700,
        'backgroundColor': theme['bg_secondary'],
        'color': theme['text_secondary'],
        'textTransform': 'uppercase',
        'fontSize': FONT_SIZES['sm'],
        'fontFamily': FONT_FAMILY,
        'border': f'1px solid {theme["border_primary"]}',
        'height': '28px',
        'minHeight': '28px',
        'maxHeight': '28px',
        'lineHeight': '20px',
    }


def _table_cell_style(theme: dict) -> dict[str, Any]:
    return {
        'textAlign': 'right',
        'padding': '5px 7px',
        'backgroundColor': theme['bg_tertiary'],
        'color': theme['text_primary'],
        'border': f'1px solid {theme["border_secondary"]}',
        'fontSize': '12px',
        'fontFamily': FONT_FAMILY,
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


def _valuation_metric_style(metric: str, theme: dict) -> dict[str, Any]:
    normalized = _canonical_metric(metric)
    if normalized == 'Year-end Close':
        return {'backgroundColor': f'{theme["accent_red"]}25', 'color': theme['accent_red']}
    if normalized == 'Entry Price':
        return {'backgroundColor': f'{theme["accent_green"]}22', 'color': theme['accent_green']}
    if normalized == 'Fut. Market Price (10 Y)':
        return {'backgroundColor': f'{theme["accent_blue"]}18'}
    if normalized == 'Sticker Price':
        return {'backgroundColor': f'{theme["accent_blue"]}12'}
    return {}


def _valuation_conditionals(theme: dict) -> list[dict[str, Any]]:
    conditionals = []
    for metric in _VALUATION_EXPLAIN_MAP:
        style = _valuation_metric_style(metric, theme)
        if style:
            conditionals.append({'if': {'filter_query': f'{{metric}} = "{_escape_filter(metric)}"'}, **style})
    conditionals.extend([
        {'if': {'state': 'active'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
        {'if': {'state': 'selected'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
    ])
    return conditionals


def _valuation_assumptions(rows: list[dict[str, Any]], theme: dict) -> html.Div:
    row_map = {str(row.get('metric', '')): str(row.get('value', '--')) for row in rows}
    marr = row_map.get('MARR', '--')
    mos = row_map.get('MOS', '--')
    return html.Div(
        f"Assumptions: MARR {marr} | MOS {mos}. Select a cell to view formula sources.",
        className='sfa-valuation-assumption',
        style={
            'fontFamily': FONT_FAMILY,
            'fontSize': FONT_SIZES['sm'],
            'color': theme['text_secondary'],
            'lineHeight': '1.4',
            'marginBottom': '6px',
        },
    )


def _dcf_assumptions(rows: list[dict[str, Any]], theme: dict) -> html.Div:
    row_map = {str(row.get('metric', '')): str(row.get('value', '--')) for row in rows}
    if not rows:
        text = 'DCF unavailable for this symbol (needs positive FCFE and share count).'
    else:
        text = (
            f"Assumptions: r {row_map.get('Cost of Equity', '--')} | "
            f"g1 {row_map.get('Stage 1 FCFE GR', '--')} | "
            f"g2 {row_map.get('Terminal GR', '--')}. "
            "Sibling of Rule #1 — not averaged."
        )
    return html.Div(
        text,
        className='sfa-valuation-assumption',
        style={
            'fontFamily': FONT_FAMILY,
            'fontSize': FONT_SIZES['sm'],
            'color': theme['text_secondary'],
            'lineHeight': '1.4',
            'marginTop': '10px',
            'marginBottom': '6px',
        },
    )


def _dcf_sensitivity_grid(grid: list[dict[str, Any]], theme: dict) -> html.Div:
    """Render discount-rate × terminal-growth fair-value matrix."""
    if not grid:
        return html.Div(id='fundamentals-dcf-sensitivity', style={'display': 'none'})

    growths: list[float] = []
    for cell in grid[0].get('cells', []):
        growths.append(float(cell.get('terminal_growth', 0.0)))

    columns = [{'name': 'r \\ g₂', 'id': 'discount_rate'}]
    for growth in growths:
        col_id = f'g_{growth:.4f}'
        columns.append({'name': f'{growth * 100:.1f}%', 'id': col_id})

    data: list[dict[str, Any]] = []
    for row in grid:
        rate = float(row.get('discount_rate', 0.0))
        record: dict[str, Any] = {'discount_rate': f'{rate * 100:.1f}%'}
        for cell in row.get('cells', []):
            growth = float(cell.get('terminal_growth', 0.0))
            value = cell.get('value_per_share')
            try:
                numeric = float(value)
                display = f'${numeric:,.2f}' if numeric == numeric else 'n/a'
            except (TypeError, ValueError):
                display = 'n/a'
            record[f'g_{growth:.4f}'] = display
        data.append(record)

    return html.Div([
        html.Div(
            'Sensitivity (fair value / share)',
            style={
                'fontFamily': FONT_FAMILY,
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_secondary'],
                'marginTop': '8px',
                'marginBottom': '4px',
            },
        ),
        dash_table.DataTable(
            id='fundamentals-dcf-sensitivity',
            columns=columns,
            data=data,
            fill_width=True,
            style_table={'overflowX': 'auto', 'width': '100%'},
            style_cell=_valuation_table_cell_style(theme),
            style_header=_valuation_table_header_style(theme),
            style_cell_conditional=[
                {
                    'if': {'column_id': 'discount_rate'},
                    'textAlign': 'left',
                    'fontWeight': 700,
                    'width': '22%',
                },
            ],
            style_data_conditional=_valuation_conditionals(theme),
        ),
    ], className='sfa-dcf-sensitivity')


def _valuation_tooltips(rows: list[dict[str, Any]]) -> list[dict[str, dict[str, str]]]:
    tooltip_rows: list[dict[str, dict[str, str]]] = []
    for row in rows:
        metric = _canonical_metric(str(row.get('metric', '')))
        explain = _VALUATION_EXPLAIN_MAP.get(metric)
        if not explain:
            tooltip_rows.append({
                'metric': {'value': metric, 'type': 'text'},
                'value': {'value': metric, 'type': 'text'},
            })
            continue
        tooltip_text = f"{explain.get('what', explain['explanation'])}\n{explain.get('why_use', explain['explanation'])}"
        tooltip_rows.append({
            'metric': {'value': tooltip_text, 'type': 'text'},
            'value': {'value': tooltip_text, 'type': 'text'},
        })
    return tooltip_rows


def _big_five_value_columns(columns: list[dict[str, Any]] | None) -> list[str]:
    if not columns:
        return ['10Y', '5Y', '1Y']
    return [
        str(column.get('id'))
        for column in columns
        if str(column.get('id')) not in {'metric', 'unit', 'status_10Y', 'status_5Y', 'status_1Y'}
    ]


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
        {'if': {'filter_query': '{metric} = "Stock Price (31/12)"'}, 'backgroundColor': f'{theme["accent_orange"]}24', 'fontWeight': 700},
        {'if': {'column_id': 'Last', 'filter_query': '{Last} != "--"'}, 'backgroundColor': f'{theme["accent_orange"]}30', 'color': theme['accent_orange'], 'fontWeight': 700},
        {'if': {'column_id': 'Last', 'filter_query': '{Last} = "--"'}, 'color': theme['text_tertiary']},
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


def _chart_card(label: str, values: list[float | None], years: list[Any], theme: dict) -> html.Div:
    return html.Div([
        _panel_title(label, theme),
        dcc.Graph(figure=_metric_figure(label, values, years, theme), config={'displayModeBar': False}, style={'height': 'clamp(145px, 19vh, 190px)'}),
    ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-chart')


def _metric_figure(label: str, values: list[float | None], years: list[Any], theme: dict) -> go.Figure:
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
        font={'family': FONT_FAMILY, 'size': 11, 'color': theme['text_secondary']},
        xaxis={'gridcolor': theme['chart_grid'], 'showline': True, 'linecolor': theme['border_primary']},
        yaxis={'gridcolor': theme['chart_grid'], 'showline': True, 'linecolor': theme['border_primary']},
        showlegend=False,
    )
    return fig


def _add_trendline(fig: go.Figure, years: list[Any], values: list[float | None], theme: dict) -> None:
    pairs = [(index, value) for index, value in enumerate(values) if value is not None]
    if len(pairs) < 2:
        return
    x_values = [pair[0] for pair in pairs]
    y_values = [pair[1] for pair in pairs]
    slope, intercept = _linear_fit(x_values, y_values)
    fig.add_trace(go.Scatter(
        x=[years[index] for index in x_values],
        y=[slope * index + intercept for index in x_values],
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
        'fontFamily': FONT_FAMILY,
        'fontSize': FONT_SIZES['xs'],
        'color': theme['text_secondary'],
    })


def _empty_state(theme: dict, message: str) -> html.Div:
    return html.Div(message, style={
        'fontFamily': FONT_FAMILY,
        'fontSize': FONT_SIZES['sm'],
        'color': theme['text_secondary'],
        'padding': '18px',
    })

