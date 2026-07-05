"""URL route helpers for the dashboard (no Dash imports)."""

from __future__ import annotations

from lib.dash.dash_config import (
    ROUTE_FUNDAMENTALS,
    ROUTE_FLOW,
    ROUTE_TERMINAL,
    ROUTE_TICKER_TERMINAL,
)

_FUNDAMENTALS_PATH = ROUTE_FUNDAMENTALS.rstrip('/')
_FLOW_PATH = ROUTE_FLOW.rstrip('/')
_TICKER_TERMINAL_PATH = ROUTE_TICKER_TERMINAL.rstrip('/')


def normalize_pathname(pathname: str | None) -> str:
    """Return a normalized pathname without trailing slashes (except root)."""
    if not pathname:
        return ROUTE_TERMINAL
    pathname = pathname.strip()
    if pathname != '/' and pathname.endswith('/'):
        pathname = pathname.rstrip('/')
    return pathname or ROUTE_TERMINAL


def _split_path(pathname: str | None) -> list[str]:
    normalized = normalize_pathname(pathname)
    if normalized == ROUTE_TERMINAL:
        return []
    return [segment for segment in normalized.split('/') if segment]


def parse_path(pathname: str | None) -> tuple[str, str | None]:
    """Parse pathname into (route_name, ticker).

    route_name is one of: terminal, fundamentals, flow, ticker_terminal, unknown.
    """
    segments = _split_path(pathname)
    if not segments:
        return 'terminal', None
    head = segments[0].lower()
    if head == _FUNDAMENTALS_PATH.lstrip('/'):
        ticker = segments[1].strip().upper() if len(segments) > 1 else None
        return 'fundamentals', ticker or None
    if head == _FLOW_PATH.lstrip('/'):
        ticker = segments[1].strip().upper() if len(segments) > 1 else None
        return 'flow', ticker or None
    if head == _TICKER_TERMINAL_PATH.lstrip('/'):
        ticker = segments[1].strip().upper() if len(segments) > 1 else None
        return 'ticker_terminal', ticker or None
    return 'unknown', None


def extract_path_ticker(pathname: str | None) -> str | None:
    """Return the uppercased ticker segment from the URL path, if present."""
    _, ticker = parse_path(pathname)
    return ticker


def ticker_from_search(search: str | None) -> str | None:
    """Parse ?ticker=SYM from a query string."""
    if not search:
        return None
    for part in search.lstrip('?').split('&'):
        if part.startswith('ticker='):
            value = part.split('=', 1)[1].strip().upper()
            return value or None
    return None


def is_fundamentals_route(pathname: str | None) -> bool:
    """True when the browser URL targets the fundamentals workspace."""
    route, _ = parse_path(pathname)
    return route == 'fundamentals'


def is_flow_route(pathname: str | None) -> bool:
    """True when the browser URL targets the flow scanner workspace."""
    route, _ = parse_path(pathname)
    return route == 'flow'


def is_ticker_terminal_route(pathname: str | None) -> bool:
    """True when the browser URL is /ticker/<symbol> (terminal deep-link)."""
    route, _ = parse_path(pathname)
    return route == 'ticker_terminal'


def build_fundamentals_path(ticker: str | None = None) -> str:
    """Build a fundamentals URL, optionally including a ticker segment."""
    symbol = str(ticker or '').strip().upper()
    if symbol:
        return f'{ROUTE_FUNDAMENTALS}/{symbol}'
    return ROUTE_FUNDAMENTALS


def build_ticker_terminal_path(ticker: str | None = None) -> str:
    """Build a /ticker/<symbol> terminal deep-link, or the root terminal path."""
    symbol = str(ticker or '').strip().upper()
    if symbol:
        return f'{ROUTE_TICKER_TERMINAL}/{symbol}'
    return ROUTE_TERMINAL


def build_flow_path(ticker: str | None = None) -> str:
    """Build a flow-scanner URL, optionally including a ticker segment."""
    symbol = str(ticker or '').strip().upper()
    if symbol:
        return f'{ROUTE_FLOW}/{symbol}'
    return ROUTE_FLOW
