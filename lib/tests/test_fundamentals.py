"""Tests for fundamentals calculations and the SEC EDGAR source adapter."""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from lib.fundamentals import (
    _build_sec_statement,
    _fetch_sec_fundamentals,
    _sec_annual_series,
    build_fundamentals_result,
)


class TestFundamentalsResult(unittest.TestCase):
    def setUp(self):
        million = 1_000_000
        years = pd.to_datetime([f"{year}-12-31" for year in range(2013, 2024)])
        self.income = pd.DataFrame(
            [
                [1000 * million * (1.12 ** idx) for idx in range(11)],
                [120 * million * (1.10 ** idx) for idx in range(11)],
                [150 * million * (1.11 ** idx) for idx in range(11)],
                [30 * million * (1.08 ** idx) for idx in range(11)],
                [2 * (1.15 ** idx) for idx in range(11)],
            ],
            index=["Total Revenue", "Operating Income", "Pretax Income", "Tax Provision", "Diluted EPS"],
            columns=years,
        )
        self.balance = pd.DataFrame(
            [
                [500 * million * (1.10 ** idx) for idx in range(11)],
                [20 * million for _ in range(11)],
                [50 * million for _ in range(11)],
                [10 * million for _ in range(11)],
                [100 * million for _ in range(11)],
            ],
            index=["Stockholders Equity", "Current Debt", "Long Term Debt", "Cash And Cash Equivalents", "Total Debt"],
            columns=years,
        )
        self.cashflow = pd.DataFrame(
            [
                [130 * million * (1.11 ** idx) for idx in range(11)],
                [-25 * million * (1.07 ** idx) for idx in range(11)],
            ],
            index=["Operating Cash Flow", "Capital Expenditure"],
            columns=years,
        )
        self.prices = pd.Series({year: 20 * (1.18 ** idx) for idx, year in enumerate(range(2013, 2024))})

    def test_builds_dashboard_payload(self):
        result = build_fundamentals_result(
            ticker="TEST",
            info={"longName": "Test Corp", "financialCurrency": "USD", "earningsGrowth": 0.18, "forwardPE": 25},
            income=self.income,
            balance=self.balance,
            cashflow=self.cashflow,
            yearly_prices=self.prices,
        )

        payload = result.to_dict()

        self.assertEqual(payload["ticker"], "TEST")
        self.assertEqual(payload["company_name"], "Test Corp")
        self.assertEqual(payload["years"][0], 2013)
        self.assertEqual(payload["years"][-1], 2023)
        self.assertEqual(len(payload["financials"]), 13)
        self.assertEqual(len(payload["big_five"]), 7)
        self.assertIn("big_five_note", payload)
        self.assertIn("Entry Price", [row["metric"] for row in payload["valuation"]])
        self.assertIn("ROIC", payload["chart_series"])

    def test_growth_summary_uses_cagr(self):
        result = build_fundamentals_result(
            ticker="TEST",
            info={},
            income=self.income,
            balance=self.balance,
            cashflow=self.cashflow,
            yearly_prices=self.prices,
        )

        equity_growth = next(row for row in result.big_five if row["metric"] == "Equity-GR")

        self.assertEqual(equity_growth["10Y"], "10.00%")

    def test_pe_summary_is_not_percent_formatted(self):
        result = build_fundamentals_result(
            ticker="TEST",
            info={},
            income=self.income,
            balance=self.balance,
            cashflow=self.cashflow,
            yearly_prices=self.prices,
        )

        pe_ratio = next(row for row in result.big_five if row["metric"] == "PE Ratio")

        self.assertNotIn("%", pe_ratio["10Y"])

    def test_free_cash_flow_falls_back_to_operating_less_capex(self):
        result = build_fundamentals_result(
            ticker="TEST",
            info={},
            income=self.income,
            balance=self.balance,
            cashflow=self.cashflow,
            yearly_prices=self.prices,
        )

        fcf_row = next(row for row in result.financials if row["metric"] == "FCF")

        self.assertEqual(fcf_row["2013"], "$105")

    def test_statement_years_take_priority_over_newer_price_years(self):
        prices = pd.concat([self.prices, pd.Series({2024: 100.0})])

        result = build_fundamentals_result(
            ticker="TEST",
            info={},
            income=self.income,
            balance=self.balance,
            cashflow=self.cashflow,
            yearly_prices=prices,
        )

        self.assertEqual(result.years[-1], 2023)


