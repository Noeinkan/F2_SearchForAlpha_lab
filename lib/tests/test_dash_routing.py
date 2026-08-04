"""Tests for dashboard URL routing helpers."""

import unittest

from lib.dash.routes import (
    build_fundamentals_path,
    build_flow_path,
    build_optimize_path,
    extract_path_ticker,
    is_flow_route,
    is_fundamentals_route,
    is_optimize_route,
    is_ticker_terminal_route,
    normalize_pathname,
    parse_path,
    ticker_from_search,
)
from lib.dash.dash_config import ROUTE_FUNDAMENTALS, ROUTE_OPTIMIZE, ROUTE_TERMINAL


class TestDashRouting(unittest.TestCase):
    def test_normalize_pathname_root(self):
        self.assertEqual(normalize_pathname(None), ROUTE_TERMINAL)
        self.assertEqual(normalize_pathname('/'), ROUTE_TERMINAL)
        self.assertEqual(normalize_pathname('//'), ROUTE_TERMINAL)

    def test_normalize_pathname_strips_trailing_slash(self):
        self.assertEqual(normalize_pathname('/fundamentals/'), ROUTE_FUNDAMENTALS)

    def test_is_fundamentals_route(self):
        self.assertFalse(is_fundamentals_route('/'))
        self.assertFalse(is_fundamentals_route('/other'))
        self.assertTrue(is_fundamentals_route('/fundamentals'))
        self.assertTrue(is_fundamentals_route('/fundamentals/'))
        self.assertTrue(is_fundamentals_route('/fundamentals/TSLA'))
        self.assertTrue(is_fundamentals_route('/fundamentals/tsla'))

    def test_is_flow_route(self):
        self.assertFalse(is_flow_route('/'))
        self.assertTrue(is_flow_route('/flow'))
        self.assertTrue(is_flow_route('/flow/'))
        self.assertTrue(is_flow_route('/flow/AAPL'))

    def test_is_optimize_route(self):
        self.assertFalse(is_optimize_route('/'))
        self.assertFalse(is_optimize_route('/flow/AAPL'))
        self.assertTrue(is_optimize_route('/optimize'))
        self.assertTrue(is_optimize_route('/optimize/'))
        self.assertTrue(is_optimize_route('/optimize/TSLA'))
        self.assertTrue(is_optimize_route('/optimize/tsla'))

    def test_is_ticker_terminal_route(self):
        self.assertFalse(is_ticker_terminal_route('/'))
        self.assertFalse(is_ticker_terminal_route('/fundamentals/TSLA'))
        self.assertTrue(is_ticker_terminal_route('/ticker/MSFT'))

    def test_parse_path(self):
        self.assertEqual(parse_path('/'), ('terminal', None))
        self.assertEqual(parse_path('/fundamentals'), ('fundamentals', None))
        self.assertEqual(parse_path('/fundamentals/TSLA'), ('fundamentals', 'TSLA'))
        self.assertEqual(parse_path('/flow/AAPL'), ('flow', 'AAPL'))
        self.assertEqual(parse_path('/optimize/TSLA'), ('optimize', 'TSLA'))
        self.assertEqual(parse_path('/ticker/MSFT'), ('ticker_terminal', 'MSFT'))
        self.assertEqual(parse_path('/unknown/foo'), ('unknown', None))

    def test_extract_path_ticker(self):
        self.assertIsNone(extract_path_ticker('/'))
        self.assertIsNone(extract_path_ticker('/fundamentals'))
        self.assertEqual(extract_path_ticker('/fundamentals/TSLA'), 'TSLA')
        self.assertEqual(extract_path_ticker('/flow/AAPL'), 'AAPL')
        self.assertEqual(extract_path_ticker('/optimize/MSFT'), 'MSFT')

    def test_ticker_from_search(self):
        self.assertIsNone(ticker_from_search(None))
        self.assertIsNone(ticker_from_search(''))
        self.assertEqual(ticker_from_search('?ticker=TSLA'), 'TSLA')
        self.assertEqual(ticker_from_search('?foo=1&ticker=aapl'), 'AAPL')

    def test_build_paths(self):
        self.assertEqual(build_fundamentals_path(), ROUTE_FUNDAMENTALS)
        self.assertEqual(build_fundamentals_path('TSLA'), '/fundamentals/TSLA')
        self.assertEqual(build_flow_path('AAPL'), '/flow/AAPL')
        self.assertEqual(build_optimize_path(), ROUTE_OPTIMIZE)
        self.assertEqual(build_optimize_path('TSLA'), '/optimize/TSLA')


class TestDashShellRoutes(unittest.TestCase):
    def test_fundamentals_ticker_route_serves_shell_with_boot_script(self):
        import dash
        import dash_bootstrap_components as dbc

        from lib.dash.integrated_dashboard import create_dashboard_layout
        from lib.dash.dash_config import DEFAULT_THEME, get_theme

        theme = get_theme(DEFAULT_THEME)
        app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        app.layout = create_dashboard_layout(theme)

        def _serve_dash_shell():
            import json
            from flask import request

            html = app.index()
            path = request.path or '/'
            query = request.query_string.decode('utf-8')
            search = f'?{query}' if query else ''
            boot = json.dumps({'pathname': path, 'search': search})
            script = f'<script>window.__SFA_BOOT_URL__={boot};</script>'
            if isinstance(html, str):
                html = html.replace('</head>', f'{script}</head>', 1)
            return html

        for route in ("/fundamentals", "/fundamentals/", "/fundamentals/TSLA"):
            app.server.add_url_rule(route, endpoint=f"test_{route.replace('/', '_')}", view_func=_serve_dash_shell)

        client = app.server.test_client()
        base = client.get("/fundamentals/").data
        ticker = client.get("/fundamentals/TSLA").data
        self.assertIn(b"react-entry-point", base)
        self.assertIn(b'"/fundamentals/TSLA"', ticker)
        self.assertIn(b"__SFA_BOOT_URL__", ticker)

    def test_optimize_route_layout_includes_overlay(self):
        import dash
        import dash_bootstrap_components as dbc

        from lib.dash.integrated_dashboard import create_dashboard_layout
        from lib.dash.dash_config import DEFAULT_THEME, get_theme

        theme = get_theme(DEFAULT_THEME)
        app = dash.Dash(__name__, external_stylesheets=[dbc.themes.BOOTSTRAP])
        app.layout = create_dashboard_layout(theme)
        layout_str = str(app.layout)
        self.assertIn('optimize-overlay', layout_str)
        self.assertIn('open-optimizer-button', layout_str)
        self.assertIn('open-optimizer-from-teaser', layout_str)
        self.assertIn('run-optimization-btn', layout_str)
        self.assertIn('optimize-chart-slot', layout_str)
        self.assertIn('opt-initial-capital', layout_str)
        self.assertIn('optimizer-buy-universe', layout_str)
        self.assertIn('optimizer-realistic-ranking', layout_str)
        self.assertIn('validate-oos-btn', layout_str)
        self.assertIn('optimizer-landscape-graph', layout_str)
        self.assertIn('optimizer-history-panel', layout_str)
        self.assertIn('bayesian-strategy-dropdown', layout_str)
        self.assertIn('run-bayesian-btn', layout_str)
        self.assertIn('chart-area-home', layout_str)
