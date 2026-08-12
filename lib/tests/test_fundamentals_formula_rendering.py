"""Tests for fundamentals valuation formula rendering helpers."""

from lib.dash.callbacks import fundamentals as fundamentals_module
from lib.dash.callbacks.fundamentals import (
    _build_substituted_equation,
    _build_symbolic_equation,
    _formula_card,
    _parse_display_number,
    _valuation_row_map,
)


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


def test_build_substituted_equation_entry_price_uses_table_values():
    row_map = {
        'Sticker Price': '$80.00',
        'MOS': '50.00%',
        'Entry Price': '$40.00',
    }
    equation = _build_substituted_equation('Entry Price', row_map)
    assert equation is not None
    text = str(equation)
    assert 'entry' in text
    assert '$80.00' in text
    assert '$40.00' in text


def test_build_substituted_equation_sticker_price_includes_marr():
    row_map = {
        'Fut. Market Price (10 Y)': '$400.00',
        'MARR': '15.00%',
        'Sticker Price': '$98.88',
    }
    equation = _build_substituted_equation('Sticker Price', row_map)
    assert equation is not None
    text = str(equation)
    assert 'sticker' in text
    assert '$400.00' in text
    assert '$98.88' in text


def test_build_substituted_equation_mos_shows_percent_and_multiplier():
    row_map = {'MOS': '50.00%'}
    equation = _build_substituted_equation('MOS', row_map)
    assert equation is not None
    text = str(equation)
    assert 'MOS' in text
    assert '50.00%' in text
    assert '0.50' in text


def test_build_substituted_equation_cost_of_equity_uses_numeric_inputs():
    row_map = {
        'Beta (clamped)': '2.00',
        'Cost of Equity': '14.00%',
    }
    equation = _build_substituted_equation('Cost of Equity', row_map)
    assert equation is not None
    text = str(equation)
    assert '4.00%' in text
    assert '2.00' in text
    assert '5.00%' in text
    assert '14.00%' in text
    assert 'r_f' not in text
    assert 'ERP' not in text


def test_build_symbolic_equation_entry_price():
    equation = _build_symbolic_equation('Entry Price')
    assert equation is not None
    assert equation.className == 'sfa-formula-equation'


def test_formula_card_includes_symbolic_and_substituted_blocks():
    symbolic = _build_symbolic_equation('Entry Price')
    substituted = _build_substituted_equation(
        'Entry Price',
        {'Sticker Price': '$80.00', 'MOS': '50.00%', 'Entry Price': '$40.00'},
    )
    card = _formula_card(symbolic, substituted)
    class_names = [child.className for child in card.children]
    assert any('sfa-formula-symbolic' in name for name in class_names)
    assert any('sfa-formula-substituted' in name for name in class_names)


def test_all_valuation_metrics_have_explain_what_and_why():
    for metric, details in fundamentals_module._VALUATION_EXPLAIN_MAP.items():
        assert details.get('what'), f'Missing what for {metric}'
        assert details.get('why_use'), f'Missing why_use for {metric}'


def test_all_valuation_metrics_have_symbolic_equation():
    missing = [
        metric for metric in fundamentals_module._VALUATION_EXPLAIN_MAP
        if _build_symbolic_equation(metric) is None
    ]
    assert not missing, f'Missing symbolic equation for: {missing}'


def test_render_payload_quarterly_keeps_annual_valuation_and_big_five():
    from lib.dash.callbacks.fundamentals import _render_payload
    from lib.dash.dash_config import DEFAULT_THEME, get_theme

    payload = {
        'ticker': 'TEST',
        'currency': 'USD',
        'as_of': '2026-01-01 00:00:00',
        'last_price': 100.0,
        'quality_notes': ['All core annual fields available'],
        'annual': {
            'years': [2023, 2024],
            'valuation': [{'metric': 'Entry Price', 'value': '$40.00'}],
            'dcf': [{'metric': 'DCF Fair Value', 'value': '$55.00'}],
            'dcf_sensitivity': [],
            'big_five': [{'metric': 'Equity-GR', 'unit': '%', '2023': '10.00%', '2024': '10.00%'}],
            'big_five_note': 'NOTE: Big Five should be >= 10% per year over the last 10 years.',
        },
        'quarterly': {
            'years': ['2024-Q1', '2024-Q2'],
            'financials': [{
                'metric': 'Sales (Rev)',
                'unit': '$mil',
                '2024-Q1': '$100',
                '2024-Q2': '$110',
            }],
            'chart_series': {'Sales': [100.0, 110.0]},
        },
    }
    rendered = _render_payload(payload, 'quarterly', get_theme(DEFAULT_THEME))
    text = str(rendered)
    assert 'Valuation' in text
    assert 'DCF (FCFE)' in text
    assert 'Big Five' in text
    assert 'Financials' in text
    assert '2024-Q2' in text
    assert 'sfa-fundamentals-band-quality' in text
    assert 'sfa-fundamentals-band-growth' in text
    assert 'sfa-fundamentals-band-financials' in text
    assert 'sfa-fundamentals-band-valuation' in text
    assert 'sfa-fundamentals-valuation-band' in text
    assert 'sfa-fundamentals-valuation-rule1' in text
    assert 'sfa-fundamentals-valuation-dcf' in text

    # Story order: Quality (Big Five) → Growth (charts) → Financials → Valuation
    idx_quality = text.find('sfa-fundamentals-band-quality')
    idx_growth = text.find('sfa-fundamentals-band-growth')
    idx_financials = text.find('sfa-fundamentals-band-financials')
    idx_valuation = text.find('sfa-fundamentals-band-valuation')
    assert idx_quality != -1
    assert idx_quality < idx_growth < idx_financials < idx_valuation
    assert text.find('Big Five') < text.find('sfa-fundamentals-charts')
    assert text.find('sfa-fundamentals-charts') < text.find('fundamentals-financial-table')
    assert text.find('fundamentals-financial-table') < text.find('DCF (FCFE)')
