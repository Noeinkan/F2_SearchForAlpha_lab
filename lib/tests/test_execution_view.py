"""
Tests for the Execution Type explainer UI.

Two jobs:
  1. structural tripwires — the ids and classes the callbacks target must exist;
  2. an honesty guard — the panel copy must not re-acquire claims the engine
     does not implement. The captions this feature replaced were wrong for
     months because nothing checked them.
"""

from __future__ import annotations

import pytest

from lib.dash.dash_config import THEMES, get_theme
from lib.dash.execution_glossary import (
    ACTIVE_CONTROLS,
    CELL_TONES,
    EXECUTION_SECTIONS,
    MECHANICS_ROWS,
    MODE_ORDER,
    MODE_SPECS,
    PREDICT_QUESTIONS,
)
from lib.dash.execution_view import (
    render_execution_learn_content,
    render_fingerprint,
    render_mechanics_matrix,
    render_mode_preview,
    render_progress_dots,
    sparkline_data_uri,
)
from lib.dash.layout.shell import create_dashboard_layout


@pytest.fixture(scope='module')
def theme():
    return get_theme()


def _serialized(component) -> str:
    return str(component)


def _walk(component):
    """Depth-first walk over a Dash component tree."""
    yield component
    children = getattr(component, 'children', None)
    if children is None:
        return
    if not isinstance(children, (list, tuple)):
        children = [children]
    for child in children:
        if hasattr(child, 'children') or hasattr(child, 'id'):
            yield from _walk(child)


def _find_by_id(tree, component_id):
    return next((c for c in _walk(tree) if getattr(c, 'id', None) == component_id), None)


# --------------------------------------------------------------------------- #
# Glossary integrity
# --------------------------------------------------------------------------- #

class TestGlossary:
    def test_every_mode_has_a_spec(self):
        assert set(MODE_SPECS) == set(MODE_ORDER)
        for spec in MODE_SPECS.values():
            assert spec['name'] and spec['caption'] and spec['one_liner']

    def test_every_matrix_row_answers_all_three_modes(self):
        for row in MECHANICS_ROWS:
            for mode in MODE_ORDER:
                assert row.get(mode), f"{row['label']} has no answer for {mode}"

    def test_cell_tones_reference_real_rows_and_modes(self):
        labels = {row['label'] for row in MECHANICS_ROWS}
        for label, mode in CELL_TONES:
            assert label in labels
            assert mode in MODE_ORDER

    def test_every_mode_has_a_predict_question(self):
        assert set(PREDICT_QUESTIONS) == set(MODE_ORDER)
        for spec in PREDICT_QUESTIONS.values():
            assert len(spec['options']) >= 2
            assert spec['sting']

    def test_active_controls_cover_every_mode(self):
        assert set(ACTIVE_CONTROLS) == set(MODE_ORDER)
        assert ACTIVE_CONTROLS['accumulation'] == ('Amount per buy',)

    def test_sections_are_non_empty(self):
        assert len(EXECUTION_SECTIONS) >= 3
        for section in EXECUTION_SECTIONS:
            assert section['title'] and section['body']


# --------------------------------------------------------------------------- #
# Honesty guards
# --------------------------------------------------------------------------- #

class TestCopyMatchesTheEngine:
    """The specific false claims this feature was built to remove."""

    def test_no_mode_claims_it_buys_or_sells_one_hundred_percent(self):
        for spec in MODE_SPECS.values():
            blob = f"{spec['suffix']} {spec['caption']} {spec['one_liner']}".lower()
            assert '100%' not in blob

    def test_rebalancing_copy_says_portfolio_value_not_cash(self):
        spec = MODE_SPECS['rebalancing']
        assert 'portfolio' in spec['caption'].lower()
        blob = spec['one_liner'].lower()
        assert 'portfolio value' in blob

    def test_accumulation_copy_states_it_never_sells(self):
        blob = (MODE_SPECS['accumulation']['caption'] + ' '
                + MODE_SPECS['accumulation']['one_liner']).lower()
        assert 'never sells' in blob or 'only ever accumulates' in blob

    def test_matrix_marks_accumulation_sells_as_ignored(self):
        row = next(r for r in MECHANICS_ROWS if r['label'] == 'On a SELL signal')
        assert 'ignored' in row['accumulation'].lower()
        assert CELL_TONES[('On a SELL signal', 'accumulation')] == 'off'


