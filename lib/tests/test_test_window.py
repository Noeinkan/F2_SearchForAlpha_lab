"""Test-window behaviour — the period the backtest and optimizer evaluate.

The regression these guard: the optimizer used to slice the loaded frame to the
sidebar date range while the backtest ran on the whole thing, so a narrowed
window ranked combinations over one period and reported metrics for another.
Both now go through `slice_df_to_window` and read the same two component ids.
"""

from __future__ import annotations

import dash
import dash_bootstrap_components as dbc
import numpy as np
import pandas as pd
import pytest

from lib.dash.callbacks import register_callbacks
from lib.dash.callbacks.shared import slice_df_to_window
from lib.dash.callbacks.test_window import resolve_preset
from lib.dash.dash_config import DEFAULT_THEME, get_theme
from lib.dash.integrated_dashboard import create_dashboard_layout


@pytest.fixture(scope="module")
def app():
    theme = get_theme(DEFAULT_THEME)
    application = dash.Dash(
        __name__,
        external_stylesheets=[dbc.themes.BOOTSTRAP],
        suppress_callback_exceptions=True,
    )
    application.layout = create_dashboard_layout(theme, bootstrap=None)
    register_callbacks(application)
    return application


def _daily_frame(start: str, periods: int) -> pd.DataFrame:
    index = pd.date_range(start, periods=periods, freq="D")
    return pd.DataFrame({"Close": np.arange(periods, dtype=float)}, index=index)


def _state_ids(spec) -> list[str]:
    return [item["id"] for item in spec.get("state", []) if isinstance(item["id"], str)]


def _spec_for(app, output_fragment: str):
    for spec in app.callback_map.values():
        if output_fragment in str(spec["output"]):
            return spec
    raise AssertionError(f"no callback writing {output_fragment}")


# --- the regression -----------------------------------------------------------

def test_backtest_and_optimizer_read_the_same_window(app):
    """Neither may go back to using its own idea of the evaluated period."""
    backtest = _state_ids(_spec_for(app, "backtest-results.children"))
    optimizer = _state_ids(_spec_for(app, "optimization-state.data"))

    for ids in (backtest, optimizer):
        assert "test-window-start" in ids
        assert "test-window-end" in ids
        assert "start-date" not in ids
        assert "end-date" not in ids


def test_backtest_slices_before_running():
    """The bug in one assertion: a narrowed window must shrink the frame."""
    df = _daily_frame("2020-01-01", 400)
    sliced, label = slice_df_to_window(df, "2020-06-01", "2020-06-30")

    assert len(sliced) == 30
    assert sliced.index.min() == pd.Timestamp("2020-06-01")
    assert sliced.index.max() == pd.Timestamp("2020-06-30")
    assert label == "2020-06-01 → 2020-06-30"


# --- slice_df_to_window -------------------------------------------------------

def test_slice_is_inclusive_of_the_end_date():
    df = _daily_frame("2024-01-01", 10)
    sliced, _ = slice_df_to_window(df, "2024-01-02", "2024-01-04")
    assert list(sliced.index.day) == [2, 3, 4]


def test_open_ended_bounds_pass_through():
    df = _daily_frame("2024-01-01", 10)
    assert len(slice_df_to_window(df, None, None)[0]) == 10
    assert len(slice_df_to_window(df, "2024-01-08", None)[0]) == 3
    assert len(slice_df_to_window(df, None, "2024-01-03")[0]) == 3


def test_empty_window_falls_back_to_the_full_frame():
    """Better a visibly wrong window than a silent zero-row run."""
    df = _daily_frame("2024-01-01", 10)
    sliced, label = slice_df_to_window(df, "2030-01-01", "2030-02-01")
    assert len(sliced) == 10
    assert "test window empty" in label


def test_non_datetime_index_is_untouched():
    df = pd.DataFrame({"Close": [1.0, 2.0, 3.0]})
    sliced, label = slice_df_to_window(df, "2024-01-01", "2024-12-31")
    assert len(sliced) == 3
    assert label == "full history (no date index)"


