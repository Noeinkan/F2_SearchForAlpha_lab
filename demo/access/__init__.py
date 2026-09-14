"""Email-gated access to the public demo, and a record of how it is used.

- ``settings``  every knob, from ``DEMO_*`` environment variables
- ``emails``    validation, the canonical form a trial is keyed on, throwaway-inbox blocklist
- ``store``     SQLite: visitors, sign-in codes, browser grants, usage events
- ``mailer``    sends the sign-in email over SMTP (or logs it, locally)
- ``pages``     the sign-in pages and the emails
- ``gate``      the Flask routes and the before-request check in front of Dash
- ``admin``     ``/admin``: usage per person, CSV export, extend / revoke / delete

``DEMO_ACCESS_GATE=false`` turns all of it off (for a local run); the demo is
then open to anyone and nothing is recorded. See ``docs/DEMO.md``.
"""

from __future__ import annotations

from typing import Callable

from demo.access.settings import AccessSettings


def build_access(settings: AccessSettings, *, wall: Callable[[str], str], client_ip: Callable[[], str], mailer=None):
    """Open the store and build the gate and the admin panel. Returns ``(gate, admin)``."""
    from demo.access.admin import AdminPanel
    from demo.access.gate import AccessGate
    from demo.access.mailer import build_mailer
    from demo.access.store import AccessStore

    store = AccessStore(settings.db_path)
    gate = AccessGate(settings, store, mailer or build_mailer(settings), wall=wall, client_ip=client_ip)
    admin = AdminPanel(settings, store, client_ip=client_ip)
    return gate, admin


__all__ = ["AccessSettings", "build_access"]
