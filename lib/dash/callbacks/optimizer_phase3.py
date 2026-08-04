"""
Optimizer workspace Phase 3/4 — landscape, history, OOS validation, Bayesian sweep.
"""

from __future__ import annotations

import threading
import time
from datetime import datetime
from typing import Any

import pandas as pd
from dash import callback_context, dash_table, html, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.agent_strategy import load_bundle
from lib.bayesian_optimization import run_study
from lib.config_loader import get_agent_strategies
from lib.dash.combo_walkforward import ComboSpec, run_combo_walkforward
from lib.dash.components import build_alert
from lib.dash.dash_config import FONT_SIZES, get_theme
from lib.dash.optimizer_bayesian_apply import merge_indicator_settings_from_params
from lib.dash.optimizer_history import history_for_ticker
from lib.dash.optimizer_landscape import build_return_sharpe_figure
from lib.dash.routes import build_ticker_terminal_path, is_optimize_route
from lib.dash.state import dashboard_state
from lib.timeframes import normalize_interval
from lib.walkforward.runner import WalkForwardOptions, run_walkforward

_bayesian_lock = threading.Lock()
_bayesian_cancel = threading.Event()
_bayesian_job: dict[str, Any] = {
    'running': False,
    'result': None,
    'error': None,
    'trials_done': 0,
    'n_trials': 0,
    'strategy_name': None,
    'cancelled': False,
}

_oos_lock = threading.Lock()
_oos_cancel = threading.Event()
_oos_job: dict[str, Any] = {
    'running': False,
    'result': None,
    'error': None,
    'cancelled': False,
    'kind': None,
}


def _trunc(text: Any, max_len: int = 36) -> str:
    s = str(text or '')
    if len(s) <= max_len:
        return s
    return s[: max_len - 1] + '…'


def _winner_signals(results_data: list[dict[str, Any]], sort_by: str | None) -> tuple[list[str], list[str]]:
    results_df = pd.DataFrame(results_data)
    metric = sort_by or 'Robustness_Score'
    if metric not in results_df.columns:
        metric = 'Robustness_Score' if 'Robustness_Score' in results_df.columns else 'Total_Return_%'
    ascending = metric == 'Max_Drawdown_%'
    if 'Low_Sample' in results_df.columns:
        results_df = results_df.sort_values(['Low_Sample', metric], ascending=[True, ascending])
    else:
        results_df = results_df.sort_values(metric, ascending=ascending)
    best = results_df.iloc[0]
    buy = [s.strip() for s in str(best['Buy_Signals']).split(',') if s.strip()]
    sell = [s.strip() for s in str(best.get('Sell_Signals', '')).split(',') if s.strip()]
    return buy, sell


def _format_ts(iso: str | None) -> str:
    if not iso:
        return '—'
    try:
        dt = datetime.fromisoformat(str(iso).replace('Z', '+00:00'))
        return dt.strftime('%Y-%m-%d %H:%M')
    except (TypeError, ValueError):
        return str(iso)[:16]


def _render_history_panel(history: list[dict[str, Any]] | None, ticker: str | None, theme: dict) -> html.Div:
    """Body-only: accordion header supplies the 'Run history' title."""
    rows = history_for_ticker(history, ticker)
    if not rows:
        hint = f"No runs recorded for {ticker} yet." if ticker else "No optimizer runs recorded yet."
        return html.Div(hint, style={
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_tertiary'],
        })

    items = []
    for entry in rows:
        top = entry.get('top') or {}
        items.append(html.Div([
            html.Div([
                html.Span(_format_ts(entry.get('recorded_at')), style={
                    'color': theme['text_secondary'],
                    'fontFamily': 'ui-monospace, monospace',
                }),
                html.Span(
                    f" · {entry.get('total_combos', 0)} combos",
                    style={'color': theme['text_tertiary'], 'marginLeft': '6px'},
                ),
            ]),
            html.Div([
                html.Span(
                    f"RET {float(top.get('Total_Return_%') or 0):+.1f}%",
                    style={'color': theme['accent_green'], 'marginRight': '8px'},
                ),
                html.Span(
                    f"Sharpe {float(top.get('Sharpe_Ratio') or 0):.2f}",
                    style={'color': theme['accent_blue'], 'marginRight': '8px'},
                ),
            ], style={'fontSize': FONT_SIZES['xs'], 'marginTop': '2px'}),
            html.Div(
                f"B: {_trunc(top.get('Buy_Signals'))}  ·  S: {_trunc(top.get('Sell_Signals'))}",
                style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_tertiary'],
                    'marginTop': '2px',
                    'fontFamily': 'ui-monospace, monospace',
                },
            ),
        ], style={
            'padding': '6px 0',
            'borderBottom': f'1px solid {theme["border_primary"]}',
        }))

    return html.Div(items)


