"""Who is using the dashboard, and are they an admin.

The dashboard runs in three ways, set as ``SFA_AUTH_MODE`` on the Flask config:

- ``local`` (default) -- ``python main.py`` on your own machine. There is no
  login, and the person at the keyboard is the owner, so they are admin.
- ``hosted`` -- alpha.noeinsolutions.com. ``hosted.login`` checks the cookie
  before every request and leaves ``g.user_email`` / ``g.is_admin``.
- ``demo`` -- the public demo. Nobody is ever admin there.

Works from a Flask route and from inside a Dash callback, since both run in a
request context.
"""

from __future__ import annotations

from flask import current_app, g, has_request_context

LOCAL, HOSTED, DEMO = "local", "hosted", "demo"


def auth_mode() -> str:
    if not has_request_context():
        return LOCAL
    return current_app.config.get("SFA_AUTH_MODE", LOCAL)


def current_email() -> str | None:
    if not has_request_context() or auth_mode() != HOSTED:
        return None
    return getattr(g, "user_email", None)


def is_admin() -> bool:
    mode = auth_mode()
    if mode == LOCAL:
        return True
    if mode == HOSTED:
        return bool(getattr(g, "is_admin", False))
    return False
