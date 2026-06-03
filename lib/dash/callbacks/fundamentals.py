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
from lib.dash.dash_config import DEFAULT_THEME, DEFAULT_TICKER, FONT_MONO, FONT_SIZES, get_theme
from lib.dash.ticker_search import resolve_ticker_symbol
from lib.fundamentals import fetch_fundamentals

logger = logging.getLogger(__name__)

_METRIC_ALIASES = {
    'Current Price': 'Year-end Close',
    'Current/Entry price ratio': 'Close/Entry price ratio',
}

_VALUATION_EXPLAIN_MAP: dict[str, dict[str, Any]] = {
    "Analysts' GR": {
        'formula': 'Analysts\' GR comes from earningsGrowth, revenueGrowth, or earningsQuarterlyGrowth when available.',
        'explanation': 'The model prefers analyst-provided growth fields from market data to seed long-term estimates.',
        'sources': {'valuation': [], 'financial': [], 'big_five': []},
        'inputs': ['yfinance info: earningsGrowth/revenueGrowth/earningsQuarterlyGrowth'],
    },
    'Historical Equity GR': {
        'formula': 'Historical Equity GR = 10Y CAGR of equity.',
        'explanation': 'Equity CAGR is used as a stable fallback when analyst growth is unavailable.',
        'sources': {'valuation': [], 'financial': ['Equity'], 'big_five': ['Equity-GR']},
        'inputs': [],
    },
    'Estimated EPS GR': {
        'formula': 'Estimated EPS GR = first positive among Analysts\' GR, Historical Equity GR, and historical EPS CAGR.',
        'explanation': 'A conservative selector chooses the first positive growth estimate from analyst and historical signals.',
        'sources': {'valuation': ["Analysts' GR", 'Historical Equity GR'], 'financial': ['EPS'], 'big_five': ['EPS-GR']},
        'inputs': [],
    },
    'Current EPS': {
        'formula': 'Current EPS = trailingEps from info when available, otherwise latest annual EPS.',
        'explanation': 'Current EPS prefers market trailing EPS and falls back to statement-derived EPS.',
        'sources': {'valuation': [], 'financial': ['EPS'], 'big_five': []},
        'inputs': ['yfinance info: trailingEps'],
    },
    'Estimated EPS 10y': {
        'formula': 'Estimated EPS 10y = Current EPS * (1 + Estimated EPS GR)^10.',
        'explanation': 'Future EPS is projected over ten years using compound growth.',
        'sources': {'valuation': ['Current EPS', 'Estimated EPS GR'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Rule #1st Price/Earn Ratio': {
        'formula': 'Rule #1st Price/Earn Ratio = max(0, Estimated EPS GR * 200).',
        'explanation': 'Rule #1 ties acceptable P/E to growth and clamps negative values to zero.',
        'sources': {'valuation': ['Estimated EPS GR'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Forward Price/Earn Ratio': {
        'formula': 'Forward Price/Earn Ratio = forwardPE from market info.',
        'explanation': 'This is the market-implied forward P/E estimate from the data provider.',
        'sources': {'valuation': [], 'financial': [], 'big_five': []},
        'inputs': ['yfinance info: forwardPE'],
    },
    'Historical PE': {
        'formula': 'Historical PE = mean of last 10 annual PE values.',
        'explanation': 'A 10-year average P/E smooths one-off valuation spikes.',
        'sources': {'valuation': [], 'financial': ['PE Ratio'], 'big_five': ['PE Ratio']},
        'inputs': [],
    },
    'Rule #1 PE': {
        'formula': 'Rule #1 PE = min(Rule #1st Price/Earn Ratio, Forward Price/Earn Ratio, Historical PE).',
        'explanation': 'The model picks the most conservative P/E candidate.',
        'sources': {'valuation': ['Rule #1st Price/Earn Ratio', 'Forward Price/Earn Ratio', 'Historical PE'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'PEG': {
        'formula': 'PEG = Rule #1 PE / (Estimated EPS GR * 100).',
        'explanation': 'PEG relates valuation multiple to growth to sanity-check pricing versus expansion.',
        'sources': {'valuation': ['Rule #1 PE', 'Estimated EPS GR'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'MARR': {
        'formula': 'MARR is a configured annual required return.',
        'explanation': 'MARR discounts future value into present value at your required return.',
        'sources': {'valuation': [], 'financial': [], 'big_five': []},
        'inputs': ['Default 15% unless overridden'],
    },
    'MOS': {
        'formula': 'MOS is the configured margin of safety multiplier.',
        'explanation': 'MOS applies an extra safety buffer before considering an entry.',
        'sources': {'valuation': [], 'financial': [], 'big_five': []},
        'inputs': ['Default 50% unless overridden'],
    },
    'Fut. Market Price (10 Y)': {
        'formula': 'Fut. Market Price (10 Y) = Estimated EPS 10y * Rule #1 PE.',
        'explanation': 'Projected price combines future EPS with conservative terminal P/E.',
        'sources': {'valuation': ['Estimated EPS 10y', 'Rule #1 PE'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Sticker Price': {
        'formula': 'Sticker Price = Fut. Market Price (10 Y) / (1 + MARR)^10.',
        'explanation': 'Future value is discounted back 10 years at the required return.',
        'sources': {'valuation': ['Fut. Market Price (10 Y)', 'MARR'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Year-end Close': {
        'formula': 'Year-end Close uses the latest available annual close from price history.',
        'explanation': 'Current comparison uses the annual close series used across fundamentals.',
        'sources': {'valuation': [], 'financial': ['Stock Price (31/12)'], 'big_five': []},
        'inputs': ['yfinance history: yearly close'],
    },
    'Entry Price': {
        'formula': 'Entry Price = Sticker Price * MOS.',
        'explanation': 'Entry price applies a safety discount to the discounted intrinsic estimate.',
        'sources': {'valuation': ['Sticker Price', 'MOS'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
    'Close/Entry price ratio': {
        'formula': 'Close/Entry price ratio = Year-end Close / Entry Price.',
        'explanation': 'A ratio above 1.0 means price is above the conservative entry threshold.',
        'sources': {'valuation': ['Year-end Close', 'Entry Price'], 'financial': [], 'big_five': []},
        'inputs': [],
    },
}

_REVERSE_DEPENDENCY_MAP: dict[str, list[str]] = {}
for _valuation_metric, _details in _VALUATION_EXPLAIN_MAP.items():
    for _table_sources in _details.get('sources', {}).values():
        for _source_metric in _table_sources:
            _REVERSE_DEPENDENCY_MAP.setdefault(_source_metric, []).append(_valuation_metric)

_VALUATION_LATEX: dict[str, str] = {
    "Analysts' GR": r"\text{Analysts' GR} \leftarrow \text{earningsGrowth, revenueGrowth, earningsQuarterlyGrowth}",
    'Historical Equity GR': r"g_{\text{eq}} = \mathrm{CAGR}_{10Y}(\text{Equity})",
    "Estimated EPS GR": r"g_{\text{EPS}} = \text{first positive}(\text{Analysts' GR},\; g_{\text{eq}},\; \mathrm{CAGR}_{10Y}(\text{EPS}))",
    'Current EPS': r"\text{EPS}_0 = \text{trailingEps} \;\|\; \text{latest annual EPS}",
    'Estimated EPS 10y': r"\text{EPS}_{10} = \text{EPS}_0 \cdot (1 + g_{\text{EPS}})^{10}",
    'Rule #1st Price/Earn Ratio': r"\text{P/E}_{\text{calc}} = \max(0,\; g_{\text{EPS}} \times 200)",
    'Forward Price/Earn Ratio': r"\text{P/E}_{\text{fwd}} = \text{forwardPE}",
    'Historical PE': r"\text{P/E}_{\text{hist}} = \mathrm{mean}(\text{last 10 annual P/E})",
    'Rule #1 PE': r"\text{P/E}_{\text{Rule1}} = \min(\text{P/E}_{\text{calc}},\; \text{P/E}_{\text{fwd}},\; \text{P/E}_{\text{hist}})",
    'PEG': r"\text{PEG} = \dfrac{\text{P/E}_{\text{Rule1}}}{g_{\text{EPS}} \times 100}",
    'MARR': r"r_{\text{MARR}} = \text{configured annual required return}",
    'MOS': r"m_{\text{MOS}} = \text{configured margin-of-safety multiplier}",
    'Fut. Market Price (10 Y)': r"P_{10} = \text{EPS}_{10} \times \text{P/E}_{\text{Rule1}}",
    'Sticker Price': r"P_{\text{sticker}} = \dfrac{P_{10}}{(1 + r_{\text{MARR}})^{10}}",
    'Year-end Close': r"P_{\text{close}} = \text{latest annual close}",
    'Entry Price': r"P_{\text{entry}} = P_{\text{sticker}} \times m_{\text{MOS}}",
    'Close/Entry price ratio': r"\text{Ratio} = \dfrac{P_{\text{close}}}{P_{\text{entry}}}",
}


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


def _latex_money(value: float | None) -> str:
    if value is None:
        return r'\text{--}'
    return rf'\${value:,.2f}'


def _latex_decimal(value: float | None, places: int = 2) -> str:
    if value is None:
        return r'\text{--}'
    return f'{value:.{places}f}'


def _latex_pct(value: float | None, places: int = 2) -> str:
    if value is None:
        return r'\text{--}'
    return rf'{value * 100:.{places}f}\%'


def _build_substituted_latex(metric: str, row_map: dict[str, str]) -> str | None:
    """Build a numeric substitution line for metrics with table inputs."""
    canonical = _canonical_metric(metric)

    def raw(key: str) -> str:
        return row_map.get(_canonical_metric(key), '--')

    def num(key: str) -> float | None:
        return _parse_display_number(raw(key))

    def append_result(expression: str, result_key: str | None = None) -> str:
        result = num(result_key or canonical)
        if result is None:
            return expression
        if canonical in {'PEG', 'Close/Entry price ratio', 'Rule #1st Price/Earn Ratio', 'Forward Price/Earn Ratio', 'Historical PE', 'Rule #1 PE'}:
            return rf'{expression} = {_latex_decimal(result, 1)}'
        if canonical in {"Analysts' GR", 'Historical Equity GR', 'Estimated EPS GR', 'MARR', 'MOS'}:
            return rf'{expression} = {_latex_pct(result)}'
        return rf'{expression} = {_latex_money(result)}'

    if canonical == 'Estimated EPS 10y':
        eps0, growth = num('Current EPS'), num('Estimated EPS GR')
        if eps0 is None or growth is None:
            return None
        return append_result(
            rf'\text{{EPS}}_{{10}} = {_latex_money(eps0)} \cdot (1 + {_latex_decimal(growth)})^{{10}}',
        )

    if canonical == 'Rule #1st Price/Earn Ratio':
        growth = num('Estimated EPS GR')
        if growth is None:
            return None
        return append_result(
            rf'\text{{P/E}}_{{\text{{calc}}}} = \max(0,\; {_latex_decimal(growth)} \times 200)',
        )

    if canonical == 'Rule #1 PE':
        calc, fwd, hist = num('Rule #1st Price/Earn Ratio'), num('Forward Price/Earn Ratio'), num('Historical PE')
        candidates = [value for value in (calc, fwd, hist) if value is not None and value > 0]
        if not candidates:
            return None
        expr = (
            rf'\text{{P/E}}_{{\text{{Rule1}}}} = \min('
            rf'{_latex_decimal(calc, 1) if calc is not None else r"\text{--}" },\; '
            rf'{_latex_decimal(fwd, 1) if fwd is not None else r"\text{--}" },\; '
            rf'{_latex_decimal(hist, 1) if hist is not None else r"\text{--}" })'
        )
        return append_result(expr)

    if canonical == 'PEG':
        pe, growth = num('Rule #1 PE'), num('Estimated EPS GR')
        if pe is None or growth is None or growth <= 0:
            return None
        return append_result(
            rf'\text{{PEG}} = \dfrac{{{_latex_decimal(pe, 1)}}}{{{_latex_decimal(growth)} \times 100}}',
        )

    if canonical == 'Fut. Market Price (10 Y)':
        eps10, pe = num('Estimated EPS 10y'), num('Rule #1 PE')
        if eps10 is None or pe is None:
            return None
        return append_result(
            rf'P_{{10}} = {_latex_money(eps10)} \times {_latex_decimal(pe, 1)}',
        )

    if canonical == 'Sticker Price':
        future_price, marr = num('Fut. Market Price (10 Y)'), num('MARR')
        if future_price is None or marr is None:
            return None
        return append_result(
            rf'P_{{\text{{sticker}}}} = \dfrac{{{_latex_money(future_price)}}}{{(1 + {_latex_decimal(marr)})^{{10}}}}',
        )

    if canonical == 'Entry Price':
        sticker, mos = num('Sticker Price'), num('MOS')
        if sticker is None or mos is None:
            return None
        return append_result(
            rf'P_{{\text{{entry}}}} = {_latex_money(sticker)} \times {_latex_decimal(mos)}',
        )

    if canonical == 'Close/Entry price ratio':
        close, entry = num('Year-end Close'), num('Entry Price')
        if close is None or entry is None or entry == 0:
            return None
        return append_result(
            rf'\text{{Ratio}} = \dfrac{{{_latex_money(close)}}}{{{_latex_money(entry)}}}',
        )

    if canonical == 'MARR':
        marr = num('MARR')
        return rf'r_{{\text{{MARR}}}} = {_latex_pct(marr)}' if marr is not None else None

    if canonical == 'MOS':
        mos = num('MOS')
        return rf'm_{{\text{{MOS}}}} = {_latex_pct(mos)} \; (\times {_latex_decimal(mos)})' if mos is not None else None

    return None


def _formula_card(symbolic_latex: str, substituted_latex: str | None) -> html.Div:
    blocks: list[Any] = [
        html.Div(
            className='sfa-formula-block sfa-formula-symbolic',
            children=[
                html.Div('Formula', className='sfa-formula-block-label'),
                html.Div(className='sfa-formula-math', children=rf'\[{symbolic_latex}\]'),
            ],
        ),
    ]
    if substituted_latex:
        blocks.append(
            html.Div(
                className='sfa-formula-block sfa-formula-substituted',
                children=[
                    html.Div('With current values', className='sfa-formula-block-label'),
                    html.Div(className='sfa-formula-math', children=rf'\[{substituted_latex}\]'),
                ],
            ),
        )
    return html.Div(blocks, className='sfa-formula-card')


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
         Input('refresh-fundamentals-button', 'n_clicks'),
         Input('load-fundamentals-ticker-button', 'n_clicks'),
         Input('fundamentals-ticker-input', 'n_submit')],
        [State('ticker-dropdown', 'value'),
         State('fundamentals-ticker-input', 'value')],
        prevent_initial_call='initial_duplicate',
    )
    def load_fundamentals(pathname, refresh_clicks, load_clicks, input_submit, ticker, overlay_ticker):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger_id == 'app-url':
            if not is_fundamentals_route(pathname):
                raise PreventUpdate
            raw = str(overlay_ticker or ticker or DEFAULT_TICKER).strip()
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

    @app.callback(
        [Output('fundamentals-financial-table', 'style_data_conditional'),
         Output('fundamentals-big-five-table', 'style_data_conditional'),
         Output('fundamentals-valuation-table', 'style_data_conditional'),
         Output('fundamentals-valuation-explain', 'children'),
         Output('fundamentals-valuation-explain', 'style'),
         Output('fundamentals-financial-table', 'active_cell'),
         Output('fundamentals-big-five-table', 'active_cell'),
         Output('fundamentals-valuation-table', 'active_cell')],
        [Input('fundamentals-financial-table', 'active_cell'),
         Input('fundamentals-big-five-table', 'active_cell'),
         Input('fundamentals-valuation-table', 'active_cell'),
         Input('fundamentals-esc-signal', 'value'),
         Input('theme-store', 'data')],
        [State('fundamentals-financial-table', 'data'),
         State('fundamentals-big-five-table', 'data'),
         State('fundamentals-big-five-table', 'columns'),
         State('fundamentals-valuation-table', 'data')],
    )
    def update_fundamentals_explainability(fin_active, big_active, val_active, esc_signal, theme_name, fin_rows, big_rows, big_columns, val_rows):
        theme = get_theme(theme_name or DEFAULT_THEME)
        value_columns = _big_five_value_columns(big_columns)
        financial_style = _financial_conditionals(theme)
        big_five_style = _big_five_conditionals(theme, value_columns)
        valuation_style = _valuation_conditionals(theme)
        explain_style = _valuation_explain_style(theme, visible=False)
        explain_children = []
        clear_cells = no_update, no_update, no_update

        trigger = callback_context.triggered[0]['prop_id'].split('.')[0] if callback_context.triggered else ''
        if trigger == 'fundamentals-esc-signal' and esc_signal:
            return (
                financial_style, big_five_style, valuation_style,
                explain_children, explain_style,
                None, None, None,
            )

        metric = _resolve_selected_metric(fin_active, big_active, val_active, fin_rows, big_rows, val_rows)
        if not metric:
            return financial_style, big_five_style, valuation_style, explain_children, explain_style, *clear_cells

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
        return financial_style, big_five_style, valuation_style, explain_children, explain_style, *clear_cells

    app.clientside_callback(
        """
        function(children) {
            const panel = document.getElementById('fundamentals-valuation-explain');
            if (!panel || !children || (Array.isArray(children) && children.length === 0)) {
                return window.dash_clientside.no_update;
            }
            const typeset = function() {
                if (window.MathJax && window.MathJax.typesetPromise) {
                    return window.MathJax.typesetPromise([panel]);
                }
                if (window.MathJax && window.MathJax.startup && window.MathJax.startup.promise) {
                    return window.MathJax.startup.promise.then(function() {
                        return window.MathJax.typesetPromise([panel]);
                    });
                }
                return Promise.resolve();
            };
            typeset().catch(function(err) {
                console.warn('MathJax typeset failed', err);
            });
            return window.dash_clientside.no_update;
        }
        """,
        Output('fundamentals-mathjax-sync', 'children'),
        Input('fundamentals-valuation-explain', 'children'),
    )


def _render_payload(payload: dict[str, Any], theme: dict) -> html.Div:
    years = [str(year) for year in payload.get('years', [])]
    valuation_rows = payload.get('valuation', [])
    return html.Div([
        _summary_strip(payload, theme),
        html.Div([
            html.Div([
                _panel_title('Financials', theme),
                _financial_table(payload.get('financials', []), years, theme),
            ], style=_panel_style(theme), className='sfa-fundamentals-panel sfa-fundamentals-main'),
            html.Div([
                _panel_title('Valuation', theme),
                _valuation_assumptions(valuation_rows, theme),
                _valuation_table(valuation_rows, theme),
                html.Div(
                    id='fundamentals-valuation-explain',
                    className='sfa-valuation-explain',
                    style=_valuation_explain_style(theme, visible=False),
                ),
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
        'id': 'fundamentals-financial-table',
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
        'fontFamily': FONT_MONO,
        'fontSize': FONT_SIZES['xs'],
        'fontWeight': 700,
        'color': theme['accent_red'],
        'marginBottom': '4px',
        'lineHeight': '1.25',
    })


def _valuation_table(rows: list[dict[str, Any]], theme: dict) -> dash_table.DataTable:
    columns = [{'name': 'Metric', 'id': 'metric'}, {'name': 'Value', 'id': 'value'}]
    props: dict[str, Any] = {
        'id': 'fundamentals-valuation-table',
        'columns': columns,
        'data': rows,
        'fill_width': True,
        'style_table': {'overflowX': 'auto', 'width': '100%', 'minWidth': '100%'},
        'style_cell': _table_cell_style(theme),
        'style_cell_conditional': [
            {'if': {'column_id': 'metric'}, 'textAlign': 'left', 'fontWeight': 700, 'minWidth': '170px', 'width': '62%'},
            {'if': {'column_id': 'value'}, 'textAlign': 'right', 'width': '38%'},
        ],
        'style_header': _table_header_style(theme),
        'style_data_conditional': _valuation_conditionals(theme),
        'tooltip_data': _valuation_tooltips(rows),
        'tooltip_duration': None,
    }
    return dash_table.DataTable(**props)


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
            'fontFamily': FONT_MONO,
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_secondary'],
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
        tooltip_text = f"{explain['formula']}\n{explain['explanation']}"
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
    symbolic_latex = _VALUATION_LATEX.get(canonical, explain.get('formula', '--'))
    substituted_latex = _build_substituted_latex(canonical, row_map)
    return [
        html.Div(f"Calculation detail: {metric}", className='sfa-formula-title', style={
            'color': theme['accent_blue'],
        }),
        _formula_card(symbolic_latex, substituted_latex),
        html.Div(explain.get('explanation', '--'), className='sfa-formula-explanation', style={
            'color': theme['text_secondary'],
        }),
        html.Div(_source_summary(explain), className='sfa-formula-meta', style={
            'color': theme['text_secondary'],
        }),
        html.Div(_layer_summary_text(layers), className='sfa-formula-meta', style={
            'color': theme['text_secondary'],
        }),
    ]


def _valuation_source_content(metric: str, dependents: list[str], theme: dict) -> list[html.Div]:
    joined = ', '.join(dependents[:5])
    more = '' if len(dependents) <= 5 else f" (+{len(dependents) - 5} more)"
    return [
        html.Div(f"Source metric: {metric}", style={
            'fontFamily': FONT_MONO,
            'fontSize': FONT_SIZES['xs'],
            'fontWeight': 700,
            'color': theme['accent_blue'],
            'marginBottom': '5px',
        }),
        html.Div(f"This source contributes to: {joined}{more}.", style={
            'fontFamily': FONT_MONO,
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_secondary'],
            'lineHeight': '1.35',
        }),
    ]


def _valuation_generic_content(metric: str, theme: dict) -> list[html.Div]:
    return [
        html.Div(f"Selected metric: {metric}", style={
            'fontFamily': FONT_MONO,
            'fontSize': FONT_SIZES['xs'],
            'fontWeight': 700,
            'color': theme['accent_blue'],
            'marginBottom': '5px',
        }),
        html.Div('No explicit calculation graph is configured for this metric yet.', style={
            'fontFamily': FONT_MONO,
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


def _resolve_selected_metric(fin_active: dict[str, Any] | None, big_active: dict[str, Any] | None, val_active: dict[str, Any] | None, fin_rows: list[dict[str, Any]] | None, big_rows: list[dict[str, Any]] | None, val_rows: list[dict[str, Any]] | None) -> str | None:
    ctx = callback_context
    trigger = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else ''
    if trigger == 'fundamentals-valuation-table':
        return _metric_from_active_cell(val_active, val_rows)
    if trigger == 'fundamentals-financial-table':
        return _metric_from_active_cell(fin_active, fin_rows)
    if trigger == 'fundamentals-big-five-table':
        return _metric_from_active_cell(big_active, big_rows)
    return (
        _metric_from_active_cell(val_active, val_rows)
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