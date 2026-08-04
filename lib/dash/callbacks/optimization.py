"""
Optimization callbacks.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import pandas as pd
from dash import html
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.components import build_alert, build_progress_bar
from lib.dash.dash_config import (
    FONT_SIZES,
    OPTIMIZER_COST_FALLBACK_SEC_PER_COMBO,
    OPTIMIZER_WORKERS,
    get_theme,
)
from lib.dash.helpers import (
    extract_signals,
    generate_signal_combinations,
    evaluate_signal_combination,
    compute_robustness_scores,
)
from lib.dash.state import dashboard_state
from lib.dash.styles import get_styles
from lib.dash.callbacks.shared import (
    OPTIMIZATION_BATCH_SIZE,
    _create_best_strategy_highlight,
    _create_optimization_table,
    _create_optimization_table_mini,
    slice_df_to_window,
)

logger = logging.getLogger(__name__)

_RUN_LABEL = "RUN OPTIMIZER"
_STOP_LABEL = "STOP OPTIMIZER"

# Sentinel returned by a worker whose run was cancelled mid-flight (user
# clicked STOP, which calls ``reset_optimization()``). Treated specially by
# ``process_optimization_batch``.
_CANCELLED = object()


def _eval_with_cancel_guard(
    run_token: int,
    df: pd.DataFrame,
    initial_capital: float,
    buy_combo,
    sell_combo,
):
    """Evaluate a single combination, returning ``_CANCELLED`` if the run was
    stopped (``reset_optimization`` swapped the state dict) while we were
    waiting in the thread pool queue.

    Cheap check: ``id(dashboard_state.optimization_state)`` will differ from
    ``run_token`` if ``reset_optimization()`` swapped in a fresh dict.
    """
    if id(dashboard_state.optimization_state) != run_token:
        return _CANCELLED
    return evaluate_signal_combination(
        df,
        initial_capital,
        tuple(buy_combo),
        tuple(sell_combo),
    )


# -----------------------------------------------------------------------------
# Thread-pool executor — shared across interval ticks so we don't pay the pool
# spin-up cost on every batch. NumPy/pandas release the GIL during numeric
# work, so multiple workers give real speedup on multi-core boxes.
# Lazy-initialised on first use so importing this module is side-effect free.
# -----------------------------------------------------------------------------
_EXECUTOR: ThreadPoolExecutor | None = None
_EXECUTOR_LOCK = threading.Lock()
# Latest measured seconds-per-combo, calibrated on the first batch of the
# current run. Used to populate the cost-estimate pill before the user clicks
# RUN, and as the speedometer shown next to the progress bar mid-run.
_LAST_SEC_PER_COMBO: float | None = None


def _get_executor() -> ThreadPoolExecutor:
    global _EXECUTOR
    if _EXECUTOR is not None:
        return _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is None:
            _EXECUTOR = ThreadPoolExecutor(
                max_workers=OPTIMIZER_WORKERS,
                thread_name_prefix="opt-batch",
            )
            logger.info(
                "Optimizer thread-pool initialised with %d workers (cpu_count=%d)",
                OPTIMIZER_WORKERS,
                __import__("os").cpu_count(),
            )
    return _EXECUTOR


def _shutdown_executor() -> None:
    """Tear down the shared pool. Hooked into DashboardState.reset for clean
    shutdown and into cancel / re-start so queued futures are abandoned."""
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is not None:
            _EXECUTOR.shutdown(wait=False, cancel_futures=True)
            _EXECUTOR = None
            logger.info("Optimizer thread-pool shut down")


def _format_duration(seconds: float) -> str:
    """Render a duration in the form ``~3.2 s`` / ``~1 m 12 s`` / ``~2 m``."""
    if seconds is None or seconds <= 0:
        return "—"
    if seconds < 1:
        return f"~{seconds * 1000:.0f} ms"
    if seconds < 60:
        return f"~{seconds:.1f} s"
    minutes = int(seconds // 60)
    secs = int(seconds % 60)
    if minutes < 10:
        return f"~{minutes} m {secs:02d} s"
    return f"~{minutes} m"


def _estimate_runtime_seconds(combinations: int) -> float | None:
    """Estimate how long the optimizer will take to chew through ``combinations``.

    Uses the last calibrated seconds-per-combo (set after the first batch of a
    real run) and divides by the worker count so the estimate reflects the
    parallel speedup. Falls back to ``OPTIMIZER_COST_FALLBACK_SEC_PER_COMBO``
    on first use.
    """
    if combinations <= 0:
        return None
    sec_per_combo = _LAST_SEC_PER_COMBO or OPTIMIZER_COST_FALLBACK_SEC_PER_COMBO
    workers = max(1, OPTIMIZER_WORKERS)
    return (combinations * sec_per_combo) / workers


def _calibrate_sec_per_combo(elapsed: float, n_combos: int) -> None:
    """Update the rolling seconds-per-combo estimate after a batch finishes."""
    global _LAST_SEC_PER_COMBO
    if elapsed <= 0 or n_combos <= 0:
        return
    measured = elapsed / n_combos
    # Exponential moving average so a slow first batch doesn't pin the estimate.
    alpha = 0.4
    if _LAST_SEC_PER_COMBO is None:
        _LAST_SEC_PER_COMBO = measured
    else:
        _LAST_SEC_PER_COMBO = (1 - alpha) * _LAST_SEC_PER_COMBO + alpha * measured
    logger.debug(
        "Optimizer calibration: %.4fs/combo (batch avg=%.4fs over %d combos, workers=%d)",
        _LAST_SEC_PER_COMBO, measured, n_combos, OPTIMIZER_WORKERS,
    )


def _optimizer_btn_style(theme: dict, *, stop: bool = False) -> dict:
    """Primary RUN style, or danger STOP style."""
    base = {**get_styles(theme)['button_primary'], 'width': '100%'}
    if stop:
        base['backgroundColor'] = theme['accent_red']
        base['color'] = '#fff'
    return base


def _interval_display_label(bar_interval: str | None) -> str:
    """Map RadioItems values (``1d``/``1h``/``4h``) to short toolbar labels."""
    if not bar_interval:
        return dashboard_state.interval.upper() if dashboard_state.interval else "—"
    key = str(bar_interval).strip().lower()
    return {
        '1d': '1D',
        '1h': '1H',
        '4h': '4H',
        '1w': '1W',
    }.get(key, str(bar_interval).upper())


def format_capital_label(capital: Any) -> str:
    """Format initial capital for the conditions strip (pure; unit-tested)."""
    try:
        value = float(capital)
    except (TypeError, ValueError):
        return "—"
    if value >= 1000 and value == int(value):
        return f"${int(value):,}"
    return f"${value:,.2f}"


def truncate_signal_names(names: list[str], limit: int = 6) -> str:
    """Join signal names, truncating with ``+N more`` when over ``limit``."""
    if not names:
        return "—"
    if len(names) <= limit:
        return ", ".join(names)
    shown = ", ".join(names[:limit])
    return f"{shown} +{len(names) - limit} more"


def format_optimizer_conditions(
    *,
    interval_label: str,
    capital_label: str,
    window_label: str,
    buy_signals: list[str],
    sell_signals: list[str],
    max_names: int = 6,
) -> str:
    """Plain-text run conditions for the Optimizer strip (pure; unit-tested)."""
    line1 = f"{interval_label} · {capital_label} · {window_label}"
    buy = truncate_signal_names(buy_signals, max_names)
    sell = truncate_signal_names(sell_signals, max_names)
    return f"{line1}\nBuy: {buy}\nSell: {sell}"


def _rank_results_df(
    results: list[dict],
    min_trades: int,
    sort_by: str | None,
) -> pd.DataFrame:
    """Score and sort optimization result rows; empty if none are usable."""
    results_df = pd.DataFrame(results)
    if results_df.empty:
        return results_df
    if 'Total_Return_%' in results_df.columns:
        results_df = results_df[results_df['Total_Return_%'].notna()]
    else:
        return results_df.iloc[0:0]

    if results_df.empty:
        return results_df

    results_df = compute_robustness_scores(results_df, min_trades)
    metric = sort_by or 'Robustness_Score'
    if metric not in results_df.columns:
        metric = 'Robustness_Score'
    return results_df.sort_values(
        ['Low_Sample', metric],
        ascending=[True, metric == 'Max_Drawdown_%'],
    )


def _results_ui_from_df(results_df: pd.DataFrame, theme: dict) -> html.Div:
    return html.Div([
        _create_best_strategy_highlight(results_df.iloc[0], theme),
        _create_optimization_table(results_df.head(10), theme),
    ], className='fade-in')


def _build_origin_note(best: pd.Series, theme: dict) -> html.Div:
    """Reconciliation banner shown above the auto-run scorecard.

    Explains that the Optimizer leaderboard number is idealized (no costs, no
    Trade Setup) while the scorecard below reflects the user's real settings, so
    the two figures are expected to differ.
    """
    total_return = best.get('Total_Return_%', None)
    alpha = best.get('Alpha_%', None)
    low_sample = bool(best.get('Low_Sample', False))

    headline = (
        f"{float(total_return):+.1f}%" if total_return is not None else "—"
    )
    alpha_txt = (
        f" ({float(alpha):+.1f}% vs buy & hold)" if alpha is not None else ""
    )

    children = [
        html.Span("Applied from Optimizer ", style={'fontWeight': '600'}),
        html.Span(
            f"— leaderboard showed {headline}{alpha_txt} with no costs or stops. ",
        ),
        html.Span(
            "The scorecard below uses your current Transaction Costs & Trade Setup, "
            "so the number will differ — that's the honest, tradeable figure.",
            style={'color': theme['text_secondary']},
        ),
    ]
    if low_sample:
        children.append(
            html.Div(
                "⚠ This winner is low-sample (few trades) — treat it with extra caution.",
                style={'color': theme['accent_orange'], 'marginTop': '4px', 'fontSize': FONT_SIZES['xs']},
            )
        )

    return html.Div(
        children,
        style={
            'padding': '8px 10px',
            'borderRadius': '6px',
            'border': f'1px solid {theme["accent_blue"]}40',
            'backgroundColor': f'{theme["accent_blue"]}12',
            'color': theme['text_primary'],
            'fontSize': FONT_SIZES['xs'],
            'lineHeight': '1.5',
        },
    )


def _cancel_optimization(theme: dict, client_state: dict | None):
    """Stop an in-flight run: abandon workers, keep partial ranked results."""
    opt_state = dashboard_state.optimization_state
    results = list(opt_state.get('results') or [])
    current_idx = int(opt_state.get('current_index') or 0)
    total = int(opt_state.get('total_combinations') or 0)
    min_trades = int(
        opt_state.get('min_trades')
        or (client_state or {}).get('min_trades')
        or 10
    )
    sort_by = (client_state or {}).get('sort_by', 'Robustness_Score')

    dashboard_state.reset_optimization()
    _shutdown_executor()

    idle_state = {
        'running': False,
        'current_index': current_idx,
        'total_combinations': total,
        'completed': False,
        'cancelled': True,
        'sort_by': sort_by,
        'sort_ascending': False,
        'min_trades': min_trades,
    }

    progress = html.Div([
        html.Div([
            html.Span("■ ", style={'color': theme['accent_orange']}),
            html.Span(
                f"Stopped at {current_idx}/{total} combinations",
                style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_orange']},
            ),
        ]),
        html.Div(
            "Partial results kept below when available. Click RUN to start a new search.",
            style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_secondary'],
                'marginTop': '4px',
            },
        ),
    ])

    ranked = _rank_results_df(results, min_trades, sort_by)
    run_style = _optimizer_btn_style(theme, stop=False)
    if ranked.empty:
        return (
            idle_state,
            True,  # disable interval
            progress,
            False,  # button enabled
            _RUN_LABEL,
            run_style,
            html.Div(),
            {'display': 'none'},
            [],
        )

    records = ranked.to_dict('records')
    dashboard_state.update_optimization_state(
        results=records,
        completed=True,
        running=False,
        current_index=current_idx,
        total_combinations=total,
        min_trades=min_trades,
    )
    idle_state['completed'] = True
    return (
        idle_state,
        True,
        progress,
        False,
        _RUN_LABEL,
        run_style,
        _results_ui_from_df(ranked, theme),
        {'display': 'block'},
        records,
    )


def register_optimization_callbacks(app) -> None:
    @app.callback(
        [Output('preview-buy-count', 'children'),
         Output('preview-sell-count', 'children'),
         Output('preview-combo-count', 'children'),
         Output('optimization-cost', 'children'),
         Output('optimizer-run-conditions', 'children')],
        [Input('data-loaded-store', 'data'),
         Input('max-signals-slider', 'value'),
         Input('max-combos-input', 'value'),
         Input('initial-capital', 'value'),
         Input('test-window-start', 'date'),
         Input('test-window-end', 'date'),
         Input('bar-interval', 'value')]
    )
    def update_signal_preview(
        data_loaded,
        max_signals,
        max_combos,
        initial_capital,
        start_date,
        end_date,
        bar_interval,
    ):
        """Show preview counts, EST runtime, and the run-conditions strip."""
        empty_conditions = "Load data to see interval, capital, window and signals."
        if not data_loaded or dashboard_state.df is None:
            return "0", "0", "0", "—", empty_conditions

        full_df = dashboard_state.df
        df, window_label = slice_df_to_window(full_df, start_date, end_date)
        buy_signals, sell_signals = extract_signals(df)

        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        actual_combos = min(len(combinations), max_combos or 100)

        est_seconds = _estimate_runtime_seconds(actual_combos)
        cost_label = _format_duration(est_seconds) if est_seconds is not None else "—"

        theme = get_theme()
        conditions_text = format_optimizer_conditions(
            interval_label=_interval_display_label(bar_interval),
            capital_label=format_capital_label(initial_capital),
            window_label=window_label,
            buy_signals=buy_signals,
            sell_signals=sell_signals,
        )
        conditions_ui = html.Div(
            conditions_text,
            style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_secondary'],
                'lineHeight': '1.45',
                'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                'whiteSpace': 'pre-wrap',
            },
        )

        return (
            str(len(buy_signals)),
            str(len(sell_signals)),
            str(actual_combos),
            cost_label,
            conditions_ui,
        )

    @app.callback(
        [Output('optimization-state', 'data'),
         Output('optimization-interval', 'disabled'),
         Output('optimization-progress', 'children'),
         Output('run-optimization-btn', 'disabled'),
         Output('run-optimization-btn', 'children'),
         Output('run-optimization-btn', 'style'),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True),
         Output('optimization-results-store', 'data', allow_duplicate=True)],
        [Input('run-optimization-btn', 'n_clicks')],
        [State('initial-capital', 'value'),
         State('max-signals-slider', 'value'),
         State('max-combos-input', 'value'),
         State('min-trades-input', 'value'),
         State('test-window-start', 'date'),
         State('test-window-end', 'date'),
         State('optimization-state', 'data'),
         State('run-optimization-btn', 'children'),
         State('sort-metric-dropdown', 'value')],
        prevent_initial_call=True
    )
    def start_optimization(
        n_clicks,
        initial_capital,
        max_signals,
        max_combos,
        min_trades,
        start_date,
        end_date,
        current_state,
        button_label,
        sort_by,
    ):
        """Start a run, or cancel when the button currently reads STOP."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()
        label = (button_label or "").strip().upper()
        server_running = bool(dashboard_state.optimization_state.get('running'))

        # Explicit Stop when the button already shows STOP.
        if "STOP" in label:
            return _cancel_optimization(theme, {
                **(current_state or {}),
                'sort_by': sort_by or (current_state or {}).get('sort_by'),
            })

        # Double-start before the label flips to STOP — ignore.
        if server_running:
            raise PreventUpdate

        full_df = dashboard_state.df
        run_style = _optimizer_btn_style(theme, stop=False)

        if full_df is None:
            return (
                current_state,
                True,
                build_alert("Please load market data first", "warning", theme=theme),
                False,
                _RUN_LABEL,
                run_style,
                html.Div(),
                {'display': 'none'},
                [],
            )

        df, window_label = slice_df_to_window(full_df, start_date, end_date)

        buy_signals, sell_signals = extract_signals(df)
        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        combinations = combinations[:max_combos]

        if not combinations:
            return (
                current_state,
                True,
                build_alert("No valid signal combinations found", "warning", theme=theme),
                False,
                _RUN_LABEL,
                run_style,
                html.Div(),
                {'display': 'none'},
                [],
            )

        combinations_serializable = [[list(buy), list(sell)] for buy, sell in combinations]

        # Reset state — replaces the dict so any leftover workers from a prior
        # run see id(state) change and drop pending writes.
        _shutdown_executor()
        dashboard_state.reset_optimization()
        dashboard_state.update_optimization_state(
            running=True,
            total_combinations=len(combinations),
            combinations=combinations_serializable,
            initial_capital=initial_capital,
            min_trades=min_trades or 10,
        )

        new_state = {
            'running': True,
            'current_index': 0,
            'total_combinations': len(combinations),
            'completed': False,
            'sort_by': sort_by or 'Robustness_Score',
            'sort_ascending': False,
            'min_trades': min_trades or 10,
        }

        est_seconds = _estimate_runtime_seconds(len(combinations))
        est_label = _format_duration(est_seconds) if est_seconds is not None else "…"
        progress_ui = html.Div([
            build_progress_bar(0, f"Testing 0/{len(combinations)} combinations...", theme=theme),
            html.Div(
                f"Window: {window_label}  ·  Est. runtime: {est_label} "
                f"({OPTIMIZER_WORKERS} worker{'s' if OPTIMIZER_WORKERS != 1 else ''})",
                style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginTop': '4px'},
            ),
        ])

        return (
            new_state,
            False,  # Enable interval
            progress_ui,
            False,  # Keep button enabled so STOP works
            _STOP_LABEL,
            _optimizer_btn_style(theme, stop=True),
            html.Div(),
            {'display': 'none'},
            [],
        )

    @app.callback(
        [Output('optimization-state', 'data', allow_duplicate=True),
         Output('optimization-progress', 'children', allow_duplicate=True),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('optimization-interval', 'disabled', allow_duplicate=True),
         Output('run-optimization-btn', 'disabled', allow_duplicate=True),
         Output('run-optimization-btn', 'children', allow_duplicate=True),
         Output('run-optimization-btn', 'style', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True),
         Output('optimization-results-store', 'data')],
        [Input('optimization-interval', 'n_intervals')],
        [State('optimization-state', 'data'),
         State('test-window-start', 'date'),
         State('test-window-end', 'date')],
        prevent_initial_call=True
    )
    def process_optimization_batch(n_intervals, state, start_date, end_date):
        """Process a batch of combinations on each interval tick.

        Uses a thread pool so multiple backtests run in parallel. Each worker
        re-checks ``id(dashboard_state.optimization_state)`` against the token
        captured at dispatch time — if the user clicked STOP mid-flight
        (which replaces the state dict), stale results are discarded.
        """
        theme = get_theme()

        if not state or not state.get('running'):
            raise PreventUpdate

        # Bail if Stop already reset server state (interval tick still queued).
        if not dashboard_state.optimization_state.get('running'):
            raise PreventUpdate

        full_df = dashboard_state.df
        if full_df is None:
            raise PreventUpdate

        df, _window_label = slice_df_to_window(full_df, start_date, end_date)

        opt_state = dashboard_state.optimization_state
        current_idx = opt_state.get('current_index', 0)
        total = opt_state.get('total_combinations', 0)
        combinations = opt_state.get('combinations', [])
        results = opt_state.get('results', [])
        initial_capital = opt_state.get('initial_capital', 10000)

        if not combinations or current_idx >= total:
            raise PreventUpdate

        run_token = id(opt_state)

        end_idx = min(current_idx + OPTIMIZATION_BATCH_SIZE, total)
        batch = combinations[current_idx:end_idx]
        batch_size = len(batch)

        t0 = time.perf_counter()
        executor = _get_executor()
        futures = [
            executor.submit(
                _eval_with_cancel_guard,
                run_token,
                df,
                initial_capital,
                buy_combo,
                sell_combo,
            )
            for buy_combo, sell_combo in batch
        ]
        for fut in futures:
            result = fut.result()
            if result is _CANCELLED:
                # Stop cancelled mid-batch; cancel callback owns the UI update.
                raise PreventUpdate
            results.append(result)

        _calibrate_sec_per_combo(time.perf_counter() - t0, batch_size)

        dashboard_state.update_optimization_state(
            current_index=end_idx,
            results=results
        )

        progress_pct = int((end_idx / total) * 100)
        run_style = _optimizer_btn_style(theme, stop=True)
        idle_style = _optimizer_btn_style(theme, stop=False)

        if end_idx >= total:
            dashboard_state.update_optimization_state(running=False, completed=True)
            min_trades = opt_state.get('min_trades', 10)
            results_df = _rank_results_df(results, min_trades, state.get('sort_by'))

            if results_df.empty:
                state['running'] = False
                state['completed'] = True
                first_error = next((r.get('Error') for r in results if r.get('Error')), None)
                msg = "All combinations failed"
                if first_error:
                    msg += f": {first_error}"
                return (
                    state,
                    build_alert(msg, "warning", theme=theme),
                    html.Div(),
                    True,
                    False,
                    _RUN_LABEL,
                    idle_style,
                    {'display': 'none'},
                    [],
                )

            state['running'] = False
            state['completed'] = True

            final_progress = html.Div([
                html.Div([
                    html.Span("\u2713 ", style={'color': theme['accent_green']}),
                    html.Span(f"Completed! Tested {total} combinations",
                             style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_green']})
                ]),
                html.Div(
                    f"Ranked from {total} combos \u2014 the more you test, the more likely the top "
                    "result is luck. Re-run the winner on the Backtest tab with real costs, and "
                    "ideally on a different date range.",
                    style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'],
                           'marginTop': '4px', 'fontStyle': 'italic'}
                ),
            ])

            return (
                state,
                final_progress,
                _results_ui_from_df(results_df, theme),
                True,
                False,
                _RUN_LABEL,
                idle_style,
                {'display': 'block'},
                results_df.to_dict('records'),
            )

        state['current_index'] = end_idx

        remaining = max(0, total - end_idx)
        if _LAST_SEC_PER_COMBO is not None and remaining > 0:
            eta_seconds = (remaining * _LAST_SEC_PER_COMBO) / max(1, OPTIMIZER_WORKERS)
            eta_label = f"~{_format_duration(eta_seconds)} remaining"
        else:
            eta_label = (
                f"{OPTIMIZER_WORKERS} worker"
                f"{'s' if OPTIMIZER_WORKERS != 1 else ''} running"
            )

        progress_ui = html.Div([
            build_progress_bar(progress_pct, f"Testing {end_idx}/{total} combinations...", theme=theme),
            html.Div(
                f"{eta_label}  ·  Found {len([r for r in results if 'Total_Return_%' in r])} valid strategies so far…",
                style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginTop': '4px'},
            ),
        ])

        valid_results = [r for r in results if 'Total_Return_%' in r]
        partial_results = html.Div()
        if len(valid_results) >= 5:
            partial_df = pd.DataFrame(valid_results).sort_values('Total_Return_%', ascending=False).head(5)
            partial_results = html.Div([
                html.Div("Top strategies so far:",
                        style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '8px'}),
                _create_optimization_table_mini(partial_df, theme)
            ], style={'marginTop': '12px'})

        return (
            state,
            progress_ui,
            partial_results,
            False,
            False,
            _STOP_LABEL,
            run_style,
            {'display': 'none'},
            [],
        )

    @app.callback(
        Output('optimization-results', 'children', allow_duplicate=True),
        [Input('sort-metric-dropdown', 'value')],
        [State('optimization-results-store', 'data'),
         State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def sort_optimization_results(sort_by, results_data, state):
        """Re-sort results when sort metric changes."""
        if not results_data or not state.get('completed'):
            raise PreventUpdate

        theme = get_theme()
        results_df = pd.DataFrame(results_data)
        if sort_by not in results_df.columns:
            sort_by = 'Robustness_Score' if 'Robustness_Score' in results_df.columns else 'Total_Return_%'

        ascending = sort_by == 'Max_Drawdown_%'
        sort_cols = ['Low_Sample', sort_by] if 'Low_Sample' in results_df.columns else [sort_by]
        sort_asc = [True, ascending] if 'Low_Sample' in results_df.columns else [ascending]
        results_df = results_df.sort_values(sort_cols, ascending=sort_asc)

        return html.Div([
            _create_best_strategy_highlight(results_df.iloc[0], theme),
            _create_optimization_table(results_df.head(10), theme),
        ], className='fade-in')

    @app.callback(
        [Output('optimizer-apply-store', 'data'),
         Output('tab-backtest', 'n_clicks', allow_duplicate=True),
         Output('backtest-origin-note', 'children'),
         Output('app-url', 'pathname', allow_duplicate=True)],
        [Input('apply-strategy-btn', 'n_clicks')],
        [State('optimization-results-store', 'data'),
         State('sort-metric-dropdown', 'value'),
         State('tab-backtest', 'n_clicks'),
         State('ticker-dropdown', 'value')],
        prevent_initial_call=True
    )
    def apply_best_strategy(
        n_clicks,
        results_data,
        sort_by,
        current_backtest_clicks,
        ticker,
    ):
        """Apply the best strategy from optimization to the backtest panel.

        Signals are routed through ``optimizer-apply-store`` (consumed by
        ``sync_signal_selection``, the single source of truth for the visible
        toggle rows) rather than written to ``buy-signals``/``sell-signals``
        directly — this keeps the on-screen SIGNALS list in sync, exactly like
        the preset-apply path, and avoids a dual-writer race. That sync callback
        also fires the Backtest auto-run once the signals are committed, so the
        user lands on the honest scorecard (real costs/Trade Setup applied). The
        note reconciles that figure against the Optimizer's idealized leaderboard.

        Also returns to the terminal (/ticker/<sym>) so Apply from the full-screen
        workspace closes the overlay.
        """
        if not n_clicks or not results_data:
            raise PreventUpdate

        from lib.dash.routes import build_ticker_terminal_path

        theme = get_theme()
        results_df = pd.DataFrame(results_data)

        if sort_by not in results_df.columns:
            sort_by = 'Robustness_Score' if 'Robustness_Score' in results_df.columns else 'Total_Return_%'
        ascending = sort_by == 'Max_Drawdown_%'
        if 'Low_Sample' in results_df.columns:
            results_df = results_df.sort_values(['Low_Sample', sort_by], ascending=[True, ascending])
        else:
            results_df = results_df.sort_values(sort_by, ascending=ascending)

        best = results_df.iloc[0]

        buy_signals = [s.strip() for s in str(best['Buy_Signals']).split(',') if s.strip()]
        sell_signals_str = str(best.get('Sell_Signals', ''))
        sell_signals = [s.strip() for s in sell_signals_str.split(',') if s.strip()]

        note = _build_origin_note(best, theme)

        apply_payload = {
            'buy': buy_signals,
            'sell': sell_signals,
            'nonce': time.time(),
        }
        return (
            apply_payload,
            (current_backtest_clicks or 0) + 1,
            note,
            build_ticker_terminal_path(ticker),
        )

    # Clientside: when ``optimizer-autorun`` changes (set by sync_signal_selection
    # AFTER buy/sell-signals are committed), click RUN BACKTEST. Ordering is
    # guaranteed because the signal values and this trigger are written by the
    # same server callback return, so run_backtest_callback reads fresh signals.
    app.clientside_callback(
        """
        function(trigger) {
            if (!trigger) { return window.dash_clientside.no_update; }
            var btn = document.getElementById('run-backtest-btn');
            if (btn) { btn.click(); }
            return window.dash_clientside.no_update;
        }
        """,
        Output('optimizer-autorun-sink', 'data'),  # dummy sink (avoids self-cycle)
        Input('optimizer-autorun', 'data'),
        prevent_initial_call=True,
    )
