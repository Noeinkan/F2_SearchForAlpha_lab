"""
Phase 2 layout callbacks — collapsible sidebars + right-panel splitter.

Server side only flips session-store booleans. Clientside callbacks mirror
those flags onto the DOM and wire up the splitter drag so CSS in
`dashboard.css` does all the visual work without a server roundtrip.

Resizing the panels used to have to poke the chart (`Plotly.Plots.resize`) on
every drag frame. Lightweight Charts is created with `autoSize: true` and
watches its own container, so the chart now keeps up on its own.
"""

from dash import callback_context
from dash.dependencies import Input, Output, State
from dash.exceptions import PreventUpdate


def register_layout_callbacks(app) -> None:
    @app.callback(
        Output('sidebar-collapsed', 'data'),
        Input('sidebar-toggle-btn', 'n_clicks'),
        Input('mobile-menu-btn', 'n_clicks'),
        Input('mobile-nav-scrim', 'n_clicks'),
        State('sidebar-collapsed', 'data'),
        prevent_initial_call=True,
    )
    def toggle_sidebar(n_sidebar, n_menu, n_scrim, current):
        if not callback_context.triggered:
            raise PreventUpdate
        trigger = callback_context.triggered[0]['prop_id'].split('.')[0]
        # Scrim always dismisses the drawer (collapsed = closed on phone).
        if trigger == 'mobile-nav-scrim':
            if not n_scrim:
                raise PreventUpdate
            return True
        if trigger == 'mobile-menu-btn' and not n_menu:
            raise PreventUpdate
        if trigger == 'sidebar-toggle-btn' and not n_sidebar:
            raise PreventUpdate
        return not bool(current)

    @app.callback(
        Output('right-panel-collapsed', 'data'),
        Input('right-panel-toggle-btn', 'n_clicks'),
        State('right-panel-collapsed', 'data'),
        prevent_initial_call=True,
    )
    def toggle_right_panel(n_clicks, current):
        if not n_clicks:
            raise PreventUpdate
        return not bool(current)

    # On phones, start with both drawers closed so the chart fills the width.
    # One-shot per page load; session prefs after the user toggles still win
    # for the rest of the session via the stores below.
    app.clientside_callback(
        """
        function(nIntervals) {
            if (!nIntervals || window._sfaPhoneCollapseInit) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            if (!window.matchMedia('(max-width: 900px)').matches) {
                return [window.dash_clientside.no_update, window.dash_clientside.no_update];
            }
            window._sfaPhoneCollapseInit = true;
            return [true, true];
        }
        """,
        [Output('sidebar-collapsed', 'data', allow_duplicate=True),
         Output('right-panel-collapsed', 'data', allow_duplicate=True)],
        Input('startup-interval', 'n_intervals'),
        prevent_initial_call=True,
    )

    # Mirror the collapsed flags onto the DOM. On viewports <1180px the right
    # panel is a slide-out drawer (`sfa-open` controls translateX). On phones
    # (≤900px) the left sidebar is the same pattern, plus a dismiss scrim.
    #
    # The chevrons point at the direction the panel will *move*, so they have to
    # flip with the state: a left sidebar that is open collapses leftward ("<<")
    # and reopens rightward (">>"); the right panel is the mirror image. A fixed
    # glyph reads as pointing the wrong way in one of the two states.
    app.clientside_callback(
        """
        function(sidebarCollapsed, rightCollapsed) {
            const sidebar = document.querySelector('aside.sfa-sidebar');
            const right = document.querySelector('aside.sfa-right-panel');
            const scrim = document.getElementById('mobile-nav-scrim');
            const menuBtn = document.getElementById('mobile-menu-btn');
            const phone = window.matchMedia('(max-width: 900px)').matches;
            const setGlyph = function(id, collapsed, openGlyph, closedGlyph) {
                const btn = document.getElementById(id);
                if (!btn) { return; }
                btn.textContent = collapsed ? closedGlyph : openGlyph;
                btn.title = collapsed ? 'Expand panel' : 'Collapse panel';
                btn.setAttribute('aria-expanded', collapsed ? 'false' : 'true');
            };
            if (sidebar) {
                sidebar.classList.toggle('sfa-collapsed', !!sidebarCollapsed);
                sidebar.classList.toggle('sfa-open', !sidebarCollapsed);
            }
            if (right) {
                right.classList.toggle('sfa-collapsed', !!rightCollapsed);
                right.classList.toggle('sfa-open', !rightCollapsed);
            }
            if (scrim) {
                scrim.classList.toggle('sfa-visible', phone && !sidebarCollapsed);
            }
            if (menuBtn) {
                menuBtn.setAttribute('aria-expanded', (!sidebarCollapsed && phone) ? 'true' : 'false');
                menuBtn.title = (!sidebarCollapsed && phone)
                    ? 'Close navigation'
                    : 'Open navigation (Flow, Fundamentals, controls)';
            }
            setGlyph('sidebar-toggle-btn', !!sidebarCollapsed, '<<', '>>');
            setGlyph('right-panel-toggle-btn', !!rightCollapsed, '>>', '<<');
            return window.dash_clientside.no_update;
        }
        """,
        Output('layout-class-sync', 'children'),
        [Input('sidebar-collapsed', 'data'),
         Input('right-panel-collapsed', 'data')],
    )

    # Splitter drag — written into a hidden dcc.Input by the clientside handler,
    # then read by the server callback that mirrors it into the session store.
    @app.callback(
        Output('right-panel-width', 'data'),
        Input('right-panel-width-input', 'value'),
        prevent_initial_call=True,
    )
    def persist_right_panel_width(value):
        if not value:
            raise PreventUpdate
        try:
            width = int(value)
        except (TypeError, ValueError):
            raise PreventUpdate
        if width < 240 or width > 560:
            raise PreventUpdate
        return width

    # Re-apply the persisted width on initial load (and whenever the splitter
    # commits a new value). Skip when collapsed — width:0 already wins there.
    app.clientside_callback(
        """
        function(width) {
            if (!width) { return window.dash_clientside.no_update; }
            const right = document.querySelector('aside.sfa-right-panel');
            if (!right || right.classList.contains('sfa-collapsed')) {
                return window.dash_clientside.no_update;
            }
            right.style.width = width + 'px';
            right.style.minWidth = width + 'px';
            return window.dash_clientside.no_update;
        }
        """,
        Output('right-panel-width-sync', 'children'),
        Input('right-panel-width', 'data'),
    )

    # One-shot bind of the splitter drag listeners. Idempotent via a flag on
    # the splitter element. Clientside uses mousedown on the handle and
    # mousemove/mouseup on document.
    app.clientside_callback(
        """
        function(n_intervals) {
            const splitter = document.getElementById('right-panel-splitter');
            const right = document.querySelector('aside.sfa-right-panel');
            if (!splitter || !right || splitter._sfaBound) {
                return window.dash_clientside.no_update;
            }
            splitter._sfaBound = true;
            let dragging = false;
            let startX = 0;
            let startWidth = 0;

            // Phase 4: keyboard resize — the splitter now has tabIndex=0 and
            // role="separator" so users navigating by keyboard can resize
            // the right panel with Left/Right arrow keys (8px step; Shift
            // multiplies by 4 for a 32px step). The persistent-width
            // commit happens on keyup so we don't hammer the server.
            splitter.addEventListener('keydown', function(e) {
                if (e.key !== 'ArrowLeft' && e.key !== 'ArrowRight') { return; }
                e.preventDefault();
                const current = parseInt(right.style.width, 10)
                    || right.getBoundingClientRect().width;
                const step = e.shiftKey ? 32 : 8;
                const dx = e.key === 'ArrowLeft' ? step : -step;  // wider on Left
                const next = Math.min(560, Math.max(240, current + dx));
                right.style.width = next + 'px';
                right.style.minWidth = next + 'px';
            });
            splitter.addEventListener('keyup', function() {
                const finalWidth = parseInt(right.style.width, 10) || 0;
                if (!finalWidth) { return; }
                const input = document.getElementById('right-panel-width-input');
                if (input) {
                    const native = Object.getOwnPropertyDescriptor(
                        window.HTMLInputElement.prototype, 'value'
                    );
                    if (native && native.set) { native.set.call(input, String(finalWidth)); }
                    else { input.value = String(finalWidth); }
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                }
            });

            splitter.addEventListener('mousedown', function(e) {
                dragging = true;
                startX = e.clientX;
                startWidth = right.getBoundingClientRect().width;
                splitter.classList.add('dragging');
                document.body.style.cursor = 'col-resize';
                document.body.style.userSelect = 'none';
                e.preventDefault();
            });
            document.addEventListener('mousemove', function(e) {
                if (!dragging) { return; }
                const dx = startX - e.clientX;  // dragging left => wider
                const next = Math.min(560, Math.max(240, startWidth + dx));
                right.style.width = next + 'px';
                right.style.minWidth = next + 'px';
            });
            document.addEventListener('mouseup', function() {
                if (!dragging) { return; }
                dragging = false;
                splitter.classList.remove('dragging');
                document.body.style.cursor = '';
                document.body.style.userSelect = '';
                const finalWidth = parseInt(right.style.width, 10) || 0;
                if (finalWidth) {
                    const input = document.getElementById('right-panel-width-input');
                    if (input) {
                        const native = Object.getOwnPropertyDescriptor(
                            window.HTMLInputElement.prototype, 'value'
                        );
                        if (native && native.set) { native.set.call(input, String(finalWidth)); }
                        else { input.value = String(finalWidth); }
                        input.dispatchEvent(new Event('input', { bubbles: true }));
                    }
                }
            });
            return window.dash_clientside.no_update;
        }
        """,
        Output('splitter-bind-trigger', 'children'),
        Input('startup-interval', 'n_intervals'),
    )