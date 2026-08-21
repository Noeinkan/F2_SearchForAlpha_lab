"""
Visitor feedback — formatting, delivery, and the form that feeds them.

The thing these guard: the feedback button is the one control whose failure is
invisible. A backtest that breaks is obvious; a note that never arrives looks
exactly like nobody having anything to say. So the tests here are mostly about
the note surviving the hand-off — that the mailto URL is well-formed, that a
relay failure still leaves the visitor something to copy, and that the form
never reports success when nothing left the building.
"""

from __future__ import annotations

from urllib.parse import parse_qs, unquote, urlparse

import pytest

from lib.dash import feedback as fb
from lib.dash.dash_config import FEEDBACK_EMAIL, get_theme
from lib.dash.layout.shell import create_dashboard_layout


# --- Catalogue ---------------------------------------------------------------

def test_every_type_carries_the_fields_the_form_and_the_email_need():
    for entry in fb.FEEDBACK_TYPES:
        for key in ('id', 'icon', 'label', 'subject', 'blurb', 'placeholder'):
            assert entry.get(key), f"{entry.get('id', '?')} is missing {key}"


def test_type_ids_are_unique():
    ids = [entry['id'] for entry in fb.FEEDBACK_TYPES]
    assert len(ids) == len(set(ids))


def test_unknown_type_falls_back_rather_than_raising():
    """An id can only reach here from a stale browser store; never 500 on it."""
    assert fb.get_type('no-such-type') == fb.FEEDBACK_TYPES[0]
    assert fb.get_type(None) == fb.FEEDBACK_TYPES[0]


# --- Validation --------------------------------------------------------------

@pytest.mark.parametrize("message", ['', '   ', '\n\n'])
def test_empty_message_is_rejected(message):
    assert fb.validate_feedback(message=message, reply_to=None)


def test_too_short_is_rejected():
    assert fb.validate_feedback(message='broken', reply_to=None)


def test_over_the_cap_is_rejected():
    huge = 'x' * (fb.MAX_MESSAGE_CHARS + 1)
    assert fb.validate_feedback(message=huge, reply_to=None)


@pytest.mark.parametrize("address", ['not-an-email', '@example.com', 'me@'])
def test_malformed_reply_address_is_rejected(address):
    assert fb.validate_feedback(message='The RSI pane is blank.', reply_to=address)


@pytest.mark.parametrize("address", ['', None, '   ', 'someone@example.com'])
def test_blank_or_valid_reply_address_passes(address):
    assert fb.validate_feedback(
        message='The RSI pane is blank on TSLA.', reply_to=address
    ) is None


# --- Body + subject ----------------------------------------------------------

def test_subject_stays_ascii_so_no_mail_client_mangles_it():
    for entry in fb.FEEDBACK_TYPES:
        fb.build_subject(entry['id']).encode('ascii')


def test_body_carries_the_message_verbatim():
    body = fb.build_body(type_id='bug', message='  The chart is blank.  ')
    assert 'The chart is blank.' in body


def test_body_names_the_type_so_the_inbox_is_sortable():
    body = fb.build_body(type_id='idea', message='Add a Sharpe column please.')
    assert fb.get_type('idea')['label'] in body


def test_body_says_anonymous_when_no_address_is_given():
    body = fb.build_body(type_id='bug', message='Something broke badly.')
    assert 'anonymous' in body


def test_body_includes_diagnostics_when_attached():
    body = fb.build_body(
        type_id='bug',
        message='Something broke badly.',
        diagnostics={'Symbol': 'TSLA', 'Theme': 'bloomberg'},
    )
    assert 'TSLA' in body and 'bloomberg' in body


def test_body_omits_the_context_section_when_the_box_is_unticked():
    body = fb.build_body(type_id='bug', message='Something broke badly.')
    assert '--- Context ---' not in body


def test_diagnostics_carry_no_identifying_detail():
    """The modal promises 'nothing beyond what you see here' — keep it true."""
    import getpass
    import socket

    values = ' '.join(fb.collect_diagnostics(ticker='TSLA').values())
    for secret in (getpass.getuser(), socket.gethostname()):
        if secret:
            assert secret.lower() not in values.lower()


# --- mailto ------------------------------------------------------------------

def test_mailto_is_addressed_to_the_configured_inbox():
    url = fb.build_mailto(subject='s', body='b')
    assert urlparse(url).scheme == 'mailto'
    assert url.startswith(f'mailto:{FEEDBACK_EMAIL}?')


def test_mailto_round_trips_newlines_and_punctuation():
    """A three-line bug template must survive URL encoding intact."""
    body = 'What I did:\nOpened TSLA & pressed "run".\nIt broke — 100% of the time.'
    url = fb.build_mailto(subject='[SearchForAlpha] Bug report', body=body)
    params = parse_qs(urlparse(url).query, keep_blank_values=True)
    assert params['body'][0] == body
    assert params['subject'][0] == '[SearchForAlpha] Bug report'


def test_mailto_encodes_the_ampersand_rather_than_splitting_the_body():
    url = fb.build_mailto(subject='s', body='a & b')
    assert '&body=' in url
    assert unquote(url.split('&body=')[1]) == 'a & b'


# --- Delivery ----------------------------------------------------------------

def test_no_relay_configured_falls_back_to_composing_a_mail(monkeypatch):
    monkeypatch.setattr(fb, 'FEEDBACK_ENDPOINT', '')
    result = fb.submit_feedback(type_id='bug', message='The chart will not draw.')
    assert result.status == 'compose'
    assert result.ok
    assert result.mailto and result.mailto.startswith('mailto:')
    assert 'The chart will not draw.' in result.transcript


