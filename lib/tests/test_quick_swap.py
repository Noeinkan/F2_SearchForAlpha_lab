"""Quick swap — change the symbol, keep the test, compare the runs.

What these guard: a swap must change nothing but the symbol. The window a user
narrowed has to survive it (a plain symbol change resets it to the full range),
and the comparison table must only call two runs "the same test" when every
input but the symbol matched.
"""

from __future__ import annotations

import json

import dash
import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import pytest

from lib.dash.callbacks import register_callbacks
from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.integrated_dashboard import create_dashboard_layout
from lib.dash.layout.quick_swap import build_chips, build_compare_table
from lib.dash.quick_swap import (
    MAX_COMPARE_ROWS,
    build_row,
    condition_tags,
    conditions_key,
    held_window,
    neighbour_symbol,
    upsert_row,
    window_short,
)
from lib.dash.state import dashboard_state
from lib.tests._dash_post import callback_key, post_callback


@pytest.fixture(scope="module")
def app():
    application = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        suppress_callback_exceptions=True,
    )
    application.layout = create_dashboard_layout(get_theme(DEFAULT_THEME), bootstrap=None)
    register_callbacks(application)
    return application


@pytest.fixture
def loaded_frame():
    """A small daily tape with one buy/sell pair, installed as the loaded session."""
    saved = (dashboard_state.df, dashboard_state.ticker, dashboard_state.interval)
    rng = np.random.default_rng(7)
    index = pd.date_range("2020-01-01", periods=300, freq="B")
    close = 100 + np.cumsum(rng.normal(0, 1, len(index)))
    frame = pd.DataFrame({
        "Open": close, "High": close * 1.01, "Low": close * 0.99, "Close": close,
        "Volume": 1_000_000.0,
        "Returns": pd.Series(close, index=index).pct_change().fillna(0.0),
        "Test_Cross_Buy": (np.arange(len(index)) % 40 == 5).astype(int),
        "Test_Cross_Sell": (np.arange(len(index)) % 40 == 25).astype(int),
    }, index=index)
    dashboard_state.df = frame
    dashboard_state.ticker = "AAA"
    dashboard_state.interval = "1d"
    yield frame
    dashboard_state.df, dashboard_state.ticker, dashboard_state.interval = saved


# --- which symbol comes next --------------------------------------------------

def test_next_and_previous_wrap_around():
    symbols = ["SPY", "QQQ", "AAPL"]
    assert neighbour_symbol(symbols, "QQQ", 1) == "AAPL"
    assert neighbour_symbol(symbols, "AAPL", 1) == "SPY"
    assert neighbour_symbol(symbols, "SPY", -1) == "AAPL"


def test_a_symbol_off_the_list_starts_from_the_edge():
    symbols = ["SPY", "QQQ", "AAPL"]
    assert neighbour_symbol(symbols, "TSLA", 1) == "SPY"
    assert neighbour_symbol(symbols, "TSLA", -1) == "AAPL"
    assert neighbour_symbol([], "TSLA", 1) is None


# --- the held window -----------------------------------------------------------

def test_held_window_keeps_the_dates_even_past_the_data():
    """A shorter listing gets fewer bars, not a different question."""
    assert held_window("2018-01-01", "2024-06-30", "2020-03-01", "2026-09-14") == (
        "2018-01-01", "2024-06-30",
    )


def test_held_window_falls_back_when_the_data_misses_it_entirely():
    assert held_window("2001-01-01", "2002-01-01", "2020-03-01", "2026-09-14") == (
        "2020-03-01", "2026-09-14",
    )
    assert held_window(None, "junk", "2020-03-01", "2026-09-14") == ("2020-03-01", "2026-09-14")


def test_short_history_is_flagged_but_a_holiday_is_not():
    index = pd.date_range("2020-01-06", "2020-12-31", freq="B")
    frame = pd.DataFrame({"Close": 1.0}, index=index)
    # Window opens on a Saturday before a long weekend: still covered.
    assert not window_short("2020-01-01", "2020-12-31", frame)
    assert window_short("2019-06-01", "2020-12-31", frame)
    assert window_short("2020-01-01", "2021-03-01", frame)


# --- what counts as the same test ----------------------------------------------

def test_fingerprint_ignores_signal_order_but_not_a_stop():
    base = {"buy_signals": ["A", "B"], "sell_signals": ["C"], "trailing_stop_loss": 0.05}
    reordered = {"buy_signals": ["B", "A"], "sell_signals": ["C"], "trailing_stop_loss": 0.05}
    nudged = {**base, "trailing_stop_loss": 0.06}
    assert conditions_key(base) == conditions_key(reordered)
    assert conditions_key(base) != conditions_key(nudged)


def test_rerun_replaces_its_row_and_new_runs_go_first():
    def row(symbol, key="k1"):
        return build_row(symbol=symbol, interval="1d", key=key, window_label="w",
                         bars=10, short=False, metrics={"total_return": 0.1})

    rows = upsert_row([], row("AAA"))
    rows = upsert_row(rows, row("BBB"))
    rows = upsert_row(rows, row("AAA"))
    assert [r["symbol"] for r in rows] == ["AAA", "BBB"]

    rows = upsert_row(rows, row("AAA", key="k2"))
    assert [(r["symbol"], r["key"]) for r in rows] == [("AAA", "k2"), ("AAA", "k1"), ("BBB", "k1")]

    for n in range(MAX_COMPARE_ROWS + 5):
        rows = upsert_row(rows, row(f"S{n}"))
    assert len(rows) == MAX_COMPARE_ROWS


