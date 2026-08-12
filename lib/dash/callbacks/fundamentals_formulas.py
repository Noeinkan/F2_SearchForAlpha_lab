"""Fundamentals valuation formulas and explainability helpers."""

from __future__ import annotations

import json
from typing import Any

from dash import callback_context, html

from lib.config_loader import get_config
from lib.dash.dash_config import FONT_FAMILY, FONT_SIZES
from lib.dcf import DEFAULT_EQUITY_RISK_PREMIUM, DEFAULT_RISK_FREE

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
        'explanation': 'Same series as Stock Price (FYE) in financials—period-end close, not intraday.',
        'sources': {'valuation': [], 'financial': ['Stock Price (FYE)'], 'big_five': []},
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
    # --- FCFE DCF (sibling of Rule #1; not blended) -------------------------
    'Base FCFE (3y avg)': {
        'what': 'Average free cash flow to equity over the last three years, in $ millions.',
        'why_use': 'A multi-year average stops one capex-heavy year from setting the entire DCF base.',
        'formula': 'Base FCFE = mean of last 3 years of FCF (OCF + CapEx when FCF is missing).',
        'explanation': 'Uses the same FCF series as the financials table; values are already scaled to $mil.',
        'sources': {'valuation': [], 'financial': ['FCF'], 'big_five': []},
        'inputs': [],
    },
    'Stage 1 FCFE GR': {
        'what': 'Near-term FCFE growth used for the explicit forecast stage (up to 10 years).',
        'why_use': 'Growth drives the cash-flow path; we take the more conservative of analyst and historical rates.',
        'formula': 'Stage 1 FCFE GR = min(positive analyst growth, historical FCF CAGR), capped and floored at terminal growth.',
        'explanation': 'Mirrors Rule #1 conservatism: when sources disagree, use the least optimistic positive rate.',
        'sources': {'valuation': [], 'financial': ['FCF'], 'big_five': []},
        'inputs': ['yfinance info: earningsGrowth/revenueGrowth/earningsQuarterlyGrowth'],
    },
    'Terminal GR': {
        'what': 'Perpetual growth rate applied after stage 1 in the Gordon growth terminal value.',
        'why_use': 'Long-run growth must stay below the discount rate or the terminal value is undefined.',
        'formula': 'Terminal GR is configured (default 2.5%).',
        'explanation': 'Set in strategy_config.yaml under dcf.terminal_growth.',
        'sources': {'valuation': [], 'financial': [], 'big_five': []},
        'inputs': ['config dcf.terminal_growth'],
    },
    'Beta (clamped)': {
        'what': 'Equity beta used in CAPM, clamped between configured floor and cap.',
        'why_use': 'Extreme betas produce unrealistic discount rates; clamping keeps cost of equity in a defensible band.',
        'formula': 'Beta (clamped) = min(max(beta, beta_floor), beta_cap); default 1.0 if beta missing.',
        'explanation': 'Raw beta comes from market info; floor/cap come from dcf config.',
        'sources': {'valuation': [], 'financial': [], 'big_five': []},
        'inputs': ['yfinance info: beta', 'config dcf.beta_floor/beta_cap'],
    },
    'Cost of Equity': {
        'what': 'CAPM required return used to discount levered free cash flow.',
        'why_use': 'FCFE is already after interest, so discounting at cost of equity yields equity value directly (no WACC).',
        'formula': 'Cost of Equity = risk_free + Beta (clamped) × equity_risk_premium.',
        'explanation': 'Risk-free and ERP come from config; beta is clamped from quote data.',
        'sources': {'valuation': ['Beta (clamped)'], 'financial': [], 'big_five': []},
        'inputs': ['config dcf.risk_free', 'config dcf.equity_risk_premium'],
    },
    'PV Stage 1': {
        'what': 'Present value of the explicit-stage FCFE forecasts.',
        'why_use': 'Shows how much of equity value comes from cash flows you actually project year by year.',
        'formula': 'PV Stage 1 = Σ FCFE_t / (1 + r)^t for t = 1…N.',
        'explanation': 'Each year’s FCFE grows along the stage-1 path (optionally fading to terminal growth), then is discounted at cost of equity.',
        'sources': {'valuation': ['Base FCFE (3y avg)', 'Stage 1 FCFE GR', 'Cost of Equity'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'PV Terminal Value': {
        'what': 'Present value of the Gordon growth terminal value at the end of stage 1.',
        'why_use': 'Most of the answer often sits here—so the grid and terminal share matter more than year-3 precision.',
        'formula': 'TV = FCFE_N × (1 + g2) / (r − g2); PV Terminal = TV / (1 + r)^N.',
        'explanation': 'Requires r > g2. Discounted back from year N at the cost of equity.',
        'sources': {'valuation': ['Cost of Equity', 'Terminal GR', 'Stage 1 FCFE GR'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Terminal Value Share': {
        'what': 'Share of total equity value that comes from the terminal value.',
        'why_use': 'A high share means the answer is mostly an assumption about year N+1 onward.',
        'formula': 'Terminal Value Share = PV Terminal Value / Equity Value.',
        'explanation': 'Flagged in quality notes when above 75%.',
        'sources': {'valuation': ['PV Terminal Value', 'Equity Value'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Equity Value': {
        'what': 'Total equity value from the two-stage FCFE model ($ millions).',
        'why_use': 'The firm-level output before dividing by shares outstanding.',
        'formula': 'Equity Value = PV Stage 1 + PV Terminal Value.',
        'explanation': 'Already an equity value because FCFE is levered and discounted at cost of equity.',
        'sources': {'valuation': ['PV Stage 1', 'PV Terminal Value'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'DCF Fair Value': {
        'what': 'Equity value per share from the two-stage FCFE DCF.',
        'why_use': 'Sibling of Rule #1 sticker/entry prices—same company, different theory of value. Do not average them.',
        'formula': 'DCF Fair Value = Equity Value / shares outstanding (millions).',
        'explanation': 'Shares come from market info. Soft inputs (r, g2) move this number a lot—see the sensitivity grid.',
        'sources': {'valuation': ['Cost of Equity', 'Stage 1 FCFE GR', 'Terminal GR'], 'financial': [], 'big_five': []},
        'inputs': ['yfinance info: sharesOutstanding'],
    },
    'Upside vs Price': {
        'what': 'Percentage gap between DCF fair value and the current market price.',
        'why_use': 'Quick read of whether the market price sits above or below the FCFE-implied value.',
        'formula': 'Upside vs Price = DCF Fair Value / current price − 1.',
        'explanation': 'Uses currentPrice when available, otherwise the latest stock price from financials.',
        'sources': {'valuation': ['DCF Fair Value'], 'financial': ['Stock Price (FYE)'], 'big_five': []},
        'inputs': ['yfinance info: currentPrice'],
    },
}


_REVERSE_DEPENDENCY_MAP: dict[str, list[str]] = {}


for _valuation_metric, _details in _VALUATION_EXPLAIN_MAP.items():
    for _table_sources in _details.get('sources', {}).values():
        for _source_metric in _table_sources:
            _REVERSE_DEPENDENCY_MAP.setdefault(_source_metric, []).append(_valuation_metric)


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
    if not text or text in {'--', 'n/a'}:
        return None
    is_pct = text.endswith('%')
    cleaned = text.replace('$', '').replace(',', '').replace('%', '').strip()
    if cleaned.endswith(('m', 'M')):
        cleaned = cleaned[:-1].strip()
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


def _dcf_capm_inputs() -> tuple[float, float]:
    """Risk-free rate and ERP from config (same source as build_dcf)."""
    raw = get_config().get('dcf', {}) or {}
    if not isinstance(raw, dict):
        raw = {}
    risk_free = float(raw.get('risk_free', DEFAULT_RISK_FREE))
    erp = float(raw.get('equity_risk_premium', DEFAULT_EQUITY_RISK_PREMIUM))
    return risk_free, erp


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
    if c == 'Base FCFE (3y avg)':
        return _f_equation(_f_var('FCFE', '0'), _f_op(' = mean('), _f_text('last 3y FCF'), _f_op(')'))
    if c == 'Stage 1 FCFE GR':
        return _f_equation(
            _f_var('g', '1'), _f_op(' = min('),
            _f_text('analyst growth'), _f_op(', '),
            _f_text('FCF CAGR'), _f_op(')'),
        )
    if c == 'Terminal GR':
        return _f_equation(_f_var('g', '2'), _f_op(' = '), _f_text('configured terminal growth'))
    if c == 'Beta (clamped)':
        return _f_equation(
            _f_var('β', 'used'), _f_op(' = clamp('),
            _f_var('β', 'raw'), _f_op(', floor, cap)'),
        )
    if c == 'Cost of Equity':
        return _f_equation(
            _f_var('r', 'e'), _f_op(' = '),
            _f_var('r', 'f'), _f_op(' + '),
            _f_var('β', 'used'), _f_op(' × ERP'),
        )
    if c == 'PV Stage 1':
        return _f_equation(
            _f_text('PV₁'), _f_op(' = Σ '),
            _f_frac(_f_var('FCFE', 't'), html.Span([_f_op('(1 + '), _f_var('r', 'e'), _f_op(')ᵗ')])),
        )
    if c == 'PV Terminal Value':
        return _f_equation(
            _f_text('PVₜᵥ'), _f_op(' = '),
            _f_frac(
                html.Span([
                    _f_var('FCFE', 'N'), _f_op(' × (1 + '), _f_var('g', '2'), _f_op(') / ('),
                    _f_var('r', 'e'), _f_op(' − '), _f_var('g', '2'), _f_op(')'),
                ]),
                html.Span([_f_op('(1 + '), _f_var('r', 'e'), _f_op(')ᴺ')]),
            ),
        )
    if c == 'Terminal Value Share':
        return _f_equation(
            _f_text('Share'), _f_op(' = '),
            _f_frac(_f_text('PVₜᵥ'), _f_text('Equity Value')),
        )
    if c == 'Equity Value':
        return _f_equation(
            _f_text('Equity'), _f_op(' = '),
            _f_text('PV₁'), _f_op(' + '), _f_text('PVₜᵥ'),
        )
    if c == 'DCF Fair Value':
        return _f_equation(
            _f_var('P', 'dcf'), _f_op(' = '),
            _f_frac(_f_text('Equity Value'), _f_text('shares (mil)')),
        )
    if c == 'Upside vs Price':
        return _f_equation(
            _f_text('Upside'), _f_op(' = '),
            _f_var('P', 'dcf'), _f_op(' / '), _f_var('P', 'mkt'), _f_op(' − 1'),
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
        if canonical in {
            "Analysts' GR", 'Historical Equity GR', 'Estimated EPS GR', 'MARR', 'MOS',
            'Stage 1 FCFE GR', 'Terminal GR', 'Cost of Equity', 'Terminal Value Share', 'Upside vs Price',
        }:
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

    if canonical == 'Cost of Equity':
        rate = num('Cost of Equity')
        beta = num('Beta (clamped)')
        if rate is None or beta is None:
            return None
        risk_free, erp = _dcf_capm_inputs()
        return with_result(
            _f_var('r', 'e'), _f_op(' = '),
            _f_val(_fmt_pct(risk_free)), _f_op(' + '),
            _f_val(_fmt_decimal(beta)), _f_op(' × '),
            _f_val(_fmt_pct(erp)),
        )

    if canonical == 'DCF Fair Value':
        fair = num('DCF Fair Value')
        if fair is None:
            return None
        return _f_equation(
            _f_var('P', 'dcf'), _f_op(' = '),
            _f_text('Equity / shares'), _f_op(' = '), _f_val(_fmt_money(fair)),
        )

    if canonical in {
        'Stage 1 FCFE GR', 'Terminal GR', 'Terminal Value Share', 'Upside vs Price',
    }:
        rate = num(canonical)
        if rate is None:
            return None
        return _f_equation(_f_text(canonical), _f_op(' = '), _f_val(_fmt_pct(rate)))

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
    row_map: dict[str, str] | None = None,
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
    dep_chips = _dependency_chip_rows(layers, row_map or {})
    has_dep_metrics = _has_dependency_metrics(layers)
    # Chips already list upstream metrics; keep prose only when there are no chip rows.
    source_text = _source_summary(explain)
    if source_text and source_text != 'No upstream rows required.' and not has_dep_metrics:
        sections.extend([
            html.Div('Data sources', className='sfa-explain-heading'),
            html.Div(source_text, className='sfa-formula-meta'),
        ])
    if dep_chips is not None:
        sections.extend([
            html.Div('Dependencies', className='sfa-explain-heading'),
            dep_chips,
        ])
    inputs = explain.get('inputs', [])
    if inputs:
        sections.extend([
            html.Div('Inputs', className='sfa-explain-heading'),
            html.Div(', '.join(inputs), className='sfa-formula-meta'),
        ])
    return html.Div(sections, className='sfa-explain-col-notes')


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
        html.Div([
            html.Div(f"Calculation detail: {metric}", className='sfa-formula-title', style={
                'color': theme['accent_blue'],
            }),
            html.Div(
                'Sources highlighted above · Esc to close',
                className='sfa-formula-subtitle',
            ),
        ], className='sfa-formula-header'),
        html.Div([
            html.Div(_formula_card(symbolic, substituted), className='sfa-explain-col-formulas'),
            _explain_notes_column(explain, layers, row_map),
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
    dcf_active: dict[str, Any] | None = None,
    dcf_rows: list[dict[str, Any]] | None = None,
) -> str | None:
    """Resolve which metric owns the explain panel.

    Prefer the triggering table when it still has a cell selected. When a
    sibling table is cleared to ``None`` (Outputs are also Inputs), that
    cascade must not wipe the panel — fall through to any remaining selection.
    """
    ctx = callback_context
    trigger = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ''
    by_trigger = {
        'fundamentals-valuation-table-a': (val_a_active, val_a_rows),
        'fundamentals-valuation-table-b': (val_b_active, val_b_rows),
        'fundamentals-dcf-table': (dcf_active, dcf_rows),
        'fundamentals-financial-table': (fin_active, fin_rows),
        'fundamentals-big-five-table': (big_active, big_rows),
    }
    if trigger in by_trigger:
        metric = _metric_from_active_cell(*by_trigger[trigger])
        if metric:
            return metric
    return (
        _metric_from_active_cell(val_a_active, val_a_rows)
        or _metric_from_active_cell(val_b_active, val_b_rows)
        or _metric_from_active_cell(dcf_active, dcf_rows)
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


def _has_dependency_metrics(layers: dict[str, list[str]]) -> bool:
    return any(
        layers.get(key)
        for key in (
            'direct_valuation',
            'indirect_valuation',
            'direct_financial',
            'indirect_financial',
            'direct_big_five',
            'indirect_big_five',
        )
    )


def _dependency_chip_rows(layers: dict[str, list[str]], row_map: dict[str, str]) -> html.Div | None:
    """Build direct/indirect dependency chips with live table values when available."""
    groups: list[tuple[str, str, list[str]]] = [
        ('Direct', 'direct', (
            list(layers.get('direct_valuation') or [])
            + list(layers.get('direct_financial') or [])
            + list(layers.get('direct_big_five') or [])
        )),
        ('Indirect', 'indirect', (
            list(layers.get('indirect_valuation') or [])
            + list(layers.get('indirect_financial') or [])
            + list(layers.get('indirect_big_five') or [])
        )),
    ]
    sections: list[Any] = []
    for label, tone, metrics in groups:
        unique = []
        seen: set[str] = set()
        for metric in metrics:
            canonical = _canonical_metric(metric)
            if canonical in seen:
                continue
            seen.add(canonical)
            unique.append(canonical)
        if not unique:
            continue
        chips = [_dependency_chip(metric, row_map, tone=tone) for metric in unique]
        sections.append(html.Div([
            html.Div(label, className='sfa-dep-group-label'),
            html.Div(chips, className='sfa-dep-chip-row'),
        ], className=f'sfa-dep-group sfa-dep-group-{tone}'))
    if not sections:
        return html.Div('No dependency rows for this metric.', className='sfa-formula-meta')
    return html.Div(sections, className='sfa-dep-chips')


def _dependency_chip(metric: str, row_map: dict[str, str], *, tone: str) -> html.Button:
    canonical = _canonical_metric(metric)
    value = row_map.get(canonical)
    children: list[Any] = [html.Span(metric, className='sfa-dep-chip-name')]
    if value and value != '--':
        children.extend([
            html.Span('·', className='sfa-dep-chip-sep'),
            html.Span(value, className='sfa-dep-chip-value'),
        ])
    return html.Button(
        children,
        id={'type': 'sfa-dep-chip', 'metric': canonical},
        n_clicks=0,
        type='button',
        title=f'Open formula for {metric}',
        className=f'sfa-dep-chip sfa-dep-chip-{tone}',
    )


def _locate_metric_cell(
    metric: str,
    fin_rows: list[dict[str, Any]] | None,
    big_rows: list[dict[str, Any]] | None,
    val_a_rows: list[dict[str, Any]] | None,
    val_b_rows: list[dict[str, Any]] | None,
    dcf_rows: list[dict[str, Any]] | None = None,
) -> tuple[str, dict[str, Any]] | None:
    """Return (table_id, active_cell) for a metric row, or None if not found."""
    canonical = _canonical_metric(metric)
    tables: list[tuple[str, list[dict[str, Any]] | None]] = [
        ('fundamentals-valuation-table-a', val_a_rows),
        ('fundamentals-valuation-table-b', val_b_rows),
        ('fundamentals-dcf-table', dcf_rows),
        ('fundamentals-financial-table', fin_rows),
        ('fundamentals-big-five-table', big_rows),
    ]
    for table_id, rows in tables:
        if not rows:
            continue
        for index, row in enumerate(rows):
            if _canonical_metric(str(row.get('metric', ''))) == canonical:
                return table_id, {
                    'row': index,
                    'column': 0,
                    'column_id': 'metric',
                }
    return None


def _triggered_dep_chip_metric(prop_id: str) -> str | None:
    """Parse pattern-matched ``sfa-dep-chip`` metric from a Dash prop_id."""
    try:
        payload = json.loads(str(prop_id).split('.', 1)[0])
    except (TypeError, ValueError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict) or payload.get('type') != 'sfa-dep-chip':
        return None
    metric = payload.get('metric')
    return _canonical_metric(str(metric)) if metric else None


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


