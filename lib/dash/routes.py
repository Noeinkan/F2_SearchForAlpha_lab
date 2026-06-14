"""URL route helpers for the dashboard (no Dash imports)."""

from __future__ import annotations

from lib.dash.dash_config import ROUTE_FUNDAMENTALS, ROUTE_FLOW, ROUTE_TERMINAL

_FUNDAMENTALS_PATH = ROUTE_FUNDAMENTALS.rstrip('/')
_FLOW_PATH = ROUTE_FLOW.rstrip('/')


def normalize_pathname(pathname: str | None) -> str:
    """Return a normalized pathname without trailing slashes (except root)."""
    if not pathname:
        return ROUTE_TERMINAL
    pathname = pathname.strip()
    if pathname != '/' and pathname.endswith('/'):
        pathname = pathname.rstrip('/')
    return pathname or ROUTE_TERMINAL


def is_fundamentals_route(pathname: str | None) -> bool:
    """True when the browser URL targets the fundamentals workspace."""
    return normalize_pathname(pathname) == _FUNDAMENTALS_PATH


def is_flow_route(pathname: str | None) -> bool:
    """True when the browser URL targets the flow scanner workspace."""
    return normalize_pathname(pathname) == _FLOW_PATH
