"""Tests for fundamentals explainability dependency/highlight helpers."""

from unittest.mock import MagicMock, patch

from lib.dash.dash_config import get_theme
from lib.dash.callbacks.fundamentals import (
    _canonical_metric,
    _dependency_layers,
    _highlight_metric_rules,
)
from lib.dash.callbacks.fundamentals_formulas import _resolve_selected_metric


def test_canonical_metric_aliases_current_price():
    assert _canonical_metric('Current Price') == 'Year-end Close'


def test_dependency_layers_for_entry_price_include_direct_and_indirect_sources():
    layers = _dependency_layers('Entry Price')

    # Direct dependencies from configured map.
    assert 'Sticker Price' in layers['direct_valuation']
    assert 'MOS' in layers['direct_valuation']

    # Indirect dependencies resolved transitively from Sticker Price branch.
    assert 'Fut. Market Price (10 Y)' in layers['indirect_valuation']


def test_dcf_fair_value_sources_trace_soft_inputs():
    from lib.dash.callbacks.fundamentals import _VALUATION_EXPLAIN_MAP

    explain = _VALUATION_EXPLAIN_MAP['DCF Fair Value']
    assert explain['sources']['valuation'] == [
        'Cost of Equity',
        'Stage 1 FCFE GR',
        'Terminal GR',
    ]
    layers = _dependency_layers('DCF Fair Value')
    assert 'Cost of Equity' in layers['direct_valuation']
    assert 'Beta (clamped)' in layers['indirect_valuation']

def test_highlight_rules_use_different_colors_for_direct_and_indirect():
    theme = get_theme('dark')

    direct_rules = _highlight_metric_rules(['Entry Price'], theme, tone='direct')
    indirect_rules = _highlight_metric_rules(['Entry Price'], theme, tone='indirect')

    assert direct_rules
    assert indirect_rules

    direct_color = direct_rules[0]['textDecorationColor']
    indirect_color = indirect_rules[0]['textDecorationColor']

    assert direct_color == theme['accent_orange']
    assert indirect_color == theme['accent_cyan']
    assert direct_color != indirect_color


def test_selected_highlight_rule_adds_selected_border_color():
    theme = get_theme('dark')
    selected_rules = _highlight_metric_rules(['Entry Price'], theme, tone='selected')

    assert selected_rules
    assert selected_rules[0]['border'] == f"1px solid {theme['accent_blue']}"


def test_resolve_selected_metric_survives_sibling_table_clear():
    """Clearing DCF/table-b after selecting PEG must keep PEG as the metric.

    Valuation tables write active_cell=None on siblings; those Outputs are also
    Inputs, so the clear re-fires the explain callback. Falling through to the
    remaining selection keeps the formula panel visible.
    """
    val_a_rows = [{'metric': 'PEG', 'value': '0.8'}]
    val_b_rows = [{'metric': 'Entry Price', 'value': '$324.37'}]
    dcf_rows = [{'metric': 'Base FCFE', 'value': '$6,866'}]
    ctx = MagicMock()
    ctx.triggered = [{'prop_id': 'fundamentals-dcf-table.active_cell'}]

    with patch('lib.dash.callbacks.fundamentals_formulas.callback_context', ctx):
        metric = _resolve_selected_metric(
            None,
            None,
            {'row': 0, 'column_id': 'value'},
            None,
            None,
            None,
            val_a_rows,
            val_b_rows,
            None,  # dcf cleared
            dcf_rows,
        )

    assert metric == 'PEG'
