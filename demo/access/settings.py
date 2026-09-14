"""Access-gate settings. Every one is an environment variable with a default.

Numbers and switches live in ``.deploy/compose.yml``. The three secrets --
``DEMO_SMTP_PASSWORD``, ``DEMO_ADMIN_TOKEN`` and, if the provider wants one,
``DEMO_SMTP_USER`` -- live only in ``/opt/sites/alpha/.env`` on the server.
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
    codes_per_hour: int = 60               # DEMO_CODES_PER_HOUR: sign-in emails in total (protects the mail quota)
    signups_per_ip_per_day: int = 5        # DEMO_SIGNUPS_PER_IP_PER_DAY: new addresses from one connection
    blocked_domains: frozenset[str] = field(default_factory=frozenset)  # DEMO_BLOCKED_EMAIL_DOMAINS: comma list, added to emails.DISPOSABLE_DOMAINS
    # Mail
    mail_backend: str = "smtp"             # DEMO_MAIL_BACKEND: smtp | console (console logs the code; local runs only)
    smtp_host: str = ""                    # DEMO_SMTP_HOST
    smtp_port: int = 587                   # DEMO_SMTP_PORT
    smtp_security: str = "starttls"        # DEMO_SMTP_SECURITY: starttls | ssl | none
    smtp_user: str = ""                    # DEMO_SMTP_USER (secret file)
    smtp_password: str = ""                # DEMO_SMTP_PASSWORD (secret file)
    mail_from: str = ""                    # DEMO_MAIL_FROM: e.g. "SearchForAlpha Lab <demo@noeinsolutions.com>"
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
            signups_per_ip_per_day=_int("DEMO_SIGNUPS_PER_IP_PER_DAY", base.signups_per_ip_per_day),
            blocked_domains=frozenset(extra),
            mail_backend=_str("DEMO_MAIL_BACKEND", base.mail_backend).lower(),
            smtp_host=_str("DEMO_SMTP_HOST", base.smtp_host),
            smtp_port=_int("DEMO_SMTP_PORT", base.smtp_port),
            smtp_security=_str("DEMO_SMTP_SECURITY", base.smtp_security).lower(),
            smtp_user=_str("DEMO_SMTP_USER", base.smtp_user),
            smtp_password=os.environ.get("DEMO_SMTP_PASSWORD", base.smtp_password),
            mail_from=_str("DEMO_MAIL_FROM", base.mail_from),
            public_url=_str("DEMO_PUBLIC_URL", base.public_url).rstrip("/"),
            contact_email=_str("DEMO_CONTACT_EMAIL", _default_contact()),
            admin_token=_str("DEMO_ADMIN_TOKEN", base.admin_token),
        )

    @property
    def admin_enabled(self) -> bool:
        return len(self.admin_token) >= MIN_ADMIN_TOKEN_LENGTH

    def problems(self) -> list[str]:
        """What stops the gate from working. The server refuses to start on any."""
        if not self.enabled:
            return []
        found = []
        if self.mail_backend not in ("smtp", "console"):
            found.append(f"DEMO_MAIL_BACKEND must be smtp or console, not {self.mail_backend!r}")
        if self.mail_backend == "smtp":
            if not self.smtp_host:
                found.append("DEMO_SMTP_HOST is not set, so no sign-in email can be sent")
            if not self.mail_from:
                found.append("DEMO_MAIL_FROM is not set")
            if self.smtp_security not in ("starttls", "ssl", "none"):
                found.append(f"DEMO_SMTP_SECURITY must be starttls, ssl or none, not {self.smtp_security!r}")
        return found

    def as_manifest_limits(self) -> dict[str, int]:
        return {
            "trial_days": self.trial_days,
            "jobs_per_email_per_day": self.jobs_per_email_per_day,
            "code_minutes": self.code_minutes,
            "codes_per_email_per_hour": self.codes_per_email_per_hour,
            "codes_per_hour": self.codes_per_hour,
            "signups_per_ip_per_day": self.signups_per_ip_per_day,
            "retention_days": self.retention_days,
        }
