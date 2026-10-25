"""Fundamentals page layout builders (tables, charts, summary)."""

from __future__ import annotations

from typing import Any, Sequence

from dash import dash_table, dcc, html

from lib.dash.dash_config import (
    DEFAULT_FUNDAMENTALS_PERIOD,
    FONT_FAMILY,
    FONT_SIZES,
    FUNDAMENTALS_PERIOD_OPTIONS,
)

# Charts and the top strip live in their own modules; re-exported so existing
# imports from this module keep working.
from .fundamentals_charts import (  # noqa: F401
    CHART_LABEL_MAX_POINTS,
    _chart_card,
    _chart_text,
    _metric_figure,
)
from .fundamentals_summary import (  # noqa: F401
    _format_change,
    _market_state_label,
    _price_hero_cell,
    _summary_strip,
)
from .fundamentals_formulas import (
    _FINANCIAL_EXPLAIN_MAP,
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
    analyst_rows = annual.get('analyst_targets', [])
    chart_labels = _period_column_labels(active.get('years', []))

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

    quality_band = _section_band(
        'Quality',
        'quality',
        html.Div([
            _panel_title('Big Five', theme),
            _big_five_legend(),
            _big_five_table(
                annual.get('big_five', []),
                _period_column_labels(annual.get('years', [])),
                theme,
            ),
        ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-big-five'),
    )

    growth_band = _section_band(
        'Growth',
        'growth',
        html.Div([
            _chart_card(label, values, chart_labels, theme)
            for label, values in active.get('chart_series', {}).items()
        ], className='sfa-fundamentals-charts'),
    )

    financials_band = _section_band(
        'Financials',
        'financials',
        html.Div([
            quarterly_notice,
            _financial_table(
                active.get('financials', []),
                period_labels,
                theme,
                last_price=payload.get('last_price'),
            ),
        ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-main'),
        header_extra=_period_toggle(active_period),
    )

    valuation_band = _section_band(
        'Valuation',
        'valuation',
        html.Div([
            html.Div([
                _panel_title('Rule #1', theme, size='sm'),
                _valuation_assumptions(valuation_rows, theme),
                _valuation_tables(valuation_rows, theme),
                html.Div(
                    id='fundamentals-valuation-explain',
                    className='sfa-valuation-explain',
                    style=_valuation_explain_style(theme, visible=False),
                ),
            ], style=_panel_style(theme), className=(
                'sfa-fundamentals-panel sfa-fundamentals-valuation '
                'sfa-fundamentals-valuation-rule1'
            )),
            html.Div([
                _panel_title('DCF (FCFE)', theme, size='sm'),
                _dcf_assumptions(dcf_rows, theme),
                _valuation_table(dcf_rows, theme, table_id='fundamentals-dcf-table'),
                _dcf_sensitivity_grid(dcf_sensitivity, theme),
            ], style=_panel_style(theme), className=(
                'sfa-fundamentals-panel sfa-fundamentals-valuation '
                'sfa-fundamentals-valuation-dcf'
            )),
            html.Div([
                _panel_title('Analyst Targets', theme, size='sm'),
                _analyst_targets_caption(theme, payload.get('ticker')),
                (
                    _valuation_table(
                        analyst_rows, theme, table_id='fundamentals-analyst-table'
                    )
                    if analyst_rows
                    else _analyst_targets_empty(theme, payload.get('ticker'))
                ),
            ], style=_panel_style(theme), className=(
                'sfa-fundamentals-panel sfa-fundamentals-valuation '
                'sfa-fundamentals-valuation-analyst'
            )),
        ], className='sfa-fundamentals-valuation-band'),
    )

    return html.Div([
        _summary_strip(payload, active, active_period, theme),
        quality_band,
        growth_band,
        financials_band,
        valuation_band,
        _quality_notes(payload.get('quality_notes', []), theme),
    ], style={'width': '100%', 'minWidth': 0}, className='sfa-fundamentals-root')


def _section_band(title: str, slug: str, body: Any, header_extra: Any = None) -> html.Section:
    header_children: list[Any] = [
        html.Div(title, className='sfa-fundamentals-band-title'),
    ]
    if header_extra is not None:
        header_children.append(header_extra)
    return html.Section(
        [
            html.Div(header_children, className='sfa-fundamentals-band-header'),
            body,
        ],
        className=f'sfa-fundamentals-band sfa-fundamentals-band-{slug}',
    )


def _period_toggle(period: str, *, hidden: bool = False) -> dcc.RadioItems:
    active = period if period in {'annual', 'quarterly'} else DEFAULT_FUNDAMENTALS_PERIOD
    kwargs: dict[str, Any] = {
        'id': 'fundamentals-period-toggle',
        'options': FUNDAMENTALS_PERIOD_OPTIONS,
        'value': active,
        'inline': True,
        'className': 'bbg-radio-seg sfa-fundamentals-period-toggle',
        'inputClassName': 'bbg-radio-seg-input',
        'labelClassName': 'bbg-radio-seg-label',
        'persistence': True,
        'persistence_type': 'session',
    }
    if hidden:
        kwargs['style'] = {'display': 'none'}
    return dcc.RadioItems(**kwargs)


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
    # No 'Last' column: it was '--' on every row but Stock Price, and the live
    # price now leads the page. `last_price` stays in the signature for callers.
    del last_price
    columns = [{'name': 'Metric', 'id': 'metric'}, {'name': 'Unit', 'id': 'unit'}] + [{'name': year, 'id': year} for year in years]
    enriched_rows = _with_display_units(rows)
    props: dict[str, Any] = {
        'id': 'fundamentals-financial-table',
        'columns': columns,
        'data': enriched_rows,
        'fill_width': True,
        'style_table': {'overflowX': 'auto', 'width': '100%', 'minWidth': '100%'},
        'style_cell': _table_cell_style(theme),
        'style_cell_conditional': _label_column_widths(),
        'style_header': _table_header_style(theme),
        'style_data_conditional': _financial_conditionals(theme),
        'fixed_columns': {'headers': True, 'data': 1},
        'tooltip_data': _financial_tooltips(enriched_rows, columns),
        'tooltip_delay': 0,
        'tooltip_duration': None,
    }
    return dash_table.DataTable(**props)


# Debt Ratio was written with unit 'y' (a typo for 'x'); payloads frozen before
# the fix (demo fixtures) still carry it.
_UNIT_FIXES = {'y': 'x'}


def _with_display_units(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    fixed = []
    for row in rows:
        unit = row.get('unit')
        fixed.append({**row, 'unit': _UNIT_FIXES.get(unit, unit)} if unit in _UNIT_FIXES else row)
    return fixed


def _label_column_widths() -> list[dict[str, Any]]:
    """Fixed-width label columns, so the year columns get the spare width
    (METRIC used to take 16-18% of a 1920px screen for 20-character names)."""
    return [
        {'if': {'column_id': 'metric'}, 'textAlign': 'left', 'fontWeight': 700,
         'width': '170px', 'minWidth': '150px', 'maxWidth': '190px'},
        {'if': {'column_id': 'unit'}, 'textAlign': 'center', 'color': 'var(--text-tertiary)',
         'width': '48px', 'minWidth': '44px', 'maxWidth': '52px'},
    ]


def _big_five_table(rows: list[dict[str, Any]], years: list[str], theme: dict) -> dash_table.DataTable:
    rows = _decorate_big_five_rows(_with_display_units(rows))
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
        'style_cell_conditional': _label_column_widths() + [
            {'if': {'column_id': '10Y'}, 'borderLeft': f'2px solid {theme["accent_blue"]}'},
        ],
        'style_header': _table_header_style(theme),
        'style_data_conditional': _big_five_conditionals(theme, years + ['10Y', '5Y', '1Y']),
        'tooltip_data': _financial_tooltips(rows, columns),
        'tooltip_delay': 0,
        'tooltip_duration': None,
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


def _big_five_legend() -> html.Div:
    """One line saying what the 10Y/5Y/1Y columns are and what the colours mean.

    Replaces the bare '↑ ≥10% · → 0–10% · ↓ ≤0' plus the payload's separate
    NOTE line, which said the same target in other words.
    """
    return html.Div([
        html.Span('10Y · 5Y · 1Y = average growth per year. Target: 10% or more every year. '),
        html.Span('↑ 10%+', className='sfa-legend-good'),
        html.Span('→ 0–10%', className='sfa-legend-warn'),
        html.Span('↓ shrinking', className='sfa-legend-bad'),
    ], className='sfa-fundamentals-legend')


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
    # Key results (the per-share values the top strip repeats) share one blue
    # highlight; Year-end Close is an input, so it is no longer painted red.
    normalized = _canonical_metric(metric)
    if normalized == 'Entry Price':
        return {'backgroundColor': f'{theme["accent_green"]}22', 'color': theme['accent_green'], 'fontWeight': 700}
    if normalized == 'Sticker Price':
        return {
            'backgroundColor': f'{theme["accent_blue"]}1F',
            'color': theme['accent_blue'],
            'fontWeight': 700,
        }
    if normalized == 'DCF Fair Value':
        return {
            'backgroundColor': f'{theme["accent_blue"]}1F',
            'color': theme['accent_blue'],
            'fontWeight': 700,
        }
    if normalized == 'Target Mean':
        return {
            'backgroundColor': f'{theme["accent_blue"]}1F',
            'color': theme['accent_blue'],
            'fontWeight': 700,
        }
    if normalized == 'Last Price':
        return {
            'backgroundColor': f'{theme["accent_orange"]}1F',
            'color': theme['accent_orange'],
            'fontWeight': 700,
        }
    return {}


def _signed_pct_conditionals(metric: str, theme: dict) -> list[dict[str, Any]]:
    """Color upside/downside pct rows: green when positive, red when negative."""
    escaped = _escape_filter(metric)
    # Green first for any %; red overrides when the value is negative.
    return [
        {
            'if': {
                'filter_query': f'{{metric}} = "{escaped}" && {{value}} contains "%"',
            },
            'backgroundColor': f'{theme["accent_green"]}22',
            'color': theme['accent_green'],
            'fontWeight': 700,
        },
        {
            'if': {
                'filter_query': (
                    f'{{metric}} = "{escaped}" && {{value}} contains "-" '
                    f'&& {{value}} != "--"'
                ),
            },
            'backgroundColor': f'{theme["accent_red"]}22',
            'color': theme['accent_red'],
            'fontWeight': 700,
        },
    ]


def _recommendation_conditionals(theme: dict) -> list[dict[str, Any]]:
    buy = ('Strong Buy', 'Buy', 'Outperform', 'Overweight')
    hold = ('Hold', 'Neutral', 'Equal Weight', 'Market Perform')
    sell = ('Sell', 'Strong Sell', 'Underperform', 'Underweight')
    conditionals: list[dict[str, Any]] = []
    for label in buy:
        conditionals.append({
            'if': {'filter_query': f'{{metric}} = "Recommendation" && {{value}} = "{label}"'},
            'backgroundColor': f'{theme["accent_green"]}22',
            'color': theme['accent_green'],
            'fontWeight': 700,
        })
    for label in hold:
        conditionals.append({
            'if': {'filter_query': f'{{metric}} = "Recommendation" && {{value}} = "{label}"'},
            'backgroundColor': f'{theme["accent_orange"]}22',
            'color': theme['accent_orange'],
            'fontWeight': 700,
        })
    for label in sell:
        conditionals.append({
            'if': {'filter_query': f'{{metric}} = "Recommendation" && {{value}} = "{label}"'},
            'backgroundColor': f'{theme["accent_red"]}22',
            'color': theme['accent_red'],
            'fontWeight': 700,
        })
    return conditionals


def _valuation_conditionals(theme: dict) -> list[dict[str, Any]]:
    conditionals = []
    styled_metrics = set()
    for metric in _VALUATION_EXPLAIN_MAP:
        style = _valuation_metric_style(metric, theme)
        if style:
            conditionals.append({'if': {'filter_query': f'{{metric}} = "{_escape_filter(metric)}"'}, **style})
            styled_metrics.add(_canonical_metric(metric))
    for metric in ('DCF Fair Value', 'Target Mean', 'Last Price'):
        if metric in styled_metrics:
            continue
        style = _valuation_metric_style(metric, theme)
        if style:
            conditionals.append({'if': {'filter_query': f'{{metric}} = "{_escape_filter(metric)}"'}, **style})
    conditionals.extend(_signed_pct_conditionals('Upside vs Price', theme))
    conditionals.extend(_signed_pct_conditionals('Upside vs Last', theme))
    conditionals.extend(_recommendation_conditionals(theme))
    conditionals.extend([
        {'if': {'state': 'active'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
        {'if': {'state': 'selected'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
    ])
    return conditionals


def _parse_money_cell(value: Any) -> float | None:
    text = str(value or '').replace('$', '').replace(',', '').strip()
    if not text or text in {'--', 'n/a', 'N/A'}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if number == number else None


def _sensitivity_conditionals(
    data: list[dict[str, Any]],
    value_columns: list[str],
    theme: dict,
) -> list[dict[str, Any]]:
    """Soft heatmap vs base-case (center) cell: above = green, below = red."""
    conditionals: list[dict[str, Any]] = []
    if not data or not value_columns:
        return [
            {'if': {'state': 'active'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
            {'if': {'state': 'selected'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
        ]

    mid_row = len(data) // 2
    mid_col = value_columns[len(value_columns) // 2]
    base = _parse_money_cell(data[mid_row].get(mid_col))

    # Mark base-case cell so the eye finds the model assumptions.
    conditionals.append({
        'if': {'row_index': mid_row, 'column_id': mid_col},
        'backgroundColor': f'{theme["accent_blue"]}28',
        'color': theme['accent_blue'],
        'fontWeight': 700,
        'border': f'1px solid {theme["accent_blue"]}',
    })

    if base is not None and base > 0:
        for row_index, row in enumerate(data):
            for column_id in value_columns:
                if row_index == mid_row and column_id == mid_col:
                    continue
                value = _parse_money_cell(row.get(column_id))
                if value is None:
                    continue
                if value > base * 1.02:
                    conditionals.append({
                        'if': {'row_index': row_index, 'column_id': column_id},
                        'backgroundColor': f'{theme["accent_green"]}1A',
                        'color': theme['accent_green'],
                    })
                elif value < base * 0.98:
                    conditionals.append({
                        'if': {'row_index': row_index, 'column_id': column_id},
                        'backgroundColor': f'{theme["accent_red"]}1A',
                        'color': theme['accent_red'],
                    })

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


def _yahoo_analysis_url(ticker: Any) -> str | None:
    symbol = str(ticker or '').strip().upper()
    if not symbol:
        return None
    return f'https://finance.yahoo.com/quote/{symbol}/analysis/'


def _yahoo_source_link(ticker: Any, theme: dict, *, label: str = 'Yahoo Finance') -> Any:
    url = _yahoo_analysis_url(ticker)
    if not url:
        return label
    return html.A(
        label,
        href=url,
        target='_blank',
        rel='noopener noreferrer',
        className='sfa-fundamentals-source-link',
        style={
            'color': theme.get('accent_cyan') or theme['accent_blue'],
            'textDecoration': 'underline',
            'textUnderlineOffset': '2px',
        },
    )


def _analyst_targets_caption(theme: dict, ticker: Any = None) -> html.Div:
    return html.Div(
        [
            _yahoo_source_link(ticker, theme),
            ' consensus — broker price targets, not a model fair value. ',
            _yahoo_source_link(ticker, theme, label='Open analysis ↗'),
        ],
        className='sfa-valuation-assumption',
        style={
            'fontFamily': FONT_FAMILY,
            'fontSize': FONT_SIZES['sm'],
            'color': theme['text_secondary'],
            'lineHeight': '1.4',
            'marginBottom': '6px',
        },
    )


def _analyst_targets_empty(theme: dict, ticker: Any = None) -> html.Div:
    children: list[Any] = ['No ']
    children.append(_yahoo_source_link(ticker, theme, label='Yahoo'))
    children.append(' consensus targets for this symbol.')
    url = _yahoo_analysis_url(ticker)
    if url:
        children.extend([' ', _yahoo_source_link(ticker, theme, label='Open analysis')])
    return html.Div(
        children,
        className='sfa-valuation-assumption',
        style={
            'fontFamily': FONT_FAMILY,
            'fontSize': FONT_SIZES['sm'],
            'color': theme['text_secondary'],
            'lineHeight': '1.4',
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

    value_columns = [column['id'] for column in columns if column['id'] != 'discount_rate']
    return html.Div([
        html.Div(
            'Sensitivity (fair value / share) — center = base case',
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
            style_data_conditional=_sensitivity_conditionals(data, value_columns, theme),
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
        what = str(explain.get('what') or explain.get('explanation') or metric).strip()
        if len(what) > 110:
            what = what[:107].rstrip() + '...'
        tooltip_text = f"{what}\nClick for formula & sources."
        tooltip_rows.append({
            'metric': {'value': tooltip_text, 'type': 'text'},
            'value': {'value': tooltip_text, 'type': 'text'},
        })
    return tooltip_rows


def _financial_tooltip_text(metric: str) -> str:
    canonical = _canonical_metric(metric)
    explain = _FINANCIAL_EXPLAIN_MAP.get(canonical) or _VALUATION_EXPLAIN_MAP.get(canonical)
    if not explain:
        return canonical
    what = str(explain.get('what') or explain.get('explanation') or canonical).strip()
    if len(what) > 160:
        what = what[:157].rstrip() + '...'
    return what


def _financial_tooltips(
    rows: list[dict[str, Any]],
    columns: list[dict[str, Any]],
) -> list[dict[str, dict[str, str]]]:
    """Hover help for each row; mirrored across columns so fixed metric clones still tip."""
    column_ids = [str(col.get('id')) for col in columns if col.get('id')] or ['metric']
    tooltip_rows: list[dict[str, dict[str, str]]] = []
    for row in rows:
        metric = str(row.get('metric', '')).strip()
        tip = {'value': _financial_tooltip_text(metric), 'type': 'text'}
        tooltip_rows.append({cid: tip for cid in column_ids})
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
    # Plain zebra rows. The old cyan/orange group fills had no key on screen,
    # so they read as warnings. The debt block keeps a divider above it.
    return [
        {'if': {'row_index': 'odd'}, 'backgroundColor': theme['table_row_alt']},
        {'if': {'filter_query': '{metric} = "Stock Price (FYE)"'}, 'fontWeight': 700},
        {'if': {'filter_query': '{metric} = "Current Debt (Liab)"'}, 'borderTop': f'2px solid {theme["border_primary"]}'},
        {'if': {'filter_query': '{metric} = "Debt Ratio"'}, 'borderTop': f'2px solid {theme["border_primary"]}'},
        {'if': {'state': 'active'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
        {'if': {'state': 'selected'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
    ]


def _big_five_conditionals(theme: dict, value_columns: list[str]) -> list[dict[str, Any]]:
    conditionals = [
        {'if': {'row_index': 'odd'}, 'backgroundColor': theme['table_row_alt']},
        # Debt Ratio and PE are context, not growth rates: set them apart.
        {'if': {'filter_query': '{metric} = "Debt Ratio"'}, 'borderTop': f'2px solid {theme["border_primary"]}'},
    ]
    for column in value_columns:
        conditionals.append(
            {'if': {'column_id': column, 'filter_query': f'{{{column}}} contains "--"'}, 'color': theme['text_tertiary']},
        )
    for summary_label in ('10Y', '5Y', '1Y'):
        status_key = f'status_{summary_label}'
        conditionals.extend([
            {'if': {'column_id': summary_label, 'filter_query': f'{{{status_key}}} = "good"'}, 'backgroundColor': f'{theme["accent_green"]}22', 'color': theme['accent_green'], 'fontWeight': 700},
            {'if': {'column_id': summary_label, 'filter_query': f'{{{status_key}}} = "warn"'}, 'backgroundColor': f'{theme["accent_orange"]}22', 'color': theme['accent_orange'], 'fontWeight': 700},
            {'if': {'column_id': summary_label, 'filter_query': f'{{{status_key}}} = "bad"'}, 'backgroundColor': f'{theme["accent_red"]}22', 'color': theme['accent_red'], 'fontWeight': 700},
        ])
    conditionals.extend([
        {'if': {'state': 'active'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
        {'if': {'state': 'selected'}, 'backgroundColor': theme['table_row_hover'], 'border': f'1px solid {theme["accent_blue"]}', 'color': theme['text_primary']},
    ])
    return conditionals


def _quality_notes(notes: list[str], theme: dict) -> html.Details:
    """Sources and caveats, one per line, folded by default.

    Was a single ' | '-joined line that ran off the right edge.
    """
    del theme  # styled by 50-fundamentals.css
    notes = [str(n) for n in notes or [] if str(n).strip()]
    return html.Details([
        html.Summary([
            html.Span('Data quality & sources'),
            html.Span(f'{len(notes)} note{"s" if len(notes) != 1 else ""}',
                      className='sfa-fundamentals-notes-count'),
        ]),
        html.Ul([html.Li(note) for note in notes] or [html.Li('No notes')]),
    ], className='sfa-fundamentals-notes')


def _empty_state(theme: dict, message: str) -> html.Div:
    return html.Div([
        html.Div(message, style={
            'fontFamily': FONT_FAMILY,
            'fontSize': FONT_SIZES['sm'],
            'color': theme['text_secondary'],
            'padding': '18px',
        }),
        # Keep the period Input mounted when Financials is unavailable.
        _period_toggle(DEFAULT_FUNDAMENTALS_PERIOD, hidden=True),
    ])

