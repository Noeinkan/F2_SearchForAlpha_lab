"""
Optimizer workspace — Grid Search panel (estimate, ranges, run, landscape, apply).
"""

from __future__ import annotations

import threading
import time
from typing import Any

from dash import html, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.agent_strategy import load_bundle
from lib.config_loader import get_agent_strategies
from lib.dash.components import build_alert
from lib.dash.dash_config import FONT_SIZES, get_theme
from lib.dash.optimizer_glossary import GRID_RUN_LABEL, GRID_STOP_LABEL
from lib.dash.optimizer_bayesian_apply import merge_indicator_settings_from_params
from lib.dash.optimizer_space_viz import (
    build_combo_estimate_card,
    build_grid_progress,
    build_param_landscape_figure,
    build_param_range_figure,
)
from lib.dash.routes import build_ticker_terminal_path, is_optimize_route
from lib.grid_search import run_grid_search
from lib.timeframes import normalize_interval
from lib.walkforward.spaces import estimate_grid_size, resolve_search_space

_grid_lock = threading.Lock()
_grid_cancel = threading.Event()
_grid_job: dict[str, Any] = {
    'running': False,
    'result': None,
    'error': None,
    'combos_done': 0,
    'n_combos': 0,
    'strategy_name': None,
    'cancelled': False,
}


def _render_grid_results(data: dict[str, Any] | None, theme: dict) -> html.Div:
    if not data:
        return html.Div()
    best = data.get('best_trial') or {}
    metrics = best.get('metrics') or {}
    params = best.get('params') or {}
    param_lines = [
        html.Div(f"{k}: {v}", style={'fontSize': FONT_SIZES['xs']})
        for k, v in sorted(params.items())
    ]
    status = " (cancelled early)" if data.get('cancelled') else ""
    return html.Div([
        html.Div(f"Best combo{status}", style={
            'fontSize': FONT_SIZES['xs'],
            'fontWeight': '600',
            'color': theme['accent_green'],
            'marginBottom': '6px',
        }),
        html.Div([
            html.Span(
                f"{data.get('metric', '')}={float(best.get('value', 0)):.4f}",
                style={'marginRight': '10px'},
            ),
            html.Span(
                f"Sharpe {float(metrics.get('sharpe', 0)):.2f}",
                style={'marginRight': '10px'},
            ),
            html.Span(f"Ret {float(metrics.get('total_return', 0)):+.1f}%"),
        ], style={
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_primary'],
            'marginBottom': '6px',
        }),
        html.Div(param_lines, style={'color': theme['text_secondary']}),
        html.Div(
            f"{int(data.get('combinations_tested', 0))}/"
            f"{int(data.get('combinations_total', 0))} combos · "
            f"{float(data.get('duration_seconds', 0)):.1f}s",
            style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_tertiary'],
                'marginTop': '6px',
            },
        ),
    ])


def _build_grid_origin_note(data: dict[str, Any], theme: dict) -> html.Div:
    best = data.get('best_trial') or {}
    metrics = best.get('metrics') or {}
    strategy_name = data.get('strategy_name') or 'bundle'
    metric = data.get('metric') or best.get('metric') or 'sortino'
    value = float(best.get('value', 0))
    sharpe = float(metrics.get('sharpe', 0))
    return html.Div([
        html.Span("Applied from Grid Search ", style={'color': theme['text_secondary']}),
        html.Span(f"({strategy_name})", style={'color': theme['accent_cyan'], 'fontWeight': '600'}),
        html.Span(
            f" — best {metric}={value:.4f}, Sharpe {sharpe:.2f}. "
            "Scorecard below uses your current Backtest panel settings.",
            style={'color': theme['text_secondary']},
        ),
    ], style={'fontSize': FONT_SIZES['xs'], 'lineHeight': '1.45'})