def _render_oos_panel(payload: dict[str, Any], theme: dict) -> html.Div:
    agg = payload.get('aggregate') or {}
    windows = payload.get('windows') or []
    robust = bool(agg.get('robust'))
    verdict_color = theme['accent_green'] if robust else theme['accent_orange']

    table_rows = []
    for w in windows:
        train = w.get('train') or {}
        test = w.get('test') or {}
        table_rows.append({
            'Window': int(w.get('index', 0)) + 1,
            'IS Sharpe': f"{float(train.get('sharpe', 0)):.2f}",
            'OOS Sharpe': f"{float(test.get('sharpe', 0)):.2f}",
            'OOS Ret %': f"{float(test.get('total_return', 0)):+.1f}",
        })

    return html.Div([
        html.Div("Out-of-sample walk-forward", style={
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_tertiary'],
            'fontWeight': '600',
            'letterSpacing': '0.5px',
            'marginBottom': '8px',
        }),
        html.Div([
            html.Span(f"IS Sharpe μ {float(agg.get('is_sharpe_mean', 0)):.2f}", style={'marginRight': '12px'}),
            html.Span(f"OOS Sharpe μ {float(agg.get('oos_sharpe_mean', 0)):.2f}", style={'marginRight': '12px'}),
            html.Span(f"Degradation {float(agg.get('degradation', 0)):.2f}", style={'marginRight': '12px'}),
            html.Span(
                f"{'ROBUST' if robust else 'NOT ROBUST'}",
                style={'color': verdict_color, 'fontWeight': '600'},
            ),
        ], style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_primary'], 'marginBottom': '6px'}),
        html.Div(
            agg.get('robust_reason', ''),
            style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '8px'},
        ),
        dash_table.DataTable(
            columns=[{'name': c, 'id': c} for c in ('Window', 'IS Sharpe', 'OOS Sharpe', 'OOS Ret %')],
            data=table_rows,
            style_table={'overflowX': 'auto'},
            style_header={
                'backgroundColor': theme['bg_tertiary'],
                'color': theme['text_secondary'],
                'fontSize': FONT_SIZES['xs'],
                'border': f'1px solid {theme["border_primary"]}',
            },
            style_cell={
                'backgroundColor': theme['bg_primary'],
                'color': theme['text_primary'],
                'fontSize': FONT_SIZES['xs'],
                'border': f'1px solid {theme["border_primary"]}',
                'padding': '4px 8px',
                'fontFamily': 'ui-monospace, monospace',
            },
        ) if table_rows else html.Div(),
    ])


