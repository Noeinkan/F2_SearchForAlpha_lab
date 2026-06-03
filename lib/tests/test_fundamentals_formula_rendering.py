"""Tests for fundamentals valuation formula rendering helpers."""

from lib.dash.callbacks import fundamentals as fundamentals_module
from lib.dash.callbacks.fundamentals import (
    _build_substituted_latex,
    _formula_card,
    _parse_display_number,
    _valuation_row_map,
)

_VALUATION_LATEX = fundamentals_module._VALUATION_LATEX


def test_parse_display_number_handles_money_and_percent():
    assert _parse_display_number('$12.50') == 12.5
    assert _parse_display_number('15.00%') == 0.15
    assert _parse_display_number('--') is None


def test_valuation_row_map_canonicalizes_aliases():
    rows = [
        {'metric': 'Current Price', 'value': '$100.00'},
        {'metric': 'MARR', 'value': '15.00%'},
    ]
    mapped = _valuation_row_map(rows)
    assert mapped['Year-end Close'] == '$100.00'
    assert mapped['MARR'] == '15.00%'


def test_build_substituted_latex_entry_price_uses_table_values():
    row_map = {
        'Sticker Price': '$80.00',
        'MOS': '50.00%',
        'Entry Price': '$40.00',
    }
    latex = _build_substituted_latex('Entry Price', row_map)
    assert latex is not None
    assert r'P_{\text{entry}}' in latex
    assert r'\$80.00' in latex
    assert '0.50' in latex
    assert r'\$40.00' in latex


def test_build_substituted_latex_sticker_price_includes_marr():
    row_map = {
        'Fut. Market Price (10 Y)': '$400.00',
        'MARR': '15.00%',
        'Sticker Price': '$98.88',
    }
    latex = _build_substituted_latex('Sticker Price', row_map)
    assert latex is not None
    assert r'P_{\text{sticker}}' in latex
    assert r'\$400.00' in latex
    assert '0.15' in latex
    assert r'\$98.88' in latex


def test_build_substituted_latex_mos_shows_percent_and_multiplier():
    row_map = {'MOS': '50.00%'}
    latex = _build_substituted_latex('MOS', row_map)
    assert latex is not None
    assert r'm_{\text{MOS}}' in latex
    assert '50.00\\%' in latex
    assert '0.50' in latex


def test_formula_card_includes_symbolic_and_substituted_blocks():
    card = _formula_card(r'P_{\text{entry}} = P_{\text{sticker}} \times m_{\text{MOS}}', r'P_{\text{entry}} = 1')
    class_names = [child.className for child in card.children]
    assert any('sfa-formula-symbolic' in name for name in class_names)
    assert any('sfa-formula-substituted' in name for name in class_names)


def test_all_valuation_metrics_have_latex_symbolic():
    explain_metrics = fundamentals_module._VALUATION_EXPLAIN_MAP.keys()
    missing = [metric for metric in explain_metrics if metric not in _VALUATION_LATEX]
    assert not missing, f'Missing LaTeX for: {missing}'
