"""Fundamentals page callbacks."""

from __future__ import annotations

import logging
from typing import Any, Sequence

from dash import callback_context, dash_table, dcc, html, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from lib.dash.routes import is_fundamentals_route
from lib.dash.callbacks.startup import _ensure_ticker_options_loaded
from lib.dash.dash_config import (
    DEFAULT_THEME,
    DEFAULT_TICKER,
    FONT_FAMILY,
    FONT_SIZES,
    FUNDAMENTALS_FALLBACK_TICKER,
    get_theme,
)
from lib.dash.ticker_search import resolve_ticker_symbol
from lib.fundamentals import fetch_fundamentals

logger = logging.getLogger(__name__)

_METRIC_ALIASES = {
    'Current Price': 'Year-end Close',
    'Current/Entry price ratio': 'Close/Entry price ratio',
}

_VALUATION_EXPLAIN_MAP: dict[str, dict[str, Any]] = {
    "Analysts' GR": {
        'what': 'The growth rate implied by analyst and market data (earnings, revenue, or quarterly earnings growth).',
        'why_use': 'Forward-looking growth anchors the earnings projection when you do not want to rely only on past financials.',
        'formula': 'Analysts\' GR comes from earningsGrowth, revenueGrowth, or earningsQuarterlyGrowth when available.',
        'explanation': 'We take the first usable growth field from the data provider, in that priority order.',
        'sources': {'valuation': [], 'financial': [], 'big_five': []},
        'inputs': ['yfinance info: earningsGrowth/revenueGrowth/earningsQuarterlyGrowth'],
    },
    'Historical Equity GR': {
        'what': 'The compound annual growth rate of shareholders\' equity over the last ten years.',
        'why_use': 'Equity growth is a stable, historical signal used when analyst growth is missing or unreliable.',
        'formula': 'Historical Equity GR = 10Y CAGR of equity.',
        'explanation': 'Computed from the equity series in financial statements (Big Five / financials tables).',
        'sources': {'valuation': [], 'financial': ['Equity'], 'big_five': ['Equity-GR']},
        'inputs': [],
    },
    'Estimated EPS GR': {
        'what': 'A conservative earnings growth rate chosen from analyst, equity, and historical EPS growth.',
        'why_use': 'Rule #1-style valuation needs one prudent growth input; we cap optimism so projections stay realistic.',
        'formula': 'Estimated EPS GR = min(positive Analysts\' GR, Historical Equity GR, historical EPS CAGR), capped at 50%.',
        'explanation': 'We use the minimum of positive candidates, then cap at 50% to avoid extreme compound projections.',
        'sources': {'valuation': ["Analysts' GR", 'Historical Equity GR'], 'financial': ['EPS'], 'big_five': ['EPS-GR']},
        'inputs': [],
    },
    'Current EPS': {
        'what': 'Earnings per share for the latest period—what the company earns per share today.',
        'why_use': 'Every future EPS and price estimate starts from a current earnings baseline.',
        'formula': 'Current EPS = trailingEps from info when available, otherwise latest annual EPS.',
        'explanation': 'Trailing EPS from market data is preferred; otherwise we use the latest annual EPS from statements.',
        'sources': {'valuation': [], 'financial': ['EPS'], 'big_five': []},
        'inputs': ['yfinance info: trailingEps'],
    },
    'Estimated EPS 10y': {
        'what': 'Projected EPS ten years from now, assuming constant growth at Estimated EPS GR.',
        'why_use': 'A terminal earnings figure is required to estimate a fair future share price.',
        'formula': 'Estimated EPS 10y = Current EPS * (1 + Estimated EPS GR)^10.',
        'explanation': 'Standard compound growth over ten years from current EPS and the selected growth rate.',
        'sources': {'valuation': ['Current EPS', 'Estimated EPS GR'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Rule #1st Price/Earn Ratio': {
        'what': 'A P/E multiple derived from growth: growth rate × 200 (Phil Town Rule #1 heuristic).',
        'why_use': 'Links how fast earnings can grow to a plausible ceiling on the price/earnings ratio.',
        'formula': 'Rule #1st Price/Earn Ratio = max(0, Estimated EPS GR * 200).',
        'explanation': 'Negative growth yields zero; otherwise growth (as a decimal) is multiplied by 200.',
        'sources': {'valuation': ['Estimated EPS GR'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Forward Price/Earn Ratio': {
        'what': 'The market\'s forward price-to-earnings ratio from live quote data.',
        'why_use': 'Shows what investors are currently willing to pay for next-year earnings.',
        'formula': 'Forward Price/Earn Ratio = forwardPE from market info.',
        'explanation': 'Taken directly from the data provider\'s forward P/E field when available.',
        'sources': {'valuation': [], 'financial': [], 'big_five': []},
        'inputs': ['yfinance info: forwardPE'],
    },
    'Historical PE': {
        'what': 'The average P/E ratio over the last ten annual observations.',
        'why_use': 'Long-run average valuation helps avoid using a single unusually high or low year.',
        'formula': 'Historical PE = mean of last 10 annual PE values.',
        'explanation': 'A simple mean of annual P/E from financials / Big Five history.',
        'sources': {'valuation': [], 'financial': ['PE Ratio'], 'big_five': ['PE Ratio']},
        'inputs': [],
    },
    'Rule #1 PE': {
        'what': 'The most conservative (lowest) P/E among the Rule #1, forward, and historical estimates.',
        'why_use': 'Using the minimum P/E keeps the intrinsic value estimate cautious.',
        'formula': 'Rule #1 PE = min(Rule #1st Price/Earn Ratio, Forward Price/Earn Ratio, Historical PE).',
        'explanation': 'Only positive P/E candidates are considered; the smallest value is selected.',
        'sources': {'valuation': ['Rule #1st Price/Earn Ratio', 'Forward Price/Earn Ratio', 'Historical PE'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'PEG': {
        'what': 'Price/earnings-to-growth: P/E divided by growth (expressed as a percentage).',
        'why_use': 'A quick check that the chosen P/E is reasonable relative to expected earnings growth.',
        'formula': 'PEG = Rule #1 PE / (Estimated EPS GR * 100).',
        'explanation': 'Values near 1.0 are often seen as “fair”; much higher suggests rich valuation vs growth.',
        'sources': {'valuation': ['Rule #1 PE', 'Estimated EPS GR'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'MARR': {
        'what': 'Minimum acceptable rate of return—your required annual return (default 15%).',
        'why_use': 'Future fair value must be discounted back to today at the return you need to justify the investment.',
        'formula': 'MARR is a configured annual required return.',
        'explanation': 'Configured in the model (default 15%); shown as a percentage in the valuation table.',
        'sources': {'valuation': [], 'financial': [], 'big_five': []},
        'inputs': ['Default 15% unless overridden'],
    },
    'MOS': {
        'what': 'Margin of safety—a discount factor (default 50%) applied below intrinsic value.',
        'why_use': 'Buffett/Rule #1 practice: only buy with a buffer so mistakes or downturns hurt less.',
        'formula': 'MOS is the configured margin of safety multiplier.',
        'explanation': 'Configured as a percent but applied as a multiplier on price (e.g. 50% → multiply by 0.50).',
        'sources': {'valuation': [], 'financial': [], 'big_five': []},
        'inputs': ['Default 50% unless overridden'],
    },
    'Fut. Market Price (10 Y)': {
        'what': 'An estimated share price in ten years if EPS and P/E reach the projected levels.',
        'why_use': 'Connects long-term earnings power to a tangible future price target before discounting.',
        'formula': 'Fut. Market Price (10 Y) = Estimated EPS 10y * Rule #1 PE.',
        'explanation': 'Future EPS × conservative P/E; no discounting yet.',
        'sources': {'valuation': ['Estimated EPS 10y', 'Rule #1 PE'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Sticker Price': {
        'what': 'Present value of the ten-year future price—what the stock could be worth today at your MARR.',
        'why_use': 'Turns a distant price target into a today “fair value” using your required return.',
        'formula': 'Sticker Price = Fut. Market Price (10 Y) / (1 + MARR)^10.',
        'explanation': 'Discounts Fut. Market Price (10 Y) back ten years at MARR.',
        'sources': {'valuation': ['Fut. Market Price (10 Y)', 'MARR'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Year-end Close': {
        'what': 'The latest annual closing price from price history (aligned with financial year-ends).',
        'why_use': 'A consistent “current price” for comparing the market quote to your entry threshold.',
        'formula': 'Year-end Close uses the latest available annual close from price history.',
        'explanation': 'Same series as Stock Price (31/12) in financials—yearly close, not intraday.',
        'sources': {'valuation': [], 'financial': ['Stock Price (31/12)'], 'big_five': []},
        'inputs': ['yfinance history: yearly close'],
    },
    'Entry Price': {
        'what': 'The maximum price you would pay today after applying margin of safety to sticker price.',
        'why_use': 'Defines a concrete buy-below level: only attractive if the market trades under this price.',
        'formula': 'Entry Price = Sticker Price * MOS.',
        'explanation': 'Sticker price multiplied by the MOS factor (e.g. 50% MOS → half of sticker).',
        'sources': {'valuation': ['Sticker Price', 'MOS'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Close/Entry price ratio': {
        'what': 'How the current price compares to your entry price (above 1 = more expensive than entry).',
        'why_use': 'Instant signal: below 1 suggests price is under your conservative entry; above 1 suggests it is not.',
        'formula': 'Close/Entry price ratio = Year-end Close / Entry Price.',
        'explanation': 'Year-end close divided by entry price from the same valuation run.',
        'sources': {'valuation': ['Year-end Close', 'Entry Price'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
}

_REVERSE_DEPENDENCY_MAP: dict[str, list[str]] = {}
for _valuation_metric, _details in _VALUATION_EXPLAIN_MAP.items():
    for _table_sources in _details.get('sources', {}).values():
        for _source_metric in _table_sources:
            _REVERSE_DEPENDENCY_MAP.setdefault(_source_metric, []).append(_valuation_metric)

# Matches row order in lib.fundamentals._build_valuation (growth/PE block | price block).
_VALUATION_COL_A_SIZE = 10


def _split_valuation_rows(rows: list[dict[str, Any]]) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    return rows[:_VALUATION_COL_A_SIZE], rows[_VALUATION_COL_A_SIZE:]


def _merge_valuation_rows(
    rows_a: list[dict[str, Any]] | None,
    rows_b: list[dict[str, Any]] | None,
) -> list[dict[str, Any]]:
    return list(rows_a or []) + list(rows_b or [])


def _valuation_row_map(rows: list[dict[str, Any]] | None) -> dict[str, str]:
    if not rows:
        return {}
    return {
        _canonical_metric(str(row.get('metric', ''))): str(row.get('value', '--'))
        for row in rows
    }


def _parse_display_number(raw: str) -> float | None:
    text = str(raw or '').strip()
    if not text or text == '--':
        return None
    is_pct = text.endswith('%')
    cleaned = text.replace('$', '').replace(',', '').replace('%', '').strip()
    try:
        value = float(cleaned)
    except ValueError:
        return None
    return value / 100.0 if is_pct else value


def _fmt_money(value: float | None) -> str:
    if value is None:
        return '--'
    return f'${value:,.2f}'


def _fmt_decimal(value: float | None, places: int = 2) -> str:
    if value is None:
        return '--'
    return f'{value:.{places}f}'


def _fmt_pct(value: float | None, places: int = 2) -> str:
    if value is None:
        return '--'
    return f'{value * 100:.{places}f}%'


def _f_op(text: str) -> html.Span:
    return html.Span(text, className='sfa-f-op')


def _f_text(text: str) -> html.Span:
    return html.Span(text, className='sfa-f-text')


def _f_var(base: str, sub: str | None = None) -> html.Span:
    children: list[Any] = [base]
    if sub:
        children.append(html.Sub(sub, className='sfa-f-sub'))
    return html.Span(children, className='sfa-f-var')


def _f_val(display: str) -> html.Span:
    return html.Span(display, className='num sfa-f-val')


def _f_frac(numerator: Any, denominator: Any) -> html.Span:
    return html.Span([
        html.Span(numerator, className='sfa-f-frac-num'),
        html.Span(denominator, className='sfa-f-frac-den'),
    ], className='sfa-f-frac')


def _f_equation(*parts: Any) -> html.Div:
    return html.Div(list(parts), className='sfa-formula-equation')


def _build_symbolic_equation(metric: str) -> html.Div | None:
    """Readable symbolic equation using dashboard typography (no MathJax)."""
    c = _canonical_metric(metric)
    if c == "Analysts' GR":
        return _f_equation(
            _f_text("Analysts' GR"), _f_op(' ← '),
            _f_text('earningsGrowth, revenueGrowth, earningsQuarterlyGrowth'),
        )
    if c == 'Historical Equity GR':
        return _f_equation(_f_var('g', 'eq'), _f_op(' = '), _f_text('CAGR₁₀Y(Equity)'))
    if c == 'Estimated EPS GR':
        return _f_equation(
            _f_var('g', 'EPS'), _f_op(' = min('),
            _f_text("positive Analysts' GR"), _f_op(', '),
            _f_var('g', 'eq'), _f_op(', '), _f_text('CAGR₁₀Y(EPS)'), _f_op(', 50%)'),
        )
    if c == 'Current EPS':
        return _f_equation(
            _f_var('EPS', '0'), _f_op(' = '),
            _f_text('trailingEps'), _f_op(' | '), _f_text('latest annual EPS'),
        )
    if c == 'Estimated EPS 10y':
        return _f_equation(
            _f_var('EPS', '10'), _f_op(' = '),
            _f_var('EPS', '0'), _f_op(' × (1 + '), _f_var('g', 'EPS'), _f_op(')¹⁰'),
        )
    if c == 'Rule #1st Price/Earn Ratio':
        return _f_equation(
            _f_var('P/E', 'calc'), _f_op(' = max(0, '),
            _f_var('g', 'EPS'), _f_op(' × 200)'),
        )
    if c == 'Forward Price/Earn Ratio':
        return _f_equation(_f_var('P/E', 'fwd'), _f_op(' = '), _f_text('forwardPE'))
    if c == 'Historical PE':
        return _f_equation(_f_var('P/E', 'hist'), _f_op(' = mean('), _f_text('last 10 annual P/E'), _f_op(')'))
    if c == 'Rule #1 PE':
        return _f_equation(
            _f_var('P/E', 'Rule1'), _f_op(' = min('),
            _f_var('P/E', 'calc'), _f_op(', '),
            _f_var('P/E', 'fwd'), _f_op(', '),
            _f_var('P/E', 'hist'), _f_op(')'),
        )
    if c == 'PEG':
        return _f_equation(
            _f_text('PEG'), _f_op(' = '),
            _f_frac(_f_var('P/E', 'Rule1'), html.Span([
                _f_var('g', 'EPS'), _f_op(' × 100'),
            ])),
        )
    if c == 'MARR':
        return _f_equation(_f_var('r', 'MARR'), _f_op(' = '), _f_text('configured annual required return'))
    if c == 'MOS':
        return _f_equation(_f_var('m', 'MOS'), _f_op(' = '), _f_text('configured margin-of-safety multiplier'))
    if c == 'Fut. Market Price (10 Y)':
        return _f_equation(
            _f_var('P', '10'), _f_op(' = '),
            _f_var('EPS', '10'), _f_op(' × '), _f_var('P/E', 'Rule1'),
        )
    if c == 'Sticker Price':
        return _f_equation(
            _f_var('P', 'sticker'), _f_op(' = '),
            _f_frac(_f_var('P', '10'), html.Span([
                _f_op('(1 + '), _f_var('r', 'MARR'), _f_op(')¹⁰'),
            ])),
        )
    if c == 'Year-end Close':
        return _f_equation(_f_var('P', 'close'), _f_op(' = '), _f_text('latest annual close'))
    if c == 'Entry Price':
        return _f_equation(
            _f_var('P', 'entry'), _f_op(' = '),
            _f_var('P', 'sticker'), _f_op(' × '), _f_var('m', 'MOS'),
        )
    if c == 'Close/Entry price ratio':
        return _f_equation(
            _f_text('Ratio'), _f_op(' = '),
            _f_frac(_f_var('P', 'close'), _f_var('P', 'entry')),
        )
    return None


def _build_substituted_equation(metric: str, row_map: dict[str, str]) -> html.Div | None:
    """Build a numeric substitution line for metrics with table inputs."""
    canonical = _canonical_metric(metric)

    def raw(key: str) -> str:
        return row_map.get(_canonical_metric(key), '--')

    def num(key: str) -> float | None:
        return _parse_display_number(raw(key))

    def result_display(result_key: str | None = None) -> str | None:
        result = num(result_key or canonical)
        if result is None:
            return None
        if canonical in {'PEG', 'Close/Entry price ratio', 'Rule #1st Price/Earn Ratio', 'Forward Price/Earn Ratio', 'Historical PE', 'Rule #1 PE'}:
            return _fmt_decimal(result, 1)
        if canonical in {"Analysts' GR", 'Historical Equity GR', 'Estimated EPS GR', 'MARR', 'MOS'}:
            return _fmt_pct(result)
        return _fmt_money(result)

    def with_result(*parts: Any, result_key: str | None = None) -> html.Div:
        children: list[Any] = list(parts)
        shown = result_display(result_key)
        if shown is not None:
            children.extend([_f_op(' = '), _f_val(shown)])
        return _f_equation(*children)

    if canonical == 'Estimated EPS 10y':
        eps0, growth = num('Current EPS'), num('Estimated EPS GR')
        if eps0 is None or growth is None:
            return None
        return with_result(
            _f_var('EPS', '10'), _f_op(' = '),
            _f_val(_fmt_money(eps0)), _f_op(' × (1 + '),
            _f_val(_fmt_decimal(growth)), _f_op(')¹⁰'),
        )

    if canonical == 'Rule #1st Price/Earn Ratio':
        growth = num('Estimated EPS GR')
        if growth is None:
            return None
        return with_result(
            _f_var('P/E', 'calc'), _f_op(' = max(0, '),
            _f_val(_fmt_decimal(growth)), _f_op(' × 200)'),
        )

    if canonical == 'Rule #1 PE':
        calc, fwd, hist = num('Rule #1st Price/Earn Ratio'), num('Forward Price/Earn Ratio'), num('Historical PE')
        if not any(value is not None and value > 0 for value in (calc, fwd, hist)):
            return None
        return with_result(
            _f_var('P/E', 'Rule1'), _f_op(' = min('),
            _f_val(_fmt_decimal(calc, 1) if calc is not None else '--'),
            _f_op(', '),
            _f_val(_fmt_decimal(fwd, 1) if fwd is not None else '--'),
            _f_op(', '),
            _f_val(_fmt_decimal(hist, 1) if hist is not None else '--'),
            _f_op(')'),
        )

    if canonical == 'PEG':
        pe, growth = num('Rule #1 PE'), num('Estimated EPS GR')
        if pe is None or growth is None or growth <= 0:
            return None
        return with_result(
            _f_text('PEG'), _f_op(' = '),
            _f_frac(_f_val(_fmt_decimal(pe, 1)), html.Span([
                _f_val(_fmt_decimal(growth)), _f_op(' × 100'),
            ])),
        )

    if canonical == 'Fut. Market Price (10 Y)':
        eps10, pe = num('Estimated EPS 10y'), num('Rule #1 PE')
        if eps10 is None or pe is None:
            return None
        return with_result(
            _f_var('P', '10'), _f_op(' = '),
            _f_val(_fmt_money(eps10)), _f_op(' × '),
            _f_val(_fmt_decimal(pe, 1)),
        )

    if canonical == 'Sticker Price':
        future_price, marr = num('Fut. Market Price (10 Y)'), num('MARR')
        if future_price is None or marr is None:
            return None
        return with_result(
            _f_var('P', 'sticker'), _f_op(' = '),
            _f_frac(_f_val(_fmt_money(future_price)), html.Span([
                _f_op('(1 + '), _f_val(_fmt_decimal(marr)), _f_op(')¹⁰'),
            ])),
        )

    if canonical == 'Entry Price':
        sticker, mos = num('Sticker Price'), num('MOS')
        if sticker is None or mos is None:
            return None
        return with_result(
            _f_var('P', 'entry'), _f_op(' = '),
            _f_val(_fmt_money(sticker)), _f_op(' × '),
            _f_val(_fmt_decimal(mos)),
        )

    if canonical == 'Close/Entry price ratio':
        close, entry = num('Year-end Close'), num('Entry Price')
        if close is None or entry is None or entry == 0:
            return None
        return with_result(
            _f_text('Ratio'), _f_op(' = '),
            _f_frac(_f_val(_fmt_money(close)), _f_val(_fmt_money(entry))),
        )

    if canonical == 'MARR':
        marr = num('MARR')
        if marr is None:
            return None
        return _f_equation(_f_var('r', 'MARR'), _f_op(' = '), _f_val(_fmt_pct(marr)))

    if canonical == 'MOS':
        mos = num('MOS')
        if mos is None:
            return None
        return _f_equation(
            _f_var('m', 'MOS'), _f_op(' = '), _f_val(_fmt_pct(mos)),
            _f_op(' (× '), _f_val(_fmt_decimal(mos)), _f_op(')'),
        )

    return None


def _formula_card(symbolic: html.Div | None, substituted: html.Div | None) -> html.Div:
    blocks: list[Any] = []
    if symbolic is not None:
        blocks.append(
            html.Div(
                className='sfa-formula-block sfa-formula-symbolic',
                children=[
                    html.Div('Formula', className='sfa-formula-block-label'),
                    html.Div(symbolic, className='sfa-formula-math'),
                ],
            ),
        )
    if substituted is not None:
        blocks.append(
            html.Div(
                className='sfa-formula-block sfa-formula-substituted',
                children=[
                    html.Div('With current values', className='sfa-formula-block-label'),
                    html.Div(substituted, className='sfa-formula-math'),
                ],
            ),
        )
    return html.Div(blocks, className='sfa-formula-card')


def _explain_notes_column(
    explain: dict[str, Any],
    layers: dict[str, Any],
) -> html.Div:
    """Right column: definitions, rationale, calculation notes, sources."""
    sections: list[Any] = [
        html.Div('What it is', className='sfa-explain-heading'),
        html.Div(explain.get('what') or explain.get('explanation', '--'), className='sfa-formula-what'),
        html.Div('Why we use it', className='sfa-explain-heading'),
        html.Div(explain.get('why_use') or '--', className='sfa-formula-why'),
        html.Div('How we calculate it', className='sfa-explain-heading'),
        html.Div(explain.get('explanation', '--'), className='sfa-formula-explanation'),
    ]
    source_text = _source_summary(explain)
    if source_text and source_text != 'No upstream rows required.':
        sections.extend([
            html.Div('Data sources', className='sfa-explain-heading'),
            html.Div(source_text, className='sfa-formula-meta'),
        ])
    layer_text = _layer_summary_text(layers)
    if layer_text:
        sections.extend([
            html.Div('Dependencies', className='sfa-explain-heading'),
            html.Div(layer_text, className='sfa-formula-meta'),
        ])
    inputs = explain.get('inputs', [])
    if inputs:
        sections.extend([
            html.Div('Inputs', className='sfa-explain-heading'),
            html.Div(', '.join(inputs), className='sfa-formula-meta'),
        ])
    return html.Div(sections, className='sfa-explain-col-notes')


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
        [Output('fundamentals-store', 'data'),
         Output('fundamentals-title', 'children'),
         Output('fundamentals-status', 'children'),
         Output('ticker-dropdown', 'value', allow_duplicate=True)],
        [Input('app-url', 'pathname'),
         Input('app-url', 'search'),
         Input('refresh-fundamentals-button', 'n_clicks'),
         Input('load-fundamentals-ticker-button', 'n_clicks'),
         Input('fundamentals-ticker-input', 'n_submit')],
        [State('ticker-dropdown', 'value'),
         State('fundamentals-ticker-input', 'value'),
         State('user-ticker-store', 'data')],
        prevent_initial_call='initial_duplicate',
    )
    def load_fundamentals(
        pathname,
        search,
        refresh_clicks,
        load_clicks,
        input_submit,
        ticker,
        overlay_ticker,
        user_ticker,
    ):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        url_ticker = None
        if search:
            for part in search.lstrip('?').split('&'):
                if part.startswith('ticker='):
                    url_ticker = part.split('=', 1)[1].strip().upper()
                    break

        # user_ticker is only populated by the startup callback when the
        # user actually changes the dropdown (prevent_initial_call=True).
        # It stays None on a fresh direct visit, which is exactly the
        # signal we use to swap the SPY page-default for a real company.
        if trigger_id == 'app-url':
            if not is_fundamentals_route(pathname):
                raise PreventUpdate
            cold_load = not (url_ticker or overlay_ticker or user_ticker or ticker)
            fallback = FUNDAMENTALS_FALLBACK_TICKER if cold_load else DEFAULT_TICKER
            raw = str(url_ticker or overlay_ticker or user_ticker or ticker or fallback).strip()
        else:
            raw = str(overlay_ticker or ticker or DEFAULT_TICKER).strip()

        options = _ensure_ticker_options_loaded()
        symbol = resolve_ticker_symbol(raw, options)

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
        update_global_ticker = symbol if trigger_id in {
            'load-fundamentals-ticker-button',
            'fundamentals-ticker-input',
            'app-url',
        } else no_update
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

    @app.callback(
        [Output('fundamentals-financial-table', 'style_data_conditional'),
         Output('fundamentals-big-five-table', 'style_data_conditional'),
         Output('fundamentals-valuation-table-a', 'style_data_conditional'),
         Output('fundamentals-valuation-table-b', 'style_data_conditional'),
         Output('fundamentals-valuation-explain', 'children'),
         Output('fundamentals-valuation-explain', 'style'),
         Output('fundamentals-financial-table', 'active_cell'),
         Output('fundamentals-big-five-table', 'active_cell'),
         Output('fundamentals-valuation-table-a', 'active_cell'),
         Output('fundamentals-valuation-table-b', 'active_cell')],
        [Input('fundamentals-financial-table', 'active_cell'),
         Input('fundamentals-big-five-table', 'active_cell'),
         Input('fundamentals-valuation-table-a', 'active_cell'),
         Input('fundamentals-valuation-table-b', 'active_cell'),
         Input('fundamentals-esc-signal', 'value'),
         Input('theme-store', 'data')],
        [State('fundamentals-financial-table', 'data'),
         State('fundamentals-big-five-table', 'data'),
         State('fundamentals-big-five-table', 'columns'),
         State('fundamentals-valuation-table-a', 'data'),
         State('fundamentals-valuation-table-b', 'data')],
    )
    def update_fundamentals_explainability(
        fin_active,
        big_active,
        val_a_active,
        val_b_active,
        esc_signal,
        theme_name,
        fin_rows,
        big_rows,
        big_columns,
        val_a_rows,
        val_b_rows,
    ):
        theme = get_theme(theme_name or DEFAULT_THEME)
        value_columns = _big_five_value_columns(big_columns)
        financial_style = _financial_conditionals(theme)
        big_five_style = _big_five_conditionals(theme, value_columns)
        valuation_style = _valuation_conditionals(theme)
        val_rows = _merge_valuation_rows(val_a_rows, val_b_rows)
        explain_style = _valuation_explain_style(theme, visible=False)
        explain_children = []
        clear_cells = no_update, no_update, no_update, no_update

        trigger = callback_context.triggered[0]['prop_id'].split('.')[0] if callback_context.triggered else ''
        if trigger == 'fundamentals-esc-signal' and esc_signal:
            return (
                financial_style, big_five_style, valuation_style, valuation_style,
                explain_children, explain_style,
                None, None, None, None,
            )

        metric = _resolve_selected_metric(
            fin_active,
            big_active,
            val_a_active,
            val_b_active,
            fin_rows,
            big_rows,
            val_a_rows,
            val_b_rows,
        )
        if not metric:
            return (
                financial_style,
                big_five_style,
                valuation_style,
                valuation_style,
                explain_children,
                explain_style,
                *clear_cells,
            )

        canonical_metric = _canonical_metric(metric)
        explain = _VALUATION_EXPLAIN_MAP.get(canonical_metric)

        if explain:
            layers = _dependency_layers(canonical_metric)
            financial_style += _highlight_metric_rules(layers['direct_financial'], theme, tone='direct')
            financial_style += _highlight_metric_rules(layers['indirect_financial'], theme, tone='indirect')
            big_five_style += _highlight_metric_rules(layers['direct_big_five'], theme, tone='direct')
            big_five_style += _highlight_metric_rules(layers['indirect_big_five'], theme, tone='indirect')
            valuation_style += _highlight_metric_rules(layers['direct_valuation'], theme, tone='direct')
            valuation_style += _highlight_metric_rules(layers['indirect_valuation'], theme, tone='indirect')
            valuation_style += _highlight_metric_rules([canonical_metric], theme, tone='selected')
            explain_children = _valuation_explain_content(canonical_metric, explain, theme, val_rows)
        else:
            dependents = _REVERSE_DEPENDENCY_MAP.get(canonical_metric, [])
            if dependents:
                valuation_style += _highlight_metric_rules(dependents, theme, tone='direct')
                financial_style += _highlight_metric_rules([canonical_metric], theme, tone='selected')
                big_five_style += _highlight_metric_rules([canonical_metric], theme, tone='selected')
                explain_children = _valuation_source_content(canonical_metric, dependents, theme)
            else:
                explain_children = _valuation_generic_content(canonical_metric, theme)

        explain_style = _valuation_explain_style(theme, visible=True)
        val_a_cell, val_b_cell = clear_cells[2], clear_cells[3]
        if trigger == 'fundamentals-valuation-table-a':
            val_b_cell = None
        elif trigger == 'fundamentals-valuation-table-b':
            val_a_cell = None
        return (
            financial_style,
            big_five_style,
            valuation_style,
            valuation_style,
            explain_children,
            explain_style,
            clear_cells[0],
            clear_cells[1],
            val_a_cell,
            val_b_cell,
        )

def _render_payload(payload: dict[str, Any], theme: dict) -> html.Div:
    years = [str(year) for year in payload.get('years', [])]
    valuation_rows = payload.get('valuation', [])
    return html.Div([
        _summary_strip(payload, theme),
        html.Div([
            html.Div([
                _panel_title('Financials', theme),
                _financial_table(
                    payload.get('financials', []),
                    years,
                    theme,
                    last_price=payload.get('last_price'),
                ),
            ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-main'),
            html.Div([
                _panel_title('Valuation', theme, size='sm'),
                _valuation_assumptions(valuation_rows, theme),
                _valuation_tables(valuation_rows, theme),
                html.Div(
                    id='fundamentals-valuation-explain',
                    className='sfa-valuation-explain',
                    style=_valuation_explain_style(theme, visible=False),
                ),
            ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-side sfa-fundamentals-valuation'),
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
        _price_hero_cell(payload, theme),
        _summary_cell('Ticker', payload.get('ticker', '--'), theme),
        _summary_cell('Currency', payload.get('currency', '--'), theme),
        _summary_cell('Last FY', last_year, theme),
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


def _valuation_explain_style(theme: dict, *, visible: bool) -> dict[str, Any]:
    return {
        'display': 'block' if visible else 'none',
    }


def _valuation_explain_content(metric: str, explain: dict[str, Any], theme: dict, valuation_rows: list[dict[str, Any]] | None) -> list[Any]:
    layers = _dependency_layers(metric)
    canonical = _canonical_metric(metric)
    row_map = _valuation_row_map(valuation_rows)
    symbolic = _build_symbolic_equation(canonical)
    substituted = _build_substituted_equation(canonical, row_map)
    return [
        html.Div(f"Calculation detail: {metric}", className='sfa-formula-title', style={
            'color': theme['accent_blue'],
        }),
        html.Div([
            html.Div(_formula_card(symbolic, substituted), className='sfa-explain-col-formulas'),
            _explain_notes_column(explain, layers),
        ], className='sfa-explain-grid'),
    ]


def _valuation_source_content(metric: str, dependents: list[str], theme: dict) -> list[html.Div]:
    joined = ', '.join(dependents[:5])
    more = '' if len(dependents) <= 5 else f" (+{len(dependents) - 5} more)"
    return [
        html.Div(f"Source metric: {metric}", style={
            'fontFamily': FONT_FAMILY,
            'fontSize': FONT_SIZES['xs'],
            'fontWeight': 700,
            'color': theme['accent_blue'],
            'marginBottom': '5px',
        }),
        html.Div(f"This source contributes to: {joined}{more}.", style={
            'fontFamily': FONT_FAMILY,
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_secondary'],
            'lineHeight': '1.35',
        }),
    ]


def _valuation_generic_content(metric: str, theme: dict) -> list[html.Div]:
    return [
        html.Div(f"Selected metric: {metric}", style={
            'fontFamily': FONT_FAMILY,
            'fontSize': FONT_SIZES['xs'],
            'fontWeight': 700,
            'color': theme['accent_blue'],
            'marginBottom': '5px',
        }),
        html.Div('No explicit calculation graph is configured for this metric yet.', style={
            'fontFamily': FONT_FAMILY,
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_secondary'],
        }),
    ]


def _source_summary(explain: dict[str, Any]) -> str:
    sources = explain.get('sources', {})
    segments = []
    for label, metrics in (
        ('Valuation', sources.get('valuation', [])),
        ('Financials', sources.get('financial', [])),
        ('Big Five', sources.get('big_five', [])),
    ):
        if metrics:
            segments.append(f"{label}: {', '.join(metrics)}")
    inputs = explain.get('inputs', [])
    if inputs:
        segments.append(f"Inputs: {', '.join(inputs)}")
    return ' | '.join(segments) if segments else 'No upstream rows required.'


def _resolve_selected_metric(
    fin_active: dict[str, Any] | None,
    big_active: dict[str, Any] | None,
    val_a_active: dict[str, Any] | None,
    val_b_active: dict[str, Any] | None,
    fin_rows: list[dict[str, Any]] | None,
    big_rows: list[dict[str, Any]] | None,
    val_a_rows: list[dict[str, Any]] | None,
    val_b_rows: list[dict[str, Any]] | None,
) -> str | None:
    ctx = callback_context
    trigger = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ''
    if trigger == 'fundamentals-valuation-table-a':
        return _metric_from_active_cell(val_a_active, val_a_rows)
    if trigger == 'fundamentals-valuation-table-b':
        return _metric_from_active_cell(val_b_active, val_b_rows)
    if trigger == 'fundamentals-financial-table':
        return _metric_from_active_cell(fin_active, fin_rows)
    if trigger == 'fundamentals-big-five-table':
        return _metric_from_active_cell(big_active, big_rows)
    return (
        _metric_from_active_cell(val_a_active, val_a_rows)
        or _metric_from_active_cell(val_b_active, val_b_rows)
        or _metric_from_active_cell(fin_active, fin_rows)
        or _metric_from_active_cell(big_active, big_rows)
    )


def _metric_from_active_cell(active_cell: dict[str, Any] | None, rows: list[dict[str, Any]] | None) -> str | None:
    if not active_cell or not rows:
        return None
    row_index = active_cell.get('row')
    if row_index is None or row_index < 0 or row_index >= len(rows):
        return None
    metric = str(rows[row_index].get('metric', '')).strip()
    return metric or None


def _big_five_value_columns(columns: list[dict[str, Any]] | None) -> list[str]:
    if not columns:
        return ['10Y', '5Y', '1Y']
    return [
        str(column.get('id'))
        for column in columns
        if str(column.get('id')) not in {'metric', 'unit', 'status_10Y', 'status_5Y', 'status_1Y'}
    ]


def _highlight_metric_rules(metrics: list[str], theme: dict, *, tone: str = 'direct') -> list[dict[str, Any]]:
    styles = {
        'direct': {
            'textDecorationColor': theme['accent_orange'],
            'borderBottom': f'2px solid {theme["accent_orange"]}',
        },
        'indirect': {
            'textDecorationColor': theme['accent_cyan'],
            'borderBottom': f'2px solid {theme["accent_cyan"]}',
        },
        'selected': {
            'textDecorationColor': theme['accent_blue'],
            'borderBottom': f'2px solid {theme["accent_blue"]}',
            'border': f'1px solid {theme["accent_blue"]}',
        },
    }
    style = styles.get(tone, styles['direct'])
    rules = []
    for metric in metrics:
        canonical = _canonical_metric(metric)
        rules.append({
            'if': {'filter_query': f'{{metric}} = "{_escape_filter(canonical)}"'},
            'textDecoration': 'underline',
            'textDecorationColor': style['textDecorationColor'],
            'textDecorationThickness': '2px',
            'fontWeight': 700,
            'borderBottom': style['borderBottom'],
            **({'border': style['border']} if 'border' in style else {}),
        })
    return rules


def _dependency_layers(metric: str) -> dict[str, list[str]]:
    canonical = _canonical_metric(metric)
    explain = _VALUATION_EXPLAIN_MAP.get(canonical, {})
    direct_sources = explain.get('sources', {})
    direct_valuation = [_canonical_metric(m) for m in direct_sources.get('valuation', [])]
    direct_financial = [_canonical_metric(m) for m in direct_sources.get('financial', [])]
    direct_big_five = [_canonical_metric(m) for m in direct_sources.get('big_five', [])]

    visited: set[str] = set()
    stack = list(direct_valuation)
    while stack:
        current = _canonical_metric(stack.pop())
        if current in visited:
            continue
        visited.add(current)
        nested = _VALUATION_EXPLAIN_MAP.get(current, {}).get('sources', {}).get('valuation', [])
        stack.extend(_canonical_metric(value) for value in nested)

    indirect_valuation = sorted(visited.difference(direct_valuation))

    indirect_financial: set[str] = set()
    indirect_big_five: set[str] = set()
    for nested_metric in indirect_valuation:
        nested_sources = _VALUATION_EXPLAIN_MAP.get(nested_metric, {}).get('sources', {})
        indirect_financial.update(_canonical_metric(value) for value in nested_sources.get('financial', []))
        indirect_big_five.update(_canonical_metric(value) for value in nested_sources.get('big_five', []))

    return {
        'direct_valuation': sorted(set(direct_valuation)),
        'indirect_valuation': indirect_valuation,
        'direct_financial': sorted(set(direct_financial)),
        'indirect_financial': sorted(indirect_financial.difference(direct_financial)),
        'direct_big_five': sorted(set(direct_big_five)),
        'indirect_big_five': sorted(indirect_big_five.difference(direct_big_five)),
    }


def _layer_summary_text(layers: dict[str, list[str]]) -> str:
    segments = []
    if layers.get('direct_valuation'):
        segments.append(f"Direct valuation sources: {', '.join(layers['direct_valuation'])}")
    if layers.get('indirect_valuation'):
        segments.append(f"Indirect valuation sources: {', '.join(layers['indirect_valuation'])}")
    if layers.get('direct_financial'):
        segments.append(f"Direct financial sources: {', '.join(layers['direct_financial'])}")
    if layers.get('indirect_financial'):
        segments.append(f"Indirect financial sources: {', '.join(layers['indirect_financial'])}")
    if layers.get('direct_big_five'):
        segments.append(f"Direct big-five sources: {', '.join(layers['direct_big_five'])}")
    if layers.get('indirect_big_five'):
        segments.append(f"Indirect big-five sources: {', '.join(layers['indirect_big_five'])}")
    return ' | '.join(segments) if segments else 'No dependency rows for this metric.'


def _canonical_metric(metric: str) -> str:
    normalized = str(metric or '').strip()
    return _METRIC_ALIASES.get(normalized, normalized)


def _escape_filter(value: str) -> str:
    return str(value).replace('"', '\\"')


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
        font={'family': FONT_FAMILY, 'size': 11, 'color': theme['text_secondary']},
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