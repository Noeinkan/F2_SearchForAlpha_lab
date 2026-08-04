"""
Optimizer workspace Phase 3 — landscape, run history, OOS validation, Bayesian sweep.
"""

from __future__ import annotations

import threading
from datetime import datetime
from typing import Any

import pandas as pd
from dash import dash_table, html, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.bayesian_optimization import run_study
from lib.config_loader import get_agent_strategies
from lib.dash.combo_walkforward import ComboSpec, run_combo_walkforward
from lib.dash.components import build_alert
from lib.dash.dash_config import FONT_SIZES, get_theme
from lib.dash.optimizer_history import history_for_ticker
from lib.dash.optimizer_landscape import build_return_sharpe_figure
from lib.dash.routes import is_optimize_route
from lib.dash.state import dashboard_state
from lib.timeframes import normalize_interval
from lib.walkforward.runner import WalkForwardOptions

_bayesian_lock = threading.Lock()
_bayesian_job: dict[str, Any] = {
    'running': False,
    'result': None,
    'error': None,
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
    rows = history_for_ticker(history, ticker)
    if not rows:
        hint = f"No runs recorded for {ticker} yet." if ticker else "No optimizer runs recorded yet."
        return html.Div([
            html.Div("Run history", style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_tertiary'],
                'fontWeight': '600',
                'letterSpacing': '0.5px',
                'marginBottom': '6px',
            }),
            html.Div(hint, style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_tertiary'],
            }),
        ])

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

    return html.Div([
        html.Div("Run history", style={
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_tertiary'],
            'fontWeight': '600',
            'letterSpacing': '0.5px',
            'marginBottom': '6px',
        }),
        html.Div(items),
    ])


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
        )
        with _bayesian_lock:
            _bayesian_job['result'] = result.to_contract()
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
        [Output('optimizer-oos-panel', 'children'),
         Output('optimizer-oos-store', 'data')],
        Input('validate-oos-btn', 'n_clicks'),
        [State('optimization-results-store', 'data'),
         State('sort-metric-dropdown', 'value'),
         State('ticker-dropdown', 'value'),
         State('initial-capital', 'value'),
         State('bar-interval', 'value'),
         State('indicator-settings-store', 'data'),
         State('optimization-state', 'data')],
        prevent_initial_call=True,
    )
    def validate_oos(n_clicks, results_data, sort_by, ticker, capital, bar_interval, settings, opt_state):
        if not n_clicks or not results_data:
            raise PreventUpdate

        theme = get_theme()
        try:
            buy, sell = _winner_signals(results_data, sort_by)
            if not buy:
                return (
                    build_alert("No buy signals on the current winner.", "warning", theme=theme),
                    None,
                )

            eval_kwargs = (dashboard_state.optimization_state.get('eval_kwargs') or {})
            combo = ComboSpec(
                buy_signals=tuple(buy),
                sell_signals=tuple(sell),
                ticker=str(ticker or 'TSLA').upper(),
                indicator_settings=settings or {},
                backtest_kwargs=eval_kwargs or None,
            )
            options = WalkForwardOptions(
                n_windows=5,
                train_months=12,
                test_months=3,
                initial_capital=float(capital or 10_000),
                interval=normalize_interval(bar_interval or '1d'),
            )
            payload = run_combo_walkforward(combo=combo, options=options)
            return _render_oos_panel(payload, theme), payload
        except Exception as exc:
            return (
                build_alert(f"Walk-forward failed: {exc}", "danger", theme=theme),
                None,
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
         Output('bayesian-progress', 'children', allow_duplicate=True)],
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
        with _bayesian_lock:
            if _bayesian_job['running']:
                raise PreventUpdate

        if not strategy_name:
            return (
                True,
                'RUN BAYESIAN',
                False,
                build_alert("Select a strategy bundle first.", "warning", theme=theme),
            )
        if not window_from or not window_to:
            return (
                True,
                'RUN BAYESIAN',
                False,
                build_alert("Set a test window before running Bayesian sweep.", "warning", theme=theme),
            )

        try:
            trials = max(5, min(200, int(n_trials or 30)))
        except (TypeError, ValueError):
            trials = 30
        try:
            held_out = max(1, min(24, int(held_out_months or 6)))
        except (TypeError, ValueError):
            held_out = 6

        with _bayesian_lock:
            _bayesian_job.update(running=True, result=None, error=None)

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
        return False, 'Running…', True, progress

    @app.callback(
        [Output('bayesian-results-store', 'data'),
         Output('bayesian-results', 'children'),
         Output('bayesian-progress', 'children', allow_duplicate=True),
         Output('bayesian-interval', 'disabled'),
         Output('run-bayesian-btn', 'children', allow_duplicate=True),
         Output('run-bayesian-btn', 'disabled', allow_duplicate=True)],
        Input('bayesian-interval', 'n_intervals'),
        prevent_initial_call=True,
    )
    def poll_bayesian_study(_n_intervals):
        theme = get_theme()
        with _bayesian_lock:
            running = _bayesian_job['running']
            result = _bayesian_job['result']
            error = _bayesian_job['error']

        if running:
            raise PreventUpdate

        if result is None and error is None:
            raise PreventUpdate

        if error:
            return (
                None,
                build_alert(f"Bayesian sweep failed: {error}", "danger", theme=theme),
                html.Div(),
                True,
                'RUN BAYESIAN',
                False,
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
        )
