"""Tests for dashboard URL routing helpers."""

import unittest

from lib.dash.routes import is_fundamentals_route, normalize_pathname
from lib.dash.dash_config import ROUTE_FUNDAMENTALS, ROUTE_TERMINAL


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
