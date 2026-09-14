"""Sending the sign-in email.

``SmtpMailer`` speaks plain SMTP through the standard library, so any provider
works (Brevo, Resend, Postmark, a domain mailbox) and nothing new is installed.
The demo process is sealed off from the network (``demo.sealing``); the server
opens exactly one door in that seal, to ``DEMO_SMTP_HOST:DEMO_SMTP_PORT``.

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
from email.utils import formatdate, make_msgid, parseaddr

from demo.access.settings import AccessSettings

logger = logging.getLogger(__name__)


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

    def send(self, mail: Mail) -> None:
        self.outbox.append(mail)
        logger.warning("DEMO_MAIL_BACKEND=console, not sending. To %s: %s\n%s", mail.to, mail.subject, mail.text)


class SmtpMailer:
    def __init__(self, settings: AccessSettings) -> None:
        self.settings = settings

    def send(self, mail: Mail) -> None:
        s = self.settings
        message = EmailMessage()
        message["From"] = s.mail_from
        message["To"] = mail.to
        message["Subject"] = mail.subject
        message["Date"] = formatdate(localtime=False)
        domain = parseaddr(s.mail_from)[1].rpartition("@")[2] or None
        message["Message-ID"] = make_msgid(domain=domain)
        message["Auto-Submitted"] = "auto-generated"
        message.set_content(mail.text)
        message.add_alternative(mail.html, subtype="html")
        try:
            if s.smtp_security == "ssl":
                client = smtplib.SMTP_SSL(s.smtp_host, s.smtp_port, timeout=15, context=ssl.create_default_context())
            else:
                client = smtplib.SMTP(s.smtp_host, s.smtp_port, timeout=15)
            with client:
                if s.smtp_security == "starttls":
                    client.starttls(context=ssl.create_default_context())
                if s.smtp_user:
                    client.login(s.smtp_user, s.smtp_password)
                client.send_message(message)
        except (OSError, smtplib.SMTPException) as exc:
            logger.error("sign-in email to %s failed: %s", mail.to.rpartition("@")[2], exc)
            raise MailError(str(exc)) from exc


def build_mailer(settings: AccessSettings):
    return ConsoleMailer() if settings.mail_backend == "console" else SmtpMailer(settings)
