"""Chart callbacks — one server writer for the payload, one client renderer.

The chart is drawn by ``assets/10-sfa-chart.js``. Python's only job is to keep
``chart-payload-store`` current; everything interactive (pan, zoom, crosshair,
autoscale, chart type, price scale) happens on the client.

Output ownership, which is not merely a style preference here — Dash 4 aborts an
entire dispatch batch with "Duplicate callback outputs" if two callbacks write
the same output in one layer, and every control in the app then goes inert:

  chart-payload-store.data   <- update_chart_payload   (this file, only writer)
  chart-render-sync.children <- render_chart           (this file, only writer)
  chart-focus-store.data     <- focus_chart_from_row        (data_table.py)
                              + focus_chart_on_test_window  (test_window.py)

Two writers on chart-focus-store is fine — they are different triggers in
different dispatch layers, and the second one carries allow_duplicate=True.
What Dash 4 rejects is two writers reached in the *same* layer.
"""

from __future__ import annotations

import logging
from datetime import datetime

import pandas as pd
from dash import html
from dash.dcc.express import send_data_frame
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate

from lib.dash.bootstrap import build_default_chart_config
from lib.dash.chart_payload import build_chart_payload, empty_payload
from lib.dash.components import ticker_pill
from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS, get_theme
from lib.dash.signal_markers import trigger_counts
from lib.dash.state import dashboard_state
from lib.dash.callbacks.shared import (
    _collect_selected_plots,
    _build_plot_toggle_values,
    get_enriched,
)

logger = logging.getLogger(__name__)


def _build_chart_config(
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
) -> dict:
    """Assemble the chart config dict from current sidebar state."""
    defaults = build_default_chart_config(indicator_settings or DEFAULT_INDICATOR_SETTINGS)
    chart_elements = (
        chart_elements
        if chart_elements is not None
        else ['candlesticks', 'signals', 'bollinger']
    )
    selected_plots = _collect_selected_plots(plot_values) or defaults['selected_plots']
    return {
        'selected_plots': selected_plots,
        'show_candlesticks': 'candlesticks' in chart_elements,
        'show_bollinger': 'bollinger' in chart_elements,
        'show_sma': 'sma' in chart_elements,
        'show_ema': 'ema' in chart_elements,
        'show_buy_sell_signals': 'signals' in chart_elements,
        'show_legend': 'legend' in chart_elements,
        'selected_signals': selected_signals or [],
        'buy_signal_columns': buy_signals or [],
        'sell_signal_columns': sell_signals or [],
        'consecutive_signal_mode': consecutive_signal_mode or 'scale_in',
        'cooldown_bars': signal_cooldown_bars or 0,
        'signal_logic': signal_logic or 'or',
        'signal_window': signal_window or 0,
        'title': '',
        'indicator_settings': indicator_settings or DEFAULT_INDICATOR_SETTINGS,
    }


# Sidebar inputs that change what the chart shows. Shared by the payload
# builder and the TRIG/REJ counter so the two can never drift apart.
_SIGNAL_INPUTS = [
    Input('chart-elements-checklist', 'value'),
    Input('signal-checklist', 'value'),
    Input('buy-signals', 'value'),
    Input('sell-signals', 'value'),
    Input('consecutive-signal-mode', 'value'),
    Input('signal-cooldown-bars', 'value'),
    Input('signal-logic-mode', 'value'),
    Input('signal-window', 'value'),
    Input('indicator-settings-store', 'data'),
]


