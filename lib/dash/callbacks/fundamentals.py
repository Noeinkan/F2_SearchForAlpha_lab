"""Fundamentals page callbacks."""

from __future__ import annotations

import logging

from dash import callback_context, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.routes import extract_path_ticker, is_fundamentals_route, ticker_from_search
from lib.dash.callbacks.startup import _ensure_ticker_options_loaded
from lib.dash.dash_config import (
    DEFAULT_THEME,
    DEFAULT_TICKER,
    DEFAULT_FUNDAMENTALS_PERIOD,
    FUNDAMENTALS_FALLBACK_TICKER,
    get_theme,
)
from lib.dash.ticker_search import resolve_ticker_symbol
from lib.fundamentals import fetch_fundamentals

from .fundamentals_formulas import (
    _VALUATION_EXPLAIN_MAP,
    _REVERSE_DEPENDENCY_MAP,
    _build_substituted_equation,
    _build_symbolic_equation,
    _canonical_metric,
    _dependency_layers,
    _formula_card,
    _highlight_metric_rules,
    _merge_valuation_rows,
    _parse_display_number,
    _resolve_selected_metric,
    _valuation_explain_content,
    _valuation_explain_style,
    _valuation_generic_content,
    _valuation_row_map,
    _valuation_source_content,
)
from .fundamentals_render import (
    _big_five_conditionals,
    _big_five_value_columns,
    _empty_state,
    _financial_conditionals,
    _render_payload,
    _valuation_conditionals,
)

logger = logging.getLogger(__name__)

# Re-exports for tests / external callers that imported from this module.
__all__ = [
    "register_fundamentals_callbacks",
    "_VALUATION_EXPLAIN_MAP",
    "_build_substituted_equation",
    "_build_symbolic_equation",
    "_canonical_metric",
    "_dependency_layers",
    "_formula_card",
    "_highlight_metric_rules",
    "_parse_display_number",
    "_render_payload",
    "_valuation_row_map",
]


