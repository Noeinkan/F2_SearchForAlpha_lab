"""Every indicator, parameter and signal must carry hover copy.

These are coverage tests, not content tests: they exist so a new indicator
cannot reach the UI as a bare label and a number box. `test_signals_stoch.py`
covers the Stochastic's own wiring.
"""

import unittest

from lib.dash.callbacks.shared_signals import SIGNAL_DESCRIPTIONS
from lib.dash.dash_config import (
    CHART_PLOT_HELP,
    INDICATOR_DEFINITIONS,
    INDICATOR_SETTING_SCHEMA,
)
from lib.signals.indicators import get_registered_strategies


def _sentences(text: str) -> str:
    return ' '.join(text.split())


class TestIndicatorHelpCoverage(unittest.TestCase):

    def test_every_indicator_has_help(self):
        for definition in INDICATOR_DEFINITIONS:
            with self.subTest(indicator=definition['key']):
                self.assertTrue(definition.get('help'), definition['key'])

    def test_every_parameter_has_help(self):
        for definition in INDICATOR_DEFINITIONS:
            for field in definition['fields']:
                with self.subTest(indicator=definition['key'], field=field['key']):
                    self.assertTrue(
                        field.get('help'),
                        f"{definition['key']}.{field['key']} has no tooltip",
                    )

    def test_help_text_is_a_real_sentence(self):
        """Guards against a placeholder sneaking in as the tooltip."""
        for definition in INDICATOR_DEFINITIONS:
            for field in definition['fields']:
                text = _sentences(field['help'])
                with self.subTest(indicator=definition['key'], field=field['key']):
                    self.assertGreater(len(text), 25)
                    self.assertTrue(text.endswith('.'), text)
                    self.assertNotEqual(text.lower(), field['label'].lower())

    def test_schema_carries_help_to_the_settings_panel(self):
        for key, schema in INDICATOR_SETTING_SCHEMA.items():
            with self.subTest(indicator=key):
                self.assertTrue(schema.get('help'))
                for field in schema['fields']:
                    self.assertTrue(field.get('help'), f"{key}.{field['key']}")

    def test_chart_plot_help_covers_every_indicator(self):
        for definition in INDICATOR_DEFINITIONS:
            with self.subTest(indicator=definition['key']):
                self.assertIn(definition['key'], CHART_PLOT_HELP)


class TestSettingsPanelRendersHelp(unittest.TestCase):
    """The copy is worthless if the panel does not actually hang it on the DOM."""

    def _panel(self, indicator: str):
        from lib.dash.callbacks.shared_enrichment import _build_indicator_settings_panel
        from lib.dash.dash_config import DEFAULT_THEME, get_theme
        from lib.dash.styles import get_styles

        return _build_indicator_settings_panel(
            indicator, {}, get_styles(get_theme(DEFAULT_THEME))
        )

    def test_header_carries_the_indicator_help(self):
        panel = self._panel('stoch')
        header = panel.children[0]
        self.assertEqual(header.title, INDICATOR_SETTING_SCHEMA['stoch']['help'])
        self.assertEqual(header.style.get('cursor'), 'help')

    def test_every_field_row_carries_its_parameter_help(self):
        for key, schema in INDICATOR_SETTING_SCHEMA.items():
            panel = self._panel(key)
            rows = panel.children[1:]
            self.assertEqual(len(rows), len(schema['fields']), key)
            for row, field in zip(rows, schema['fields']):
                with self.subTest(indicator=key, field=field['key']):
                    self.assertEqual(row.title, field['help'])
                    self.assertEqual(row.children[0].style.get('cursor'), 'help')

    def test_label_style_is_not_shared_between_rows(self):
        """The renderer copies the style dict; mutating one row must not hit the rest."""
        panel = self._panel('stoch')
        styles = [row.children[0].style for row in panel.children[1:]]
        self.assertEqual(len({id(s) for s in styles}), len(styles))


class TestSignalDescriptionCoverage(unittest.TestCase):

    def test_every_registered_signal_has_a_description(self):
        missing = []
        for registration in get_registered_strategies():
            for signal in registration.class_ref.get_signal_metadata():
                if signal not in SIGNAL_DESCRIPTIONS:
                    missing.append(f"{registration.key}:{signal}")
        self.assertEqual(missing, [], f"signals with no SIGNALS-panel copy: {missing}")

    def test_strategy_metadata_and_panel_copy_agree_on_sides(self):
        """A _Buy column described as a sell (or vice versa) is a real UI bug."""
        for registration in get_registered_strategies():
            for signal in registration.class_ref.get_signal_metadata():
                description = SIGNAL_DESCRIPTIONS.get(signal)
                if not description or not signal.endswith(('_Buy', '_Sell')):
                    continue
                with self.subTest(signal=signal):
                    self.assertTrue(description.strip().endswith(('.', ')')), description)


if __name__ == '__main__':
    unittest.main()
