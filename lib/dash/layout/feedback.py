"""
Feedback modal — the "tell me what you think" form behind the header button.

Shape of the form, and why:

  1. **An accordion of note types.** Opening an item both picks the category and
     shows what a useful note of that kind contains. A bare dropdown would pick
     the category just as well but teaches nothing; the accordion body is where
     "what happened instead" gets asked without a wall of instructions above an
     empty box.
  2. **One shared message box**, not one per accordion item — switching category
     must never eat what someone has already typed. Its placeholder swaps to the
     selected type's template (callbacks/feedback.py).
  3. **Optional reply address and optional context**, both below the fold of
     attention. Neither is required; an anonymous note with no diagnostics is
     still a good note, and asking for identity up front costs replies.

Delivery, validation and formatting all live in `lib/dash/feedback.py` — this
module is markup only.
"""

from dash import dcc, html
import dash_bootstrap_components as dbc

from lib.dash.dash_config import FEEDBACK_EMAIL
from lib.dash.feedback import (
    DEFAULT_TYPE_ID,
    FEEDBACK_TYPES,
    MAX_MESSAGE_CHARS,
    get_type,
)


def _accordion_items() -> list[dbc.AccordionItem]:
    """One item per feedback type; the open item is the selected category."""
    return [
        dbc.AccordionItem(
            html.Div(entry['blurb'], className='sfa-feedback-blurb'),
            title=html.Span(
                [
                    html.Span(
                        entry['icon'],
                        className='sfa-feedback-type-icon',
                        **{'aria-hidden': 'true'},
                    ),
                    html.Span(entry['label'], className='sfa-feedback-type-label'),
                ],
                className='sfa-feedback-type-title',
            ),
            item_id=entry['id'],
        )
        for entry in FEEDBACK_TYPES
    ]


def _step_label(number: str, text: str, optional: bool = False) -> html.Div:
    children = [
        html.Span(number, className='sfa-feedback-step-num'),
        html.Span(text, className='sfa-feedback-step-text'),
    ]
    if optional:
        children.append(html.Span('optional', className='sfa-feedback-step-opt'))
    return html.Div(children, className='sfa-feedback-step')


def _create_feedback_modal(styles: dict, theme: dict) -> html.Div:
    """Return the feedback modal plus the stores its callbacks need.

    Wrapped in a plain Div (rather than returned bare) so the stores are
    siblings of the modal and stay mounted whether or not it is open — the
    same arrangement the execution-explainer modal uses in backtest_panel.py.
    """
    body = dbc.ModalBody(
        [
            html.P(
                [
                    'This project is open, and the part I cannot get on my own '
                    'is what it feels like to use. Bug, idea, or a blunt '
                    'first impression — all of it is welcome, and it comes '
                    'straight to me.',
                ],
                className='sfa-feedback-intro',
            ),

            _step_label('1', 'What kind of note is this?'),
            dbc.Accordion(
                _accordion_items(),
                id='feedback-type-accordion',
                active_item=DEFAULT_TYPE_ID,
                always_open=False,
                flush=True,
                className='compact-accordion sfa-feedback-accordion',
            ),

            _step_label('2', 'In your own words'),
            dcc.Textarea(
                id='feedback-message',
                value='',
                placeholder=get_type(DEFAULT_TYPE_ID)['placeholder'],
                maxLength=MAX_MESSAGE_CHARS,
                spellCheck=True,
                className='sfa-feedback-textarea',
                title='Your feedback',
            ),

            _step_label('3', 'So I can reply', optional=True),
            html.Div(
                [
                    # dcc.Input takes no aria-* or title props, so the
                    # accessible name comes from a real <label>, hidden with
                    # Bootstrap's own utility class.
                    html.Label(
                        'Your email address (optional)',
                        htmlFor='feedback-reply-to',
                        className='visually-hidden',
                    ),
                    dcc.Input(
                        id='feedback-reply-to',
                        type='email',
                        value='',
                        placeholder='you@example.com',
                        autoComplete='email',
                        className='bbg-input sfa-feedback-email',
                    ),
                    html.Span(
                        'Leave blank to stay anonymous.',
                        className='sfa-feedback-hint',
                    ),
                ],
                className='sfa-feedback-email-row',
            ),

            dcc.Checklist(
                id='feedback-include-context',
                options=[{
                    'label': 'Attach what I was looking at (helps with bugs)',
                    'value': 'yes',
                }],
                value=['yes'],
                className='sfa-feedback-check',
            ),
            html.Details(
                [
                    html.Summary(
                        'Show exactly what that attaches',
                        className='sfa-feedback-summary',
                    ),
                    html.Div(id='feedback-context-preview',
                             className='sfa-feedback-context'),
                ],
                className='sfa-feedback-details',
            ),

            html.Div(id='feedback-status', className='sfa-feedback-status'),

            # Safety net for the mailto path: if the browser has no mail
            # handler the hand-off fails silently, so the composed message is
            # always available to copy out by hand.
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                'Mail app did not open?',
                                className='sfa-feedback-fallback-title',
                            ),
                            html.Button(
                                'Copy message',
                                id='feedback-copy-btn',
                                n_clicks=0,
                                type='button',
                                className='bbg-button-ghost sfa-feedback-copy',
                            ),
                        ],
                        className='sfa-feedback-fallback-head',
                    ),
                    html.Div(
                        [
                            'Copy the text below and email it to ',
                            html.A(
                                FEEDBACK_EMAIL,
                                href=f'mailto:{FEEDBACK_EMAIL}',
                                className='sfa-feedback-address',
                            ),
                            '.',
                        ],
                        className='sfa-feedback-hint',
                    ),
                    dcc.Textarea(
                        id='feedback-transcript',
                        value='',
                        readOnly=True,
                        className='sfa-feedback-transcript',
                        title='Your message, ready to copy',
                    ),
                ],
                id='feedback-fallback',
                style={'display': 'none'},
            ),
        ],
        className='sfa-feedback-body',
    )

    footer = dbc.ModalFooter(
        [
            html.Span(
                'Nothing is collected beyond what you see here.',
                className='sfa-feedback-privacy',
            ),
            html.Div(
                [
                    html.Button(
                        'Close',
                        id='feedback-close-btn',
                        n_clicks=0,
                        type='button',
                        className='bbg-button-ghost sfa-feedback-cancel',
                    ),
                    html.Button(
                        'Send',
                        id='feedback-send-btn',
                        n_clicks=0,
                        type='button',
                        className='sfa-feedback-send',
                    ),
                ],
                className='sfa-feedback-actions',
            ),
        ],
        className='sfa-feedback-footer',
    )

    return html.Div([
        # Written by the submit callback, read by a clientside handler that
        # hands the URL to the browser's mail handler.
        dcc.Store(id='feedback-mailto', data=None),
        html.Div(id='feedback-mailto-sync', style={'display': 'none'}),
        html.Div(id='feedback-scroll-sync', style={'display': 'none'}),
        # Survives collapsing every accordion item, which would otherwise
        # reset the chosen category to None mid-compose.
        dcc.Store(id='feedback-type-store', data=DEFAULT_TYPE_ID),

        dbc.Modal(
            [
                dbc.ModalHeader(
                    dbc.ModalTitle('Tell me what you think'),
                    close_button=True,
                    className='sfa-feedback-header',
                ),
                body,
                footer,
            ],
            id='feedback-modal',
            is_open=False,
            centered=True,
            size='lg',
            backdrop=True,
            keyboard=True,
            scrollable=True,
            className='sfa-feedback-modal',
            content_class_name='sfa-feedback-content',
        ),
    ])


__all__ = ['_create_feedback_modal']
