"""SEC XBRL quarterly statements (ROADMAP 7.6).

Fact shapes are taken from Apple's real company-facts file: three-month income
facts filed directly, cash flow filed only year-to-date, and no fourth quarter
in any filing.
"""

from unittest.mock import MagicMock, patch

import pandas as pd
import pytest

from lib import fundamentals_sec as sec
from lib.fundamentals import build_fundamentals_result, fetch_fundamentals
from lib.fundamentals_cache import FILINGS, CacheRead


def fact(start, end, val, form="10-Q", filed="2025-01-01"):
    entry = {"end": end, "val": val, "form": form, "filed": filed}
    if start:
        entry["start"] = start
    return entry


def concept(*entries, unit="USD"):
    return {"units": {unit: list(entries)}}


# Apple's fiscal 2025: 2024-09-29 .. 2025-09-27.
FY_START = "2024-09-29"
Q1_END, Q2_END, Q3_END, FY_END = "2024-12-28", "2025-03-29", "2025-06-28", "2025-09-27"


def ytd_cashflow():
    return concept(
        fact(FY_START, Q1_END, 29_935),
        fact(FY_START, Q2_END, 53_887),
        fact(FY_START, Q3_END, 81_754),
        fact(FY_START, FY_END, 111_482, form="10-K"),
    )


def test_cash_flow_quarters_are_differences_of_year_to_date_totals():
    values, ends = sec._sec_quarterly_series_and_ends(
        {"NetCashProvidedByUsedInOperatingActivities": ytd_cashflow()},
        "NetCashProvidedByUsedInOperatingActivities",
    )
    assert values == {
        (2024, 4): 29_935,
        (2025, 1): 53_887 - 29_935,
        (2025, 2): 81_754 - 53_887,
        (2025, 3): 111_482 - 81_754,  # Q4 = full year - nine months
    }
    assert ends[(2025, 3)] == pd.Timestamp(FY_END)


def test_direct_three_month_fact_wins_over_derivation():
    usgaap = {"Revenues": concept(
        fact(FY_START, Q1_END, 124_300),
        fact(FY_START, Q2_END, 219_659),
        fact("2024-12-29", Q2_END, 95_359),  # filed directly
        fact(FY_START, Q3_END, 313_695),
        fact(FY_START, FY_END, 416_161, form="10-K"),
    )}
    values, _ = sec._sec_quarterly_series_and_ends(usgaap, "Revenues")
    assert values[(2025, 1)] == 95_359
    assert values[(2025, 3)] == 416_161 - 313_695


def test_no_quarter_is_derived_across_a_six_month_gap():
    usgaap = {"Revenues": concept(
        fact(FY_START, Q1_END, 100),
        fact(FY_START, Q3_END, 300),  # six-month total missing
    )}
    values, _ = sec._sec_quarterly_series_and_ends(usgaap, "Revenues")
    assert values == {(2024, 4): 100}


def test_week_shift_keeps_52_53_week_quarter_ends_in_their_quarter():
    # 2022-10-01 is a Saturday-closest-to-Sep-30 year end: it belongs to Q3.
    assert sec._sec_quarter_key(pd.Timestamp("2022-10-01")) == (2022, 3)
    assert sec._sec_quarter_key(pd.Timestamp("2025-09-27")) == (2025, 3)
    assert sec._sec_quarter_key(pd.Timestamp("2026-01-03")) == (2025, 4)
    assert sec._sec_quarter_key(pd.Timestamp("2025-12-31")) == (2025, 4)


def test_balance_instants_read_at_every_quarter_end_including_the_10k():
    usgaap = {"StockholdersEquity": concept(
        fact(None, Q3_END, 65_830),
        fact(None, FY_END, 73_733, form="10-K"),
        fact(None, "2025-12-27", 88_190),
    )}
    values, _ = sec._sec_quarterly_series_and_ends(usgaap, "StockholdersEquity")
    assert values == {(2025, 2): 65_830, (2025, 3): 73_733, (2025, 4): 88_190}


def test_latest_filing_wins_for_a_restated_quarter():
    usgaap = {"Revenues": concept(
        fact("2025-01-01", "2025-03-31", 100, filed="2025-05-01"),
        fact("2025-01-01", "2025-03-31", 90, filed="2026-05-01"),
    )}
    values, _ = sec._sec_quarterly_series_and_ends(usgaap, "Revenues")
    assert values == {(2025, 1): 90}


def test_annual_only_and_foreign_forms_yield_no_quarters():
    usgaap = {"Revenues": concept(
        fact("2024-01-01", "2024-12-31", 400, form="10-K"),
        fact("2025-01-01", "2025-03-31", 100, form="8-K"),
    )}
    assert sec._sec_quarterly_series_and_ends(usgaap, "Revenues") == ({}, {})


def test_derived_q4_eps_uses_the_per_share_unit():
    usgaap = {"EarningsPerShareDiluted": concept(
        fact(FY_START, Q3_END, 5.62),
        fact(FY_START, FY_END, 7.46, form="10-K"),
        unit="USD/shares",
    )}
    values, _ = sec._sec_quarterly_series_and_ends(usgaap, "EarningsPerShareDiluted")
    assert values[(2025, 3)] == pytest.approx(1.84)


