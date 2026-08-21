"""
Visitor feedback — payload assembly and delivery.

The header ships a FEEDBACK button (layout/feedback.py) that opens a modal:
pick what kind of note it is, write it, send. This module owns everything that
happens after Send — validating the note, formatting it as an email, and
getting it to the maintainer.

Delivery has two paths, tried in order:

1. **HTTP relay.** When ``FEEDBACK_ENDPOINT`` is configured the note is POSTed
   as JSON and the visitor never leaves the page. Any relay that accepts a JSON
   form post works — Web3Forms, Formspree, or something self-hosted;
   ``FEEDBACK_ACCESS_KEY`` is included in the body when set because that is what
   Web3Forms expects. This is the path to configure for a public repo: the
   destination address then lives in the relay's dashboard rather than in the
   published source.

2. **mailto fallback.** With nothing configured — the state of a fresh clone —
   the browser is handed a pre-filled ``mailto:`` URL. No account, no key, no
   server, but it needs the visitor to have a mail client and to press Send.

Neither hand-off is guaranteed, so every submission also returns a plain-text
``transcript`` that the modal shows back to the visitor. A feedback button that
silently eats feedback is worse than no button, and this is the cheap insurance.

Everything here is pure except :func:`submit_feedback`, which is the only
function that touches the network.
"""

from __future__ import annotations

import platform
from dataclasses import dataclass, field
from datetime import datetime
from urllib.parse import quote

from lib.dash.dash_config import (
    FEEDBACK_ACCESS_KEY,
    FEEDBACK_EMAIL,
    FEEDBACK_ENDPOINT,
    UI_STORAGE_VERSION,
)


# The modal's accordion is built straight from this list, and ``subject`` is
# what lands in the maintainer's inbox — so the order here is the order of
# triage: broken first, then wishes, then impressions.
#
# ``placeholder`` is deliberately a template rather than a hint. People write
# far more useful bug reports when the box already shows the shape of one.
FEEDBACK_TYPES: list[dict[str, str]] = [
    {
        'id': 'bug',
        'icon': '🐞',
        'label': 'Something is broken',
        'subject': 'Bug report',
        'blurb': (
            'A chart that will not draw, a control that does nothing, an error '
            'on screen. The three lines below are all I need.'
        ),
        'placeholder': (
            'What I did:\n'
            'What I expected:\n'
            'What happened instead:'
        ),
    },
    {
        'id': 'data',
        'icon': '📉',
        'label': 'The numbers look wrong',
        'subject': 'Data quality',
        'blurb': (
            'A price, a fundamental, or a backtest result that disagrees with '
            'your own source. Say which symbol, and what you expected.'
        ),
        'placeholder': (
            'Symbol:\n'
            'Field and the value shown:\n'
            'Value I expected, and where mine comes from:'
        ),
    },
    {
        'id': 'idea',
        'icon': '💡',
        'label': 'I have an idea',
        'subject': 'Feature idea',
        'blurb': (
            'An indicator, a metric, a workflow — anything you wish the '
            'terminal did.'
        ),
        'placeholder': (
            'What would you like to be able to do, and what decision would it '
            'help you make?'
        ),
    },
    {
        'id': 'usability',
        'icon': '🧭',
        'label': 'Something confused me',
        'subject': 'Usability',
        'blurb': (
            'A label that reads wrong, a control you could not find, a screen '
            'that fights you. Confusion is a bug I cannot see from here.'
        ),
        'placeholder': 'What were you trying to do, and where did it lose you?',
    },
    {
        'id': 'impression',
        'icon': '💬',
        'label': 'General impressions',
        'subject': 'General feedback',
        'blurb': (
            'What works, what does not, whether you would keep using it. '
            'Blunt is useful — polite is not.'
        ),
        'placeholder': 'Anything you want to say about the project.',
    },
]

_TYPES_BY_ID = {entry['id']: entry for entry in FEEDBACK_TYPES}

