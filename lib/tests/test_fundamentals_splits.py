"""SEC per-share figures restated for stock splits.

Filings report EPS on the share count of their day; Yahoo's prices are
split-adjusted. Before this, Apple's annual EPS fell from 9.21 (fiscal 2017,
last filed in 2019) to 2.98 (fiscal 2018, re-filed after the 2020 split).
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from lib import fundamentals_sec as sec
from lib.fundamentals import _decode_history, _encode_history, _stock_splits, fetch_fundamentals
from lib.fundamentals_cache import FILINGS, CacheRead

APPLE_SPLIT = ((pd.Timestamp("2020-08-31"), 4.0),)


def eps_fact(start, end, val, filed, form="10-K"):
    return {"start": start, "end": end, "val": val, "filed": filed, "form": form, "fp": "FY" if form == "10-K" else "Q3"}


def test_only_per_share_values_filed_before_a_split_are_divided():
    assert sec._split_factor("USD/shares", "2019-10-31", APPLE_SPLIT) == 4.0
    assert sec._split_factor("USD/shares", "2020-10-30", APPLE_SPLIT) == 1.0
    assert sec._split_factor("USD/shares", "2020-08-31", APPLE_SPLIT) == 1.0  # filed on the day: reflected
    assert sec._split_factor("USD", "2019-10-31", APPLE_SPLIT) == 1.0
    assert sec._split_factor("USD/shares", "", APPLE_SPLIT) == 1.0


def test_successive_and_reverse_splits_compound():
    splits = ((pd.Timestamp("2014-06-09"), 7.0), (pd.Timestamp("2020-08-31"), 4.0), (pd.Timestamp("2024-01-02"), 0.5))
    assert sec._split_factor("USD/shares", "2013-10-30", splits) == pytest.approx(14.0)


def test_annual_eps_is_put_on_todays_share_basis():
    usgaap = {"EarningsPerShareDiluted": {"units": {"USD/shares": [
        # Fiscal 2017, last filed in the fiscal 2019 10-K: before the split.
        eps_fact("2016-09-25", "2017-09-30", 9.21, "2019-10-31"),
        # Fiscal 2018, re-filed in the fiscal 2020 10-K: already restated.
        eps_fact("2017-10-01", "2018-09-29", 2.98, "2020-10-30"),
    ]}}}
    values, _ = sec._sec_annual_series_and_ends(usgaap, "EarningsPerShareDiluted", splits=APPLE_SPLIT)
    assert values[2017] == pytest.approx(2.3025)
    assert values[2018] == pytest.approx(2.98)
    unadjusted, _ = sec._sec_annual_series_and_ends(usgaap, "EarningsPerShareDiluted")
    assert unadjusted[2017] == 9.21


def test_q4_is_derived_on_one_share_basis_when_a_split_falls_between_the_filings():
    usgaap = {"EarningsPerShareDiluted": {"units": {"USD/shares": [
        eps_fact("2019-09-29", "2020-06-27", 10.00, "2020-07-31", form="10-Q"),  # nine months, pre-split
        eps_fact("2019-09-29", "2020-09-26", 3.28, "2020-10-30"),  # full year, post-split
    ]}}}
    values, _ = sec._sec_quarterly_series_and_ends(usgaap, "EarningsPerShareDiluted", splits=APPLE_SPLIT)
    assert values[(2020, 3)] == pytest.approx(3.28 - 10.00 / 4)


def test_split_history_is_read_from_yahoo_prices_on_the_exchange_date():
    index = pd.DatetimeIndex(["2020-08-28", "2020-08-31", "2020-09-01"]).tz_localize("America/New_York")
    history = pd.DataFrame({"Close": [499.0, 129.0, 134.0], "Stock Splits": [0.0, 4.0, 0.0]}, index=index)
    assert _stock_splits(history) == ((pd.Timestamp("2020-08-31"), 4.0),)
    assert _stock_splits(history[["Close"]]) == ()


def test_cached_history_without_splits_is_refetched():
    history = pd.DataFrame(
        {"Close": [1.0], "Stock Splits": [4.0]}, index=pd.to_datetime(["2020-08-31"]),
    )
    raw = _encode_history(history, 2015)
    assert list(_decode_history(raw, 2015).columns) == ["Close", "Stock Splits"]
    old_shape = {"first_year": 2015, "frame": raw["frame"]}  # written before splits were kept
    assert _decode_history(old_shape, 2015) is None


def test_fetch_fundamentals_restates_sec_eps_and_says_so():
    quarters = [("2018-12-30", "2019-03-30"), ("2019-03-31", "2019-06-29"), ("2019-06-30", "2019-09-28"),
                ("2019-09-29", "2019-12-28")]
    usgaap = {
        "Revenues": {"units": {"USD": [
            {"start": s, "end": e, "val": 5e10, "filed": "2020-01-31", "form": "10-Q"} for s, e in quarters
        ] + [eps_fact("2018-09-30", "2019-09-28", 2.6e11, "2019-10-31")]}},
        "EarningsPerShareDiluted": {"units": {"USD/shares": [
            {"start": s, "end": e, "val": 4.0, "filed": "2020-01-31", "form": "10-Q"} for s, e in quarters
        ] + [eps_fact("2018-09-30", "2019-09-28", 11.89, "2019-10-31")]}},
    }
    facts = {"entityName": "Apple Inc.", "facts": {"us-gaap": usgaap}}
    history = pd.DataFrame(
        {"Close": [60.0, 70.0, 130.0], "Stock Splits": [0.0, 0.0, 4.0]},
        index=pd.to_datetime(["2019-09-27", "2019-12-27", "2020-08-31"]),
    )
    with patch("lib.fundamentals.load_company_facts", return_value=CacheRead(facts, "network", 0.0, FILINGS)), \
         patch("lib.fundamentals.yf.Ticker", return_value=MagicMock()), \
         patch("lib.fundamentals._safe_info", return_value={}), \
         patch("lib.fundamentals._safe_history", return_value=history):
        payload = fetch_fundamentals("AAPL", use_cache=False)

    eps = next(row for row in payload["financials"] if row["metric"] == "EPS")
    assert eps[2019] == "$2.97"  # 11.89 / 4
    quarterly_eps = next(row for row in payload["quarterly"]["financials"] if row["metric"] == "EPS")
    assert quarterly_eps["2019-Q4"] == "$1.00"  # 4.00 / 4
    assert any("4-for-1 on 2020-08-31" in note for note in payload["quality_notes"])