def _render_bayesian_results(data: dict[str, Any] | None, theme: dict) -> html.Div:
    if not data:
        return html.Div()
    best = data.get('best_trial') or {}
    metrics = best.get('metrics') or {}
    params = best.get('params') or {}
    param_lines = [html.Div(f"{k}: {v}", style={'fontSize': FONT_SIZES['xs']}) for k, v in sorted(params.items())]
    return html.Div([
        html.Div("Best trial", style={
            'fontSize': FONT_SIZES['xs'],
            'fontWeight': '600',
            'color': theme['accent_green'],
            'marginBottom': '6px',
        }),
        html.Div([
            html.Span(f"{data.get('metric', '')}={float(best.get('value', 0)):.4f}", style={'marginRight': '10px'}),
            html.Span(f"Sharpe {float(metrics.get('sharpe', 0)):.2f}", style={'marginRight': '10px'}),
            html.Span(f"Sortino {float(metrics.get('sortino', 0)):.2f}", style={'marginRight': '10px'}),
            html.Span(f"Ret {float(metrics.get('total_return', 0)):+.1f}%"),
        ], style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_primary'], 'marginBottom': '6px'}),
        html.Div(param_lines, style={'color': theme['text_secondary']}),
        html.Div(
            f"{int(data.get('trials_completed', 0))} trials · "
            f"{float(data.get('duration_seconds', 0)):.1f}s",
            style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_tertiary'], 'marginTop': '6px'},
        ),
    ])


def _build_bayesian_origin_note(data: dict[str, Any], theme: dict) -> html.Div:
    best = data.get('best_trial') or {}
    metrics = best.get('metrics') or {}
    strategy_name = data.get('strategy_name') or 'bundle'
    metric = data.get('metric') or best.get('metric') or 'sortino'
    value = float(best.get('value', 0))
    sharpe = float(metrics.get('sharpe', 0))
    return html.Div([
        html.Span("Applied from Bayesian sweep ", style={'color': theme['text_secondary']}),
        html.Span(f"({strategy_name})", style={'color': theme['accent_blue'], 'fontWeight': '600'}),
        html.Span(
            f" — best {metric}={value:.4f}, Sharpe {sharpe:.2f}. "
            "Scorecard below uses your current Backtest panel settings.",
            style={'color': theme['text_secondary']},
        ),
    ], style={'fontSize': FONT_SIZES['xs'], 'lineHeight': '1.45'})


def _oos_combo_worker(
    *,
    buy: list[str],
    sell: list[str],
    ticker: str,
    settings: dict[str, Any] | None,
    capital: float,
    bar_interval: str,
) -> None:
    try:
        eval_kwargs = (dashboard_state.optimization_state.get('eval_kwargs') or {})
        combo = ComboSpec(
            buy_signals=tuple(buy),
            sell_signals=tuple(sell),
            ticker=ticker,
            indicator_settings=settings or {},
            backtest_kwargs=eval_kwargs or None,
        )
        options = WalkForwardOptions(
            n_windows=5,
            train_months=12,
            test_months=3,
            initial_capital=capital,
            interval=normalize_interval(bar_interval),
        )
        payload = run_combo_walkforward(combo=combo, options=options)
        with _oos_lock:
            if _oos_job.get('cancelled'):
                _oos_job['error'] = 'Cancelled'
                _oos_job['result'] = None
            else:
                _oos_job['result'] = payload
                _oos_job['error'] = None
    except Exception as exc:
        with _oos_lock:
            _oos_job['error'] = str(exc)
            _oos_job['result'] = None
    finally:
        with _oos_lock:
            _oos_job['running'] = False


def _oos_bundle_worker(
    *,
    strategy_name: str,
    params: dict[str, Any],
    capital: float,
    bar_interval: str,
) -> None:
    try:
        options = WalkForwardOptions(
            n_windows=5,
            train_months=12,
            test_months=3,
            initial_capital=capital,
            interval=normalize_interval(bar_interval),
        )
        payload = run_walkforward(
            strategy_name=strategy_name,
            params=params,
            options=options,
        )
        with _oos_lock:
            if _oos_job.get('cancelled'):
                _oos_job['error'] = 'Cancelled'
                _oos_job['result'] = None
            else:
                _oos_job['result'] = payload
                _oos_job['error'] = None
    except Exception as exc:
        with _oos_lock:
            _oos_job['error'] = str(exc)
            _oos_job['result'] = None
    finally:
        with _oos_lock:
            _oos_job['running'] = False


def _bayesian_worker(
    *,
    strategy_name: str,
    n_trials: int,
    metric: str,
    window_from: str,
    window_to: str,
    held_out_months: int,
    ticker: str,
    interval: str,
) -> None:
    def _progress(done: int, total: int) -> None:
        with _bayesian_lock:
            _bayesian_job['trials_done'] = int(done)

    try:
        result = run_study(
            strategy_name=strategy_name,
            n_trials=n_trials,
            metric=metric,
            window_from=window_from,
            window_to=window_to,
            held_out_months=held_out_months,
            ticker_override=ticker,
            interval=interval,
            cancel_event=_bayesian_cancel,
            progress_callback=_progress,
        )
        contract = result.to_contract()
        contract['strategy_name'] = strategy_name
        contract['metric'] = metric
        with _bayesian_lock:
            if _bayesian_job.get('cancelled'):
                _bayesian_job['error'] = 'Cancelled'
                _bayesian_job['result'] = None
            else:
                _bayesian_job['result'] = contract
                _bayesian_job['error'] = None
    except Exception as exc:
        with _bayesian_lock:
            _bayesian_job['error'] = str(exc)
            _bayesian_job['result'] = None
    finally:
        with _bayesian_lock:
            _bayesian_job['running'] = False


def register_optimizer_phase3_callbacks(app) -> None:
    @app.callback(
        Output('optimizer-landscape-graph', 'figure'),
        Input('optimization-results-store', 'data'),
        prevent_initial_call=False,
    )
    def update_optimizer_landscape(results_data):
        theme = get_theme()
        return build_return_sharpe_figure(results_data, theme)

    @app.callback(
        Output('optimizer-history-panel', 'children'),
        [Input('optimizer-run-history-store', 'data'),
         Input('ticker-dropdown', 'value')],
        prevent_initial_call=False,
    )
    def render_optimizer_history(history, ticker):
        theme = get_theme()
        return _render_history_panel(history, ticker, theme)

    @app.callback(
        [Output('optimizer-oos-interval', 'disabled', allow_duplicate=True),
         Output('validate-oos-btn', 'children', allow_duplicate=True),
         Output('validate-bayesian-oos-btn', 'children', allow_duplicate=True),
         Output('optimizer-oos-panel', 'children', allow_duplicate=True)],
        [Input('validate-oos-btn', 'n_clicks'),
         Input('validate-bayesian-oos-btn', 'n_clicks')],
        [State('optimization-results-store', 'data'),
         State('sort-metric-dropdown', 'value'),
         State('bayesian-results-store', 'data'),
         State('ticker-dropdown', 'value'),
         State('initial-capital', 'value'),
         State('bar-interval', 'value'),
         State('indicator-settings-store', 'data')],
        prevent_initial_call=True,
    )
    def control_oos_validation(
        combo_clicks,
        bundle_clicks,
        results_data,
        sort_by,
        bayesian_data,
        ticker,
        capital,
        bar_interval,
        settings,
    ):
        triggered = callback_context.triggered_id
        if not triggered:
            raise PreventUpdate

        theme = get_theme()

        with _oos_lock:
            if _oos_job['running']:
                _oos_cancel.set()
                _oos_job['cancelled'] = True
                return (
                    no_update,
                    'Stopping…',
                    'Stopping…',
                    build_alert("Stopping walk-forward…", "info", theme=theme),
                )

        _oos_cancel.clear()

        if triggered == 'validate-oos-btn':
            if not combo_clicks or not results_data:
                raise PreventUpdate
            try:
                buy, sell = _winner_signals(results_data, sort_by)
            except Exception as exc:
                return (
                    True,
                    'VALIDATE OOS',
                    no_update,
                    build_alert(f"Could not resolve winner: {exc}", "warning", theme=theme),
                )
            if not buy:
                return (
                    True,
                    'VALIDATE OOS',
                    no_update,
                    build_alert("No buy signals on the current winner.", "warning", theme=theme),
                )
            sym = str(ticker or 'TSLA').upper()
            cap = float(capital or 10_000)
            interval = normalize_interval(bar_interval or '1d')
            with _oos_lock:
                _oos_job.update(
                    running=True,
                    result=None,
                    error=None,
                    cancelled=False,
                    kind='combo',
                )
            thread = threading.Thread(
                target=_oos_combo_worker,
                kwargs={
                    'buy': buy,
                    'sell': sell,
                    'ticker': sym,
                    'settings': settings,
                    'capital': cap,
                    'bar_interval': interval,
                },
                daemon=True,
            )
            thread.start()
            panel = html.Div(
                "Running walk-forward on combo winner…",
                style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary']},
            )
            return False, 'STOP OOS', no_update, panel

        if triggered == 'validate-bayesian-oos-btn':
            if not bundle_clicks or not bayesian_data:
                raise PreventUpdate
            strategy_name = bayesian_data.get('strategy_name')
            best = bayesian_data.get('best_trial') or {}
            params = best.get('params') or {}
            if not strategy_name or not params:
                return (
                    True,
                    no_update,
                    'VALIDATE OOS (BUNDLE)',
                    build_alert("Run a Bayesian sweep first.", "warning", theme=theme),
                )
            cap = float(capital or 10_000)
            interval = normalize_interval(bar_interval or '1d')
            with _oos_lock:
                _oos_job.update(
                    running=True,
                    result=None,
                    error=None,
                    cancelled=False,
                    kind='bundle',
                )
            thread = threading.Thread(
                target=_oos_bundle_worker,
                kwargs={
                    'strategy_name': strategy_name,
                    'params': params,
                    'capital': cap,
                    'bar_interval': interval,
                },
                daemon=True,
            )
            thread.start()
            panel = html.Div(
                f"Running walk-forward on {strategy_name}…",
                style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary']},
            )
            return False, no_update, 'STOP OOS', panel

        raise PreventUpdate

    @app.callback(
        [Output('optimizer-oos-panel', 'children'),
         Output('optimizer-oos-store', 'data'),
         Output('optimizer-oos-interval', 'disabled'),
         Output('validate-oos-btn', 'children'),
         Output('validate-bayesian-oos-btn', 'children')],
        Input('optimizer-oos-interval', 'n_intervals'),
        prevent_initial_call=True,
    )
    def poll_oos_job(_n_intervals):
        theme = get_theme()
        with _oos_lock:
            running = _oos_job['running']
            result = _oos_job['result']
            error = _oos_job['error']

        if running:
            raise PreventUpdate

        if result is None and error is None:
            raise PreventUpdate

        with _oos_lock:
            _oos_job.update(
                running=False,
                result=None,
                error=None,
                cancelled=False,
                kind=None,
            )
            _oos_cancel.clear()

        if error:
            level = 'warning' if error == 'Cancelled' else 'danger'
            msg = (
                "Walk-forward cancelled."
                if error == 'Cancelled'
                else f"Walk-forward failed: {error}"
            )
            return (
                build_alert(msg, level, theme=theme),
                None,
                True,
                'VALIDATE OOS',
                'VALIDATE OOS (BUNDLE)',
            )

        return (
            _render_oos_panel(result, theme),
            result,
            True,
            'VALIDATE OOS',
            'VALIDATE OOS (BUNDLE)',
        )

    @app.callback(
        Output('bayesian-strategy-dropdown', 'options'),
        Input('app-url', 'pathname'),
        prevent_initial_call=False,
    )
    def populate_bayesian_strategies(pathname):
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
        [Output('bayesian-interval', 'disabled', allow_duplicate=True),
         Output('run-bayesian-btn', 'children', allow_duplicate=True),
         Output('run-bayesian-btn', 'disabled', allow_duplicate=True),
         Output('bayesian-progress', 'children', allow_duplicate=True),
         Output('bayesian-actions', 'style', allow_duplicate=True)],
        Input('run-bayesian-btn', 'n_clicks'),
        [State('bayesian-strategy-dropdown', 'value'),
         State('bayesian-trials-input', 'value'),
         State('bayesian-metric-dropdown', 'value'),
         State('bayesian-held-out-input', 'value'),
         State('test-window-start', 'date'),
         State('test-window-end', 'date'),
         State('ticker-dropdown', 'value'),
         State('bar-interval', 'value')],
        prevent_initial_call=True,
    )
    def start_bayesian_study(
        n_clicks,
        strategy_name,
        n_trials,
        metric,
        held_out_months,
        window_from,
        window_to,
        ticker,
        bar_interval,
    ):
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()
        hidden_actions = {'display': 'none', 'marginTop': '10px'}

        with _bayesian_lock:
            if _bayesian_job['running']:
                _bayesian_cancel.set()
                _bayesian_job['cancelled'] = True
                progress = html.Div(
                    "Stopping Bayesian sweep…",
                    style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary']},
                )
                return no_update, 'STOP BAYESIAN', False, progress, hidden_actions

        if not strategy_name:
            return (
                True,
                'RUN BAYESIAN',
                False,
                build_alert("Select a strategy bundle first.", "warning", theme=theme),
                hidden_actions,
            )
        if not window_from or not window_to:
            return (
                True,
                'RUN BAYESIAN',
                False,
                build_alert("Set a test window before running Bayesian sweep.", "warning", theme=theme),
                hidden_actions,
            )

        try:
            trials = max(5, min(200, int(n_trials or 30)))
        except (TypeError, ValueError):
            trials = 30
        try:
            held_out = max(1, min(24, int(held_out_months or 6)))
        except (TypeError, ValueError):
            held_out = 6

        _bayesian_cancel.clear()
        with _bayesian_lock:
            _bayesian_job.update(
                running=True,
                result=None,
                error=None,
                trials_done=0,
                n_trials=trials,
                strategy_name=strategy_name,
                cancelled=False,
            )

        thread = threading.Thread(
            target=_bayesian_worker,
            kwargs={
                'strategy_name': strategy_name,
                'n_trials': trials,
                'metric': metric or 'sortino',
                'window_from': window_from,
                'window_to': window_to,
                'held_out_months': held_out,
                'ticker': str(ticker or 'TSLA').upper(),
                'interval': normalize_interval(bar_interval or '1d'),
            },
            daemon=True,
        )
        thread.start()

        progress = html.Div(
            f"Running {trials} Optuna trials on {strategy_name}…",
            style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary']},
        )
        return False, 'STOP BAYESIAN', False, progress, hidden_actions

    @app.callback(
        [Output('bayesian-results-store', 'data'),
         Output('bayesian-results', 'children'),
         Output('bayesian-progress', 'children', allow_duplicate=True),
         Output('bayesian-interval', 'disabled'),
         Output('run-bayesian-btn', 'children', allow_duplicate=True),
         Output('run-bayesian-btn', 'disabled', allow_duplicate=True),
         Output('bayesian-actions', 'style')],
        Input('bayesian-interval', 'n_intervals'),
        prevent_initial_call=True,
    )
    def poll_bayesian_study(_n_intervals):
        theme = get_theme()
        hidden_actions = {'display': 'none', 'marginTop': '10px'}
        visible_actions = {'display': 'block', 'marginTop': '10px'}

        with _bayesian_lock:
            running = _bayesian_job['running']
            result = _bayesian_job['result']
            error = _bayesian_job['error']
            trials_done = _bayesian_job.get('trials_done', 0)
            n_trials = _bayesian_job.get('n_trials', 0)

        if running:
            progress = html.Div(
                f"Trial {trials_done}/{n_trials}",
                style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary']},
            )
            return (
                no_update,
                no_update,
                progress,
                no_update,
                'STOP BAYESIAN',
                False,
                hidden_actions,
            )

        if result is None and error is None:
            raise PreventUpdate

        if error:
            level = 'warning' if error == 'Cancelled' else 'danger'
            msg = (
                "Bayesian sweep cancelled."
                if error == 'Cancelled'
                else f"Bayesian sweep failed: {error}"
            )
            with _bayesian_lock:
                _bayesian_job['result'] = None
                _bayesian_job['error'] = None
            return (
                None,
                build_alert(msg, level, theme=theme),
                html.Div(),
                True,
                'RUN BAYESIAN',
                False,
                hidden_actions,
            )

        with _bayesian_lock:
            _bayesian_job['result'] = None
            _bayesian_job['error'] = None

        return (
            result,
            _render_bayesian_results(result, theme),
            html.Div("Completed.", style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['accent_green'],
            }),
            True,
            'RUN BAYESIAN',
            False,
            visible_actions,
        )

    @app.callback(
        [Output('indicator-settings-store', 'data', allow_duplicate=True),
         Output('optimizer-apply-store', 'data', allow_duplicate=True),
         Output('tab-backtest', 'n_clicks', allow_duplicate=True),
         Output('backtest-origin-note', 'children'),
         Output('app-url', 'pathname', allow_duplicate=True),
         Output('bayesian-progress', 'children', allow_duplicate=True)],
        Input('apply-bayesian-btn', 'n_clicks'),
        [State('bayesian-results-store', 'data'),
         State('indicator-settings-store', 'data'),
         State('ticker-dropdown', 'value'),
         State('tab-backtest', 'n_clicks')],
        prevent_initial_call=True,
    )
    def apply_bayesian_params(
        n_clicks,
        bayesian_data,
        current_settings,
        ticker,
        current_backtest_clicks,
    ):
        if not n_clicks or not bayesian_data:
            raise PreventUpdate

        theme = get_theme()
        strategy_name = bayesian_data.get('strategy_name')
        best = bayesian_data.get('best_trial') or {}
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
        note = _build_bayesian_origin_note(bayesian_data, theme)
        bayesian_note = html.Div(
            "Applied to Backtest tab.",
            style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_green']},
        )

        return (
            merged_settings,
            apply_payload,
            (current_backtest_clicks or 0) + 1,
            note,
            build_ticker_terminal_path(ticker),
            bayesian_note,
        )
