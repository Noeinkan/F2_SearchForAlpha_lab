"""Header watchlist strip and its editor: rendering, clicks, draft edits, the cap."""

from lib.dash.callbacks.header_watchlist import add_to_draft, clicked_index
from lib.dash.layout.header_watchlist import build_editor_rows, build_header_chips
from lib.dash.watchlist_storage import (
    MAX_WATCHLIST_SYMBOLS,
    set_symbols,
    symbols_in,
    toggle_symbol,
)

TEN = ['NVDA', 'MSFT', 'AAPL', 'GOOGL', 'AMZN', 'META', 'AVGO', 'TSLA', 'BRK-B', 'JPM']


def test_chips_mark_the_loaded_symbol():
    chips = build_header_chips(['NVDA', 'AAPL'], 'aapl')
    assert [c.children for c in chips] == ['NVDA', 'AAPL']
    assert chips[0].className == 'sfa-hwl-chip'
    assert chips[1].className == 'sfa-hwl-chip active'
    assert chips[1].id == {'type': 'header-wl-chip', 'index': 'AAPL'}


def test_empty_list_shows_a_hint_not_buttons():
    chips = build_header_chips([], 'TSLA')
    assert len(chips) == 1 and chips[0].className == 'sfa-hwl-empty'


def test_clicked_index_reads_the_button_index():
    prop = '{"index":"BRK-B","type":"header-wl-chip"}.n_clicks'
    assert clicked_index({'prop_id': prop, 'value': 1}) == 'BRK-B'


def test_rerender_with_zero_clicks_is_not_a_click():
    prop = '{"index":"NVDA","type":"header-wl-chip"}.n_clicks'
    assert clicked_index({'prop_id': prop, 'value': 0}) is None
    assert clicked_index({'prop_id': 'other.n_clicks', 'value': 1}) is None


def test_editor_rows_keep_order_and_carry_the_symbol():
    rows = build_editor_rows(['MSFT', 'NVDA'])
    assert [getattr(r, 'data-symbol') for r in rows] == ['MSFT', 'NVDA']


def test_add_to_draft_appends_and_uppercases():
    symbols, message = add_to_draft(['NVDA'], 'zzzq')
    assert symbols == ['NVDA', 'ZZZQ'] and message == ''


def test_add_to_draft_refuses_duplicates_and_a_full_list():
    assert add_to_draft(['NVDA'], 'NVDA') == (['NVDA'], 'NVDA is already in the list.')
    symbols, message = add_to_draft(TEN, 'NFLX')
    assert symbols == TEN and 'full' in message


def test_star_cannot_grow_a_list_past_the_cap():
    data = set_symbols(None, 'L', TEN)
    assert len(TEN) == MAX_WATCHLIST_SYMBOLS
    assert symbols_in(toggle_symbol(data, 'L', 'NFLX'), 'L') == TEN
    # Removing still works on a full list.
    assert 'JPM' not in symbols_in(toggle_symbol(data, 'L', 'JPM'), 'L')


def test_set_symbols_keeps_order_dedupes_and_caps():
    data = set_symbols(None, 'L', ['msft', 'NVDA', 'MSFT', *TEN, 'NFLX'])
    saved = symbols_in(data, 'L')
    assert saved[:2] == ['MSFT', 'NVDA']
    assert len(saved) == MAX_WATCHLIST_SYMBOLS and len(set(saved)) == len(saved)