# ---------------------------------------------------------------------------
# SEC EDGAR source adapter tests
# ---------------------------------------------------------------------------

def _make_usgaap_entry(fy: int, val: float, filed: str = "2020-01-01") -> dict:
    return {"form": "10-K", "fy": fy, "val": val, "filed": filed,
            "fp": "FY", "end": f"{fy}-12-31"}


class TestSecAnnualSeries(unittest.TestCase):
    def test_returns_annual_values_for_known_concept(self):
        usgaap = {
            "Revenues": {
                "units": {
                    "USD": [
                        _make_usgaap_entry(2020, 100.0),
                        _make_usgaap_entry(2021, 120.0),
                        _make_usgaap_entry(2022, 150.0),
                    ]
                }
            }
        }
        result = _sec_annual_series(usgaap, "Revenues")
        self.assertEqual(result, {2020: 100.0, 2021: 120.0, 2022: 150.0})

    def test_filters_out_non_annual_forms(self):
        usgaap = {
            "Revenues": {
                "units": {
                    "USD": [
                        {"form": "10-Q", "fy": 2020, "val": 25.0, "filed": "2020-05-01", "fp": "Q1"},
                        _make_usgaap_entry(2020, 100.0),
                    ]
                }
            }
        }
        result = _sec_annual_series(usgaap, "Revenues")
        self.assertEqual(result, {2020: 100.0})

    def test_deduplicates_amended_filings_keeping_latest(self):
        usgaap = {
            "Revenues": {
                "units": {
                    "USD": [
                        {"form": "10-K", "fy": 2021, "val": 200.0, "filed": "2022-02-01", "fp": "FY"},
                        {"form": "10-K/A", "fy": 2021, "val": 205.0, "filed": "2022-03-15", "fp": "FY"},
                    ]
                }
            }
        }
        result = _sec_annual_series(usgaap, "Revenues")
        self.assertEqual(result[2021], 205.0)

    def test_returns_empty_dict_for_unknown_concept(self):
        result = _sec_annual_series({}, "UnknownConcept")
        self.assertEqual(result, {})

    def test_accepts_usd_per_shares_unit_for_eps(self):
        usgaap = {
            "EarningsPerShareDiluted": {
                "units": {
                    "USD/shares": [_make_usgaap_entry(2022, 3.50)]
                }
            }
        }
        result = _sec_annual_series(usgaap, "EarningsPerShareDiluted")
        self.assertEqual(result, {2022: 3.50})


