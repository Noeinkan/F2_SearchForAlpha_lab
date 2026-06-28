"""
Phase 5 — Command palette filter & layout tests.

The palette is mostly a layout/callback concern, so this module sticks
to the parts that have meaningful logic:
  - the command seed list is non-empty and includes the documented
    shortcuts from UI_UX_OVERHAUL_PLAN.md §5.1
  - the fuzzy filter ranks substring > prefix > fuzzy, and only
    synthesizes a `switch-ticker:` row for ALREADY-UPPERCASE queries
  - the layout registers the modal and all stores so callbacks don't
    miss any required dependency

Callback-level integration is exercised by the live dashboard boot
(see test_dashboard.py). These tests cover the pure logic that can
fail in isolation.
"""

import re

import dash
import dash_bootstrap_components as dbc

from lib.dash.callbacks.command_palette import (
    COMMANDS as _CMDS,
    _filter_commands,
)
from lib.dash.layout.command_palette import (
    COMMANDS as _LAYOUT_CMDS,
    _create_command_palette,
)
from lib.dash.layout import create_dashboard_layout
from lib.dash.dash_config import get_theme, DEFAULT_THEME


def _collect_ids(node, ids):
    cid = getattr(node, 'id', None)
    if cid:
        ids.append(cid)
    children = getattr(node, 'children', None)
    if isinstance(children, (list, tuple)):
        for c in children:
            _collect_ids(c, ids)
    elif children is not None:
        _collect_ids(children, ids)


def test_command_seed_matches_between_callbacks_and_layout():
    """The seed list must be the same single source of truth for both
    the server-side filter and the layout-rendered rows."""
    assert _CMDS == _LAYOUT_CMDS


def test_command_seed_includes_phase5_plan_shortcuts():
    """Phase 5 §5.1 lists the seed commands explicitly; this test guards
    against accidental removal during refactors."""
    ids = {c["id"] for c in _CMDS}
    expected = {
        "load-data", "run-backtest", "export-csv", "export-png",
        "reset-zoom", "go-fundamentals", "go-flow",
        "toggle-theme", "toggle-right", "toggle-sidebar",
    }
    assert expected.issubset(ids), f"Missing seed ids: {expected - ids}"


def test_filter_commands_returns_all_on_empty_query():
    out = _filter_commands("")
    assert len(out) == len(_CMDS)


def test_filter_commands_only_synthesizes_ticker_for_uppercase_query():
    """A bare ticker like AAPL triggers a synthetic switch-ticker row.
    A lowercase word like 'theme' must NOT, because the user is searching
    for the toggle-theme command."""
    out_upper = _filter_commands("AAPL")
    out_lower = _filter_commands("theme")
    out_mixed = _filter_commands("Theme")

    assert any(c["id"] == "switch-ticker:AAPL" for c in out_upper)

    # 'theme' must surface the toggle-theme command, never a fake ticker.
    assert not any(c["id"].startswith("switch-ticker:") for c in out_lower)
    assert any(c["id"] == "toggle-theme" for c in out_lower)

    # Same for 'Theme' (capitalised): must NOT be read as a ticker.
    assert not any(c["id"].startswith("switch-ticker:") for c in out_mixed)


def test_filter_commands_substring_beats_fuzzy():
    """A query that is a substring of a label/hint should rank that
    command above fuzzy matches on unrelated labels."""
    out = _filter_commands("run")
    ids = [c["id"] for c in out[:3]]
    assert ids[0] == "run-backtest"


def test_filter_commands_cap_top_n():
    """Server-side filter caps results so the list doesn't grow unbounded."""
    out = _filter_commands("a")
    assert len(out) <= 25


def test_ticker_regex_is_uppercase_only():
    """The regex must reject lowercase so 'theme' is never a ticker."""
    # Re-derive the regex the same way the module does; the module
    # exposes its internal symbol.
    from lib.dash.callbacks.command_palette import _TICKER_RE
    assert _TICKER_RE.match("AAPL")
    assert _TICKER_RE.match("BRK.B")
    assert not _TICKER_RE.match("theme")
    assert not _TICKER_RE.match("AAPLx")  # too long
    assert not _TICKER_RE.match("aapl")   # lowercase rejected


def test_layout_registers_palette_modal_and_stores():
    """The full layout must contain the modal and every store that the
    callback layer writes to. A missing store would surface as a
    'NoneType has no attribute data' error at callback registration
    time, so catching it here makes the failure obvious."""
    theme = get_theme(DEFAULT_THEME)
    layout = create_dashboard_layout(theme)
    ids = []
    _collect_ids(layout, ids)
    # Some components use dict IDs (Dash pattern-matching); collapse them
    # to a single key so we can use set membership.
    flat_ids = set()
    for i in ids:
        if isinstance(i, dict):
            flat_ids.add(i.get("type", ""))
        elif isinstance(i, str):
            flat_ids.add(i)
    required = {
        "command-palette",
        "command-palette-open",
        "command-palette-commands",
        "command-palette-visible",
        "command-palette-dispatch",
        "command-palette-bridge",
        "command-palette-query",
        "command-palette-list",
        "help-shortcuts-btn",
    }
    missing = required - flat_ids
    assert not missing, f"Layout missing ids: {missing}"
    # Pattern-matching rows should be present too.
    assert "sfa-palette-row" in flat_ids


def test_create_command_palette_returns_modal():
    """The builder returns a dbc.Modal with the expected id and props."""
    theme = get_theme(DEFAULT_THEME)
    styles = {"button_outline": {}, "input": {}}
    palette = _create_command_palette(styles, theme)
    assert isinstance(palette, dbc.Modal)
    assert palette.id == "command-palette"
    # Should start closed.
    assert palette.is_open is False


def test_app_registers_palette_callbacks_without_error():
    """End-to-end: building a Dash app with the palette layout must
    register all callbacks without raising. This catches typos in the
    Output/Input ids that the unit-level layout test misses."""
    app = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        suppress_callback_exceptions=True,
    )
    app.layout = create_dashboard_layout(get_theme(DEFAULT_THEME))
    # Late import to avoid pulling in the entire dashboard during the
    # layout-only tests above.
    from lib.dash.callbacks import register_callbacks
    from lib.dash.layout.shell import wire_command_palette_is_open
    register_callbacks(app)
    wire_command_palette_is_open(app)

    palette_callbacks = [
        k for k in app.callback_map
        if "command-palette" in k or "help-shortcuts" in k
    ]
    assert len(palette_callbacks) >= 6, (
        f"Expected at least 6 palette callbacks, got {len(palette_callbacks)}"
    )