def _grid_worker(
    *,
    strategy_name: str,
    metric: str,
    window_from: str,
    window_to: str,
    ticker: str,
    interval: str,
    include_execution: bool,
    only_keys: list[str] | None,
    max_combos: int,
) -> None:
    def _progress(done: int, total: int) -> None:
        with _grid_lock:
            _grid_job['combos_done'] = int(done)
            _grid_job['n_combos'] = int(total)

    try:
        result = run_grid_search(
            strategy_name=strategy_name,
            metric=metric,
            window_from=window_from,
            window_to=window_to,
            ticker_override=ticker,
            interval=interval,
            include_execution=include_execution,
            only_keys=only_keys,
            max_combos=max_combos,
            json_output=True,
            cancel_event=_grid_cancel,
            progress_callback=_progress,
        )
        assert not isinstance(result, dict)  # dry_run=False
        contract = result.to_contract()
        contract['strategy_name'] = strategy_name
        contract['metric'] = metric
        with _grid_lock:
            if _grid_job.get('cancelled'):
                _grid_job['error'] = 'Cancelled'
                _grid_job['result'] = contract if contract.get('combinations_tested') else None
            else:
                _grid_job['result'] = contract
                _grid_job['error'] = None
    except Exception as exc:
        with _grid_lock:
            _grid_job['error'] = str(exc)
            _grid_job['result'] = None
    finally:
        with _grid_lock:
            _grid_job['running'] = False


