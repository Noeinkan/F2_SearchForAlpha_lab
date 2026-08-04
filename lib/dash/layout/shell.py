"""
Top-level layout composer. Walks the page once and emits every store,
interval, hidden preload div, plus the four visible regions.

Keeping this in a single builder avoids the dual-walk bug where two
callbacks could observe different sets of `dcc.Store` ids if the stores
were defined in different files.
"""

from dash import dcc, html
from dash.exceptions import PreventUpdate
import dash_mantine_components as dmc

from lib.dash.dash_config import (
    DEFAULT_THEME, DEFAULT_FUNDAMENTALS_PERIOD,
    DEFAULT_INDICATOR_SETTINGS, DEFAULT_BAR_INTERVAL,
)
from lib.dash.styles import get_styles

from .header import _create_header, _create_status_bar
from .overlays import _create_fundamentals_overlay, _create_flow_overlay
from .sidebar import _create_sidebar
from .chart_area import _create_chart_area
from .right_panel import _create_right_panel
from .command_palette import _create_command_palette
from .symbol_search import _create_symbol_search_modal
from lib.dash.bootstrap import BootstrapSnapshot


def create_dashboard_layout(theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Div:
    """Create the main dashboard layout."""
    styles = get_styles(theme)
    content = html.Div([
        dcc.Location(id='app-url', refresh=False),
        # Hidden stores
        dcc.Store(id='theme-store', data=DEFAULT_THEME, storage_type='local'),
        dcc.Store(id='data-loaded-store', data=1 if bootstrap is not None else 0),
        dcc.Store(id='data-display-store', data=bootstrap.data_display if bootstrap else None),
        dcc.Store(id='chart-focus-store', data=None),
        # Test window bookkeeping (callbacks/test_window.py). The series key is
        # "<ticker>|<interval>" — the window resets only when that changes, so a
        # refresh of the same series keeps a hand-narrowed window. The pending
        # store parks a preset's saved window until its data has loaded.
        dcc.Store(id='test-window-series-store', data=None),
        dcc.Store(id='test-window-pending-store', data=None),
        dcc.Store(id='layout-store', data={}),
        dcc.Store(id='presets-store', data={'presets': {}}),
        dcc.Store(id='active-preset-name', data=None),
        dcc.Store(id='preset-apply-store', data=None),
        dcc.Store(id='active-tab-store', data='backtest', storage_type='local'),
        dcc.Store(id='optimization-running', data=False),
        dcc.Store(id='optimization-state', data={
            'running': False,
            'current_index': 0,
            'total_combinations': 0,
            'completed': False,
            'sort_by': 'Total_Return_%',
            'sort_ascending': False
        }),
        dcc.Store(id='optimization-results-store', data=[]),
        dcc.Store(id='optimizer-apply-store', data=None),
        dcc.Store(id='optimizer-autorun', data=None),
        dcc.Store(id='optimizer-autorun-sink', data=None),
        dcc.Store(id='signals-unified-store', data=bootstrap.unified_rows if bootstrap else []),
        dcc.Store(id='indicator-settings-store', data=DEFAULT_INDICATOR_SETTINGS),
        dcc.Store(id='bar-interval-store', data=DEFAULT_BAR_INTERVAL, storage_type='session'),
        dcc.Store(id='active-indicator-store', data=None),
        dcc.Store(id='fundamentals-store', data=None, storage_type='session'),
        dcc.Store(id='fundamentals-period-store', data=DEFAULT_FUNDAMENTALS_PERIOD, storage_type='session'),
        # Memory (not session): each page load starts with no prior ticker
        # choice so python main.py always opens on DEFAULT_TICKER (TSLA).
        # Session persistence previously restored SPY and reloaded the wrong chart.
        dcc.Store(id='user-ticker-store', data=None),
        dcc.Store(id='route-ticker-store', data=None),
        dcc.Input(id='fundamentals-esc-signal', type='text', value='', style={'display': 'none'}),
        dcc.Download(id='download-csv'),
        # Fires once on mount (~1ms) so clientside routing can sync app-url
        # from window.__SFA_BOOT_URL__ before the slower startup callbacks run.
        dcc.Interval(id='url-boot-interval', interval=1, max_intervals=1),
        dcc.Interval(id='startup-interval', interval=500, max_intervals=1),
        dcc.Interval(id='autoload-interval', interval=1000, max_intervals=1),
        # Live wall-clock for the header / status bar. Runs forever (no
        # max_intervals) so the timestamp keeps ticking every second.
        dcc.Interval(id='clock-interval', interval=1000),
        dcc.Interval(id='optimization-interval', interval=500, disabled=True, n_intervals=0),
        dcc.Store(id='flow-state-store', data={'last_scan_at': None, 'tickers': []}, storage_type='session'),
        dcc.Store(id='flow-data-store', data=None, storage_type='session'),
        dcc.Interval(id='flow-rescan-interval', interval=2000, max_intervals=1, disabled=True),

        # Phase 2 — collapsible sidebars + splitter
        dcc.Store(id='sidebar-collapsed', data=False, storage_type='session'),
        dcc.Store(id='right-panel-collapsed', data=False, storage_type='session'),
        dcc.Store(id='right-panel-width', data=None, storage_type='session'),
        dcc.Input(id='right-panel-width-input', type='number', value='', style={'display': 'none'}),
        html.Div(id='layout-class-sync', style={'display': 'none'}),
        html.Div(id='right-panel-width-sync', style={'display': 'none'}),
        html.Div(id='splitter-bind-trigger', style={'display': 'none'}),

        # Keyboard shortcut listener
        html.Div(id='keyboard-listener', style={'display': 'none'}),
        html.Div(id='theme-class-sync', style={'display': 'none'}),
        html.Div(id='ui-storage-sync', style={'display': 'none'}),

        # --- Lightweight Charts render path ---------------------------------
        # `chart-payload-store` is the only channel between Python and the
        # chart. One server callback writes it; one clientside callback reads
        # it and calls window.sfaChart.apply(). Zoom/pan/crosshair stay on the
        # client entirely, so there is no range store feeding back to Python —
        # that feedback loop is what previously collided in a single Dash 4
        # dispatch layer and took the whole callback graph down.
        dcc.Store(id='chart-payload-store', data=None),
        dcc.Store(id='chart-type-store', data='candles', storage_type='local'),
        dcc.Store(id='price-scale-store', data='normal', storage_type='local'),
        html.Div(id='chart-render-sync', style={'display': 'none'}),
        html.Div(id='chart-focus-sync', style={'display': 'none'}),
        html.Div(id='chart-tools-sync', style={'display': 'none'}),
        # First-paint trigger, clicked by the glue once the canvas is mounted.
        # It has to be a real DOM event: `data-loaded-store` is an output of
        # `load_data`, which PreventUpdates on a bootstrapped page, and Dash
        # will not dispatch a callback that sits downstream of one that never
        # ran — not even via its other inputs. The Plotly chart never hit this
        # because its figure was serialised into the layout. Same trick the
        # command palette uses to drive buttons from clientside code.
        html.Button(id='chart-boot-btn', n_clicks=0, style={'display': 'none'}),

        # Phase 5 — command palette. The modal lives at the bottom of the
        # shell so it stacks above every overlay. `is_open` is driven by
        # the `command-palette-open` store. The visible rows are computed
        # by the clientside filter from `command-palette-visible` and the
        # full command seed in `command-palette-commands`.
        # Memory (not session) storage so the palette always starts CLOSED
        # on a fresh page load — a stale `True` in sessionStorage used to
        # make the palette pop open on every reload.
        dcc.Store(id='command-palette-open', data=False),
        dcc.Store(id='command-palette-commands', data=[]),
        dcc.Store(id='command-palette-visible', data=[]),
        dcc.Store(id='command-palette-dispatch', data=None),
        dcc.Store(id='command-palette-bridge', data=None),
        dcc.Store(id='sfa-palette-esc-trigger', data=None),

        # Symbol search. `watchlists-store` mirrors config/watchlists.json —
        # memory storage on purpose, because disk is the source of truth and a
        # stale localStorage copy would silently fight it. `symbol-search-open`
        # is memory-backed for the same reason the palette's is: so the modal
        # never springs open on a page load.
        dcc.Store(id='symbol-search-open', data=False),
        dcc.Store(id='symbol-search-filters', data={
            'asset_class': 'all',
            'sector': None,
            'fav_only': False,
        }),
        dcc.Store(id='watchlists-store', data=None),
        html.Div(id='symbol-search-focus-sync', style={'display': 'none'}),
        html.Div(id='symbol-search-guard-sync', style={'display': 'none'}),
        html.Div(id='command-palette-search-sync', style={'display': 'none'}),
        html.Div(id='command-palette-after-sync', style={'display': 'none'}),
        html.Div(id='command-palette-focus-sync', style={'display': 'none'}),
        html.Div(id='command-palette-guard-sync', style={'display': 'none'}),

        html.Div([
            _create_header(styles, theme, bootstrap=bootstrap),
            html.Div([
                _create_sidebar(styles, theme),
                _create_chart_area(styles, theme, bootstrap=bootstrap),
                # Phase 4: tabIndex + role make the splitter keyboard-resizable
                # (left/right arrow keys) in addition to the existing mousedown
                # drag. The clientside bind in callbacks/layout.py adds the
                # keydown listener on the element.
                html.Div(
                    id='right-panel-splitter',
                    className='sfa-splitter',
                    n_clicks=0,
                    tabIndex=0,
                    role='separator',
                    **{'aria-label': 'Resize right panel', 'aria-orientation': 'vertical'},
                ),
                _create_right_panel(styles, theme, bootstrap=bootstrap),
            ], style=styles['main_container']),
            _create_status_bar(styles, theme, bootstrap=bootstrap),
        ], id='terminal-shell'),

        _create_fundamentals_overlay(styles, theme),
        _create_flow_overlay(styles, theme),

        # Phase 5 — command palette modal (must be the LAST child so it
        # stacks above every overlay).
        _create_command_palette(styles, theme),
        _create_symbol_search_modal(styles, theme),

        # Hidden elements
        html.Div(id='hidden-output', style={'display': 'none'}),

    ], style=styles['app'], id='app-container')

    # Wrap with MantineProvider so dmc.Select renders with our Bloomberg-amber theme.
    # dmc.MantineProvider must wrap the entire layout tree for Mantine context to be
    # available to all dmc.* components (in particular dmc.Select used for ticker search).
    return dmc.MantineProvider(
        content,
        theme={
            "primaryColor": "orange",
            "fontFamily": 'Source Sans 3, system-ui, sans-serif',
            "defaultRadius": "xs",
            "colors": {
                # Override orange scale with Bloomberg amber (#FFA726) accents.
                "orange": [
                    "#FFF3E0", "#FFE0B2", "#FFCC80", "#FFB74D", "#FFA726",
                    "#FB8C00", "#F57C00", "#EF6C00", "#E65100", "#B87420",
                ],
            },
        },
        forceColorScheme="dark",
    )


def wire_command_palette_is_open(app):
    """Bind the `is_open` prop on the modal to the open/close store.

    Called from `integrated_dashboard.py` after `app.layout` is set so the
    callback is registered exactly once. Kept out of the layout builder
    so the layout function remains pure (no callback side-effects).
    """
    from dash.dependencies import Input, Output

    @app.callback(
        Output('command-palette', 'is_open'),
        [Input('command-palette-open', 'data')],
        prevent_initial_call=True,
    )
    def _sync_palette_is_open(open_state):
        return bool(open_state)

    @app.callback(
        Output('command-palette-query', 'value', allow_duplicate=True),
        Input('command-palette-open', 'data'),
        prevent_initial_call=True,
    )
    def _clear_palette_query_on_close(open_state):
        """Reset the search box when the palette closes.

        Ensures the next open starts with the full list, not a stale
        query from the previous session.
        """
        if open_state:
            raise PreventUpdate
        return ''

    app.clientside_callback(
        """
        function(openState) {
            if (!openState) {
                return window.dash_clientside.no_update;
            }
            setTimeout(function() {
                var input = document.getElementById('command-palette-query');
                if (input) {
                    input.focus();
                }
            }, 50);
            return '';
        }
        """,
        Output('command-palette-focus-sync', 'children'),
        Input('command-palette-open', 'data'),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(_n) {
            var modal = document.getElementById('command-palette');
            if (modal) {
                modal.classList.remove('show');
                modal.style.display = 'none';
                modal.setAttribute('aria-hidden', 'true');
            }
            document.body.classList.remove('modal-open');
            document.body.style.removeProperty('overflow');
            document.body.style.removeProperty('padding-right');
            document.querySelectorAll('.modal-backdrop').forEach(function(el) {
                el.remove();
            });
            return '';
        }
        """,
        Output('command-palette-guard-sync', 'children'),
        Input('startup-interval', 'n_intervals'),
    )

    # --- Symbol search modal: same three bindings as the palette above. ---

    @app.callback(
        Output('symbol-search-modal', 'is_open'),
        Input('symbol-search-open', 'data'),
        prevent_initial_call=True,
    )
    def _sync_symbol_search_is_open(open_state):
        return bool(open_state)

    app.clientside_callback(
        """
        function(openState) {
            if (!openState) {
                return window.dash_clientside.no_update;
            }
            setTimeout(function() {
                var input = document.getElementById('symbol-search-query');
                if (input) {
                    input.focus();
                    input.select();
                }
            }, 50);
            return '';
        }
        """,
        Output('symbol-search-focus-sync', 'children'),
        Input('symbol-search-open', 'data'),
        prevent_initial_call=True,
    )

    app.clientside_callback(
        """
        function(_n) {
            // Same cold-boot guard the palette needs: dbc.Modal can hydrate
            // with a leftover `show` class and its backdrop then swallows
            // every click in the app.
            var modal = document.getElementById('symbol-search-modal');
            if (modal) {
                modal.classList.remove('show');
                modal.style.display = 'none';
                modal.setAttribute('aria-hidden', 'true');
            }
            return '';
        }
        """,
        Output('symbol-search-guard-sync', 'children'),
        Input('startup-interval', 'n_intervals'),
    )