def register_fundamentals_callbacks(app) -> None:
    @app.callback(
        Output('fundamentals-period-store', 'data'),
        Input('fundamentals-period-toggle', 'value'),
    )
    def sync_fundamentals_period(period):
        return period or DEFAULT_FUNDAMENTALS_PERIOD

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
         Output('ticker-dropdown', 'value', allow_duplicate=True),
         Output('fundamentals-ticker-input', 'value', allow_duplicate=True)],
        [Input('app-url', 'pathname'),
         Input('app-url', 'search'),
         Input('route-ticker-store', 'data'),
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
        path_ticker,
    ):
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]
        url_ticker = ticker_from_search(search)
        path_from_url = extract_path_ticker(pathname)

        # user_ticker is only populated by the startup callback when the
        # user actually changes the dropdown (prevent_initial_call=True).
        # It stays None on a fresh direct visit, which is exactly the
        # signal we use to swap the TSLA page-default for a real company.
        if trigger_id == 'app-url':
            if not is_fundamentals_route(pathname):
                raise PreventUpdate
            effective_path_ticker = path_from_url or path_ticker
            cold_load = not (effective_path_ticker or url_ticker or overlay_ticker or user_ticker or ticker)
            fallback = FUNDAMENTALS_FALLBACK_TICKER if cold_load else DEFAULT_TICKER
            raw = str(
                effective_path_ticker or url_ticker or overlay_ticker or user_ticker or ticker or fallback
            ).strip()
        elif trigger_id == 'route-ticker-store':
            if not is_fundamentals_route(pathname):
                raise PreventUpdate
            if not path_ticker:
                raise PreventUpdate
            raw = str(path_ticker).strip()
        else:
            raw = str(overlay_ticker or ticker or DEFAULT_TICKER).strip()

        options = _ensure_ticker_options_loaded()
        symbol = resolve_ticker_symbol(raw, options)

        if not symbol:
            return None, 'Invalid ticker', 'ERROR: ticker is required', no_update, no_update

        try:
            payload = fetch_fundamentals(symbol)
        except Exception as exc:
            logger.exception("Error loading fundamentals for %s", symbol)
            return None, f'{symbol} fundamentals', f'ERROR: {exc}', no_update, no_update

        title = f"{payload['company_name']} ({payload['ticker']})"
        # Promote overlay ticker edits to global symbol only when user explicitly
        # loads/submits a ticker from fundamentals.
        update_global_ticker = symbol if trigger_id in {
            'load-fundamentals-ticker-button',
            'fundamentals-ticker-input',
            'app-url',
            'route-ticker-store',
        } else no_update
        return payload, title, f"LOADED {payload['as_of']}", update_global_ticker, symbol

    @app.callback(
        Output('fundamentals-content', 'children'),
        [Input('fundamentals-store', 'data'),
         Input('fundamentals-period-store', 'data'),
         Input('theme-store', 'data')],
    )
    def render_fundamentals(payload, period, theme_name):
        theme = get_theme(theme_name or DEFAULT_THEME)
        if not payload:
            return _empty_state(theme, "Open fundamentals after selecting a stock.")
        return _render_payload(payload, period or DEFAULT_FUNDAMENTALS_PERIOD, theme)

    @app.callback(
        [Output('fundamentals-financial-table', 'style_data_conditional'),
         Output('fundamentals-big-five-table', 'style_data_conditional'),
         Output('fundamentals-valuation-table-a', 'style_data_conditional'),
         Output('fundamentals-valuation-table-b', 'style_data_conditional'),
         Output('fundamentals-dcf-table', 'style_data_conditional'),
         Output('fundamentals-valuation-explain', 'children'),
         Output('fundamentals-valuation-explain', 'style'),
         Output('fundamentals-financial-table', 'active_cell'),
         Output('fundamentals-big-five-table', 'active_cell'),
         Output('fundamentals-valuation-table-a', 'active_cell'),
         Output('fundamentals-valuation-table-b', 'active_cell'),
         Output('fundamentals-dcf-table', 'active_cell')],
        [Input('fundamentals-financial-table', 'active_cell'),
         Input('fundamentals-big-five-table', 'active_cell'),
         Input('fundamentals-valuation-table-a', 'active_cell'),
         Input('fundamentals-valuation-table-b', 'active_cell'),
         Input('fundamentals-dcf-table', 'active_cell'),
         Input('fundamentals-esc-signal', 'value'),
         Input('theme-store', 'data')],
        [State('fundamentals-financial-table', 'data'),
         State('fundamentals-big-five-table', 'data'),
         State('fundamentals-big-five-table', 'columns'),
         State('fundamentals-valuation-table-a', 'data'),
         State('fundamentals-valuation-table-b', 'data'),
         State('fundamentals-dcf-table', 'data')],
    )
    def update_fundamentals_explainability(
        fin_active,
        big_active,
        val_a_active,
        val_b_active,
        dcf_active,
        esc_signal,
        theme_name,
        fin_rows,
        big_rows,
        big_columns,
        val_a_rows,
        val_b_rows,
        dcf_rows,
    ):
        theme = get_theme(theme_name or DEFAULT_THEME)
        value_columns = _big_five_value_columns(big_columns)
        financial_style = _financial_conditionals(theme)
        big_five_style = _big_five_conditionals(theme, value_columns)
        valuation_style = _valuation_conditionals(theme)
        dcf_style = _valuation_conditionals(theme)
        val_rows = _merge_valuation_rows(val_a_rows, val_b_rows) + list(dcf_rows or [])
        explain_style = _valuation_explain_style(theme, visible=False)
        explain_children = []
        clear_cells = no_update, no_update, no_update, no_update, no_update

        trigger = callback_context.triggered[0]['prop_id'].split('.')[0] if callback_context.triggered else ''
        if trigger == 'fundamentals-esc-signal' and esc_signal:
            return (
                financial_style, big_five_style, valuation_style, valuation_style, dcf_style,
                explain_children, explain_style,
                None, None, None, None, None,
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
            dcf_active,
            dcf_rows,
        )
        if not metric:
            return (
                financial_style,
                big_five_style,
                valuation_style,
                valuation_style,
                dcf_style,
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
            dcf_style += _highlight_metric_rules(layers['direct_valuation'], theme, tone='direct')
            dcf_style += _highlight_metric_rules(layers['indirect_valuation'], theme, tone='indirect')
            dcf_style += _highlight_metric_rules([canonical_metric], theme, tone='selected')
            explain_children = _valuation_explain_content(canonical_metric, explain, theme, val_rows)
        else:
            dependents = _REVERSE_DEPENDENCY_MAP.get(canonical_metric, [])
            if dependents:
                valuation_style += _highlight_metric_rules(dependents, theme, tone='direct')
                dcf_style += _highlight_metric_rules(dependents, theme, tone='direct')
                financial_style += _highlight_metric_rules([canonical_metric], theme, tone='selected')
                big_five_style += _highlight_metric_rules([canonical_metric], theme, tone='selected')
                explain_children = _valuation_source_content(canonical_metric, dependents, theme)
            else:
                explain_children = _valuation_generic_content(canonical_metric, theme)

        explain_style = _valuation_explain_style(theme, visible=True)
        val_a_cell, val_b_cell, dcf_cell = clear_cells[2], clear_cells[3], clear_cells[4]
        if trigger == 'fundamentals-valuation-table-a':
            val_b_cell = None
            dcf_cell = None
        elif trigger == 'fundamentals-valuation-table-b':
            val_a_cell = None
            dcf_cell = None
        elif trigger == 'fundamentals-dcf-table':
            val_a_cell = None
            val_b_cell = None
        return (
            financial_style,
            big_five_style,
            valuation_style,
            valuation_style,
            dcf_style,
            explain_children,
            explain_style,
            clear_cells[0],
            clear_cells[1],
            val_a_cell,
            val_b_cell,
            dcf_cell,
        )

