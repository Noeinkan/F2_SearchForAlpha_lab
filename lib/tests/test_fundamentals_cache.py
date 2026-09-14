"""Fundamentals cache and refresh policy (ROADMAP 7.9)."""

from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd
import pytest
from dash import no_update

from lib import fundamentals_cache as cache
from lib import fundamentals_sec as sec
from lib.dash.callbacks.fundamentals import _global_ticker_update, _load_status
from lib.fundamentals import fetch_fundamentals

HOUR = 3600.0


@pytest.fixture(autouse=True)
def cache_dir(tmp_path, monkeypatch):
    monkeypatch.setattr(cache, "CACHE_DIR", tmp_path)
    monkeypatch.delenv("SFA_FUNDAMENTALS_FILINGS_TTL_HOURS", raising=False)
    monkeypatch.delenv("SFA_FUNDAMENTALS_QUOTE_TTL_MINUTES", raising=False)
    return tmp_path


def counting(value):
    loader = MagicMock(return_value=value)
    return loader


def read(loader, *, now, force=False, tier=cache.FILINGS, **kwargs):
    return cache.read_through("kind", "AAPL", tier, loader, force=force, now=now, **kwargs)


# --- read_through ----------------------------------------------------------

def test_fresh_entry_is_served_without_calling_the_source():
    read(counting({"v": 1}), now=0.0)
    loader = counting({"v": 2})
    result = read(loader, now=23 * HOUR)
    loader.assert_not_called()
    assert (result.value, result.state, result.fetched_at) == ({"v": 1}, "cache", 0.0)


def test_expired_entry_is_refetched_and_replaced():
    read(counting({"v": 1}), now=0.0)
    result = read(counting({"v": 2}), now=25 * HOUR)
    assert (result.value, result.state) == ({"v": 2}, "network")
    assert read(counting({"v": 3}), now=26 * HOUR).value == {"v": 2}


def test_force_refetches_a_fresh_entry():
    read(counting({"v": 1}), now=0.0)
    loader = counting({"v": 2})
    result = read(loader, now=60.0, force=True)
    loader.assert_called_once()
    assert result.state == "network"


def test_failed_refetch_serves_the_old_entry_as_stale():
    read(counting({"v": 1}), now=0.0)
    result = read(MagicMock(side_effect=OSError("429")), now=30 * HOUR)
    assert (result.value, result.state, result.fetched_at) == ({"v": 1}, "stale", 0.0)


def test_failed_fetch_with_nothing_cached_raises():
    with pytest.raises(OSError):
        read(MagicMock(side_effect=OSError("429")), now=0.0)


def test_empty_refetch_never_overwrites_a_good_entry(cache_dir):
    read(counting({"v": 1}), now=0.0)
    result = read(counting({}), now=30 * HOUR, force=True)
    assert (result.value, result.state) == ({"v": 1}, "stale")
    assert read(counting({"v": 9}), now=30 * HOUR + 1).state == "network"  # still expired, still refetches


def test_empty_result_is_not_written(cache_dir):
    result = read(counting(pd.DataFrame()), now=0.0)
    assert result.state == "miss"
    assert not list(cache_dir.rglob("*.json"))


def test_disabled_cache_reads_and_writes_nothing(cache_dir):
    read(counting({"v": 1}), now=0.0)
    loader = counting({"v": 2})
    result = read(loader, now=1.0, enabled=False)
    loader.assert_called_once()
    assert result.value == {"v": 2}
    assert read(counting({"v": 3}), now=2.0).value == {"v": 1}


def test_decode_can_reject_an_entry_in_an_old_shape():
    read(counting({"shape": 1}), now=0.0)
    loader = counting({"shape": 2})
    result = read(loader, now=1.0, decode=lambda raw: raw if raw.get("shape") == 2 else None)
    loader.assert_called_once()
    assert result.value == {"shape": 2}


def test_corrupt_entry_counts_as_missing(cache_dir):
    path = cache.entry_path("kind", "AAPL")
    path.parent.mkdir(parents=True)
    path.write_text("{not json", encoding="utf-8")
    assert read(counting({"v": 1}), now=0.0).state == "network"


