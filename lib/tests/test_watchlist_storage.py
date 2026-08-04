"""Tests for watchlist persistence."""

from __future__ import annotations

import json

import pytest

from lib.dash.watchlist_storage import (
    DEFAULT_LIST_NAME,
    create_list,
    delete_list,
    is_starred,
    list_names,
    load_watchlists,
    normalize,
    rename_list,
    save_watchlists,
    symbols_in,
    toggle_symbol,
)


@pytest.fixture
def path(tmp_path):
    return str(tmp_path / "watchlists.json")


def test_load_missing_file_returns_seeded_default(path):
    data = load_watchlists(path)

    assert data["active"] == DEFAULT_LIST_NAME
    assert "SPY" in data["watchlists"][DEFAULT_LIST_NAME]


def test_save_then_load_round_trip(path):
    data = load_watchlists(path)
    data = toggle_symbol(data, DEFAULT_LIST_NAME, "rklb")
    save_watchlists(path, data)

    reloaded = load_watchlists(path)
    assert "RKLB" in reloaded["watchlists"][DEFAULT_LIST_NAME]


def test_save_writes_valid_json_with_schema_version(path):
    save_watchlists(path, load_watchlists(path))

    with open(path, encoding="utf-8") as handle:
        raw = json.load(handle)

    assert raw["version"] == 1
    assert "updated_at" in raw
    assert isinstance(raw["watchlists"], dict)


def test_toggle_symbol_adds_then_removes(path):
    data = {"watchlists": {"L": []}, "active": "L"}

    data = toggle_symbol(data, "L", "NVDA")
    assert symbols_in(data, "L") == ["NVDA"]
    assert is_starred(data, "L", "nvda")

    data = toggle_symbol(data, "L", "NVDA")
    assert symbols_in(data, "L") == []
    assert not is_starred(data, "L", "NVDA")


def test_toggle_symbol_uppercases_and_dedupes():
    data = {"watchlists": {"L": ["NVDA"]}, "active": "L"}

    # Already present in canonical form, so the lowercase toggle removes it.
    data = toggle_symbol(data, "L", "nvda")
    assert symbols_in(data, "L") == []


def test_normalize_rejects_junk_and_seeds_default():
    assert normalize(None)["active"] == DEFAULT_LIST_NAME
    assert normalize({"watchlists": "not-a-dict"})["active"] == DEFAULT_LIST_NAME
    assert normalize([1, 2, 3])["active"] == DEFAULT_LIST_NAME


def test_normalize_drops_bad_entries_and_duplicates():
    data = normalize({
        "watchlists": {
            "Good": ["spy", "SPY", "", None, "qqq"],
            "": ["AAPL"],
            "BadType": "nope",
        },
        "active": "Good",
    })

    assert data["watchlists"]["Good"] == ["SPY", "QQQ"]
    assert "" not in data["watchlists"]
    assert "BadType" not in data["watchlists"]


def test_normalize_repoints_active_when_missing():
    data = normalize({"watchlists": {"A": []}, "active": "Gone"})
    assert data["active"] == "A"


def test_create_and_rename_and_delete_list():
    data = normalize({"watchlists": {"A": ["SPY"]}, "active": "A"})

    data = create_list(data, "Tech")
    assert data["active"] == "Tech"
    assert set(list_names(data)) == {"A", "Tech"}

    data = rename_list(data, "Tech", "Semis")
    assert set(list_names(data)) == {"A", "Semis"}
    assert data["active"] == "Semis"

    data = delete_list(data, "Semis")
    assert list_names(data) == ["A"]
    assert data["active"] == "A"


def test_rename_refuses_to_clobber_existing_name():
    data = normalize({"watchlists": {"A": ["SPY"], "B": ["QQQ"]}, "active": "A"})

    data = rename_list(data, "A", "B")

    assert symbols_in(data, "A") == ["SPY"]
    assert symbols_in(data, "B") == ["QQQ"]


def test_delete_last_list_empties_rather_than_removing():
    data = normalize({"watchlists": {"Only": ["SPY"]}, "active": "Only"})

    data = delete_list(data, "Only")

    assert list_names(data) == ["Only"]
    assert symbols_in(data, "Only") == []


def test_load_corrupt_file_falls_back(path):
    with open(path, "w", encoding="utf-8") as handle:
        handle.write("{not json")

    assert load_watchlists(path)["active"] == DEFAULT_LIST_NAME