DEFAULT_TYPE_ID = FEEDBACK_TYPES[0]['id']

# Short enough that a careless click cannot fire off an empty note, long enough
# that "the RSI pane is blank" still gets through.
MIN_MESSAGE_CHARS = 12
MAX_MESSAGE_CHARS = 4000


def get_type(type_id: str | None) -> dict[str, str]:
    """Return the feedback-type entry for ``type_id``, falling back to the first."""
    return _TYPES_BY_ID.get(type_id or '', FEEDBACK_TYPES[0])


@dataclass
class FeedbackResult:
    """Outcome of one submission.

    ``status`` is one of:
      - ``sent``    — the relay accepted it; nothing more for the visitor to do.
      - ``compose`` — we produced a ``mailto`` URL for the browser to open.
      - ``error``   — validation failed; nothing sent, nothing to copy.
    """

    status: str
    message: str
    mailto: str | None = None
    transcript: str = ''
    subject: str = ''
    diagnostics: dict[str, str] = field(default_factory=dict)

    @property
    def ok(self) -> bool:
        return self.status in ('sent', 'compose')


def collect_diagnostics(
    *,
    ticker: str | None = None,
    theme: str | None = None,
    page: str | None = None,
) -> dict[str, str]:
    """Environment facts worth having in a bug report.

    Deliberately boring: no machine name, no username, no file paths. The modal
    lists these verbatim so the visitor can see exactly what "attach context"
    means before they leave the box ticked.
    """
    try:
        import dash

        dash_version = getattr(dash, '__version__', 'unknown')
    except Exception:  # pragma: no cover - dash is always importable in-app
        dash_version = 'unknown'

    return {
        'Symbol': ticker or '—',
        'Workspace': page or '—',
        'Theme': theme or '—',
        'UI storage version': UI_STORAGE_VERSION,
        'Python': platform.python_version(),
        'Dash': str(dash_version),
        'OS': f'{platform.system()} {platform.release()}'.strip(),
    }


def validate_feedback(*, message: str | None, reply_to: str | None) -> str | None:
    """Return a human-readable problem with the form, or ``None`` if it is fine."""
    text = (message or '').strip()
    if not text:
        return 'Write a line or two first — the box is empty.'
    if len(text) < MIN_MESSAGE_CHARS:
        return 'A few more words, please — I want to be able to act on this.'
    if len(text) > MAX_MESSAGE_CHARS:
        return (
            f'That is {len(text):,} characters and the limit is '
            f'{MAX_MESSAGE_CHARS:,}. Trim it, or send it as a plain email.'
        )
    address = (reply_to or '').strip()
    if address and ('@' not in address or address.startswith('@') or address.endswith('@')):
        return (
            'That reply address does not look like an email. '
            'Leave it blank to stay anonymous.'
        )
    return None


def build_subject(type_id: str | None) -> str:
    """Inbox subject line. ASCII only, so no mail client mangles it."""
    return f"[SearchForAlpha] {get_type(type_id)['subject']}"


def build_body(
    *,
    type_id: str | None,
    message: str,
    reply_to: str | None = None,
    diagnostics: dict[str, str] | None = None,
) -> str:
    """Format the note as the plain-text email body.

    The sections are fixed and in a fixed order so a full inbox stays skimmable.
    """
    entry = get_type(type_id)
    address = (reply_to or '').strip()

    lines = [
        f"Type:  {entry['label']}",
        f"Sent:  {datetime.now().astimezone().strftime('%Y-%m-%d %H:%M %Z')}",
        f"Reply: {address or 'not given (anonymous)'}",
        '',
        '--- Message ---',
        (message or '').strip(),
    ]

    if diagnostics:
        lines += ['', '--- Context ---']
        width = max(len(key) for key in diagnostics)
        lines += [f'{key.ljust(width)}  {value}' for key, value in diagnostics.items()]

    lines += ['', '--- Sent from the SearchForAlpha Lab feedback button ---']
    return '\n'.join(lines)


