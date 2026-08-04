"""
Phase 5 — Command palette modal.

The palette is a Bootstrap-styled modal that overlays the entire shell.
It is closed by default and opened either by:
  - the global Ctrl/Cmd+K shortcut (handled in misc_ui.clientside)
  - clicking the `[ ? ]` button in the header

The visible result list is rendered on the server from the user's current
query (held in `command-palette-query`). A clientside callback filters
client-side to avoid a round-trip per keystroke, but the master list of
commands lives in a `dcc.Store` so it stays in one place.
"""

from dash import dcc, html
import dash_bootstrap_components as dbc

from lib.dash.dash_config import FONT_SIZES, FONT_FAMILY


# Seed commands rendered into the palette. Each row has:
#   - id: stable id used by the dispatch callback to identify which action to run
#   - label: human-readable description
#   - shortcut: short string shown on the right (informational, not the binding)
#   - group: section heading (Actions / Navigate / Theme / Data)
#   - hint: secondary text rendered under the label
COMMANDS = [
    # Load / run
    {"id": "load-data",        "label": "Load data",                "shortcut": "Ctrl+Enter",
     "group": "Data",   "hint": "Pull OHLCV for the current ticker"},
    {"id": "run-backtest",     "label": "Run backtest",             "shortcut": "Ctrl+B",
     "group": "Data",   "hint": "Execute the strategy on loaded data"},
    {"id": "export-csv",       "label": "Export CSV",               "shortcut": "E C",
     "group": "Data",   "hint": "Download chart data as CSV"},
    {"id": "export-png",       "label": "Export chart as PNG",      "shortcut": "E P",
     "group": "Data",   "hint": "Download the current chart image"},
    {"id": "reset-zoom",       "label": "Reset chart zoom",         "shortcut": "R",
     "group": "Data",   "hint": "Reset zoom on the financial chart"},
    {"id": "clear-data",       "label": "Clear loaded data",        "shortcut": "",
     "group": "Data",   "hint": "Forget the current dataset"},

    # Navigate
    {"id": "open-symbol-search", "label": "Search symbols",         "shortcut": "Ctrl+/",
     "group": "Navigate", "hint": "Browse the full universe by name, category or watchlist"},
    {"id": "go-fundamentals",  "label": "Open fundamentals",        "shortcut": "G F",
     "group": "Navigate", "hint": "Jump to fundamentals workspace for the current ticker"},
    {"id": "go-flow",          "label": "Open flow scanner",        "shortcut": "G O",
     "group": "Navigate", "hint": "Jump to options flow workspace"},
    {"id": "go-optimize",      "label": "Open optimizer",           "shortcut": "G P",
     "group": "Navigate", "hint": "Jump to full-screen signal optimizer"},
    {"id": "go-terminal",      "label": "Back to terminal",         "shortcut": "G T",
     "group": "Navigate", "hint": "Return to the main chart view"},

    # Theme + UI
    {"id": "toggle-theme",     "label": "Cycle theme",              "shortcut": "Ctrl+J",
     "group": "UI",     "hint": "Dark → CVD-safe → Light"},
    {"id": "toggle-right",     "label": "Toggle right panel",       "shortcut": "Ctrl+.",
     "group": "UI",     "hint": "Show or hide the backtest panel"},
    {"id": "toggle-sidebar",   "label": "Toggle sidebar",           "shortcut": "Ctrl+,",
     "group": "UI",     "hint": "Collapse or expand the left sidebar"},

    # Ticker switcher — the palette accepts a bare ticker as input.
    # When the user types a query that matches no command exactly but
    # looks like a ticker (1-5 uppercase letters), we suggest a synthetic
    # "Switch ticker → AAPL" row. That's handled clientside below.
]


def _build_shortcut_chip(shortcut: str, theme: dict) -> html.Span:
    """Render a shortcut key combo as a Bloomberg-pill style badge."""
    if not shortcut:
        return html.Span()
    # Render Ctrl+ combos as a stacked chip so the look matches the dense chrome.
    parts = shortcut.split('+')
    children = []
    for idx, part in enumerate(parts):
        if idx > 0:
            children.append(html.Span('+', className='sfa-palette-kbd-plus'))
        children.append(html.Span(part, className='sfa-palette-kbd-key'))
    return html.Span(children, className='sfa-palette-shortcut')


def _create_command_palette(styles: dict, theme: dict) -> dbc.Modal:
    """Return the command-palette modal mounted on the shell.

    The modal is always present in the DOM; visibility is controlled by the
    `is_open` prop on the `command-palette-open` store. Keeping it mounted
    means the keyboard listener can toggle it without re-creating focus
    state on every open.
    """
    # Group rows by their `group` so the list has section headers
    # (Bloomberg loves headers in everything).
    groups: dict[str, list[dict]] = {}
    for cmd in COMMANDS:
        groups.setdefault(cmd["group"], []).append(cmd)

    list_children: list = []
    for group_name, items in groups.items():
        list_children.append(
            html.Div(group_name.upper(), className='sfa-palette-group-header')
        )
        for cmd in items:
            list_children.append(
                html.Div(
                    id={'type': 'sfa-palette-row', 'index': cmd["id"]},
                    className='sfa-palette-row',
                    n_clicks=0,
                    # `value` is the action_id; the dispatch callback
                    # pulls this from callback_context.
                    **{'data-cmd-id': cmd["id"]},
                    children=[
                        html.Div([
                            html.Div(cmd["label"], className='sfa-palette-row-label'),
                            html.Div(cmd["hint"], className='sfa-palette-row-hint'),
                        ], className='sfa-palette-row-text'),
                        _build_shortcut_chip(cmd["shortcut"], theme),
                    ],
                )
            )

    # Empty-state row that appears when no commands match.
    list_children.append(
        html.Div(
            "No matching commands. Try a different search.",
            id='command-palette-empty',
            className='sfa-palette-empty',
            style={'display': 'none'},
        )
    )

    body = html.Div([
        # Search input — large, autofocus, monospace so tickers read clean.
        dcc.Input(
            id='command-palette-query',
            type='text',
            placeholder='Type a command or search…',
            value='',
            className='bbg-input sfa-palette-input',
            n_submit=0,
            # Note: `dcc.Input` (Dash 4.x) does not accept arbitrary HTML
            # attributes like `aria-label`. The `placeholder` below already
            # describes the field for screen readers, so no extra attr is set.
        ),
        html.Div(
            id='command-palette-list',
            className='sfa-palette-list',
            children=list_children,
        ),
        html.Div([
            html.Span('↑↓ navigate', className='sfa-palette-foot-key'),
            html.Span('↵ run',       className='sfa-palette-foot-key'),
            html.Span('esc close',   className='sfa-palette-foot-key'),
            html.Span('Ctrl+K',      className='sfa-palette-foot-key'),
        ], className='sfa-palette-foot'),
    ], className='sfa-palette-body')

    return dbc.Modal(
        children=[body],
        id='command-palette',
        is_open=False,
        centered=True,
        size='lg',
        backdrop=True,
        # dbc.Modal's `keyboard` defaults to True, which closes on Esc.
        # We keep that and additionally close from the global listener
        # so the focus-return behavior is consistent.
        keyboard=True,
        className='sfa-palette-modal',
        content_class_name='sfa-palette-content',
        # BackdropClassName allows CSS to dim the rest of the page.
        backdrop_class_name='sfa-palette-backdrop',
        style={'overflow': 'visible'},
    )


__all__ = ['_create_command_palette', 'COMMANDS']
