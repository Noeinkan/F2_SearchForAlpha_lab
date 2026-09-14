"""Access-gate settings. Every one is an environment variable with a default.

Numbers and switches live in ``.deploy/compose.yml``. The secrets live only in
``/opt/sites/alpha/.env`` on the server: the admin token, and the mail account.

The mail account uses the same variable names as Capsar (W3_capsar_io,
``server/services/emailService.js``), so one block of credentials serves both:
``NEO_SMTP_HOST`` / ``_PORT`` / ``_USER`` / ``_PASS`` and ``EMAIL_FROM``, with
the generic ``SMTP_*`` names as a fallback. Neo is the mail host of
noeinsolutions.com: ``smtp0001.neo.space``, port 465, implicit TLS, signed in
as the mailbox, sending as that mailbox.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field

_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}

MIN_ADMIN_TOKEN_LENGTH = 24


def _str(name: str, default: str) -> str:
    return os.environ.get(name, default).strip()


def _int(name: str, default: int, minimum: int = 1) -> int:
    raw = os.environ.get(name, "").strip()
    if not raw:
        return default
    try:
        return max(minimum, int(raw))
    except ValueError:
        return default


def _bool(name: str, default: bool) -> bool:
    raw = os.environ.get(name, "").strip().lower()
    if raw in _TRUE:
        return True
    if raw in _FALSE:
        return False
    return default


def _first(*names: str) -> str:
    """The first of ``names`` that is set and not blank."""
    for name in names:
        value = os.environ.get(name, "").strip()
        if value:
            return value
    return ""


def _port(raw: str, default: int) -> int:
    try:
        return int(raw) if raw else default
    except ValueError:
        return default


def _default_contact() -> str:
    return _str("SFA_FEEDBACK_EMAIL", "andrea.aita@noeinsolutions.com")


@dataclass(frozen=True)
class AccessSettings:
    enabled: bool = True                   # DEMO_ACCESS_GATE: false serves the demo to anyone, untracked (local runs only)
    db_path: str = "state/demo-access/access.sqlite3"  # DEMO_ACCESS_DB: visitors, codes, usage events
    # The trial
    trial_days: int = 7                    # DEMO_TRIAL_DAYS: access lasts this long from the first sign-in
    jobs_per_email_per_day: int = 25       # DEMO_JOBS_PER_EMAIL_PER_DAY: optimiser runs per person per UTC day
    retention_days: int = 365              # DEMO_RETENTION_DAYS: a visitor unseen this long is deleted with their usage
    # Sign-in codes
    code_minutes: int = 15                 # DEMO_CODE_MINUTES: a code or link stops working after this
    code_attempts: int = 5                 # DEMO_CODE_ATTEMPTS: wrong codes before that code is dead
    codes_per_email_per_hour: int = 3      # DEMO_CODES_PER_EMAIL_PER_HOUR: sign-in emails to one address
    codes_per_hour: int = 60               # DEMO_CODES_PER_HOUR: sign-in emails in total, per hour
    # Neo allows a mailbox about 1,000 sent emails a day, and that budget is
    # shared with the owner's own mail and with Capsar's; a bot must not spend it.
    codes_per_day: int = 200               # DEMO_CODES_PER_DAY: sign-in emails in total, per day
    signups_per_ip_per_day: int = 5        # DEMO_SIGNUPS_PER_IP_PER_DAY: new addresses from one connection
    blocked_domains: frozenset[str] = field(default_factory=frozenset)  # DEMO_BLOCKED_EMAIL_DOMAINS: comma list, added to emails.DISPOSABLE_DOMAINS
    # Mail (secret file). Names shared with Capsar; SMTP_* is the fallback for each.
    mail_backend: str = "smtp"             # DEMO_MAIL_BACKEND: smtp | console (console logs the code; local runs only)
    smtp_host: str = ""                    # NEO_SMTP_HOST, else SMTP_HOST: smtp0001.neo.space
    smtp_port: int = 587                   # NEO_SMTP_PORT, else SMTP_PORT: 465 for Neo
    smtp_security: str = "auto"            # DEMO_SMTP_SECURITY: auto (465 -> ssl, else starttls) | ssl | starttls | none
    smtp_user: str = ""                    # NEO_SMTP_USER, else SMTP_USER: the mailbox address
    smtp_password: str = ""                # NEO_SMTP_PASS, else SMTP_PASS
    mail_from: str = ""                    # EMAIL_FROM, else SMTP_FROM, else the mailbox: Neo sends only as the mailbox or its aliases
    public_url: str = ""                   # DEMO_PUBLIC_URL: base of the link in the email; empty uses the request's host
    contact_email: str = field(default_factory=_default_contact)  # DEMO_CONTACT_EMAIL: shown on the privacy note and the trial-ended page
    # Admin
    admin_token: str = ""                  # DEMO_ADMIN_TOKEN (secret file): unlocks /admin; unset and /admin 404s

    @classmethod
    def from_env(cls) -> "AccessSettings":
        base = cls()
        extra = {d.strip().lower() for d in _str("DEMO_BLOCKED_EMAIL_DOMAINS", "").split(",") if d.strip()}
        return cls(
            enabled=_bool("DEMO_ACCESS_GATE", base.enabled),
            db_path=_str("DEMO_ACCESS_DB", base.db_path),
            trial_days=_int("DEMO_TRIAL_DAYS", base.trial_days),
            jobs_per_email_per_day=_int("DEMO_JOBS_PER_EMAIL_PER_DAY", base.jobs_per_email_per_day),
            retention_days=_int("DEMO_RETENTION_DAYS", base.retention_days),
            code_minutes=_int("DEMO_CODE_MINUTES", base.code_minutes),
            code_attempts=_int("DEMO_CODE_ATTEMPTS", base.code_attempts),
            codes_per_email_per_hour=_int("DEMO_CODES_PER_EMAIL_PER_HOUR", base.codes_per_email_per_hour),
            codes_per_hour=_int("DEMO_CODES_PER_HOUR", base.codes_per_hour),
            codes_per_day=_int("DEMO_CODES_PER_DAY", base.codes_per_day),
            signups_per_ip_per_day=_int("DEMO_SIGNUPS_PER_IP_PER_DAY", base.signups_per_ip_per_day),
            blocked_domains=frozenset(extra),
            mail_backend=_str("DEMO_MAIL_BACKEND", base.mail_backend).lower(),
            smtp_host=_first("NEO_SMTP_HOST", "SMTP_HOST"),
            smtp_port=_port(_first("NEO_SMTP_PORT", "SMTP_PORT"), base.smtp_port),
            smtp_security=_str("DEMO_SMTP_SECURITY", base.smtp_security).lower(),
            smtp_user=_first("NEO_SMTP_USER", "SMTP_USER"),
            # Not stripped: a password is taken exactly as written.
            smtp_password=os.environ.get("NEO_SMTP_PASS") or os.environ.get("SMTP_PASS") or "",
            mail_from=_first("EMAIL_FROM", "SMTP_FROM") or _first("NEO_SMTP_USER", "SMTP_USER"),
            public_url=_str("DEMO_PUBLIC_URL", base.public_url).rstrip("/"),
            contact_email=_str("DEMO_CONTACT_EMAIL", _default_contact()),
            admin_token=_str("DEMO_ADMIN_TOKEN", base.admin_token),
        )

    @property
    def admin_enabled(self) -> bool:
        return len(self.admin_token) >= MIN_ADMIN_TOKEN_LENGTH

    @property
    def tls_mode(self) -> str:
        """How the SMTP connection is encrypted. 465 is implicit TLS (Neo), 587 upgrades with STARTTLS."""
        if self.smtp_security == "auto":
            return "ssl" if self.smtp_port == 465 else "starttls"
        return self.smtp_security

    def problems(self) -> list[str]:
        """What stops the gate from working. The server refuses to start on any."""
        if not self.enabled:
            return []
        found = []
        if self.mail_backend not in ("smtp", "console"):
            found.append(f"DEMO_MAIL_BACKEND must be smtp or console, not {self.mail_backend!r}")
        if self.mail_backend == "smtp":
            if not self.smtp_host:
                found.append("NEO_SMTP_HOST (or SMTP_HOST) is not set, so no sign-in email can be sent")
            if not self.smtp_user or not self.smtp_password:
                found.append("NEO_SMTP_USER and NEO_SMTP_PASS (or SMTP_USER and SMTP_PASS) are needed to sign in to the mail server")
            if self.smtp_security not in ("auto", "starttls", "ssl", "none"):
                found.append(f"DEMO_SMTP_SECURITY must be auto, ssl, starttls or none, not {self.smtp_security!r}")
        return found

    def as_manifest_limits(self) -> dict[str, int]:
        return {
            "trial_days": self.trial_days,
            "jobs_per_email_per_day": self.jobs_per_email_per_day,
            "code_minutes": self.code_minutes,
            "codes_per_email_per_hour": self.codes_per_email_per_hour,
            "codes_per_hour": self.codes_per_hour,
            "codes_per_day": self.codes_per_day,
            "signups_per_ip_per_day": self.signups_per_ip_per_day,
            "retention_days": self.retention_days,
        }