def test_tags_follow_the_order_tests_were_first_run():
    rows = [{"key": "k3"}, {"key": "k1"}, {"key": "k2"}, {"key": "k1"}]  # newest first
    assert condition_tags(rows) == {"k1": "A", "k2": "B", "k3": "C"}


def test_non_finite_metrics_are_stored_as_none():
    row = build_row(symbol="aaa", interval="1d", key="k", window_label="w", bars=3, short=False,
                    metrics={"sharpe": float("nan"), "total_return": float("inf"), "num_trades": 4})
    assert row["symbol"] == "AAA"
    assert row["sharpe"] is None and row["total_return"] is None
    assert row["num_trades"] == 4.0
    json.dumps(row)


# --- layout --------------------------------------------------------------------

def test_one_symbol_under_two_tests_gets_two_distinct_row_ids():
    """Duplicate ids make Dash abort the whole render."""
    rows = [
        build_row(symbol="AAA", interval="1d", key=k, window_label="w", bars=1, short=False, metrics={})
        for k in ("k1", "k2")
    ]
    table = build_compare_table(rows, "AAA")
    ids = [str(tr.id) for tr in table.children.children[1].children]
    assert len(set(ids)) == 2


def test_chips_mark_the_loaded_symbol():
    chips = build_chips(["SPY", "QQQ"], "qqq")
    assert [c.className for c in chips] == ["sfa-qswap-chip", "sfa-qswap-chip active"]


# --- wiring --------------------------------------------------------------------

_WATCHLISTS = {"version": 1, "active": "Default", "watchlists": {"Default": ["SPY", "QQQ", "AAPL"]}}


def _swap(app, changed, extra):
    key = callback_key(app, "quick-swap-autorun.data")
    values = {
        "watchlists-store.data": _WATCHLISTS,
        "symbol-search-list.value": "Default",
        "ticker-dropdown.value": "QQQ",
        "test-window-start.date": "2021-01-04",
        "test-window-end.date": "2023-12-29",
        **extra,
    }
    return post_callback(app, key, changed, values)


def test_next_swaps_the_symbol_and_holds_the_window(app):
    status, body = _swap(app, "quick-swap-next.n_clicks", {"quick-swap-next.n_clicks": 1})
    assert status == 200
    response = body["response"]
    ticker = next(v for k, v in response.items() if k.startswith("ticker-dropdown"))
    pending = next(v for k, v in response.items() if k.startswith("test-window-pending-store"))
    assert ticker == {"value": "AAPL"}
    assert pending == {"data": {"start": "2021-01-04", "end": "2023-12-29", "hold": True}}
    assert response["quick-swap-autorun"]["data"]["ticker"] == "AAPL"


def test_swapping_to_the_loaded_symbol_does_nothing(app):
    """Nothing would load, so the autorun would fire on some later, unrelated change."""
    status, _ = _swap(app, "quick-swap-prev.n_clicks",
                      {"quick-swap-prev.n_clicks": 1, "watchlists-store.data":
                       {**_WATCHLISTS, "watchlists": {"Default": ["QQQ"]}}})
    assert status == 204


def test_sync_test_window_keeps_held_dates_on_the_new_series(app, loaded_frame):
    key = callback_key(app, "test-window-series-store.data")
    status, body = post_callback(app, key, "data-loaded-store.data", {
        "data-loaded-store.data": 2,
        "test-window-series-store.data": "OLD|1d",
        "test-window-pending-store.data": {"start": "2019-06-03", "end": "2020-06-30", "hold": True},
    })
    assert status == 200
    response = body["response"]
    assert response["test-window-start"]["date"] == "2019-06-03"  # before the first bar, kept
    assert response["test-window-end"]["date"] == "2020-06-30"
    assert response["test-window-series-store"]["data"] == "AAA|1d"


def test_backtest_adds_its_run_to_the_comparison(app, loaded_frame):
    key = callback_key(app, "backtest-results.children")
    values = {
        "run-backtest-btn.n_clicks": 1,
        "ticker-dropdown.value": "AAA",
        "initial-capital.value": 10_000,
        "test-window-start.date": "2019-01-01",
        "test-window-end.date": "2020-06-30",
        "buy-signals.value": ["Test_Cross_Buy"],
        "sell-signals.value": ["Test_Cross_Sell"],
        "strategy-mode.value": "trading",
        "quick-swap-compare-store.data": [],
    }
    status, body = post_callback(app, key, "run-backtest-btn.n_clicks", values)
    assert status == 200
    rows = body["response"]["quick-swap-compare-store"]["data"]
    assert len(rows) == 1
    assert rows[0]["symbol"] == "AAA"
    assert rows[0]["short"] is True  # the window opens a year before the tape
    assert rows[0]["bars"] == len(loaded_frame.loc[:"2020-06-30"])

    # Same test again on the same data replaces the row rather than adding one.
    values["quick-swap-compare-store.data"] = rows
    _, body = post_callback(app, key, "run-backtest-btn.n_clicks", values)
    again = body["response"]["quick-swap-compare-store"]["data"]
    assert len(again) == 1 and again[0]["key"] == rows[0]["key"]

    # A different stop is a different test.
    values["trailing-stop-pct.value"] = 7
    _, body = post_callback(app, key, "run-backtest-btn.n_clicks", values)
    changed = body["response"]["quick-swap-compare-store"]["data"]
    assert len(changed) == 2 and changed[0]["key"] != rows[0]["key"]
