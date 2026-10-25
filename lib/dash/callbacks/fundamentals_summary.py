"""Top of the fundamentals page: live price plus "estimated value vs price".

The three valuation models sit far down the page in separate tables, so the
verdict (is the stock above or below what each model says it is worth?) took
three scrolls to piece together. This strip pulls the headline numbers up.
"""

from __future__ import annotations

from typing import Any

from dash import html

from .fundamentals_formulas import _canonical_metric, _fmt_money


def parse_money(value: Any) -> float | None:
    """'$1,234.50' -> 1234.5; '--', 'n/a' and blanks -> None."""
    text = str(value or '').replace('$', '').replace(',', '').strip()
    if not text or text.lower() in {'--', 'n/a'}:
        return None
    try:
        number = float(text)
    except ValueError:
        return None
    return number if number == number else None


def _row_map(rows: list[dict[str, Any]] | None) -> dict[str, Any]:
    return {_canonical_metric(str(r.get('metric', ''))): r.get('value') for r in rows or []}


def value_estimates(annual: dict[str, Any]) -> list[dict[str, Any]]:
    """Per-share values from each model, in page order. Missing ones are skipped."""
    rule1 = _row_map(annual.get('valuation'))
    dcf = _row_map(annual.get('dcf'))
    analyst = _row_map(annual.get('analyst_targets'))
    candidates = [
        ('sticker', 'Rule #1 sticker', 'Fair value from 10y EPS growth', parse_money(rule1.get('Sticker Price')), None),
        ('entry', 'Rule #1 entry', 'Sticker minus the margin of safety', parse_money(rule1.get('Entry Price')), None),
        ('dcf', 'DCF fair value', 'Discounted free cash flow to equity', parse_money(dcf.get('DCF Fair Value')), None),
        ('analyst', 'Analyst target', 'Broker consensus (mean)', parse_money(analyst.get('Target Mean')),
         (parse_money(analyst.get('Target Low')), parse_money(analyst.get('Target High')))),
    ]
    out = []
    for key, label, hint, value, band in candidates:
        if value is None or value <= 0:
            continue
        item = {'key': key, 'label': label, 'hint': hint, 'value': value}
        if band and band[0] and band[1]:
            item['band'] = band
        out.append(item)
    return out


def _upside(value: float, price: float | None) -> tuple[str, str]:
    if not price:
        return '', 'flat'
    pct = value / price - 1
    cls = 'up' if pct > 0.005 else ('down' if pct < -0.005 else 'flat')
    return f'{pct * 100:+.0f}% vs price', cls


def _summary_strip(
    payload: dict[str, Any],
    active: dict[str, Any],
    period: str,
    theme: dict,
) -> html.Div:
    annual = payload.get('annual') if isinstance(payload.get('annual'), dict) else payload
    periods = active.get('years') or []
    last_period = periods[-1] if periods else '--'
    last_label = 'Last FY' if period == 'annual' else 'Last period'
    return html.Div([
        _price_hero_cell(payload, f'{last_label} {last_period}'),
        _value_summary(value_estimates(annual or {}), payload.get('last_price')),
    ], className='sfa-fundamentals-summary')


def _price_hero_cell(payload: dict[str, Any], period_text: str = '') -> html.Div:
    """Live last price and daily change.

    Falls back to '--' rather than fabricating a value when yfinance does
    not expose the live quote, so the gap is visible rather than masked as 0.
    """
    market_state = str(payload.get('market_state') or '').strip().upper()
    currency = payload.get('price_currency') or payload.get('currency') or 'USD'
    change_text, change_class = _format_change(payload.get('last_change'), payload.get('last_change_pct'))
    meta = [part for part in (_market_state_label(market_state), period_text, currency) if part]
    return html.Div([
        html.Div('LAST PRICE', className='sfa-fundamentals-hero-label'),
        html.Div([
            html.Span(_fmt_money(payload.get('last_price')), className='num sfa-fundamentals-hero-value'),
            html.Span(change_text, className=f'num sfa-fundamentals-hero-change {change_class}'),
        ], className='sfa-fundamentals-hero-line'),
        html.Div(' · '.join(meta), className='sfa-fundamentals-hero-state'),
    ], className='sfa-fundamentals-hero')


def _value_summary(estimates: list[dict[str, Any]], price: float | None) -> html.Div:
    head = html.Div([
        html.Span('Estimated value per share vs price', className='sfa-value-summary-title'),
        html.Span('Models disagree by design: read them side by side, not averaged.',
                  className='sfa-value-summary-hint'),
    ], className='sfa-value-summary-head')
    if not estimates:
        return html.Div([head, html.Div('No model produced a value for this symbol.',
                                        className='sfa-value-summary-hint')],
                        className='sfa-value-summary')
    chips = []
    for item in estimates:
        upside, cls = _upside(item['value'], price)
        lines = [
            html.Div([html.I(className=f'sfa-value-dot sfa-value-{item["key"]}'), item['label']],
                     className='sfa-value-chip-label', title=item['hint']),
            html.Div(_fmt_money(item['value']), className='num sfa-value-chip-value'),
            html.Div(upside, className=f'num sfa-value-chip-sub {cls}'),
        ]
        if item.get('band'):
            low, high = item['band']
            lines.append(html.Div(f'range {_fmt_money(low)}–{_fmt_money(high)}',
                                  className='num sfa-value-chip-range'))
        chips.append(html.Div(lines, className='sfa-value-chip'))
    return html.Div([
        head,
        html.Div(chips, className='sfa-value-chips'),
        _value_track(estimates, price),
    ], className='sfa-value-summary')


def _value_track(estimates: list[dict[str, Any]], price: float | None) -> html.Div:
    """One horizontal scale with a marker per model and a line at the price."""
    points = [e['value'] for e in estimates]
    for e in estimates:
        if e.get('band'):
            points.extend(e['band'])
    if price:
        points.append(price)
    lo, hi = min(points), max(points)
    span = (hi - lo) or hi or 1.0
    lo, hi = lo - span * 0.04, hi + span * 0.04

    def pos(value: float) -> str:
        return f'{(value - lo) / (hi - lo) * 100:.2f}%'

    children: list[Any] = [html.Div(className='sfa-value-track-rail')]
    for e in estimates:
        if e.get('band'):
            low, high = e['band']
            children.append(html.Div(className=f'sfa-value-track-band sfa-value-{e["key"]}',
                                     style={'left': pos(low), 'width': f'calc({pos(high)} - {pos(low)})'}))
    for e in estimates:
        children.append(html.Div(className=f'sfa-value-track-mark sfa-value-{e["key"]}',
                                 style={'left': pos(e['value'])},
                                 title=f'{e["label"]}: {_fmt_money(e["value"])}'))
    if price:
        children.append(html.Div(
            html.Span(f'Price {_fmt_money(price)}', className='num sfa-value-track-price-label'),
            className='sfa-value-track-price', style={'left': pos(price)},
        ))
    children.append(html.Span(_fmt_money(lo if lo > 0 else 0), className='num sfa-value-track-end sfa-value-track-end--lo'))
    children.append(html.Span(_fmt_money(hi), className='num sfa-value-track-end sfa-value-track-end--hi'))
    return html.Div(children, className='sfa-value-track')


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
        'REGULAR': 'Market open',
        'PRE': 'Pre-market',
        'POST': 'After-hours',
        'CLOSED': 'Market closed',
        'PREPRE': 'Pre-pre-market',
    }.get(state, '' if not state else f'Market · {state.title()}')