def register_optimizer_grid_callbacks(app) -> None:
    @app.callback(
        Output('grid-strategy-dropdown', 'options'),
        Input('app-url', 'pathname'),
        prevent_initial_call=False,
    )
    def populate_grid_strategies(pathname):
        if not is_optimize_route(pathname):
            raise PreventUpdate
        strategies = get_agent_strategies()
        options = []
        for name in sorted(strategies):
            cfg = strategies[name] or {}
            desc = str(cfg.get('description') or '').strip()
            short = desc[:72] + ('…' if len(desc) > 72 else '')
            label = f"{name} — {short}" if short else name
            options.append({'label': label, 'value': name})
        return options

    @app.callback(
        [Output('grid-params-checklist', 'options'),
         Output('grid-params-checklist', 'value')],
        [Input('grid-strategy-dropdown', 'value'),
         Input('grid-include-execution', 'value')],
        State('grid-params-checklist', 'value'),
        prevent_initial_call=False,
    )
    def refresh_param_checklist(strategy_name, include_exec, current_values):
        if not strategy_name:
            return [], []
        try:
            bundle = load_bundle(strategy_name)
        except Exception:
            return [], []
        include_execution = 'exec' in (include_exec or [])
        try:
            space = resolve_search_space(
                bundle.search_space,
                include_execution=include_execution,
            )
        except Exception:
            return [], []
        options = [{'label': key, 'value': key} for key in space.keys()]
        available = {o['value'] for o in options}
        # Keep prior selection when still valid; otherwise default to all keys
        # from the bundle-only space (not the huge execution merge).
        prev = [v for v in (current_values or []) if v in available]
        if prev:
            return options, prev
        if include_execution:
            # Prefer indicator keys only as default when execution is merged.
            indicator_defaults = [
                k for k in bundle.search_space.keys() if k in available
            ]
            return options, indicator_defaults or list(available)[:3]
        return options, list(available)

    @app.callback(
        [Output('grid-combo-estimate', 'children'),
         Output('grid-param-ranges-graph', 'figure')],
        [Input('grid-strategy-dropdown', 'value'),
         Input('grid-params-checklist', 'value'),
         Input('grid-include-execution', 'value'),
         Input('grid-max-combos-input', 'value')],
        prevent_initial_call=False,
    )
    def update_grid_estimate(strategy_name, selected_keys, include_exec, max_combos):
        theme = get_theme()
        empty_fig = build_param_range_figure({}, theme)
        if not strategy_name or not selected_keys:
            card = build_combo_estimate_card(0, int(max_combos or 250), theme, space_keys=[])
            return card, empty_fig
        try:
            bundle = load_bundle(strategy_name)
            space = resolve_search_space(
                bundle.search_space,
                include_execution='exec' in (include_exec or []),
                only_keys=list(selected_keys),
            )
            total = estimate_grid_size(space)
            try:
                cap = max(1, int(max_combos or 250))
            except (TypeError, ValueError):
                cap = 250
            card = build_combo_estimate_card(
                total, cap, theme, space_keys=list(space.keys())
            )
            fig = build_param_range_figure(space, theme)
            return card, fig
        except Exception as exc:
            return (
                build_alert(str(exc), "warning", theme=theme),
                empty_fig,
            )

    @app.callback(
        [Output('grid-interval', 'disabled', allow_duplicate=True),
         Output('run-grid-btn', 'children', allow_duplicate=True),
         Output('run-grid-btn', 'disabled', allow_duplicate=True),
         Output('grid-progress', 'children', allow_duplicate=True),
         Output('grid-actions', 'style', allow_duplicate=True)],
        Input('run-grid-btn', 'n_clicks'),
        [State('grid-strategy-dropdown', 'value'),
         State('grid-params-checklist', 'value'),
         State('grid-include-execution', 'value'),
         State('grid-max-combos-input', 'value'),
         State('grid-metric-dropdown', 'value'),
         State('test-window-start', 'date'),
         State('test-window-end', 'date'),
         State('ticker-dropdown', 'value'),
         State('bar-interval', 'value')],
        prevent_initial_call=True,
    )
    def start_grid_search(
        n_clicks,
        strategy_name,
        selected_keys,
        include_exec,
        max_combos,
        metric,
        window_from,
        window_to,
        ticker,
        bar_interval,
    ):
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()
        hidden_actions = {'display': 'none', 'marginTop': '10px'}

        with _grid_lock:
            if _grid_job['running']:
                _grid_cancel.set()
                _grid_job['cancelled'] = True
                progress = build_grid_progress(
                    int(_grid_job.get('combos_done') or 0),
                    int(_grid_job.get('n_combos') or 0),
                    theme,
                    stopping=True,
                )
                return no_update, GRID_STOP_LABEL, False, progress, hidden_actions

        if not strategy_name:
            return (
                True,
                GRID_RUN_LABEL,
                False,
                build_alert("Select a strategy bundle first.", "warning", theme=theme),
                hidden_actions,
            )
        if not selected_keys:
            return (
                True,
                GRID_RUN_LABEL,
                False,
                build_alert("Select at least one parameter.", "warning", theme=theme),
                hidden_actions,
            )
        if not window_from or not window_to:
            return (
                True,
                GRID_RUN_LABEL,
                False,
                build_alert("Set a test window before running Grid Search.", "warning", theme=theme),
                hidden_actions,
            )

        try:
            cap = max(1, min(5000, int(max_combos or 250)))
        except (TypeError, ValueError):
            cap = 250

        # Preflight estimate — refuse over-cap before spawning the worker.
        try:
            bundle = load_bundle(strategy_name)
            space = resolve_search_space(
                bundle.search_space,
                include_execution='exec' in (include_exec or []),
                only_keys=list(selected_keys),
            )
            total = estimate_grid_size(space)
        except Exception as exc:
            return (
                True,
                GRID_RUN_LABEL,
                False,
                build_alert(str(exc), "danger", theme=theme),
                hidden_actions,
            )
        if total > cap:
            return (
                True,
                GRID_RUN_LABEL,
                False,
                build_alert(
                    f"Grid has {total} combinations (cap={cap}). "
                    "Narrow parameters or raise max combos.",
                    "warning",
                    theme=theme,
                ),
                hidden_actions,
            )

        _grid_cancel.clear()
        with _grid_lock:
            _grid_job.update(
                running=True,
                result=None,
                error=None,
                combos_done=0,
                n_combos=total,
                strategy_name=strategy_name,
                cancelled=False,
            )

        thread = threading.Thread(
            target=_grid_worker,
            kwargs={
                'strategy_name': strategy_name,
                'metric': metric or 'sortino',
                'window_from': window_from,
                'window_to': window_to,
                'ticker': ticker,
                'interval': normalize_interval(bar_interval or '1d'),
                'include_execution': 'exec' in (include_exec or []),
                'only_keys': list(selected_keys),
                'max_combos': cap,
            },
            daemon=True,
        )
        thread.start()

        progress = build_grid_progress(0, total, theme)
        return False, GRID_STOP_LABEL, False, progress, hidden_actions

    @app.callback(
        [Output('grid-results-store', 'data'),
         Output('grid-results', 'children'),
         Output('grid-progress', 'children'),
         Output('grid-interval', 'disabled'),
         Output('run-grid-btn', 'children'),
         Output('run-grid-btn', 'disabled'),
         Output('grid-actions', 'style'),
         Output('grid-param-landscape-graph', 'figure')],
        Input('grid-interval', 'n_intervals'),
        prevent_initial_call=True,
    )
    def poll_grid_job(_n):
        theme = get_theme()
        hidden_actions = {'display': 'none', 'marginTop': '10px'}
        visible_actions = {'display': 'block', 'marginTop': '10px'}
        empty_fig = build_param_landscape_figure([], [], 'sortino', theme)

        with _grid_lock:
            running = bool(_grid_job['running'])
            result = _grid_job.get('result')
            error = _grid_job.get('error')
            done = int(_grid_job.get('combos_done') or 0)
            total = int(_grid_job.get('n_combos') or 0)
            cancelled = bool(_grid_job.get('cancelled'))

        if running:
            return (
                no_update,
                no_update,
                build_grid_progress(done, total, theme, stopping=cancelled),
                False,
                GRID_STOP_LABEL,
                False,
                hidden_actions,
                no_update,
            )

        if error and error != 'Cancelled':
            with _grid_lock:
                _grid_job['result'] = None
                _grid_job['error'] = None
            return (
                None,
                build_alert(f"Grid search failed: {error}", "danger", theme=theme),
                html.Div(),
                True,
                GRID_RUN_LABEL,
                False,
                hidden_actions,
                empty_fig,
            )

        if error == 'Cancelled' and not result:
            with _grid_lock:
                _grid_job['result'] = None
                _grid_job['error'] = None
            return (
                None,
                build_alert("Grid search cancelled.", "warning", theme=theme),
                html.Div(),
                True,
                GRID_RUN_LABEL,
                False,
                hidden_actions,
                empty_fig,
            )

        if not result:
            raise PreventUpdate

        with _grid_lock:
            _grid_job['result'] = None
            _grid_job['error'] = None

        fig = build_param_landscape_figure(
            result.get('trials'),
            result.get('space_keys'),
            result.get('metric') or 'sortino',
            theme,
        )
        return (
            result,
            _render_grid_results(result, theme),
            html.Div("Completed.", style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['accent_green'],
            }),
            True,
            GRID_RUN_LABEL,
            False,
            visible_actions,
            fig,
        )

    @app.callback(
        [Output('indicator-settings-store', 'data', allow_duplicate=True),
         Output('optimizer-apply-store', 'data', allow_duplicate=True),
         Output('backtest-origin-note', 'children', allow_duplicate=True),
         Output('app-url', 'pathname', allow_duplicate=True),
         Output('grid-progress', 'children', allow_duplicate=True)],
        Input('apply-grid-btn', 'n_clicks'),
        [State('grid-results-store', 'data'),
         State('indicator-settings-store', 'data'),
         State('ticker-dropdown', 'value')],
        prevent_initial_call=True,
    )
    def apply_grid_params(
        n_clicks,
        grid_data,
        current_settings,
        ticker,
    ):
        if not n_clicks or not grid_data:
            raise PreventUpdate

        theme = get_theme()
        strategy_name = grid_data.get('strategy_name')
        best = grid_data.get('best_trial') or {}
        flat_params = best.get('params') or {}
        if not strategy_name or not flat_params:
            raise PreventUpdate

        try:
            bundle = load_bundle(strategy_name)
        except Exception as exc:
            return (
                no_update,
                no_update,
                no_update,
                build_alert(f"Could not load bundle: {exc}", "danger", theme=theme),
                no_update,
                build_alert("Apply failed.", "danger", theme=theme),
            )

        merged_settings = merge_indicator_settings_from_params(current_settings, flat_params)
        apply_payload = {
            'buy': list(bundle.buy_signals),
            'sell': list(bundle.sell_signals),
            'nonce': time.time(),
        }
        note = _build_grid_origin_note(grid_data, theme)
        grid_note = html.Div(
            "Applied to Backtest tab.",
            style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_green']},
        )

        return (
            merged_settings,
            apply_payload,
            note,
            build_ticker_terminal_path(ticker),
            grid_note,
        )
