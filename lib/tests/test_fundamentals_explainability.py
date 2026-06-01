"""Tests for fundamentals explainability dependency/highlight helpers."""

from lib.dash.dash_config import get_theme
from lib.dash.callbacks.fundamentals import (
    _canonical_metric,
    _dependency_layers,
    _highlight_metric_rules,
)


def test_canonical_metric_aliases_current_price():
    assert _canonical_metric('Current Price') == 'Year-end Close'


def test_dependency_layers_for_entry_price_include_direct_and_indirect_sources():
    layers = _dependency_layers('Entry Price')

    # Direct dependencies from configured map.
    assert 'Sticker Price' in layers['direct_valuation']
    assert 'MOS' in layers['direct_valuation']

    # Indirect dependencies resolved transitively from Sticker Price branch.
    assert 'Fut. Market Price (10 Y)' in layers['indirect_valuation']


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
