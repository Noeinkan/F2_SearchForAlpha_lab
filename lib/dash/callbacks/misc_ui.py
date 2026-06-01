"""
Misc UI callbacks (tabs, theme, clientside helpers).
"""

from datetime import datetime

from dash import callback_context
from dash.dependencies import Input, Output, State

from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.state import dashboard_state
from lib.dash.styles import get_styles


def register_misc_callbacks(app) -> None:
    @app.callback(
        [Output('panel-backtest', 'style'),
         Output('panel-optimizer', 'style'),
         Output('panel-data', 'style'),
         Output('tab-backtest', 'style'),
         Output('tab-optimizer', 'style'),
         Output('tab-data', 'style')],
        [Input('tab-backtest', 'n_clicks'),
         Input('tab-optimizer', 'n_clicks'),
         Input('tab-data', 'n_clicks')],
        [State('theme-store', 'data')]
    )
    def switch_panel(backtest_clicks, optimizer_clicks, data_clicks, theme_name):
        """Switch between right panel tabs."""
        theme = get_theme(theme_name or DEFAULT_THEME)
        styles = get_styles(theme)

        ctx = callback_context
        if not ctx.triggered:
            # Default to backtest tab
            return (
                {'display': 'block'},
                {'display': 'none'},
                {'display': 'none'},
                {**styles['tab'], **styles['tab_active']},
                styles['tab'],
                styles['tab']
            )

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'tab-backtest':
            return (
                {'display': 'block'},
                {'display': 'none'},
                {'display': 'none'},
                {**styles['tab'], **styles['tab_active']},
                styles['tab'],
                styles['tab']
            )
        if button_id == 'tab-optimizer':
            return (
                {'display': 'none'},
                {'display': 'block'},
                {'display': 'none'},
                styles['tab'],
                {**styles['tab'], **styles['tab_active']},
                styles['tab']
            )
        # tab-data
        return (
            {'display': 'none'},
            {'display': 'none'},
            {'display': 'block'},
            styles['tab'],
            styles['tab'],
            {**styles['tab'], **styles['tab_active']}
        )

    @app.callback(
        [Output('header-status', 'children'),
         Output('status-clock', 'children')],
        [Input('startup-interval', 'n_intervals')]
    )
    def update_header_status(_):
        """Update header status."""
        timestamp = datetime.now().strftime("%H:%M:%S")
        return timestamp, timestamp

    @app.callback(
        [Output('theme-store', 'data'),
         Output('theme-label', 'children')],
        [Input('theme-toggle', 'n_clicks')],
        [State('theme-store', 'data')]
    )
    def toggle_theme(n_clicks, current_theme):
        """Toggle between dark and light themes."""
        current_theme = current_theme or DEFAULT_THEME

        def _format_theme_label(theme_name):
            return '[ LIGHT ]' if theme_name == 'light' else '[ DARK ]'

        if not n_clicks:
            return DEFAULT_THEME, _format_theme_label(DEFAULT_THEME)

        new_theme = 'light' if current_theme != 'light' else DEFAULT_THEME
        dashboard_state.set_theme(new_theme)
        return new_theme, _format_theme_label(new_theme)

    app.clientside_callback(
        """
        function(themeName) {
            document.body.classList.remove('theme-light');
            if (themeName === 'light') {
                document.body.classList.add('theme-light');
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
            document.addEventListener('keydown', function(e) {
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

    app.clientside_callback(
        """
        function(n_clicks, chartLibrary) {
            if (!n_clicks) {
                return window.dash_clientside.no_update;
            }
            if (chartLibrary && chartLibrary !== 'plotly') {
                return window.dash_clientside.no_update;
            }
            const graph = document.getElementById('financial-chart');
            if (!graph || !window.Plotly) {
                return window.dash_clientside.no_update;
            }
            const plotlyGraph = graph.querySelector('.js-plotly-plot');
            if (!plotlyGraph) {
                return window.dash_clientside.no_update;
            }
            window.Plotly.downloadImage(plotlyGraph, {
                format: 'png',
                filename: 'chart',
                height: 800,
                width: 1200,
                scale: 2
            });
            return Date.now();
        }
        """,
        Output('export-img-store', 'data'),
        Input('export-img-btn', 'n_clicks'),
        State('chart-library-toggle', 'value')
    )

