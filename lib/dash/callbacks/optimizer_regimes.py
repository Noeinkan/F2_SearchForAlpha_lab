"""
Optimizer workspace — regime slicing of the combo leaderboard winner (ROADMAP 4.15).

Same background-thread + polling-interval shape as the OOS walk-forward in
``optimizer_phase3.py``: the button starts a worker, clicking it again while
running discards the result, and ``optimizer-regimes-interval`` picks it up.
"""

from __future__ import annotations

import threading
from typing import Any

from dash import html, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.callbacks.optimizer_phase3 import _winner_signals
from lib.dash.combo_regimes import run_combo_regimes
from lib.dash.combo_walkforward import ComboSpec
from lib.dash.components import build_alert
from lib.dash.dash_config import FONT_SIZES, get_theme
from lib.dash.regime_view import render_regime_panel
from lib.dash.state import dashboard_state
from lib.timeframes import normalize_interval

REGIMES_RUN_LABEL = 'REGIMES'
REGIMES_STOP_LABEL = 'STOP REGIMES'

_regimes_lock = threading.Lock()
_regimes_job: dict[str, Any] = {
    'running': False,
    'result': None,
    'error': None,
    'cancelled': False,
}


def _regimes_worker(
    *,
    buy: list[str],
    sell: list[str],
    ticker: str,
    settings: dict[str, Any] | None,
    capital: float,
    bar_interval: str,
) -> None:
    try:
        eval_kwargs = dashboard_state.optimization_state.get('eval_kwargs') or {}
        combo = ComboSpec(
            buy_signals=tuple(buy),
            sell_signals=tuple(sell),
            ticker=ticker,
            indicator_settings=settings or {},
            backtest_kwargs=eval_kwargs or None,
        )
        payload = run_combo_regimes(combo=combo, interval=bar_interval, initial_capital=capital)
        with _regimes_lock:
            if _regimes_job.get('cancelled'):
                _regimes_job.update(result=None, error='Cancelled')
            else:
                _regimes_job.update(result=payload, error=None)
    except Exception as exc:
        with _regimes_lock:
            _regimes_job.update(result=None, error=str(exc))
    finally:
        with _regimes_lock:
            _regimes_job['running'] = False


def register_optimizer_regimes_callbacks(app) -> None:
    @app.callback(
        [Output('optimizer-regimes-interval', 'disabled', allow_duplicate=True),
         Output('validate-regimes-btn', 'children', allow_duplicate=True),
         Output('optimizer-regimes-panel', 'children', allow_duplicate=True),
         Output('optimize-visuals-accordion', 'active_item', allow_duplicate=True)],
        Input('validate-regimes-btn', 'n_clicks'),
        [State('optimization-results-store', 'data'),
         State('sort-metric-dropdown', 'value'),
         State('ticker-dropdown', 'value'),
         State('initial-capital', 'value'),
         State('bar-interval', 'value'),
         State('indicator-settings-store', 'data'),
         State('optimize-visuals-accordion', 'active_item')],
        prevent_initial_call=True,
    )
    def control_regime_slicing(
        n_clicks, results_data, sort_by, ticker, capital, bar_interval, settings, active_items,
    ):
        if not n_clicks:
            raise PreventUpdate
        theme = get_theme()

        with _regimes_lock:
            if _regimes_job['running']:
                _regimes_job['cancelled'] = True
                return (
                    no_update,
                    'Stopping…',
                    build_alert("Stopping regime slicing…", "info", theme=theme),
                    no_update,
                )

        if not results_data:
            raise PreventUpdate
        try:
            buy, sell = _winner_signals(results_data, sort_by)
        except Exception as exc:
            return (
                True,
                REGIMES_RUN_LABEL,
                build_alert(f"Could not resolve winner: {exc}", "warning", theme=theme),
                no_update,
            )
        if not buy:
            return (
                True,
                REGIMES_RUN_LABEL,
                build_alert("No buy signals on the current winner.", "warning", theme=theme),
                no_update,
            )

        with _regimes_lock:
            _regimes_job.update(running=True, result=None, error=None, cancelled=False)
        threading.Thread(
            target=_regimes_worker,
            kwargs={
                'buy': buy,
                'sell': sell,
                'ticker': str(ticker or 'TSLA').upper(),
                'settings': settings,
                'capital': float(capital or 10_000),
                'bar_interval': normalize_interval(bar_interval or '1d'),
            },
            daemon=True,
        ).start()

        # Open the accordion item so the result lands where the user is looking.
        items = list(active_items or []) if isinstance(active_items, (list, tuple)) else (
            [active_items] if active_items else []
        )
        if 'viz-regimes' not in items:
            items.append('viz-regimes')
        panel = html.Div(
            "Backtesting the combo winner in each market regime since 2019…",
            style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary']},
        )
        return False, REGIMES_STOP_LABEL, panel, items

    @app.callback(
        [Output('optimizer-regimes-panel', 'children'),
         Output('optimizer-regimes-interval', 'disabled'),
         Output('validate-regimes-btn', 'children')],
        Input('optimizer-regimes-interval', 'n_intervals'),
        prevent_initial_call=True,
    )
    def poll_regime_slicing(_n_intervals):
        with _regimes_lock:
            if _regimes_job['running']:
                raise PreventUpdate
            result = _regimes_job['result']
            error = _regimes_job['error']
            if result is None and error is None:
                raise PreventUpdate
            _regimes_job.update(result=None, error=None, cancelled=False)

        theme = get_theme()
        if error:
            if error == 'Cancelled':
                body = build_alert("Regime slicing cancelled.", "warning", theme=theme)
            else:
                body = build_alert(f"Regime slicing failed: {error}", "danger", theme=theme)
            return body, True, REGIMES_RUN_LABEL
        return render_regime_panel(result, theme), True, REGIMES_RUN_LABEL
