"""
Optimization callbacks.
"""

import logging
import threading
import time
from concurrent.futures import ThreadPoolExecutor

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
from lib.dash.callbacks.shared import (
    OPTIMIZATION_BATCH_SIZE,
    _create_best_strategy_highlight,
    _create_optimization_table,
    _create_optimization_table_mini,
)

logger = logging.getLogger(__name__)


# Sentinel returned by a worker whose run was cancelled mid-flight (i.e. the
# user clicked RUN OPTIMIZER again while this batch was in flight). Treated
# specially by ``process_optimization_batch``.
_CANCELLED = object()


def _eval_with_cancel_guard(
    run_token: int,
    df: pd.DataFrame,
    initial_capital: float,
    buy_combo,
    sell_combo,
):
    """Evaluate a single combination, returning ``_CANCELLED`` if the run was
    superseded by a fresh ``start_optimization`` click while we were waiting
    in the thread pool queue.

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
    shutdown and into start_optimization so we pick up a fresh pool if the
    worker count is reconfigured at runtime."""
    global _EXECUTOR
    with _EXECUTOR_LOCK:
        if _EXECUTOR is not None:
            _EXECUTOR.shutdown(wait=False, cancel_futures=True)
            _EXECUTOR = None
            logger.info("Optimizer thread-pool shut down")


def _parse_date_bound(value, *, default: str | None) -> pd.Timestamp | None:
    """Parse a dcc.DatePickerSingle value into a tz-naive Timestamp.

    Returns ``default`` (parsed) when ``value`` is missing, ``None`` when the
    caller explicitly wants an open-ended bound (default ``None``).
    """
    if value is None or value == "":
        return pd.Timestamp(default) if default else None
    try:
        return pd.Timestamp(str(value)[:10])
    except (TypeError, ValueError):
        return pd.Timestamp(default) if default else None


def _slice_df_to_sidebar_range(
    df: pd.DataFrame, start_date: str | None, end_date: str | None
) -> tuple[pd.DataFrame, str]:
    """Return ``df`` clipped to the sidebar [start, end] window.

    The chart's Plotly 1M/3M/1Y range-selector only zooms the viewport — it
    does not filter the underlying DataFrame. The optimizer previously saw
    the full history that the sidebar had fetched, which silently
    contradicted the chart's visible window. Slicing here makes the
    optimizer's ranking match the window the user is looking at.

    Non-datetime indexes (e.g. unit tests using a synthetic int index) are
    passed through untouched. The returned label summarises the effective
    window for the progress UI.
    """
    if df.empty or not isinstance(df.index, pd.DatetimeIndex):
        return df, "full history (no date index)"

    start = _parse_date_bound(start_date, default=None)
    end = _parse_date_bound(end_date, default=None)
    # end is inclusive — bump by one day so the slice keeps the end date itself.
    end_exclusive = (end + pd.Timedelta(days=1)) if end is not None else None

    sliced = df.loc[start:end_exclusive] if start is not None or end_exclusive is not None else df
    if sliced.empty:
        # Fall back to the full df so the user sees an error instead of a
        # silent zero-row "no combinations" run.
        return df, f"{df.index.min().date()} → {df.index.max().date()} (sidebar window empty)"

    start_label = sliced.index.min().date().isoformat()
    end_label = sliced.index.max().date().isoformat()
    return sliced, f"{start_label} → {end_label}"


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


