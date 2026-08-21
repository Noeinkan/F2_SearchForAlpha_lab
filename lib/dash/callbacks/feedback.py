"""
Feedback modal — server-side wiring.

Five small concerns, in the order a visitor meets them:

  - open the modal (header button, or the command palette's Send feedback row)
  - remember which accordion item is the chosen category, even when the visitor
    collapses it
  - swap the message placeholder to that category's template
  - fill the "what does attaching context mean" preview with real values
  - submit: hand the note to `lib.dash.feedback.submit_feedback` and render
    whatever comes back

Two clientside handlers finish the job: one gives the composed `mailto:` URL to
the browser's mail handler, one copies the transcript to the clipboard. Both
have to be clientside — neither the mail handler nor the clipboard is reachable
from the server.

Layout lives in `lib/dash/layout/feedback.py`; formatting and delivery live in
`lib/dash/feedback.py`. This module owns neither.
"""

from __future__ import annotations

import time

from dash import callback_context, html, no_update
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate

from lib.dash.feedback import (
    DEFAULT_TYPE_ID,
    collect_diagnostics,
    get_type,
    submit_feedback,
)


# `dbc.ModalBody` renders the status line always; these classes carry the tone.
_STATUS_CLASS = {
    'sent': 'sfa-feedback-status is-ok',
    'compose': 'sfa-feedback-status is-ok',
    'error': 'sfa-feedback-status is-error',
}

_HIDDEN = {'display': 'none'}


def _workspace_from_path(pathname: str | None) -> str:
    """Human name for the route the visitor was on when they hit Send."""
    path = (pathname or '/').rstrip('/') or '/'
    if path.startswith('/fundamentals'):
        return 'Fundamentals'
    if path.startswith('/flow'):
        return 'Flow scanner'
    if path.startswith('/optimize'):
        return 'Optimizer'
    return 'Terminal'