def test_quarterly_statement_has_flat_quarter_columns_and_filed_period_ends():
    usgaap = {
        "PaymentsToAcquireProductiveAssets": concept(
            fact(FY_START, Q1_END, 2_940),
            fact(FY_START, Q2_END, 6_011),
        ),
        "NetCashProvidedByUsedInOperatingActivities": ytd_cashflow(),
    }
    df = sec._build_sec_statement(sec._CASHFLOW_CONCEPTS, usgaap, period="quarterly")
    assert not isinstance(df.columns, pd.MultiIndex)
    assert list(df.columns) == [(2024, 4), (2025, 1), (2025, 2), (2025, 3)]
    capex = dict(zip(df.columns, df.loc["Capital Expenditure"], strict=True))
    assert capex[(2025, 1)] == -(6_011 - 2_940)
    assert df.attrs["period_ends"][(2024, 4)] == pd.Timestamp(Q1_END)


def _apple_like_facts():
    quarters = [
        ("2024-06-30", "2024-09-28"), ("2024-09-29", Q1_END), ("2024-12-29", Q2_END),
        ("2025-03-30", Q3_END), ("2025-06-29", FY_END),
    ]
    usgaap = {
        "Revenues": concept(*[fact(s, e, 100_000_000 + i) for i, (s, e) in enumerate(quarters)]),
        "NetIncomeLoss": concept(*[fact(s, e, 20_000_000) for s, e in quarters]),
        "EarningsPerShareDiluted": concept(*[fact(s, e, 1.5) for s, e in quarters], unit="USD/shares"),
        "StockholdersEquity": concept(*[fact(None, e, 60_000_000) for _, e in quarters]),
        "NetCashProvidedByUsedInOperatingActivities": ytd_cashflow(),
        # One annual fact so the annual path has SEC data too.
        "OperatingIncomeLoss": concept(fact(FY_START, FY_END, 1, form="10-K")),
    }
    usgaap["Revenues"]["units"]["USD"].append(
        {"start": FY_START, "end": FY_END, "val": 400_000_000, "form": "10-K", "fp": "FY", "filed": "2025-10-31"}
    )
    return {"entityName": "Apple-like Inc.", "facts": {"us-gaap": usgaap}}


def test_quarterly_prices_are_read_at_the_filed_period_end_not_the_calendar_quarter_end():
    income, balance, cashflow, info = sec.sec_statements(_apple_like_facts(), "AAPL", period="quarterly")
    history = pd.DataFrame(
        {"Close": [10.0, 99.0]},
        index=pd.to_datetime([FY_END, "2025-09-30"]),  # filed end, then calendar quarter end
    )
    result = build_fundamentals_result(
        ticker="AAPL", info=info, income=income, balance=balance, cashflow=cashflow,
        history=history, periods=40, period="quarterly", as_of="2025-12-01",
    ).to_dict()
    price = next(row for row in result["financials"] if row["metric"] == "Stock Price (FYE)")
    assert price["2025-Q3"] == "$10.00"


def test_fetch_fundamentals_takes_quarters_from_sec_and_skips_yahoo_statements():
    facts = _apple_like_facts()
    yahoo_quarterly = MagicMock()
    with patch("lib.fundamentals.load_company_facts", return_value=CacheRead(facts, "network", 0.0, FILINGS)), \
         patch("lib.fundamentals.yf.Ticker", return_value=MagicMock()), \
         patch("lib.fundamentals._safe_info", return_value={}), \
         patch("lib.fundamentals._safe_history", return_value=pd.DataFrame()), \
         patch("lib.fundamentals._fetch_yfinance_quarterly", yahoo_quarterly):
        payload = fetch_fundamentals("AAPL", use_cache=False)

    yahoo_quarterly.assert_not_called()
    assert payload["quarterly"]["years"][-1] == "2025-Q3"
    assert len(payload["quarterly"]["years"]) == 5
    assert payload["quality_notes"][0] == "Data source: SEC EDGAR; quarterly: SEC EDGAR"
    assert any("derived" in note for note in payload["quality_notes"])


def test_fetch_fundamentals_keeps_yahoo_quarters_when_sec_has_under_a_year_of_them():
    # The XOM shape: SEC annual data, but only a stray quarter or two.
    facts = {"entityName": "Thin Filer", "facts": {"us-gaap": {"Revenues": concept(
        {"start": "2024-01-01", "end": "2024-12-31", "val": 400.0, "form": "10-K", "fp": "FY", "filed": "2025-02-01"},
        fact("2025-01-01", "2025-03-31", 100.0),
        fact("2025-04-01", "2025-06-30", 110.0),
    )}}}
    yahoo = pd.DataFrame(
        [[1.0, 2.0, 3.0, 4.0]], index=["Total Revenue"],
        columns=pd.to_datetime(["2024-09-30", "2024-12-31", "2025-03-31", "2025-06-30"]),
    )
    with patch("lib.fundamentals.load_company_facts", return_value=CacheRead(facts, "network", 0.0, FILINGS)), \
         patch("lib.fundamentals.yf.Ticker", return_value=MagicMock()), \
         patch("lib.fundamentals._safe_info", return_value={}), \
         patch("lib.fundamentals._safe_history", return_value=pd.DataFrame()), \
         patch("lib.fundamentals._fetch_yfinance_quarterly", return_value=(yahoo, pd.DataFrame(), pd.DataFrame())):
        payload = fetch_fundamentals("THIN", use_cache=False)

    assert payload["quality_notes"][0] == "Data source: SEC EDGAR; quarterly: yfinance"
    assert len(payload["quarterly"]["years"]) == 4