def build_mailto(*, subject: str, body: str, to: str = '') -> str:
    """Build a ``mailto:`` URL the browser can hand to the visitor's mail client."""
    address = to or FEEDBACK_EMAIL
    return (
        f'mailto:{address}'
        f'?subject={quote(subject, safe="")}'
        f'&body={quote(body, safe="")}'
    )


def _relay_payload(*, subject: str, body: str, type_id: str, reply_to: str) -> dict:
    """Superset payload that satisfies Web3Forms and Formspree alike.

    Both ignore keys they do not recognise, so one dict covers either relay and
    there is no per-provider branch to keep in sync.
    """
    payload = {
        'subject': subject,
        '_subject': subject,          # Formspree's spelling
        'from_name': 'SearchForAlpha Lab',
        # Relays use this as the Reply-To header and reject a malformed one, so
        # an anonymous note falls back to the maintainer's own address.
        'email': (reply_to or '').strip() or FEEDBACK_EMAIL,
        'feedback_type': type_id,
        'message': body,
    }
    if FEEDBACK_ACCESS_KEY:
        payload['access_key'] = FEEDBACK_ACCESS_KEY
    return payload


def _post_to_relay(payload: dict) -> tuple[bool, str]:
    """POST to ``FEEDBACK_ENDPOINT``. Returns ``(ok, detail)``.

    Never raises: a feedback button that throws a stack trace at someone
    reporting a bug is a poor first impression.
    """
    try:
        import requests

        response = requests.post(
            FEEDBACK_ENDPOINT,
            json=payload,
            headers={'Accept': 'application/json'},
            timeout=10,
        )
    except Exception as exc:
        return False, type(exc).__name__
    if 200 <= response.status_code < 300:
        return True, ''
    return False, f'HTTP {response.status_code}'


def submit_feedback(
    *,
    type_id: str | None,
    message: str,
    reply_to: str | None = None,
    diagnostics: dict[str, str] | None = None,
) -> FeedbackResult:
    """Validate, format, and deliver one note. The only networked call here."""
    problem = validate_feedback(message=message, reply_to=reply_to)
    if problem:
        return FeedbackResult(status='error', message=problem)

    entry = get_type(type_id)
    subject = build_subject(type_id)
    body = build_body(
        type_id=type_id,
        message=message,
        reply_to=reply_to,
        diagnostics=diagnostics,
    )

    if FEEDBACK_ENDPOINT:
        ok, detail = _post_to_relay(
            _relay_payload(
                subject=subject,
                body=body,
                type_id=entry['id'],
                reply_to=reply_to or '',
            )
        )
        if ok:
            return FeedbackResult(
                status='sent',
                message='Sent — thank you. That genuinely helps.',
                transcript=body,
                subject=subject,
                diagnostics=diagnostics or {},
            )
        # Relay unreachable or refusing. Do not lose the note: fall through to
        # the mail client, and say why.
        return FeedbackResult(
            status='compose',
            message=(
                f'The send relay did not answer ({detail}), so I opened your '
                'mail app with the message ready instead.'
            ),
            mailto=build_mailto(subject=subject, body=body),
            transcript=body,
            subject=subject,
            diagnostics=diagnostics or {},
        )

    return FeedbackResult(
        status='compose',
        message=(
            'Your mail app should be opening with the message ready — press '
            'send there and it reaches me.'
        ),
        mailto=build_mailto(subject=subject, body=body),
        transcript=body,
        subject=subject,
        diagnostics=diagnostics or {},
    )


__all__ = [
    'DEFAULT_TYPE_ID',
    'FEEDBACK_TYPES',
    'MAX_MESSAGE_CHARS',
    'MIN_MESSAGE_CHARS',
    'FeedbackResult',
    'build_body',
    'build_mailto',
    'build_subject',
    'collect_diagnostics',
    'get_type',
    'submit_feedback',
    'validate_feedback',
]
