"""
Misc UI callbacks (tabs, theme, clientside helpers).
"""

from datetime import datetime

from dash import callback_context
from dash.dependencies import Input, Output, State

from lib.dash.dash_config import (
    DEFAULT_THEME,
    THEME_BUTTON_LABELS,
    THEME_CYCLE,
    UI_STORAGE_VERSION,
    get_theme,
)
from lib.dash.state import dashboard_state
from lib.dash.styles import get_styles


def register_misc_callbacks(app) -> None:
    @app.callback(
        [Output('panel-backtest', 'style'),
         Output('panel-optimizer', 'style'),
         Output('panel-data', 'style'),
         Output('tab-backtest', 'style'),
         Output('tab-optimizer', 'style'),
         Output('tab-data', 'style'),
         Output('tab-backtest', 'className'),
         Output('tab-optimizer', 'className'),
         Output('tab-data', 'className'),
         Output('active-tab-store', 'data')],
        [Input('tab-backtest', 'n_clicks'),
         Input('tab-optimizer', 'n_clicks'),
         Input('tab-data', 'n_clicks')],
        [State('theme-store', 'data'),
         State('active-tab-store', 'data')]
    )
    def switch_panel(backtest_clicks, optimizer_clicks, data_clicks, theme_name, active_tab):
        """Switch between right panel tabs."""
        theme = get_theme(theme_name or DEFAULT_THEME)
        styles = get_styles(theme)

        def _styles_for_tab(tab_name):
            if tab_name == 'optimizer':
                return (
                    {'display': 'none'},
                    {'display': 'block'},
                    {'display': 'none'},
                    styles['tab'],
                    {**styles['tab'], **styles['tab_active']},
                    styles['tab'],
                    'panel-tab',
                    'panel-tab active',
                    'panel-tab',
                    'optimizer'
                )
            if tab_name == 'data':
                return (
                    {'display': 'none'},
                    {'display': 'none'},
                    {'display': 'block'},
                    styles['tab'],
                    styles['tab'],
                    {**styles['tab'], **styles['tab_active']},
                    'panel-tab',
                    'panel-tab',
                    'panel-tab active',
                    'data'
                )
            return (
                {'display': 'block'},
                {'display': 'none'},
                {'display': 'none'},
                {**styles['tab'], **styles['tab_active']},
                styles['tab'],
                styles['tab'],
                'panel-tab active',
                'panel-tab',
                'panel-tab',
                'backtest'
            )

        ctx = callback_context
        if not ctx.triggered:
            return _styles_for_tab(active_tab or 'backtest')

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'tab-backtest':
            return _styles_for_tab('backtest')
        if button_id == 'tab-optimizer':
            return _styles_for_tab('optimizer')
        # tab-data
        return _styles_for_tab('data')

    @app.callback(
        [Output('header-status', 'children'),
         Output('status-clock', 'children')],
        [Input('clock-interval', 'n_intervals')]
    )
    def update_header_status(_):
        """Update header status.

        Driven by ``clock-interval`` (1s, no max_intervals) so the
        timestamp keeps ticking every second. Previously this was wired
        to ``startup-interval``, which has ``max_intervals=1`` and only
        fires once on mount — that's why the header time appeared frozen.
        """
        timestamp = datetime.now().strftime("%H:%M:%S")
        return timestamp, timestamp

    @app.callback(
        [Output('theme-store', 'data'),
         Output('theme-label', 'children')],
        [Input('theme-toggle', 'n_clicks')],
        [State('theme-store', 'data')]
    )
    def toggle_theme(n_clicks, current_theme):
        """Cycle through DARK -> CVD -> LIGHT -> DARK.

        Phase 4 adds the CVD (color-vision-deficiency) theme as a third
        stop on the toggle. CVD swaps the green/red up/down pair for
        a blue/orange pair so ~8% of male users with red/green CVD
        can still read the P&L state without relying on color.
        """
        current_theme = current_theme or DEFAULT_THEME

        def _format_theme_label(theme_name):
            return THEME_BUTTON_LABELS.get(theme_name, THEME_BUTTON_LABELS[DEFAULT_THEME])

        if not n_clicks:
            return DEFAULT_THEME, _format_theme_label(DEFAULT_THEME)

        # Walk the cycle. Unknown values (e.g. legacy 'dark') snap to the
        # first stop so we always make forward progress.
        try:
            current_index = THEME_CYCLE.index(current_theme)
        except ValueError:
            current_index = -1
        new_theme = THEME_CYCLE[(current_index + 1) % len(THEME_CYCLE)]
        dashboard_state.set_theme(new_theme)
        return new_theme, _format_theme_label(new_theme)

    app.clientside_callback(
        f"""
        function(n) {{
            if (n === null || n === undefined) {{
                return window.dash_clientside.no_update;
            }}
            var key = 'sfa-ui-storage-version';
            var current = '{UI_STORAGE_VERSION}';
            if (localStorage.getItem(key) !== current) {{
                [localStorage, sessionStorage].forEach(function(store) {{
                    for (var i = store.length - 1; i >= 0; i--) {{
                        var k = store.key(i);
                        if (k && k.indexOf('dash-') === 0) {{
                            store.removeItem(k);
                        }}
                    }}
                }});
                localStorage.setItem(key, current);
            }}
            return window.dash_clientside.no_update;
        }}
        """,
        Output('ui-storage-sync', 'children'),
        Input('startup-interval', 'n_intervals'),
    )

    app.clientside_callback(
        """
        function(themeName) {
            // Phase 4: the body class now reflects the active theme. Each
            // theme has a matching `.theme-<name>` class on <body> so CSS
            // overrides in dashboard.css can re-skin the entire UI. Only
            // 'light' needs a full override today; bloomberg/cvd are the
            // default look and just need the class removed.
            document.body.classList.remove('theme-light', 'theme-cvd', 'theme-bloomberg');
            if (themeName && themeName !== 'bloomberg' && themeName !== 'dark') {
                document.body.classList.add('theme-' + themeName);
            }
            return themeName;
        }
        """,
        Output('theme-class-sync', 'children'),
        Input('theme-store', 'data')
    )

    # Register clientside callback for keyboard shortcuts
    app.clientside_callback(
        """
        function(id) {
            var pendingG = false;
            var gTimer = null;
            var paletteOpen = false;

            function currentTicker() {
                var select = document.getElementById('ticker-dropdown');
                if (!select) {
                    return 'TSLA';
                }
                var input = select.querySelector('input');
                if (input && input.value) {
                    return String(input.value).trim().toUpperCase() || 'TSLA';
                }
                return 'TSLA';
            }

            // Reflects the modal's actual state by reading the data attr
            // that the dbc.Modal renders. Keeps the keyboard handler in
            // sync even when the modal is opened/closed by other means.
            function isPaletteOpen() {
                var modal = document.getElementById('command-palette');
                if (!modal) {
                    return false;
                }
                // dbc.Modal renders with class 'show' on the modal when visible.
                return modal.classList.contains('show');
            }

            function openPalette() {
                var btn = document.getElementById('palette-open-btn');
                if (btn) {
                    btn.click();
                }
            }

            function isSymbolSearchOpen() {
                var modal = document.getElementById('symbol-search-modal');
                return !!(modal && modal.classList.contains('show'));
            }

            function openSymbolSearch() {
                var btn = document.getElementById('symbol-search-trigger');
                if (btn) {
                    btn.click();
                }
            }

            // True while the user is typing into a form control, so bare-key
            // shortcuts don't hijack ordinary text entry.
            function inTextField(e) {
                var el = e.target;
                if (!el) {
                    return false;
                }
                var tag = (el.tagName || '').toUpperCase();
                return tag === 'INPUT' || tag === 'TEXTAREA' || tag === 'SELECT'
                    || el.isContentEditable === true;
            }

            document.addEventListener('keydown', function(e) {
                // --- Symbol search (Ctrl+/ anywhere, or bare / outside a field) ---
                // Deliberately not Ctrl+K: that is the command palette, and
                // the two overlays must never fight over one binding.
                if (!isSymbolSearchOpen()
                    && ((e.ctrlKey || e.metaKey) && e.key === '/'
                        || (e.key === '/' && !e.ctrlKey && !e.metaKey && !e.altKey
                            && !inTextField(e)))) {
                    e.preventDefault();
                    openSymbolSearch();
                    return;
                }

                // Inside symbol search: arrow nav + Enter, mirroring the
                // palette's handling below. Enter inside the query input is
                // left alone — dcc.Input's n_submit drives free-text loading.
                if (isSymbolSearchOpen()) {
                    var symModal = document.getElementById('symbol-search-modal');
                    var symRows = symModal.querySelectorAll('.sfa-symsearch-row');
                    var symActive = symModal.querySelector('.sfa-symsearch-row.active');

                    if (e.key === 'ArrowDown' || e.key === 'ArrowUp') {
                        e.preventDefault();
                        if (symRows.length === 0) {
                            return;
                        }
                        var symIdx = -1;
                        for (var s = 0; s < symRows.length; s++) {
                            if (symRows[s] === symActive) { symIdx = s; break; }
                        }
                        var step = (e.key === 'ArrowDown') ? 1 : -1;
                        var nextIdx = (symIdx + step + symRows.length) % symRows.length;
                        var symNext = symRows[nextIdx];
                        symRows.forEach(function(r) { r.classList.remove('active'); });
                        symNext.classList.add('active');
                        symNext.scrollIntoView({ block: 'nearest' });
                        return;
                    }
                    if (e.key === 'Enter') {
                        // Only intercept when a row is highlighted; otherwise
                        // let the input submit the typed text. Click the
                        // selectable body — not the wrap — so starring stays
                        // independent of selection.
                        if (symActive) {
                            e.preventDefault();
                            var body = symActive.querySelector('.sfa-symsearch-row-body');
                            (body || symActive).click();
                        }
                        return;
                    }
                    if ((e.key === 's' || e.key === 'S')
                        && !e.ctrlKey && !e.metaKey && !e.altKey
                        && !inTextField(e)) {
                        // Star/unstar the highlighted row without selecting it.
                        e.preventDefault();
                        if (symActive) {
                            var star = symActive.querySelector('.sfa-symsearch-star');
                            if (star) { star.click(); }
                        }
                        return;
                    }
                    if (e.key === 'Escape') {
                        symRows.forEach(function(r) { r.classList.remove('active'); });
                        return;
                    }
                    // Swallow the rest so app shortcuts don't fire while the
                    // user is typing a symbol.
                    return;
                }

                // --- Command palette (Ctrl+K / Cmd+K) ---
                // Open the palette from anywhere except an input/textarea
                // so we don't hijack typing in other controls. The palette
                // itself handles its own Esc/Arrow/Enter.
                if ((e.ctrlKey || e.metaKey) && (e.key === 'k' || e.key === 'K')) {
                    e.preventDefault();
                    var wasOpen = isPaletteOpen();
                    var modal = document.getElementById('command-palette');
                    if (wasOpen) {
                        var closeBtn = modal && modal.querySelector('.btn-close');
                        if (closeBtn) {
                            closeBtn.click();
                        }
                    } else {
                        openPalette();
                    }
                    return;
                }

                // Inside the palette: arrow nav + Enter to dispatch.
                if (isPaletteOpen()) {
                    var modal = document.getElementById('command-palette');
                    var rows = modal.querySelectorAll('.sfa-palette-row');
                    if (rows.length === 0) {
                        return;
                    }
                    var active = modal.querySelector('.sfa-palette-row.active');
                    var activeIdx = -1;
                    for (var i = 0; i < rows.length; i++) {
                        if (rows[i] === active) { activeIdx = i; break; }
                    }

                    if (e.key === 'ArrowDown') {
                        e.preventDefault();
                        var next = rows[(activeIdx + 1) % rows.length];
                        rows.forEach(function(r) { r.classList.remove('active'); });
                        next.classList.add('active');
                        next.scrollIntoView({ block: 'nearest' });
                        return;
                    }
                    if (e.key === 'ArrowUp') {
                        e.preventDefault();
                        var prev = rows[(activeIdx - 1 + rows.length) % rows.length];
                        rows.forEach(function(r) { r.classList.remove('active'); });
                        prev.classList.add('active');
                        prev.scrollIntoView({ block: 'nearest' });
                        return;
                    }
                    if (e.key === 'Enter') {
                        // If the user typed a query that exactly matches
                        // a ticker pattern, let the input's n_submit
                        // handle dispatch (the input is the focused
                        // element and Enter would otherwise be ambiguous).
                        var queryInput = document.getElementById('command-palette-query');
                        if (queryInput && document.activeElement === queryInput) {
                            var q = (queryInput.value || '').trim().toUpperCase();
                            var isTicker = /^[A-Z]{1,5}(\\.[A-Z])?$/.test(q);
                            if (isTicker) {
                                // The dispatch flow is wired via the
                                // synthetic row click — find the synthetic
                                // row that was rendered for this ticker
                                // (id="switch-ticker:<TICKER>") and click it.
                                var synth = modal.querySelector(
                                    '[data-cmd-id^="switch-ticker:"]');
                                if (synth) { synth.click(); }
                                return;
                            }
                        }
                        // Otherwise dispatch whichever row is active
                        // (or the first one if none is).
                        var target = active || rows[0];
                        if (target) { target.click(); }
                        return;
                    }
                    // Escape inside palette — let dbc.Modal's native
                    // handling close it. We also clear the active state.
                    if (e.key === 'Escape') {
                        rows.forEach(function(r) { r.classList.remove('active'); });
                        // dbc.Modal with keyboard=True handles Esc.
                        return;
                    }
                    // Tab inside the palette should stay inside.
                    if (e.key === 'Tab') {
                        e.preventDefault();
                        var queryInput = document.getElementById('command-palette-query');
                        if (queryInput) { queryInput.focus(); }
                        return;
                    }
                    // Don't let other shortcuts fire while the palette
                    // is consuming input.
                    return;
                }

                // Ctrl+Enter to load data
                if (e.ctrlKey && e.key === 'Enter') {
                    var loadBtn = document.getElementById('load-data-button');
                    if (loadBtn) {
                        loadBtn.click();
                    }
                }
                // Ctrl+B to run backtest
                if (e.ctrlKey && e.key === 'b') {
                    e.preventDefault();
                    var backtestBtn = document.getElementById('run-backtest-btn');
                    if (backtestBtn) {
                        backtestBtn.click();
                    }
                }
                // G then F — open fundamentals for current ticker
                if (!e.ctrlKey && !e.metaKey && !e.altKey) {
                    if (e.key === 'g' || e.key === 'G') {
                        pendingG = true;
                        clearTimeout(gTimer);
                        gTimer = setTimeout(function() { pendingG = false; }, 1000);
                        return;
                    }
                    if (pendingG && (e.key === 'f' || e.key === 'F')) {
                        e.preventDefault();
                        pendingG = false;
                        clearTimeout(gTimer);
                        var ticker = currentTicker();
                        window.location.pathname = '/fundamentals/' + ticker;
                        return;
                    }
                    pendingG = false;
                    clearTimeout(gTimer);
                }
                // Escape to close any modals/alerts
                if (e.key === 'Escape') {
                    var alerts = document.querySelectorAll('.alert-dismissible .btn-close');
                    alerts.forEach(function(btn) { btn.click(); });
                }
            });
            return window.dash_clientside.no_update;
        }
        """,
        Output('keyboard-listener', 'children'),
        Input('startup-interval', 'n_intervals')
    )

    # Clientside: dispatch bridge. The server writes a `{action, ticker}`
    # dict into `command-palette-bridge`. This callback translates each
    # action into the right DOM side-effect (button click, chart API call,
    # etc.) without bouncing back through the server.
    app.clientside_callback(
        """
        function(dispatch) {
            if (!dispatch || !dispatch.action) {
                return window.dash_clientside.no_update;
            }
            var action = dispatch.action;

            function clickById(id) {
                var el = document.getElementById(id);
                if (el) { el.click(); }
            }

            if (action === 'open-symbol-search') {
                // The palette closes itself on dispatch; defer so the two
                // modals don't overlap during Bootstrap's close transition.
                setTimeout(function() { clickById('symbol-search-trigger'); }, 180);
            }
            else if (action === 'load-data')      { clickById('load-data-button'); }
            else if (action === 'run-backtest')   { clickById('run-backtest-btn'); }
            else if (action === 'export-csv')     { clickById('export-csv-btn'); }
            else if (action === 'export-png')     { clickById('export-img-btn'); }
            else if (action === 'toggle-theme')   { clickById('theme-toggle'); }
            else if (action === 'toggle-sidebar') { clickById('sidebar-toggle-btn'); }
            else if (action === 'toggle-right')   { clickById('right-panel-toggle-btn'); }
            else if (action === 'reset-zoom') {
                if (window.sfaChart) { window.sfaChart.fitContent(); }
            }
            else if (action === 'clear-data') {
                // No dedicated clear button in the UI; trigger the data
                // store update through the routing layer by navigating
                // to a sentinel URL with a clear flag.
                // The simplest reliable clear is to navigate to / which
                // re-runs autoload; for now this is a no-op placeholder.
                // Future work: add a clear-data-btn.
            }
            // ticker / route changes are handled by server callbacks that
            // already consume command-palette-dispatch; nothing to do here.

            // Always focus the chart after a command runs so keyboard
            // navigation keeps working.
            setTimeout(function() {
                var chart = document.getElementById('financial-chart');
                if (chart) { chart.focus({preventScroll: true}); }
            }, 0);

            return Date.now();
        }
        """,
        Output('command-palette-after-sync', 'children'),
        Input('command-palette-bridge', 'data'),
    )

    # Clientside: live-filter the palette rows as the user types. We
    # compute the score on the client using the master list loaded into
    # `command-palette-commands`, so the round-trip only happens for
    # command dispatch, not for every keystroke.
    app.clientside_callback(
        """
        function(query, commands) {
            var q = (query || '').trim();
            var rows = document.querySelectorAll('#command-palette .sfa-palette-row');
            if (!rows || rows.length === 0) {
                return window.dash_clientside.no_update;
            }
            // Synthetic ticker row: rendered for bare ticker queries.
            // Match against the raw query so a lowercase word like
            // "theme" doesn't accidentally match the ticker pattern.
            var isTicker = /^[A-Z]{1,5}(\\.[A-Z])?$/.test(q);
            var visibleCount = 0;
            rows.forEach(function(row) {
                var cmdId = row.getAttribute('data-cmd-id') || '';
                if (cmdId.indexOf('switch-ticker:') === 0) {
                    // The synthetic row only shows when the query is a ticker.
                    if (isTicker) {
                        row.style.display = '';
                        visibleCount++;
                    } else {
                        row.style.display = 'none';
                    }
                    return;
                }
                var label = (row.querySelector('.sfa-palette-row-label') || {}).textContent || '';
                var hint = (row.querySelector('.sfa-palette-row-hint') || {}).textContent || '';
                var group = (row.querySelector('.sfa-palette-group-header') || row.parentNode.querySelector('.sfa-palette-group-header'));
                var groupText = group ? group.textContent : '';
                var haystack = (label + ' ' + hint + ' ' + groupText).toLowerCase();
                var qq = q.toLowerCase();
                var match = !qq || haystack.indexOf(qq) !== -1;
                row.style.display = match ? '' : 'none';
                if (match) visibleCount++;
            });

            // Empty state
            var emptyEl = document.getElementById('command-palette-empty');
            if (emptyEl) {
                emptyEl.style.display = visibleCount === 0 ? '' : 'none';
            }

            // Hide group headers whose siblings are all hidden.
            var headers = document.querySelectorAll('#command-palette .sfa-palette-group-header');
            headers.forEach(function(h) {
                var next = h.nextElementSibling;
                var anyVisible = false;
                while (next && !next.classList.contains('sfa-palette-group-header')) {
                    if (next.classList.contains('sfa-palette-row') && next.style.display !== 'none') {
                        anyVisible = true; break;
                    }
                    next = next.nextElementSibling;
                }
                h.style.display = anyVisible ? '' : 'none';
            });

            // Highlight first visible row.
            var first = null;
            rows.forEach(function(r) {
                if (!first && r.style.display !== 'none') { first = r; }
                r.classList.remove('active');
            });
            if (first) { first.classList.add('active'); }

            return Date.now();
        }
        """,
        Output('command-palette-search-sync', 'children'),
        Input('command-palette-query', 'value'),
        State('command-palette-commands', 'data'),
    )