class TestBuildSecStatement(unittest.TestCase):
    def _income_usgaap(self) -> dict:
        return {
            "Revenues": {"units": {"USD": [
                _make_usgaap_entry(2015, 1_000_000),
                _make_usgaap_entry(2016, 1_200_000),
            ]}},
            "OperatingIncomeLoss": {"units": {"USD": [
                _make_usgaap_entry(2015, 100_000),
                _make_usgaap_entry(2016, 130_000),
            ]}},
        }

    def test_builds_dataframe_with_integer_year_columns(self):
        concepts = [
            ("Total Revenue", ["Revenues"], False),
            ("Operating Income", ["OperatingIncomeLoss"], False),
        ]
        df = _build_sec_statement(concepts, self._income_usgaap())
        self.assertFalse(df.empty)
        self.assertEqual(list(df.columns), [2015, 2016])
        self.assertIn("Total Revenue", df.index)

    def test_negates_capex_values(self):
        usgaap = {
            "PaymentsToAcquirePropertyPlantAndEquipment": {"units": {"USD": [
                _make_usgaap_entry(2020, 50_000),
            ]}}
        }
        concepts = [("Capital Expenditure", ["PaymentsToAcquirePropertyPlantAndEquipment"], True)]
        df = _build_sec_statement(concepts, usgaap)
        self.assertEqual(df.loc["Capital Expenditure", 2020], -50_000.0)

    def test_returns_empty_dataframe_when_no_concepts_found(self):
        df = _build_sec_statement([("X", ["NonExistentConcept"], False)], {})
        self.assertTrue(df.empty)

    def test_missing_year_becomes_nan(self):
        """If one concept has data for 2020 only, 2021 rows for other concepts are NaN."""
        usgaap = {
            "Revenues": {"units": {"USD": [
                _make_usgaap_entry(2020, 100.0),
                _make_usgaap_entry(2021, 110.0),
            ]}},
            "OperatingIncomeLoss": {"units": {"USD": [
                _make_usgaap_entry(2020, 10.0),
                # 2021 missing
            ]}},
        }
        concepts = [
            ("Total Revenue", ["Revenues"], False),
            ("Operating Income", ["OperatingIncomeLoss"], False),
        ]
        df = _build_sec_statement(concepts, usgaap)
        self.assertTrue(np.isnan(df.loc["Operating Income", 2021]))

    def test_falls_back_to_second_concept_when_first_is_absent(self):
        usgaap = {
            # First concept absent; second present
            "RevenueFromContractWithCustomerExcludingAssessedTax": {"units": {"USD": [
                _make_usgaap_entry(2022, 999_000),
            ]}}
        }
        concepts = [("Total Revenue", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax"], False)]
        df = _build_sec_statement(concepts, usgaap)
        self.assertEqual(df.loc["Total Revenue", 2022], 999_000.0)


class TestFetchSecFundamentals(unittest.TestCase):
    """Integration-style tests for _fetch_sec_fundamentals using mocks."""

    def _mock_facts(self) -> dict:
        return {
            "entityName": "Acme Corp",
            "facts": {
                "us-gaap": {
                    "Revenues": {"units": {"USD": [_make_usgaap_entry(2020, 500_000_000)]}},
                    "OperatingIncomeLoss": {"units": {"USD": [_make_usgaap_entry(2020, 60_000_000)]}},
                    "NetIncomeLoss": {"units": {"USD": [_make_usgaap_entry(2020, 40_000_000)]}},
                    "StockholdersEquity": {"units": {"USD": [_make_usgaap_entry(2020, 200_000_000)]}},
                    "NetCashProvidedByUsedInOperatingActivities": {"units": {"USD": [_make_usgaap_entry(2020, 70_000_000)]}},
                }
            }
        }

    def test_returns_populated_dataframes_when_cik_and_facts_available(self):
        with patch("lib.fundamentals._sec_cik", return_value="0000012345"), \
             patch("lib.fundamentals._sec_company_facts", return_value=self._mock_facts()):
            income, balance, cashflow, info = _fetch_sec_fundamentals("ACME")

        self.assertFalse(income.empty)
        self.assertIn("Total Revenue", income.index)
        self.assertEqual(info["longName"], "Acme Corp")
        self.assertEqual(info["financialCurrency"], "USD")

    def test_returns_empty_when_cik_not_found(self):
        with patch("lib.fundamentals._sec_cik", return_value=None):
            income, balance, cashflow, info = _fetch_sec_fundamentals("UNKNOWN")

        self.assertTrue(income.empty)
        self.assertEqual(info, {})

    def test_returns_empty_when_company_facts_unavailable(self):
        with patch("lib.fundamentals._sec_cik", return_value="0000099999"), \
             patch("lib.fundamentals._sec_company_facts", return_value=None):
            income, balance, cashflow, info = _fetch_sec_fundamentals("FAIL")

        self.assertTrue(income.empty)

    def test_sec_data_feeds_through_build_fundamentals_result(self):
        """End-to-end: SEC-shaped DataFrames produce a valid dashboard payload."""
        with patch("lib.fundamentals._sec_cik", return_value="0000012345"), \
             patch("lib.fundamentals._sec_company_facts", return_value=self._mock_facts()):
            income, balance, cashflow, info = _fetch_sec_fundamentals("ACME")

        # build_fundamentals_result must accept SEC-shaped DataFrames
        result = build_fundamentals_result(
            ticker="ACME",
            info=info,
            income=income,
            balance=balance,
            cashflow=cashflow,
        )
        payload = result.to_dict()
        self.assertIn(2020, payload["years"])
        self.assertEqual(payload["company_name"], "Acme Corp")


if __name__ == "__main__":
    unittest.main()