def register_optimization_callbacks(app) -> None:
    @app.callback(
        [Output('preview-buy-count', 'children'),
         Output('preview-sell-count', 'children'),
         Output('preview-combo-count', 'children'),
         Output('optimization-cost', 'children')],
        [Input('data-loaded-store', 'data'),
         Input('max-signals-slider', 'value'),
         Input('max-combos-input', 'value')]
    )
    def update_signal_preview(data_loaded, max_signals, max_combos):
        """Show preview of available signals, the combo cap, and an estimated runtime."""
        if not data_loaded or dashboard_state.df is None:
            return "0", "0", "0", "—"

        df = dashboard_state.df
        buy_signals, sell_signals = extract_signals(df)

        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        actual_combos = min(len(combinations), max_combos or 100)

        est_seconds = _estimate_runtime_seconds(actual_combos)
        cost_label = _format_duration(est_seconds) if est_seconds is not None else "—"

        return (
            str(len(buy_signals)),
            str(len(sell_signals)),
            str(actual_combos),
            cost_label,
        )

    @app.callback(
        [Output('optimization-state', 'data'),
         Output('optimization-interval', 'disabled'),
         Output('optimization-progress', 'children'),
         Output('run-optimization-btn', 'disabled'),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True)],
        [Input('run-optimization-btn', 'n_clicks')],
        [State('initial-capital', 'value'),
         State('max-signals-slider', 'value'),
         State('max-combos-input', 'value'),
         State('min-trades-input', 'value'),
         State('start-date', 'date'),
         State('end-date', 'date'),
         State('optimization-state', 'data')],
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
    ):
        """Initialize optimization run and enable interval for progress updates."""
        if not n_clicks:
            raise PreventUpdate

        # Guard against re-clicks while a run is in flight. ``current_state``
        # mirrors the most recent ``optimization-state`` snapshot the browser
        # has rendered; if the server already marked the run as running, the
        # second click is just a nervous double-click and we silently drop it.
        if current_state and current_state.get('running'):
            raise PreventUpdate

        theme = get_theme()
        full_df = dashboard_state.df

        if full_df is None:
            return (
                current_state,
                True,
                build_alert("Please load market data first", "warning", theme=theme),
                False,
                html.Div(),
                {'display': 'none'}
            )

        df, window_label = _slice_df_to_sidebar_range(full_df, start_date, end_date)

        buy_signals, sell_signals = extract_signals(df)
        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        combinations = combinations[:max_combos]

        if not combinations:
            return (
                current_state,
                True,
                build_alert("No valid signal combinations found", "warning", theme=theme),
                False,
                html.Div(),
                {'display': 'none'}
            )

        # Convert tuples to lists for JSON serialization
        combinations_serializable = [[list(buy), list(sell)] for buy, sell in combinations]

        # Reset state in dashboard_state. reset_optimization() replaces the
        # underlying dict with a brand-new one — any in-flight worker threads
        # from the previous run will see id(state) change and drop their
        # pending writes (see _eval_with_cancel_guard below).
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
            'sort_by': 'Robustness_Score',
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
            True,   # Disable button
            html.Div(),  # Clear previous results
            {'display': 'none'}  # Hide apply button
        )

    @app.callback(
        [Output('optimization-state', 'data', allow_duplicate=True),
         Output('optimization-progress', 'children', allow_duplicate=True),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('optimization-interval', 'disabled', allow_duplicate=True),
         Output('run-optimization-btn', 'disabled', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True),
         Output('optimization-results-store', 'data')],
        [Input('optimization-interval', 'n_intervals')],
        [State('optimization-state', 'data'),
         State('start-date', 'date'),
         State('end-date', 'date')],
        prevent_initial_call=True
    )
    def process_optimization_batch(n_intervals, state, start_date, end_date):
        """Process a batch of combinations on each interval tick.

        Uses a thread pool so multiple backtests run in parallel. Each worker
        re-checks ``id(dashboard_state.optimization_state)`` against the token
        captured at dispatch time — if the user clicked RUN OPTIMIZER again
        mid-flight (which replaces the state dict), stale results are
        discarded instead of polluting the new run.
        """
        theme = get_theme()

        if not state or not state.get('running'):
            raise PreventUpdate

        full_df = dashboard_state.df
        if full_df is None:
            raise PreventUpdate

        df, _window_label = _slice_df_to_sidebar_range(full_df, start_date, end_date)

        opt_state = dashboard_state.optimization_state
        current_idx = opt_state.get('current_index', 0)
        total = opt_state.get('total_combinations', 0)
        combinations = opt_state.get('combinations', [])
        results = opt_state.get('results', [])
        initial_capital = opt_state.get('initial_capital', 10000)

        if not combinations or current_idx >= total:
            raise PreventUpdate

        # Cancellation token — captured before dispatching the batch. If a
        # concurrent ``start_optimization`` call replaces ``_optimization_state``
        # (via ``reset_optimization``), this id will no longer match and the
        # workers' writes will be discarded.
        run_token = id(opt_state)

        # Process batch in parallel. Cap batch size at the actual remaining
        # work so we don't dispatch empty futures after the last tick.
        end_idx = min(current_idx + OPTIMIZATION_BATCH_SIZE, total)
        batch = combinations[current_idx:end_idx]
        batch_size = len(batch)

        t0 = time.perf_counter()
        executor = _get_executor()
        # Snapshot df once for the worker closure — workers share the read-only
        # DataFrame; pandas is fine with concurrent reads.
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
                # The user reset state mid-batch. Drop the rest and bail out
                # so the next tick can pick up the new run cleanly.
                raise PreventUpdate
            results.append(result)

        _calibrate_sec_per_combo(time.perf_counter() - t0, batch_size)

        # Update state
        dashboard_state.update_optimization_state(
            current_index=end_idx,
            results=results
        )

        progress_pct = int((end_idx / total) * 100)

        # Check if complete
        if end_idx >= total:
            dashboard_state.update_optimization_state(running=False, completed=True)
            min_trades = opt_state.get('min_trades', 10)

            results_df = pd.DataFrame(results)
            # Drop error rows (no finite return) BEFORE deciding success, so a
            # run where every combo failed shows an honest failure instead of a
            # fake 0% winner.
            if 'Total_Return_%' in results_df.columns:
                results_df = results_df[results_df['Total_Return_%'].notna()]
            else:
                results_df = results_df.iloc[0:0]

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
                    {'display': 'none'},
                    []
                )

            results_df = compute_robustness_scores(results_df, min_trades)
            sort_by = state.get('sort_by', 'Robustness_Score')
            if sort_by not in results_df.columns:
                sort_by = 'Robustness_Score'
            # Keep credible (>= min_trades) combinations above low-sample ones,
            # then rank within each group by the chosen metric.
            results_df = results_df.sort_values(
                ['Low_Sample', sort_by],
                ascending=[True, sort_by == 'Max_Drawdown_%'],
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

            results_ui = html.Div([
                _create_best_strategy_highlight(results_df.iloc[0], theme),
                _create_optimization_table(results_df.head(10), theme),
            ], className='fade-in')

            return (
                state,
                final_progress,
                results_ui,
                True,   # Disable interval
                False,  # Re-enable button
                {'display': 'block'},  # Show apply button
                results_df.to_dict('records')
            )

        # Still processing - update progress
        state['current_index'] = end_idx

        # Estimate remaining wall-clock time using the latest calibration.
        # ``None`` until the first batch finishes, in which case we just show
        # the worker count so the user sees the parallel rig is engaged.
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

        # Show partial results (top 5 so far)
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
            False,  # Keep interval enabled
            True,   # Keep button disabled
            {'display': 'none'},
            []
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

        # Ascending for drawdown (less negative is better), descending for others.
        # Keep credible combinations above low-sample ones regardless of metric.
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
         Output('backtest-origin-note', 'children')],
        [Input('apply-strategy-btn', 'n_clicks')],
        [State('optimization-results-store', 'data'),
         State('sort-metric-dropdown', 'value'),
         State('tab-backtest', 'n_clicks')],
        prevent_initial_call=True
    )
    def apply_best_strategy(n_clicks, results_data, sort_by, current_backtest_clicks):
        """Apply the best strategy from optimization to the backtest panel.

        Signals are routed through ``optimizer-apply-store`` (consumed by
        ``sync_signal_selection``, the single source of truth for the visible
        toggle rows) rather than written to ``buy-signals``/``sell-signals``
        directly — this keeps the on-screen SIGNALS list in sync, exactly like
        the preset-apply path, and avoids a dual-writer race. That sync callback
        also fires the Backtest auto-run once the signals are committed, so the
        user lands on the honest scorecard (real costs/Trade Setup applied). The
        note reconciles that figure against the Optimizer's idealized leaderboard.
        """
        if not n_clicks or not results_data:
            raise PreventUpdate

        theme = get_theme()
        results_df = pd.DataFrame(results_data)

        # Mirror the leaderboard's displayed order: credible combos above
        # low-sample ones, then by the chosen metric — so the row we apply is
        # the same #1 the user is looking at.
        if sort_by not in results_df.columns:
            sort_by = 'Robustness_Score' if 'Robustness_Score' in results_df.columns else 'Total_Return_%'
        ascending = sort_by == 'Max_Drawdown_%'
        if 'Low_Sample' in results_df.columns:
            results_df = results_df.sort_values(['Low_Sample', sort_by], ascending=[True, ascending])
        else:
            results_df = results_df.sort_values(sort_by, ascending=ascending)

        best = results_df.iloc[0]

        # Parse signal strings back to lists
        buy_signals = [s.strip() for s in str(best['Buy_Signals']).split(',') if s.strip()]
        sell_signals_str = str(best.get('Sell_Signals', ''))
        sell_signals = [s.strip() for s in sell_signals_str.split(',') if s.strip()]

        note = _build_origin_note(best, theme)

        # The nonce changes every Apply so sync_signal_selection re-fires even
        # when the same winner is applied twice in a row.
        apply_payload = {
            'buy': buy_signals,
            'sell': sell_signals,
            'nonce': time.time(),
        }
        return (
            apply_payload,
            (current_backtest_clicks or 0) + 1,
            note,
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
