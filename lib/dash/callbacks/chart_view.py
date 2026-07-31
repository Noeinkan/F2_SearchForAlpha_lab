"""
Chart viewport callbacks (Phase 8 — performance for large datasets).

Three pieces:

1. A clientside handler turns the chart's ``relayoutData`` (zoom/pan/range
   selector) into a compact ``{start, end}`` in ``chart-view-range-store``,
   or ``None`` on autoscale/reset.
2. The bar-count toolbar readout (``chart-bar-count``) reflects that window.
3. A *gated* rerender downsamples the visible window for oversized series so
   Plotly stays responsive. It ``PreventUpdate``s for any series at/under
   ``DOWNSAMPLE_THRESHOLD`` — i.e. every daily-equity case today — so the
   common path keeps its existing single-writer figure behaviour.
"""

from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate

from lib.dash.chart_builder import (
    DOWNSAMPLE_THRESHOLD,
    create_chart,
    bar_count_summary,
)
from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS, get_theme
from lib.dash.state import dashboard_state
from lib.dash.callbacks.shared import get_enriched
from lib.dash.callbacks.chart_plotly import _build_chart_config


def register_chart_view_callbacks(app) -> None:
    # relayoutData → {start, end} (or None on autoscale/reset). Scans for any
    # `<axis>.range[...]` key so it works whichever subplot the user grabs.
    app.clientside_callback(
        """
        function(relayout) {
            if (!relayout) { return window.dash_clientside.no_update; }
            var start = null, end = null, reset = false;
            for (var k in relayout) {
                if (k.indexOf('.autorange') >= 0 && relayout[k] === true) { reset = true; }
                else if (k.indexOf('.range[0]') >= 0) { start = relayout[k]; }
                else if (k.indexOf('.range[1]') >= 0) { end = relayout[k]; }
                else if (k.indexOf('.range') >= 0 && Array.isArray(relayout[k])) {
                    start = relayout[k][0];
                    end = relayout[k][1];
                }
            }
            if (start != null && end != null) {
                return { start: String(start), end: String(end) };
            }
            if (reset) { return null; }
            return window.dash_clientside.no_update;
        }
        """,
        Output('chart-view-range-store', 'data'),
        Input('financial-chart', 'relayoutData'),
        prevent_initial_call=True,
    )

    @app.callback(
        Output('chart-bar-count', 'children'),
        [Input('data-loaded-store', 'data'),
         Input('chart-view-range-store', 'data')],
    )
    def update_bar_count(data_loaded, view_range):
        """Refresh the toolbar bar-count / interval / span readout."""
        df = dashboard_state.df
        if not data_loaded or df is None:
            return ''
        return bar_count_summary(df, view_range)

    @app.callback(
        Output('financial-chart', 'figure', allow_duplicate=True),
        [Input('chart-view-range-store', 'data')],
        [State({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         State('chart-elements-checklist', 'value'),
         State('signal-checklist', 'value'),
         State('buy-signals', 'value'),
         State('sell-signals', 'value'),
         State('consecutive-signal-mode', 'value'),
         State('signal-cooldown-bars', 'value'),
         State('signal-logic-mode', 'value'),
         State('signal-window', 'value'),
         State('indicator-settings-store', 'data'),
         State('data-loaded-store', 'data')],
        prevent_initial_call=True,
    )
    def rerender_for_zoom(
        view_range,
        plot_values,
        chart_elements,
        selected_signals,
        buy_signals,
        sell_signals,
        consecutive_signal_mode,
        signal_cooldown_bars,
        signal_logic,
        signal_window,
        indicator_settings,
        data_loaded,
    ):
        """Downsample the visible window for oversized series only.

        Gated on ``DOWNSAMPLE_THRESHOLD`` so daily-equity data (which never
        needs it) leaves the figure to the normal single writer and the user's
        client-side zoom is untouched.
        """
        df = dashboard_state.df
        if not data_loaded or df is None or len(df) <= DOWNSAMPLE_THRESHOLD:
            raise PreventUpdate

        enriched = get_enriched(df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
        config = _build_chart_config(
            plot_values,
            chart_elements,
            selected_signals,
            buy_signals,
            sell_signals,
            consecutive_signal_mode,
            signal_cooldown_bars,
            signal_logic,
            signal_window,
            indicator_settings,
        )
        config['view_range'] = view_range
        return create_chart(enriched, config, get_theme())

    @app.callback(
        [
            Output('financial-chart', 'figure', allow_duplicate=True),
            Output('chart-focus-store', 'data'),
        ],
        Input('chart-focus-store', 'data'),
        [
            State({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
            State('chart-elements-checklist', 'value'),
            State('signal-checklist', 'value'),
            State('buy-signals', 'value'),
            State('sell-signals', 'value'),
            State('consecutive-signal-mode', 'value'),
            State('signal-cooldown-bars', 'value'),
            State('signal-logic-mode', 'value'),
            State('signal-window', 'value'),
            State('indicator-settings-store', 'data'),
            State('data-loaded-store', 'data'),
        ],
        prevent_initial_call=True,
    )
    def zoom_chart_to_data_focus(
        focus,
        plot_values,
        chart_elements,
        selected_signals,
        buy_signals,
        sell_signals,
        consecutive_signal_mode,
        signal_cooldown_bars,
        signal_logic,
        signal_window,
        indicator_settings,
        data_loaded,
    ):
        """Zoom the chart when a Data tab row is clicked."""
        if not focus or not data_loaded or dashboard_state.df is None:
            raise PreventUpdate

        df = dashboard_state.df
        enriched = get_enriched(df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
        config = _build_chart_config(
            plot_values,
            chart_elements,
            selected_signals,
            buy_signals,
            sell_signals,
            consecutive_signal_mode,
            signal_cooldown_bars,
            signal_logic,
            signal_window,
            indicator_settings,
        )
        # Large series: slice/downsample the focus window in create_chart
        # (same path as rerender_for_zoom) so Plotly stays responsive.
        focus_range = {'start': focus['start'], 'end': focus['end']}
        if len(df) > DOWNSAMPLE_THRESHOLD:
            config['view_range'] = focus_range

        fig = create_chart(enriched, config, get_theme())

        # shared_xaxes=True: bottom row drives all followers. Updating
        # layout.xaxis (row 1) is a no-op once matches snaps back — same
        # lesson as _add_range_selector.
        selected = list(config.get('selected_plots') or ['candlestick'])
        if 'candlestick' in selected:
            selected = ['candlestick'] + [p for p in selected if p != 'candlestick']
        plot_count = max(len(selected), 1)
        fig.update_xaxes(
            range=[focus['start'], focus['end']],
            row=plot_count,
            col=1,
        )
        return fig, None
