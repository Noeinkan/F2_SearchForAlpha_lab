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


def test_dependency_chips_include_live_values():
    from lib.dash.callbacks.fundamentals_formulas import _dependency_chip_rows

    layers = {
        'direct_valuation': ['Rule #1 PE', 'Estimated EPS GR'],
        'indirect_valuation': [],
        'direct_financial': [],
        'indirect_financial': [],
        'direct_big_five': [],
        'indirect_big_five': [],
    }
    row_map = {'Rule #1 PE': '40.0', 'Estimated EPS GR': '50.00%'}
    chips = _dependency_chip_rows(layers, row_map)
    assert chips is not None
    text = str(chips)
    assert 'Rule #1 PE' in text
    assert '40.0' in text
    assert '50.00%' in text
    assert 'sfa-dep-chip-direct' in text


def test_dependency_chip_uses_pattern_matched_button_id():
    from lib.dash.callbacks.fundamentals_formulas import _dependency_chip

    chip = _dependency_chip('Rule #1 PE', {'Rule #1 PE': '40.0'}, tone='direct')
    assert chip.id == {'type': 'sfa-dep-chip', 'metric': 'Rule #1 PE'}
    assert chip.n_clicks == 0
    assert 'sfa-dep-chip-direct' in chip.className


def test_locate_metric_cell_finds_valuation_a_and_b_rows():
    from lib.dash.callbacks.fundamentals_formulas import _locate_metric_cell

    val_a = [{'metric': 'PEG', 'value': '0.8'}, {'metric': 'Rule #1 PE', 'value': '40.0'}]
    val_b = [{'metric': 'MARR', 'value': '15.00%'}, {'metric': 'Entry Price', 'value': '$324.37'}]
    dcf = [{'metric': 'Base FCFE', 'value': '$1'}]

    peg = _locate_metric_cell('PEG', None, None, val_a, val_b, dcf)
    assert peg is not None
    assert peg[0] == 'fundamentals-valuation-table-a'
    assert peg[1]['row'] == 0

    entry = _locate_metric_cell('Entry Price', None, None, val_a, val_b, dcf)
    assert entry is not None
    assert entry[0] == 'fundamentals-valuation-table-b'
    assert entry[1]['row'] == 1


def test_triggered_dep_chip_metric_parses_prop_id():
    from lib.dash.callbacks.fundamentals_formulas import _triggered_dep_chip_metric

    prop_id = '{"metric":"Rule #1 PE","type":"sfa-dep-chip"}.n_clicks'
    assert _triggered_dep_chip_metric(prop_id) == 'Rule #1 PE'
    assert _triggered_dep_chip_metric('fundamentals-valuation-table-a.active_cell') is None


def test_valuation_explain_content_includes_subtitle_and_chips():
    from lib.dash.callbacks.fundamentals_formulas import (
        _VALUATION_EXPLAIN_MAP,
        _valuation_explain_content,
    )
    from lib.dash.dash_config import get_theme

    rows = [
        {'metric': 'PEG', 'value': '0.8'},
        {'metric': 'Rule #1 PE', 'value': '40.0'},
        {'metric': 'Estimated EPS GR', 'value': '50.00%'},
    ]
    content = _valuation_explain_content(
        'PEG',
        _VALUATION_EXPLAIN_MAP['PEG'],
        get_theme('bloomberg'),
        rows,
    )
    blob = str(content)
    assert 'Sources highlighted above' in blob
    assert 'Esc to close' in blob
    assert 'sfa-dep-chip' in blob
    assert 'Rule #1 PE' in blob
    assert 'Data sources' not in blob
    assert "{'type': 'sfa-dep-chip'" in blob or '{"type":"sfa-dep-chip"' in blob or "sfa-dep-chip" in blob
