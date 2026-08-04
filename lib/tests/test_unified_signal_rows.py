"""Unified buy/sell signal row pairing for the backtest panel."""

from lib.dash.callbacks.shared_signals import _build_unified_signal_rows


def test_paired_signals_share_one_row():
    rows = _build_unified_signal_rows(
        ['BB_Breakout_Buy', 'RSI_Oversold_Buy'],
        ['BB_Breakout_Sell', 'RSI_Overbought_Sell'],
    )
    by_label = {r['label']: r for r in rows}

    assert by_label['BB Breakout']['buy'] == 'BB_Breakout_Buy'
    assert by_label['BB Breakout']['sell'] == 'BB_Breakout_Sell'


def test_one_sided_signals_do_not_invent_missing_side():
    """Overbought is sell-only; Oversold is buy-only — no ghost opposite."""
    rows = _build_unified_signal_rows(
        ['RSI_Oversold_Buy', 'BB_DoubleBottom_Buy', 'VWAP_CrossAbove_Buy'],
        ['RSI_Overbought_Sell', 'BB_DoubleTop_Sell', 'VWAP_CrossBelow_Sell'],
    )
    by_label = {r['label']: r for r in rows}

    assert by_label['RSI Oversold'] == {
        'label': 'RSI Oversold',
        'category': 'RSI',
        'buy': 'RSI_Oversold_Buy',
        'sell': None,
    }
    assert by_label['RSI Overbought'] == {
        'label': 'RSI Overbought',
        'category': 'RSI',
        'buy': None,
        'sell': 'RSI_Overbought_Sell',
    }
    assert by_label['BB DoubleBottom']['sell'] is None
    assert by_label['BB DoubleTop']['buy'] is None
    assert by_label['VWAP CrossAbove']['sell'] is None
    assert by_label['VWAP CrossBelow']['buy'] is None