def test_validation_failure_sends_nothing_and_offers_nothing_to_copy():
    result = fb.submit_feedback(type_id='bug', message='no')
    assert result.status == 'error'
    assert not result.ok
    assert result.mailto is None
    assert result.transcript == ''


def test_a_working_relay_reports_sent_and_never_opens_a_mail_client(monkeypatch):
    monkeypatch.setattr(fb, 'FEEDBACK_ENDPOINT', 'https://relay.example/post')
    monkeypatch.setattr(fb, '_post_to_relay', lambda payload: (True, ''))
    result = fb.submit_feedback(type_id='idea', message='Add a Sharpe column.')
    assert result.status == 'sent'
    assert result.mailto is None


def test_a_dead_relay_does_not_lose_the_note(monkeypatch):
    """The regression that would matter most: a note vanishing on a bad POST."""
    monkeypatch.setattr(fb, 'FEEDBACK_ENDPOINT', 'https://relay.example/post')
    monkeypatch.setattr(fb, '_post_to_relay', lambda payload: (False, 'HTTP 502'))
    result = fb.submit_feedback(type_id='bug', message='The chart will not draw.')
    assert result.status == 'compose'
    assert result.mailto and result.mailto.startswith('mailto:')
    assert 'The chart will not draw.' in result.transcript
    assert '502' in result.message


def test_relay_transport_errors_are_swallowed_not_raised(monkeypatch):
    """`requests` failing must not surface a stack trace to a bug reporter."""
    monkeypatch.setattr(fb, 'FEEDBACK_ENDPOINT', 'https://relay.example/post')

    class _Boom:
        def post(self, *args, **kwargs):
            raise RuntimeError('no network')

    monkeypatch.setitem(__import__('sys').modules, 'requests', _Boom())
    ok, detail = fb._post_to_relay({'message': 'hi'})
    assert ok is False
    assert detail


def test_relay_payload_carries_the_access_key_only_when_one_is_set(monkeypatch):
    monkeypatch.setattr(fb, 'FEEDBACK_ACCESS_KEY', '')
    assert 'access_key' not in fb._relay_payload(
        subject='s', body='b', type_id='bug', reply_to=''
    )
    monkeypatch.setattr(fb, 'FEEDBACK_ACCESS_KEY', 'abc-123')
    assert fb._relay_payload(
        subject='s', body='b', type_id='bug', reply_to=''
    )['access_key'] == 'abc-123'


def test_relay_reply_to_falls_back_to_a_valid_address(monkeypatch):
    """Relays reject a malformed Reply-To, which would drop an anonymous note."""
    monkeypatch.setattr(fb, 'FEEDBACK_ACCESS_KEY', '')
    payload = fb._relay_payload(subject='s', body='b', type_id='bug', reply_to='')
    assert '@' in payload['email']


# --- The form ----------------------------------------------------------------

def _walk(component):
    yield component
    children = getattr(component, 'children', None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, 'children') or hasattr(child, 'id'):
            yield from _walk(child)


@pytest.fixture(scope='module')
def layout():
    return create_dashboard_layout(get_theme())


@pytest.fixture(scope='module')
def ids(layout):
    return {
        comp.id for comp in _walk(layout)
        if isinstance(getattr(comp, 'id', None), str)
    }


@pytest.mark.parametrize("component_id", [
    'feedback-open-btn',
    'feedback-modal',
    'feedback-type-accordion',
    'feedback-type-store',
    'feedback-message',
    'feedback-reply-to',
    'feedback-include-context',
    'feedback-context-preview',
    'feedback-status',
    'feedback-fallback',
    'feedback-transcript',
    'feedback-copy-btn',
    'feedback-send-btn',
    'feedback-close-btn',
    'feedback-mailto',
    'feedback-mailto-sync',
])
def test_the_form_is_mounted(ids, component_id):
    assert component_id in ids


def test_accordion_items_match_the_catalogue(layout):
    """A drifting item_id would silently mislabel every note of that type."""
    accordion = next(
        comp for comp in _walk(layout)
        if getattr(comp, 'id', None) == 'feedback-type-accordion'
    )
    item_ids = [item.item_id for item in accordion.children]
    assert item_ids == [entry['id'] for entry in fb.FEEDBACK_TYPES]


def test_the_open_item_is_a_real_type(layout):
    accordion = next(
        comp for comp in _walk(layout)
        if getattr(comp, 'id', None) == 'feedback-type-accordion'
    )
    assert accordion.active_item == fb.DEFAULT_TYPE_ID


def test_the_message_box_caps_at_the_validated_length(layout):
    """maxLength and the validator must agree, or typing hits a silent wall."""
    box = next(
        comp for comp in _walk(layout)
        if getattr(comp, 'id', None) == 'feedback-message'
    )
    assert box.maxLength == fb.MAX_MESSAGE_CHARS


def test_the_copy_fallback_starts_hidden(layout):
    """It is a rescue path — showing it up front reads as an error state."""
    panel = next(
        comp for comp in _walk(layout)
        if getattr(comp, 'id', None) == 'feedback-fallback'
    )
    assert panel.style.get('display') == 'none'


def test_the_palette_can_reach_the_form():
    """The header button is easy to miss; Ctrl+K is the other way in."""
    from lib.dash.callbacks import misc_ui
    from lib.dash.layout.command_palette import COMMANDS

    assert any(cmd['id'] == 'send-feedback' for cmd in COMMANDS)
    source = __import__('inspect').getsource(misc_ui)
    assert "'send-feedback'" in source
    assert 'feedback-open-btn' in source
