"""Global error boundary — the last stop for a callback that raised.

Most callbacks catch their own failures and render a ``build_alert`` in place
(the backtest, the data load, the chart payload). The ones that do not used to
fail silently: Dash logged the traceback, the browser showed nothing outside
dev tools, and the status bar stayed on ``WORKING…`` forever because the output
its resolver waits for never arrived.

``handle_callback_error`` is passed to ``dash.Dash(on_error=...)``. Dash calls it
with the exception instead of returning a 500, inside the failing request, so
``set_props`` can still reach any component on the page. It writes a
dismissible alert into ``#error-boundary`` and flips the status bar to
``ERROR``, and returns ``None`` — which Dash turns into ``no_update`` for every
output of the failed callback, so nothing half-computed reaches the screen.

``PreventUpdate`` never gets here: Dash re-raises it before calling the handler.
"""

from __future__ import annotations

import logging
from datetime import datetime

from dash import callback_context, html, set_props

from lib.dash.components import build_alert

logger = logging.getLogger(__name__)

ERROR_BOUNDARY_ID = 'error-boundary'

# Long enough for a useful exception message, short enough that a pandas repr
# of a whole frame cannot fill the screen.
MAX_DETAIL_CHARS = 200


def build_error_boundary() -> html.Div:
    """Empty landing pad for the handler. ``role=alert`` announces new content."""
    return html.Div(
        id=ERROR_BOUNDARY_ID,
        className='sfa-error-boundary',
        role='alert',
        **{'aria-live': 'assertive'},
    )


def _failed_target() -> str:
    """Name the output the failed callback was meant to update, for the log and alert."""
    try:
        outputs = callback_context.outputs_list
    except Exception:  # noqa: BLE001 - no request context, e.g. a direct call in a test
        return 'a dashboard callback'
    if isinstance(outputs, dict):
        outputs = [outputs]
    for item in outputs or []:
        # A pattern-matching output arrives as a list of concrete outputs.
        if isinstance(item, list):
            item = item[0] if item else None
        if not isinstance(item, dict):
            continue
        component = item.get('id')
        if isinstance(component, dict):
            component = component.get('type') or next(iter(component.values()), '')
        if component:
            # An allow_duplicate output carries "@<hash>" on its property name.
            prop = str(item.get('property') or '').split('@', 1)[0]
            return f"{component}.{prop}".rstrip('.')
    return 'a dashboard callback'


def _detail(err: Exception) -> str:
    message = ' '.join(str(err).split())
    if len(message) > MAX_DETAIL_CHARS:
        message = message[:MAX_DETAIL_CHARS - 1] + '…'
    return f"{type(err).__name__}: {message}" if message else type(err).__name__


def build_error_alert(target: str, err: Exception):
    """The alert the boundary shows. Separate so it can be tested without a request."""
    stamp = datetime.now().strftime('%H:%M:%S')
    return build_alert(
        html.Span([
            html.Strong(f"Something went wrong updating {target}. "),
            "The rest of the dashboard still works; the full traceback is in the server log.",
            html.Div(
                f"{stamp} · {_detail(err)}",
                className='sfa-error-boundary__detail num',
            ),
        ]),
        'error',
        dismissable=True,
    )


def handle_callback_error(err: Exception) -> None:
    """``on_error`` hook: log, surface the failure, and leave every output untouched."""
    target = _failed_target()
    logger.error(
        "Unhandled exception in callback for %s",
        target,
        exc_info=(type(err), err, err.__traceback__),
    )
    try:
        set_props(ERROR_BOUNDARY_ID, {'children': build_error_alert(target, err)})
        set_props('status-activity-label', {'children': 'ERROR'})
        set_props('status-activity-dot', {'className': 'dot dot-down'})
    except Exception:  # noqa: BLE001 - the handler itself must never raise
        logger.exception("error boundary could not render the failure")
    return None