def register_chart_callbacks(app) -> None:
    @app.callback(
        [Output({'type': 'plot-toggle', 'indicator': ALL}, 'value'),
         Output('chart-elements-checklist', 'value'),
         Output('signal-checklist', 'value')],
        [Input('preset-apply-store', 'data')],
        prevent_initial_call=True
    )
    def apply_chart_preset(preset_data):
        if not preset_data:
            raise PreventUpdate
        chart = preset_data.get("chart", {})
        plot_values = _build_plot_toggle_values(chart.get("plot_toggles", []))
        return plot_values, chart.get("chart_elements", []), chart.get("signal_checklist", [])

    # ------------------------------------------------------------ payload

    @app.callback(
        [Output('chart-payload-store', 'data'),
         Output('chart-render-target', 'children')],
        [Input('data-loaded-store', 'data'),
         # First paint, clicked by the glue once the canvas exists. Needed
         # because this callback is downstream of `load_data` via
         # `data-loaded-store`, and `load_data` PreventUpdates on a
         # bootstrapped page — Dash then never dispatches this one at all, not
         # even through its other inputs. A real click is a fresh dispatch.
         Input('chart-boot-btn', 'n_clicks'),
         Input({'type': 'plot-toggle', 'indicator': ALL}, 'value')] + _SIGNAL_INPUTS,
        prevent_initial_call='initial_duplicate',
    )
    def update_chart_payload(
        data_loaded,
        _boot,
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
    ):
        """Rebuild the chart payload from sidebar selections and data loads.

        Note what is *not* an Input here: the visible range. The client owns
        zoom, so panning never re-enters Python — which is both why the chart
        feels immediate and why there is no longer a store that both this
        callback and ``load_data`` could write in the same dispatch layer.

        ``chart-render-target`` is written only to give ``dcc.Loading``
        something to track while the payload is being built.
        """
        theme = get_theme()
        if not data_loaded or dashboard_state.df is None:
            return empty_payload(theme), ''

        try:
            df = get_enriched(dashboard_state.df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
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
            config['interval'] = dashboard_state.interval
            config['ticker'] = dashboard_state.ticker
            return build_chart_payload(df, config, theme), ''
        except Exception as exc:
            logger.error("update_chart_payload failed: %s", exc, exc_info=True)
            return empty_payload(theme, f"Chart error: {str(exc)[:60]}"), ''

    # ------------------------------------------------------------- render

    # Payload/theme/type/scale all land here. Keeping them in one clientside
    # callback (rather than one each) means a data load that also changes the
    # theme cannot produce two competing renders.
    app.clientside_callback(
        """
        function(payload, themeName, chartType, scaleMode) {
            if (!window.sfaChart) { return ''; }
            window.sfaChart.setChartType(chartType || 'candles');
            if (payload) { window.sfaChart.apply(payload); }
            window.sfaChart.setScaleMode(scaleMode || 'normal');
            if (typeof window.sfaChart.nudge === 'function') {
                window.sfaChart.nudge();
            }
            return '';
        }
        """,
        Output('chart-render-sync', 'children'),
        [Input('chart-payload-store', 'data'),
         Input('theme-store', 'data'),
         Input('chart-type-store', 'data'),
         Input('price-scale-store', 'data')],
    )

    # Data tab row click → scroll the chart to that window. No rebuild: the
    # bars are already on the client, so this is a time-scale call, not a
    # round trip. (The old implementation rebuilt the whole figure here.)
    app.clientside_callback(
        """
        function(focus) {
            if (!focus || !window.sfaChart || !window.sfaChart.isReady()) { return ''; }
            var toTime = function (value) {
                if (value == null) { return null; }
                var payload = window.sfaChart._state.payload;
                if (payload && payload.meta && payload.meta.subdaily) {
                    return Math.floor(Date.parse(value + 'T00:00:00Z') / 1000);
                }
                return String(value).slice(0, 10);
            };
            window.sfaChart.setVisibleRange(toTime(focus.start), toTime(focus.end));
            return '';
        }
        """,
        Output('chart-focus-sync', 'children'),
        Input('chart-focus-store', 'data'),
        prevent_initial_call=True,
    )

    # Toolbar buttons that act purely on the client.
    app.clientside_callback(
        """
        function(fitClicks, imgClicks, fullClicks, ticker) {
            var ctx = window.dash_clientside.callback_context;
            if (!ctx || !ctx.triggered || !ctx.triggered.length) { return ''; }
            var id = ctx.triggered[0].prop_id.split('.')[0];
            if (!window.sfaChart) { return ''; }
            if (id === 'chart-fit-btn') {
                window.sfaChart.fitContent();
            } else if (id === 'export-img-btn') {
                window.sfaChart.screenshot((ticker || 'chart') + '.png');
            } else if (id === 'chart-fullscreen-btn') {
                var frame = document.getElementById('chart-frame');
                if (!frame) { return ''; }
                if (document.fullscreenElement) { document.exitFullscreen(); }
                else if (frame.requestFullscreen) { frame.requestFullscreen(); }
            }
            return '';
        }
        """,
        Output('chart-tools-sync', 'children'),
        [Input('chart-fit-btn', 'n_clicks'),
         Input('export-img-btn', 'n_clicks'),
         Input('chart-fullscreen-btn', 'n_clicks')],
        State('ticker-dropdown', 'value'),
        prevent_initial_call=True,
    )

    # Toolbar selects → persisted stores. Separate callbacks so each store
    # keeps exactly one writer.
    app.clientside_callback(
        "function(v) { return v || 'candles'; }",
        Output('chart-type-store', 'data'),
        Input('chart-type-select', 'value'),
    )

    app.clientside_callback(
        "function(v) { return v || 'normal'; }",
        Output('price-scale-store', 'data'),
        Input('price-scale-select', 'value'),
    )

    # ------------------------------------------------------------ readouts

    @app.callback(
        Output('chart-bar-count', 'children'),
        Input('chart-payload-store', 'data'),
    )
    def update_bar_count(payload):
        """Seed the toolbar readout on load.

        The glue recomputes this locally on every pan — routing that through a
        callback would put the server back in the interaction loop.
        """
        if not payload or not payload.get('candles'):
            return ''
        meta = payload.get('meta', {})
        candles = payload['candles']

        def stamp(value):
            if isinstance(value, str):
                return value
            ts = pd.Timestamp(value, unit='s', tz='UTC')
            return ts.strftime('%Y-%m-%d %H:%M' if meta.get('subdaily') else '%Y-%m-%d')

        label = (meta.get('interval') or '').upper()
        return (
            f"{len(candles):,} bars · {label} · "
            f"{stamp(candles[0]['time'])} → {stamp(candles[-1]['time'])}"
        )

    @app.callback(
        Output('signal-count-bar', 'children'),
        [Input('data-loaded-store', 'data')] + _SIGNAL_INPUTS,
    )
    def update_signal_count_bar(
        data_loaded,
        chart_elements,
        selected_signals,
        buy_signals,
        sell_signals,
        consecutive_signal_mode,
        signal_cooldown_bars,
        signal_logic,
        signal_window,
        indicator_settings
    ):
        theme = get_theme()

        def pills(accepted, rejected):
            return html.Div([
                ticker_pill('TRIG', accepted, color='amber'),
                html.Span('|', className='num', style={'color': theme['border_primary']}),
                ticker_pill('REJ', rejected, color='down'),
            ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'})

        if not data_loaded or dashboard_state.df is None:
            return pills('--', '--')

        df = get_enriched(dashboard_state.df, indicator_settings or DEFAULT_INDICATOR_SETTINGS)
        # Same engine the markers come from, so the counts always describe
        # exactly what is drawn.
        counts = trigger_counts(
            df,
            selected_signals or [],
            buy_signals or [],
            sell_signals or [],
            logic=signal_logic or 'or',
            window=signal_window or 0,
            mode=consecutive_signal_mode or 'scale_in',
            cooldown=signal_cooldown_bars or 0,
        )
        return pills(counts['accepted'], counts['rejected'])

    @app.callback(
        Output('download-csv', 'data'),
        [Input('export-csv-btn', 'n_clicks')],
        [State('data-loaded-store', 'data'),
         State('ticker-dropdown', 'value')],
        prevent_initial_call=True
    )
    def export_chart_csv(n_clicks, data_loaded, ticker):
        """Export current chart data (with indicators) to CSV."""
        if not data_loaded or dashboard_state.df is None:
            raise PreventUpdate

        df = dashboard_state.df.copy()
        if isinstance(df.index, pd.DatetimeIndex):
            df = df.reset_index().rename(columns={'index': 'Date'})
        if 'Date' in df.columns:
            df['Date'] = pd.to_datetime(df['Date']).dt.strftime('%Y-%m-%d')
            cols = ['Date'] + [col for col in df.columns if col != 'Date']
            df = df.loc[:, cols]

        export_date = datetime.now().strftime('%Y%m%d')
        safe_ticker = (ticker or 'data').replace('/', '-')
        filename = f"{safe_ticker}_chart_data_{export_date}.csv"
        return send_data_frame(df.to_csv, filename, index=False, float_format='%.6f')