def test_symbols_with_path_characters_get_safe_file_names(cache_dir):
    path = cache.entry_path("yf-info", "../^GSPC")
    assert path.parent == cache_dir / "yf-info"
    assert "/" not in path.name and "\\" not in path.name


def test_ttl_overrides_come_from_the_environment(monkeypatch):
    assert cache.FILINGS.ttl_seconds == 24 * HOUR
    assert cache.QUOTE.ttl_seconds == 15 * 60
    monkeypatch.setenv("SFA_FUNDAMENTALS_FILINGS_TTL_HOURS", "6")
    monkeypatch.setenv("SFA_FUNDAMENTALS_QUOTE_TTL_MINUTES", "0")
    assert cache.FILINGS.ttl_seconds == 6 * HOUR
    assert cache.QUOTE.ttl_seconds == 0
    monkeypatch.setenv("SFA_FUNDAMENTALS_FILINGS_TTL_HOURS", "soon")
    assert cache.FILINGS.ttl_seconds == 24 * HOUR


def test_zero_ttl_always_refetches_but_keeps_the_stale_fallback(monkeypatch):
    monkeypatch.setenv("SFA_FUNDAMENTALS_QUOTE_TTL_MINUTES", "0")
    read(counting({"v": 1}), now=0.0, tier=cache.QUOTE)
    assert read(counting({"v": 2}), now=1.0, tier=cache.QUOTE).state == "network"
    assert read(counting(None), now=2.0, tier=cache.QUOTE).state == "stale"


# --- frame codec -----------------------------------------------------------

def test_statement_frame_round_trips_exactly():
    frame = pd.DataFrame(
        [[1.5, np.nan], [-2.0, 3.0]],
        index=["Total Revenue", "Net Income"],
        columns=pd.to_datetime(["2025-06-30", "2025-03-31"]),
    )
    back = cache.decode_frame(cache.encode_frame(frame))
    pd.testing.assert_frame_equal(back, frame, check_freq=False)


def test_zoned_history_across_a_dst_change_round_trips_exactly():
    index = pd.DatetimeIndex(["2025-03-07", "2025-03-10", "2025-11-03"]).tz_localize("America/New_York")
    frame = pd.DataFrame({"Close": [10.0, 11.0, 12.0]}, index=index)
    back = cache.decode_frame(cache.encode_frame(frame))
    pd.testing.assert_frame_equal(back, frame, check_freq=False)
    assert str(back.index.tz) == "America/New_York"


def test_integer_labels_stay_integers():
    frame = pd.DataFrame([[1.0, 2.0]], index=["Total Revenue"], columns=[2023, 2024])
    back = cache.decode_frame(cache.encode_frame(frame))
    assert list(back.columns) == [2023, 2024]


# --- SEC facts ---------------------------------------------------------------

def test_sec_facts_are_trimmed_to_the_concepts_read(cache_dir):
    raw = {"entityName": "Acme", "facts": {"us-gaap": {
        "Revenues": {"units": {"USD": []}},
        "SomethingNobodyReads": {"units": {"USD": []}},
    }}}
    with patch.object(sec, "_sec_cik", return_value="0000000001"), \
         patch.object(sec, "_sec_company_facts", return_value=raw):
        result = sec.load_company_facts("ACME")
    assert set(result.value["facts"]["us-gaap"]) == {"Revenues"}
    assert (cache_dir / "sec-facts" / "CIK0000000001.json").is_file()


def test_sec_facts_cached_for_another_concept_set_are_refetched():
    raw = {"entityName": "Acme", "facts": {"us-gaap": {"Revenues": {"units": {"USD": []}}}}}
    fetch = MagicMock(return_value=raw)
    with patch.object(sec, "_sec_cik", return_value="0000000001"), \
         patch.object(sec, "_sec_company_facts", fetch):
        sec.load_company_facts("ACME")
        with patch.object(sec, "SEC_CONCEPTS", sec.SEC_CONCEPTS + ("NewConcept",)):
            sec.load_company_facts("ACME")
    assert fetch.call_count == 2


# --- fetch_fundamentals ------------------------------------------------------