def register_feedback_callbacks(app) -> None:
    """Wire the feedback modal."""

    @app.callback(
        Output('feedback-modal', 'is_open'),
        [Input('feedback-open-btn', 'n_clicks'),
         Input('feedback-close-btn', 'n_clicks')],
        [State('feedback-modal', 'is_open')],
        prevent_initial_call=True,
    )
    def _toggle_feedback_modal(_open_clicks, _close_clicks, is_open):
        """Open from the header button, close from the footer button.

        Sending deliberately does *not* close: the visitor needs to read the
        confirmation, and on the mailto path they may need the copy fallback.
        """
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate
        trigger = ctx.triggered[0]['prop_id'].split('.')[0]
        if trigger == 'feedback-open-btn':
            return True
        if trigger == 'feedback-close-btn':
            return False
        return is_open

    @app.callback(
        Output('feedback-type-store', 'data'),
        Input('feedback-type-accordion', 'active_item'),
        prevent_initial_call=True,
    )
    def _remember_type(active_item):
        """Hold the last real selection.

        Clicking an open accordion item closes it and reports `None`. That is a
        fine gesture ("I have read this") but a terrible category, so the store
        keeps whatever was chosen last instead of resetting.
        """
        if not active_item:
            raise PreventUpdate
        return active_item

    @app.callback(
        Output('feedback-message', 'placeholder'),
        Input('feedback-type-store', 'data'),
    )
    def _swap_placeholder(type_id):
        """Show the selected category's template in the empty message box."""
        return get_type(type_id or DEFAULT_TYPE_ID)['placeholder']

    @app.callback(
        Output('feedback-context-preview', 'children'),
        Input('feedback-modal', 'is_open'),
        [State('ticker-dropdown', 'value'),
         State('theme-store', 'data'),
         State('app-url', 'pathname')],
    )
    def _preview_context(is_open, ticker, theme, pathname):
        """Render the exact diagnostics that would be attached, with values.

        Recomputed on open so it always describes the current session rather
        than whatever was true when the page first loaded.
        """
        if not is_open:
            raise PreventUpdate
        diagnostics = collect_diagnostics(
            ticker=ticker,
            theme=theme,
            page=_workspace_from_path(pathname),
        )
        return [
            html.Div(
                [
                    html.Span(key, className='sfa-feedback-context-key'),
                    html.Span(value, className='sfa-feedback-context-val'),
                ],
                className='sfa-feedback-context-row',
            )
            for key, value in diagnostics.items()
        ]

    @app.callback(
        [Output('feedback-status', 'children'),
         Output('feedback-status', 'className'),
         Output('feedback-mailto', 'data'),
         Output('feedback-transcript', 'value'),
         Output('feedback-fallback', 'style'),
         Output('feedback-message', 'value')],
        Input('feedback-send-btn', 'n_clicks'),
        [State('feedback-type-store', 'data'),
         State('feedback-message', 'value'),
         State('feedback-reply-to', 'value'),
         State('feedback-include-context', 'value'),
         State('ticker-dropdown', 'value'),
         State('theme-store', 'data'),
         State('app-url', 'pathname')],
        prevent_initial_call=True,
    )
    def _send_feedback(
        n_clicks,
        type_id,
        message,
        reply_to,
        include_context,
        ticker,
        theme,
        pathname,
    ):
        """Validate, deliver, and report back."""
        if not n_clicks:
            raise PreventUpdate

        diagnostics = None
        if include_context and 'yes' in include_context:
            diagnostics = collect_diagnostics(
                ticker=ticker,
                theme=theme,
                page=_workspace_from_path(pathname),
            )

        result = submit_feedback(
            type_id=type_id or DEFAULT_TYPE_ID,
            message=message or '',
            reply_to=reply_to,
            diagnostics=diagnostics,
        )

        status_class = _STATUS_CLASS.get(result.status, 'sfa-feedback-status')

        if result.status == 'error':
            # Nothing was sent, so leave the box exactly as they left it.
            return result.message, status_class, no_update, no_update, _HIDDEN, no_update

        # The mailto store carries a timestamp so two identical notes still
        # register as two separate writes and both reach the mail handler.
        mailto = (
            {'url': result.mailto, 'ts': time.time()} if result.mailto else no_update
        )

        if result.status == 'sent':
            # The relay took it; clear the box so nobody sends twice.
            return result.message, status_class, no_update, result.transcript, _HIDDEN, ''

        # compose: mail client opening. Keep the text (the hand-off may have
        # failed silently) and offer the copy fallback.
        return (
            result.message,
            status_class,
            mailto,
            result.transcript,
            {},
            no_update,
        )

    # Hand the composed URL to the browser's mail handler. `location.href` on a
    # mailto: does not unload the page, so the modal stays exactly as it was.
    app.clientside_callback(
        """
        function(payload) {
            if (!payload || !payload.url) {
                return window.dash_clientside.no_update;
            }
            window.location.href = payload.url;
            return String(payload.ts);
        }
        """,
        Output('feedback-mailto-sync', 'children'),
        Input('feedback-mailto', 'data'),
        prevent_initial_call=True,
    )

    # The form is taller than the dialog, and Send lives in a pinned footer, so
    # the status line it writes can land well below the fold. Bring it into
    # view — otherwise a validation error looks like a button that did nothing.
    app.clientside_callback(
        """
        function(status) {
            if (!status) { return window.dash_clientside.no_update; }
            var el = document.getElementById('feedback-status');
            if (el && el.scrollIntoView) {
                el.scrollIntoView({behavior: 'smooth', block: 'nearest'});
            }
            return '';
        }
        """,
        Output('feedback-scroll-sync', 'children'),
        Input('feedback-status', 'children'),
        prevent_initial_call=True,
    )

    # Clipboard fallback for when no mail handler exists. Reads the textarea
    # from the DOM rather than taking it as State so the copy is always of
    # what the visitor can actually see.
    app.clientside_callback(
        """
        function(n_clicks) {
            if (!n_clicks) { return window.dash_clientside.no_update; }
            var box = document.getElementById('feedback-transcript');
            if (!box) { return window.dash_clientside.no_update; }
            var text = box.value || '';
            if (navigator.clipboard && navigator.clipboard.writeText) {
                navigator.clipboard.writeText(text);
            } else {
                // execCommand is deprecated but is the only path on
                // non-secure origins, which a LAN-shared dashboard may be.
                box.select();
                try { document.execCommand('copy'); } catch (err) { return 'Copy failed'; }
            }
            return 'Copied';
        }
        """,
        Output('feedback-copy-btn', 'children'),
        Input('feedback-copy-btn', 'n_clicks'),
        prevent_initial_call=True,
    )


__all__ = ['register_feedback_callbacks']