# --- preset shortcuts ---------------------------------------------------------

def test_preset_max_spans_the_loaded_frame():
    assert resolve_preset("max", "2010-06-29", "2026-08-04") == ("2010-06-29", "2026-08-04")


@pytest.mark.parametrize(
    "preset,expected_start",
    [("1y", "2025-08-04"), ("2y", "2024-08-04"), ("5y", "2021-08-04")],
)
def test_year_presets_count_back_from_the_last_bar(preset, expected_start):
    """Anchored to the data's last bar, not today — a stale symbol still works."""
    assert resolve_preset(preset, "2010-06-29", "2026-08-04") == (expected_start, "2026-08-04")


@pytest.mark.parametrize(
    "preset,expected_start",
    [("1m", "2026-07-04"), ("3m", "2026-05-04"), ("6m", "2026-02-04")],
)
def test_month_presets_count_back_from_the_last_bar(preset, expected_start):
    assert resolve_preset(preset, "2010-06-29", "2026-08-04") == (expected_start, "2026-08-04")


def test_ytd_snaps_to_january_first():
    assert resolve_preset("ytd", "2010-06-29", "2026-08-04") == ("2026-01-01", "2026-08-04")


def test_presets_clamp_to_available_history():
    """5Y of a 2-year listing is 2 years, not an empty slice."""
    assert resolve_preset("5y", "2024-09-01", "2026-08-04") == ("2024-09-01", "2026-08-04")


def test_unknown_preset_falls_back_to_max():
    assert resolve_preset(None, "2020-01-01", "2026-08-04") == ("2020-01-01", "2026-08-04")


# --- forced refresh -----------------------------------------------------------

def test_force_bypasses_a_warm_cache_entry(tmp_path, monkeypatch):
    """Refresh must re-fetch, not re-serve.

    The data cache has no TTL and the key is now derived from the interval
    rather than typed dates, so it stays identical for a whole trading day.
    Without ``force`` the header refresh button would be a no-op until midnight.
    """
    from unittest.mock import patch

    from lib.dash.helpers import fetch_data_with_cache
    from lib.dash.state import dashboard_state

    monkeypatch.setenv("SFA_OHLCV_CACHE_DIR", str(tmp_path / "ohlcv_cache"))
    first = _daily_frame("2024-01-01", 5)
    second = _daily_frame("2024-01-01", 6)
    dashboard_state.clear_cache()

    with patch("lib.data_processing.fetch_data", side_effect=[first, second]) as fetch:
        assert len(fetch_data_with_cache("ZZZZ", "1900-01-01", "2026-08-04")) == 5
        # Warm key, no force → served from cache, fetch not called again.
        assert len(fetch_data_with_cache("ZZZZ", "1900-01-01", "2026-08-04")) == 5
        assert fetch.call_count == 1

        refreshed = fetch_data_with_cache("ZZZZ", "1900-01-01", "2026-08-04", force=True)
        assert len(refreshed) == 6
        assert fetch.call_count == 2

        # ...and the forced result replaces the entry rather than sitting beside it.
        assert len(fetch_data_with_cache("ZZZZ", "1900-01-01", "2026-08-04")) == 6

    dashboard_state.clear_cache()


# --- wiring -------------------------------------------------------------------

def test_test_window_is_the_only_writer_of_its_pickers(app):
    """Two writers in one dispatch layer is what Dash 4 rejects outright."""
    writers = [
        spec for spec in app.callback_map.values()
        if "test-window-start.date" in str(spec["output"])
    ]
    assert len(writers) == 1


def test_chart_focus_store_has_two_declared_writers(app):
    """Data-tab row clicks and the test window both scroll the chart."""
    writers = [
        spec for spec in app.callback_map.values()
        if "chart-focus-store.data" in str(spec["output"])
    ]
    assert len(writers) == 2