def _yahoo_only_sources():
    annual = pd.DataFrame([[1e9]], index=["Total Revenue"], columns=pd.to_datetime(["2024-12-31"]))
    quarterly = pd.DataFrame([[2.5e8]], index=["Total Revenue"], columns=pd.to_datetime(["2025-03-31"]))
    history = pd.DataFrame({"Close": [50.0, 55.0]}, index=pd.to_datetime(["2024-12-31", "2025-03-31"]))
    return {
        "info": MagicMock(return_value={"longName": "Toyota", "currentPrice": 55.0}),
        "annual": MagicMock(return_value=(annual, pd.DataFrame(), pd.DataFrame())),
        "quarterly": MagicMock(return_value=(quarterly, pd.DataFrame(), pd.DataFrame())),
        "history": MagicMock(return_value=history),
    }


def _fetch(sources, **kwargs):
    with patch.object(sec, "_sec_cik", return_value=None), \
         patch("lib.fundamentals.yf.Ticker", return_value=MagicMock()), \
         patch("lib.fundamentals._safe_info", sources["info"]), \
         patch("lib.fundamentals._fetch_yfinance_annual", sources["annual"]), \
         patch("lib.fundamentals._fetch_yfinance_quarterly", sources["quarterly"]), \
         patch("lib.fundamentals._safe_history", sources["history"]):
        return fetch_fundamentals("7203.T", **kwargs)


def test_second_load_reads_every_input_from_the_cache():
    sources = _yahoo_only_sources()
    first = _fetch(sources)
    second = _fetch(sources)

    for loader in sources.values():
        loader.assert_called_once()
    assert second["cache"]["cached"] == [
        "Yahoo quote", "Yahoo annual statements", "Yahoo quarterly statements", "Yahoo price history",
    ]
    assert second["financials"] == first["financials"]
    assert second["quarterly"]["financials"] == first["quarterly"]["financials"]
    assert any(note.startswith("From cache:") for note in second["quality_notes"])
    assert _load_status(second) == f"LOADED {second['as_of']} · FROM CACHE"


def test_status_line_says_partly_when_some_inputs_were_refetched():
    payload = {"as_of": "t", "cache": {"sources": [{}, {}], "cached": ["Yahoo price history"], "stale": []}}
    assert _load_status(payload) == "LOADED t · PARTLY FROM CACHE"


def test_refresh_refetches_every_input():
    sources = _yahoo_only_sources()
    _fetch(sources)
    refreshed = _fetch(sources, force=True)
    for loader in sources.values():
        assert loader.call_count == 2
    assert refreshed["cache"]["cached"] == []
    assert _load_status(refreshed) == f"LOADED {refreshed['as_of']}"


def test_a_throttled_refresh_shows_the_cached_copy_and_says_so():
    sources = _yahoo_only_sources()
    _fetch(sources)
    sources["info"].return_value = {}  # _safe_info swallows the 429 and returns nothing
    refreshed = _fetch(sources, force=True)
    assert refreshed["cache"]["stale"] == ["Yahoo quote"]
    assert refreshed["last_price"] == 55.0
    assert any(note.startswith("Refetch of Yahoo quote failed") for note in refreshed["quality_notes"])
    assert "REFETCH FAILED" in _load_status(refreshed)


def test_use_cache_false_leaves_no_trace(cache_dir):
    _fetch(_yahoo_only_sources(), use_cache=False)
    assert not list(cache_dir.rglob("*.json"))


def test_refresh_does_not_resend_the_ticker_the_terminal_already_has():
    # Re-sending it reloads the terminal's prices, indicators and signals.
    assert _global_ticker_update("refresh-fundamentals-button", "AAPL", "AAPL") is no_update
    assert _global_ticker_update("app-url", "AAPL", "TSLA") == "AAPL"
    assert _global_ticker_update("route-ticker-store", "MSFT", None) == "MSFT"
    assert _global_ticker_update("theme-store", "AAPL", "TSLA") is no_update


def test_status_line_tolerates_payloads_without_cache_info():
    # Demo fixtures were frozen before the cache existed.
    assert _load_status({"as_of": "2026-09-11 16:00:00"}) == "LOADED 2026-09-11 16:00:00"
