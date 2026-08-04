"""Bidirectional sync between Optimizer mirrors and Backtest SoT controls.

Dash IDs must stay unique, so the Optimizer rail hosts ``opt-*`` mirrors that
write through to the hidden Backtest components (and mirror values back).
Test-window *dates* remain owned solely by ``sync_test_window`` — this module
only syncs the preset radio and mirrors resolved dates onto the opt pickers;
opt date edits are fed into ``sync_test_window`` as extra Inputs.
"""

from __future__ import annotations

from typing import Any

from dash import callback_context, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate


def values_differ(left: Any, right: Any) -> bool:
    """True when mirror and SoT disagree enough to warrant a write."""
    if left is None and right is None:
        return False
    if left is None or right is None:
        return left != right
    # DatePicker may hand ISO strings of different precision.
    if isinstance(left, str) and isinstance(right, str):
        return left[:10] != right[:10]
    try:
        return float(left) != float(right)
    except (TypeError, ValueError):
        return left != right


def pick_mirror_write(
    triggered_id: str | None,
    left_id: str,
    left_val: Any,
    right_id: str,
    right_val: Any,
) -> tuple[Any, Any]:
    """Return ``(left_out, right_out)`` for a bidirectional pair.

    Only the side that did *not* trigger is updated; equal values → no_update.
    """
    if not triggered_id:
        return no_update, no_update
    if triggered_id == left_id:
        if values_differ(left_val, right_val):
            return no_update, left_val
        return no_update, no_update
    if triggered_id == right_id:
        if values_differ(right_val, left_val):
            return right_val, no_update
        return no_update, no_update
    return no_update, no_update


def register_optimizer_sync_callbacks(app) -> None:
    @app.callback(
        [Output('opt-initial-capital', 'value'),
         Output('initial-capital', 'value', allow_duplicate=True)],
        [Input('opt-initial-capital', 'value'),
         Input('initial-capital', 'value')],
        prevent_initial_call='initial_duplicate',
    )
    def sync_capital(opt_val, sot_val):
        ctx = callback_context
        trigger = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        return pick_mirror_write(trigger, 'opt-initial-capital', opt_val, 'initial-capital', sot_val)

    @app.callback(
        [Output('opt-test-window-preset', 'value'),
         Output('test-window-preset', 'value')],
        [Input('opt-test-window-preset', 'value'),
         Input('test-window-preset', 'value')],
        prevent_initial_call='initial_duplicate',
    )
    def sync_window_preset(opt_val, sot_val):
        ctx = callback_context
        trigger = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        return pick_mirror_write(
            trigger, 'opt-test-window-preset', opt_val, 'test-window-preset', sot_val,
        )

    # Dates: SoT → opt mirror only (opt → SoT handled inside sync_test_window).
    @app.callback(
        [Output('opt-test-window-start', 'date'),
         Output('opt-test-window-end', 'date')],
        [Input('test-window-start', 'date'),
         Input('test-window-end', 'date')],
        [State('opt-test-window-start', 'date'),
         State('opt-test-window-end', 'date')],
        prevent_initial_call=False,
    )
    def mirror_window_dates(sot_start, sot_end, opt_start, opt_end):
        start_out = sot_start if values_differ(sot_start, opt_start) else no_update
        end_out = sot_end if values_differ(sot_end, opt_end) else no_update
        if start_out is no_update and end_out is no_update:
            raise PreventUpdate
        return start_out, end_out

    _FRICTION_PAIRS = [
        ('opt-strategy-mode', 'strategy-mode'),
        ('opt-min-holding-period', 'min-holding-period'),
        ('opt-trailing-stop-pct', 'trailing-stop-pct'),
        ('opt-stop-mode', 'stop-mode'),
        ('opt-fx-fee-pct', 'fx-fee-pct'),
        ('opt-slippage-pct', 'slippage-pct'),
        ('opt-commission-pct', 'commission-pct'),
    ]

    for opt_id, sot_id in _FRICTION_PAIRS:
        app.callback(
            [Output(opt_id, 'value'),
             Output(sot_id, 'value', allow_duplicate=True)],
            [Input(opt_id, 'value'),
             Input(sot_id, 'value')],
            prevent_initial_call='initial_duplicate',
        )(_make_friction_sync(opt_id, sot_id))

    @app.callback(
        Output('opt-realistic-fields', 'className'),
        Input('optimizer-realistic-ranking', 'value'),
        prevent_initial_call=False,
    )
    def toggle_realistic_fields(ranking_flags):
        on = bool(ranking_flags) and 'on' in (ranking_flags or [])
        return '' if on else 'sfa-optimize-realistic-off'


def _make_friction_sync(opt_id: str, sot_id: str):
    def _sync(opt_val, sot_val):
        ctx = callback_context
        trigger = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        return pick_mirror_write(trigger, opt_id, opt_val, sot_id, sot_val)
    _sync.__name__ = f'sync_{opt_id.replace("-", "_")}'
    return _sync
