"""Sending the sign-in email.

``SmtpMailer`` speaks plain SMTP through the standard library, so nothing new is
installed. In production it signs in to the Neo mailbox that hosts
noeinsolutions.com mail -- the same account Capsar sends from -- on port 587
with STARTTLS. Not 465: the Hetzner server blocks outbound 465 (and 25), so a
connection there simply times out. Neo already signs and authorises that
domain's mail (SPF and DKIM are published), which is why codes from it reach
inboxes rather than spam.

``check`` signs in, announces the From address and cancels, so nothing is
sent. The server runs it once at start and logs the result, because a mail
server the demo cannot reach -- or a sender Neo will not accept -- is otherwise
invisible until a visitor asks for a code.
The demo process is sealed off from the network (``demo.sealing``); the server
opens exactly one door in that seal, to the SMTP host and port.

The login is the owner's mailbox; the From address is
``support@noeinsolutions.com`` (``EMAIL_FROM``), which Neo accepts only once
it is an alias of that mailbox -- otherwise it answers "553 Sender address
rejected: not owned by user". A display name goes in front ("SearchForAlpha
Lab demo <support@…>").

``ConsoleMailer`` logs the message instead and keeps it in ``outbox``: for a
local run without a mail account, and for the tests.

Sending happens inside the request, on purpose. It costs a second or two, but
the visitor is then told the truth -- "sent" or "could not send" -- instead of
being sent to wait for an email that is never coming.
"""

from __future__ import annotations

import logging
import smtplib
import ssl
from dataclasses import dataclass
from email.message import EmailMessage
from email.utils import formataddr, formatdate, make_msgid, parseaddr

from demo.access.settings import AccessSettings

logger = logging.getLogger(__name__)

SENDER_NAME = "SearchForAlpha Lab demo"


def sender(mail_from: str) -> str:
    """``mail_from`` with a display name, unless it already carries one."""
    name, address = parseaddr(mail_from)
    return mail_from if name or not address else formataddr((SENDER_NAME, address))


class MailError(Exception):
    """The sign-in email could not be handed to the mail server."""


@dataclass(frozen=True)
class Mail:
    to: str
    subject: str
    text: str
    html: str


class ConsoleMailer:
    def __init__(self) -> None:
        self.outbox: list[Mail] = []

    def check(self) -> None:
        return None

    def send(self, mail: Mail) -> None:
        self.outbox.append(mail)
        logger.warning("DEMO_MAIL_BACKEND=console, not sending. To %s: %s\n%s", mail.to, mail.subject, mail.text)


class SmtpMailer:
    def __init__(self, settings: AccessSettings) -> None:
        self.settings = settings

    def _session(self):
        """Connected, encrypted and signed in; use as a context manager."""
        s = self.settings
        mode = s.tls_mode
        if mode == "ssl":
            client = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=ssl.create_default_context())
        else:
            client = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
        try:
            if mode == "starttls":
                client.starttls(context=ssl.create_default_context())
            if s.smtp_user:
                client.login(s.smtp_user, s.smtp_password)
        except BaseException:
            client.close()
            raise
        return client

    def check(self) -> None:
        """Sign in, offer the From address, cancel. Sends nothing. Raises ``MailError`` on any refusal."""
        address = parseaddr(self.settings.mail_from)[1] or self.settings.smtp_user
        try:
            with self._session() as client:
                code, reply = client.mail(address)
                client.rset()
        except (OSError, smtplib.SMTPException) as exc:
            raise MailError(f"{type(exc).__name__}: {exc}") from exc
        if code != 250:
            raise MailError(f"sender {address} refused: {code} {reply.decode(errors='replace')}")

    def send(self, mail: Mail) -> None:
        s = self.settings
        message = EmailMessage()
        message["From"] = sender(s.mail_from)
        message["To"] = mail.to
        message["Subject"] = mail.subject
        message["Date"] = formatdate(localtime=False)
        domain = parseaddr(s.mail_from)[1].rpartition("@")[2] or None
        message["Message-ID"] = make_msgid(domain=domain)
        message["Auto-Submitted"] = "auto-generated"
        message.set_content(mail.text)
        message.add_alternative(mail.html, subtype="html")
        try:
            with self._session() as client:
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            logger.error("sign-in email to %s failed: %s", mail.to.rpartition("@")[2], exc)
            raise MailError(str(exc)) from exc


def build_mailer(settings: AccessSettings):
    return ConsoleMailer() if settings.mail_backend == "console" else SmtpMailer(settings)
