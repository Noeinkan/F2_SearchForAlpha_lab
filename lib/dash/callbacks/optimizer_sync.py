"""Bidirectional sync between Optimizer mirrors and Backtest SoT controls.

Dash IDs must stay unique, so the Optimizer rail hosts ``opt-*`` mirrors that
write through to the hidden Backtest components (and mirror values back).

Test-window *dates* use one bidirectional callback (same pattern as capital)
so Dash 4 does not flag a static cycle. Series/preset resets still land via
``sync_test_window`` in ``test_window.py``; this module mirrors those SoT
writes onto the opt pickers and pushes opt edits back to SoT.
"""

from __future__ import annotations

from typing import Any

from dash import callback_context, no_update
from dash.dependencies import Input, Output
from dash.exceptions import PreventUpdate

from lib.dash.callbacks.test_window import _clamp_to_loaded, _loaded_bounds


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

    # Dates: one bidirectional callback (avoids the SoT↔opt cycle Dash 4 rejects
    # when sync_test_window and a one-way mirror are separate callbacks).
    @app.callback(
        [Output('opt-test-window-start', 'date'),
         Output('opt-test-window-end', 'date'),
         Output('test-window-start', 'date', allow_duplicate=True),
         Output('test-window-end', 'date', allow_duplicate=True)],
        [Input('opt-test-window-start', 'date'),
         Input('opt-test-window-end', 'date'),
         Input('test-window-start', 'date'),
         Input('test-window-end', 'date')],
        prevent_initial_call='initial_duplicate',
    )
    def sync_window_dates(opt_start, opt_end, sot_start, sot_end):
        ctx = callback_context
        trigger = ctx.triggered[0]['prop_id'].split('.')[0] if ctx.triggered else None
        if not trigger:
            raise PreventUpdate

        if trigger in ('opt-test-window-start', 'opt-test-window-end'):
            if not opt_start or not opt_end:
                raise PreventUpdate
            start, end = opt_start, opt_end
            bounds = _loaded_bounds()
            if bounds is not None:
                start, end = _clamp_to_loaded(opt_start, opt_end, bounds[0], bounds[1])
            opt_start_out = start if values_differ(start, opt_start) else no_update
            opt_end_out = end if values_differ(end, opt_end) else no_update
            sot_start_out = start if values_differ(start, sot_start) else no_update
            sot_end_out = end if values_differ(end, sot_end) else no_update
            if (
                opt_start_out is no_update
                and opt_end_out is no_update
                and sot_start_out is no_update
                and sot_end_out is no_update
            ):
                raise PreventUpdate
            return opt_start_out, opt_end_out, sot_start_out, sot_end_out

        # SoT changed (preset / new series / backtest picker) → mirror to opt.
        start_out = sot_start if values_differ(sot_start, opt_start) else no_update
        end_out = sot_end if values_differ(sot_end, opt_end) else no_update
        if start_out is no_update and end_out is no_update:
            raise PreventUpdate
        return start_out, end_out, no_update, no_update

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