# --------------------------------------------------------------------------- #
# Renderers
# --------------------------------------------------------------------------- #

class TestRenderers:
    @pytest.mark.parametrize('mode', MODE_ORDER)
    def test_preview_quotes_a_dollar_figure(self, theme, mode):
        assert '$' in _serialized(render_mode_preview(theme, mode))

    @pytest.mark.parametrize('mode', MODE_ORDER)
    def test_fingerprint_is_a_self_contained_svg(self, theme, mode):
        html = _serialized(render_fingerprint(theme, mode))
        assert 'data:image/svg+xml' in html
        assert 'http://' not in html.replace('http://www.w3.org/2000/svg', '')

    def test_sparkline_handles_a_flat_series_without_dividing_by_zero(self):
        uri = sparkline_data_uri([100.0, 100.0, 100.0], '#fff')
        assert uri.startswith('data:image/svg+xml')

    def test_matrix_renders_every_row(self, theme):
        html = _serialized(render_mechanics_matrix(theme))
        for row in MECHANICS_ROWS:
            assert row['label'] in html

    def test_progress_dots_mark_only_explored_modes(self, theme):
        html = _serialized(render_progress_dots(theme, ['trading']))
        assert html.count('is-done') == 1

    @pytest.mark.parametrize('mode', MODE_ORDER)
    def test_modal_body_carries_the_hook_classes(self, theme, mode):
        html = _serialized(render_execution_learn_content(theme, mode, revealed=True))
        for cls in ('sfa-exec-learn-body', 'sfa-exec-matrix', 'sfa-exec-ledger',
                    'sfa-exec-tabs', 'sfa-exec-predict'):
            assert cls in html

    def test_ledger_is_hidden_until_the_user_commits_to_a_guess(self, theme):
        """Predict-then-reveal only teaches if the answer is not visible first."""
        html = _serialized(render_execution_learn_content(theme, 'trading', revealed=False))
        assert 'sfa-exec-ledger' not in html
        assert 'sfa-exec-reveal' in html

    def test_reveal_explains_why(self, theme):
        html = _serialized(render_execution_learn_content(theme, 'trading',
                                                          guess=0, revealed=True))
        assert 'sfa-exec-sting' in html

    @pytest.mark.parametrize('theme_name', sorted(THEMES))
    def test_renders_in_every_theme(self, theme_name):
        html = _serialized(
            render_execution_learn_content(get_theme(theme_name), 'rebalancing', revealed=True)
        )
        assert 'sfa-exec-learn-body' in html

    def test_accumulation_sandbox_names_the_inert_controls(self, theme):
        html = _serialized(render_execution_learn_content(theme, 'accumulation', revealed=True))
        assert 'Ignored in this mode' in html
        assert 'Trailing stop' in html


# --------------------------------------------------------------------------- #
# Layout wiring — ids the callbacks depend on
# --------------------------------------------------------------------------- #

class TestLayoutWiring:
    @pytest.fixture(scope='class')
    def layout_html(self):
        return _serialized(create_dashboard_layout(get_theme()))

    def test_help_targets_and_modal_ids_exist(self, layout_html):
        for component_id in (
            'help-strategy-mode', 'execution-learn-button', 'execution-learn-modal',
            'execution-learn-modal-body', 'execution-learn-close',
            'execution-learn-state', 'execution-explored-store',
            'accumulation-sell-warning',
        ):
            assert component_id in layout_html

    @pytest.mark.parametrize('mode', MODE_ORDER)
    def test_per_mode_help_and_preview_targets_exist(self, layout_html, mode):
        assert f'help-strategy-{mode}' in layout_html
        assert f'preview-mode-{mode}' in layout_html

    def test_scale_in_defaults_to_full_size(self):
        """A 25% default made every Trading entry a quarter of what the UI implied."""
        control = _find_by_id(create_dashboard_layout(get_theme()), 'position-scaling-pct')
        assert control is not None
        assert control.value == 100
