"""Tests for fundamentals calculations and the SEC EDGAR source adapter."""

import unittest
from unittest.mock import MagicMock, patch

import numpy as np
import pandas as pd

from lib.fundamentals import (
    _build_sec_statement,
    _clean_period_prices,
    _clean_statement,
    _fetch_sec_fundamentals,
    _live_price_snapshot,
    _quarterly_close_prices,
    _sec_annual_series,
    build_fundamentals_result,
    fetch_fundamentals,
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
        self.assertEqual(payload["period"], "annual")
        self.assertEqual(payload["years"][0], 2013)
        self.assertEqual(payload["years"][-1], 2023)
        self.assertEqual(len(payload["financials"]), 13)
        self.assertEqual(len(payload["big_five"]), 7)
        self.assertIn("big_five_note", payload)
        self.assertIn("Entry Price", [row["metric"] for row in payload["valuation"]])
        self.assertIn("ROIC", payload["chart_series"])

    def test_estimated_eps_growth_uses_minimum_positive_rate(self):
        result = build_fundamentals_result(
            ticker="TEST",
            info={"earningsGrowth": 0.82, "forwardPE": 25, "trailingEps": 10.0},
            income=self.income,
            balance=self.balance,
            cashflow=self.cashflow,
            yearly_prices=self.prices,
        )
        valuation = {row["metric"]: row["value"] for row in result.valuation}

        self.assertEqual(valuation["Analysts' GR"], "82.00%")
        self.assertEqual(valuation["Historical Equity GR"], "10.00%")
        self.assertEqual(valuation["Estimated EPS GR"], "10.00%")

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

        self.assertEqual(fcf_row[2013], "$105")

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


class TestQuarterlyFundamentals(unittest.TestCase):
    def setUp(self):
        million = 1_000_000
        quarters = pd.to_datetime([
            "2022-03-31", "2022-06-30", "2022-09-30", "2022-12-31",
            "2023-03-31", "2023-06-30", "2023-09-30", "2023-12-31",
            "2024-03-31", "2024-06-30",
        ])
        self.income = pd.DataFrame(
            [
                [100 * million * (1.03 ** idx) for idx in range(10)],
                [120 * million * (1.02 ** idx) for idx in range(10)],
                [150 * million * (1.02 ** idx) for idx in range(10)],
                [30 * million for _ in range(10)],
                [2 * (1.05 ** idx) for idx in range(10)],
            ],
            index=["Total Revenue", "Operating Income", "Pretax Income", "Tax Provision", "Diluted EPS"],
            columns=quarters,
        )
        self.balance = pd.DataFrame(
            [
                [500 * million * (1.02 ** idx) for idx in range(10)],
                [20 * million for _ in range(10)],
                [50 * million for _ in range(10)],
                [10 * million for _ in range(10)],
                [70 * million for _ in range(10)],
            ],
            index=["Stockholders Equity", "Current Debt", "Long Term Debt", "Cash And Cash Equivalents", "Total Debt"],
            columns=quarters,
        )
        self.cashflow = pd.DataFrame(
            [
                [130 * million * (1.02 ** idx) for idx in range(10)],
                [-25 * million for _ in range(10)],
            ],
            index=["Operating Cash Flow", "Capital Expenditure"],
            columns=quarters,
        )
        self.prices = pd.Series(
            {(2022, 1): 20.0, (2022, 2): 21.0, (2022, 3): 22.0, (2022, 4): 23.0,
             (2023, 1): 24.0, (2023, 2): 25.0, (2023, 3): 26.0, (2023, 4): 27.0,
             (2024, 1): 28.0, (2024, 2): 29.0},
        )

    def test_clean_statement_keeps_quarter_columns(self):
        cleaned = _clean_statement(self.income, period="quarterly")
        self.assertEqual(cleaned.columns.tolist()[0], (2022, 1))
        self.assertEqual(cleaned.columns.tolist()[-1], (2024, 2))

    def test_clean_period_prices_preserves_quarter_keys(self):
        idx = pd.date_range("2024-07-01", "2026-03-20", freq="B")
        history = pd.DataFrame({"Close": [200.0 + i for i in range(len(idx))]}, index=idx)
        cleaned = _clean_period_prices(_quarterly_close_prices(history), period="quarterly")
        self.assertIn((2025, 1), cleaned.index)
        self.assertIn((2025, 4), cleaned.index)
        self.assertTrue(all(isinstance(period, tuple) for period in cleaned.index))

    def test_quarterly_stock_price_row_populated(self):
        result = build_fundamentals_result(
            ticker="TEST",
            info={"longName": "Test Corp", "financialCurrency": "USD"},
            income=self.income,
            balance=self.balance,
            cashflow=self.cashflow,
            period_prices=self.prices,
            periods=10,
            period="quarterly",
        )
        payload = result.to_dict()

        self.assertEqual(payload["period"], "quarterly")
        self.assertEqual(payload["years"][-1], "2024-Q2")
        self.assertEqual(payload["valuation"], [])
        self.assertEqual(payload["big_five"], [])
        self.assertEqual(len(payload["financials"]), 13)
        self.assertIn("Sales", payload["chart_series"])
        sales_row = next(row for row in payload["financials"] if row["metric"] == "Sales (Rev)")
        self.assertIn("2024-Q2", sales_row)
        stock_row = next(row for row in payload["financials"] if row["metric"] == "Stock Price (31/12)")
        self.assertNotEqual(stock_row["2024-Q2"], "--")

    def test_fetch_fundamentals_exposes_annual_and_quarterly_blocks(self):
        annual_income = pd.DataFrame([[1.0]], index=["Total Revenue"], columns=[2023])
        annual_balance = pd.DataFrame([[1.0]], index=["Stockholders Equity"], columns=[2023])
        annual_cashflow = pd.DataFrame([[1.0]], index=["Operating Cash Flow"], columns=[2023])
        quarterly_income = pd.DataFrame([[1.0]], index=["Total Revenue"], columns=pd.to_datetime(["2024-03-31"]))
        quarterly_balance = pd.DataFrame([[1.0]], index=["Stockholders Equity"], columns=pd.to_datetime(["2024-03-31"]))
        quarterly_cashflow = pd.DataFrame([[1.0]], index=["Operating Cash Flow"], columns=pd.to_datetime(["2024-03-31"]))

        ticker_obj = MagicMock()
        with patch("lib.fundamentals._fetch_sec_fundamentals", return_value=(annual_income, annual_balance, annual_cashflow, {})), \
             patch("lib.fundamentals.yf.Ticker", return_value=ticker_obj), \
             patch("lib.fundamentals._safe_info", return_value={"longName": "Test Corp"}), \
             patch("lib.fundamentals._safe_history", return_value=pd.DataFrame()), \
             patch("lib.fundamentals._fetch_yfinance_quarterly", return_value=(quarterly_income, quarterly_balance, quarterly_cashflow)):
            payload = fetch_fundamentals("TEST")

        self.assertIn("annual", payload)
        self.assertIn("quarterly", payload)
        self.assertEqual(payload["financials"], payload["annual"]["financials"])
        self.assertEqual(payload["quarterly"]["period"], "quarterly")


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


class TestLivePriceSnapshot(unittest.TestCase):
    """Tests for the yfinance live-price extractor and payload attachment."""

    def test_prefers_current_price_over_regular_market_price(self):
        snap = _live_price_snapshot({
            "currentPrice": 100.0,
            "regularMarketPrice": 99.5,
            "previousClose": 98.0,
            "regularMarketChange": 2.0,
            "regularMarketChangePercent": 0.0204,
            "marketState": "REGULAR",
            "currency": "USD",
        })
        self.assertEqual(snap["last_price"], 100.0)
        self.assertEqual(snap["previous_close"], 98.0)
        self.assertEqual(snap["last_change"], 2.0)
        self.assertAlmostEqual(snap["last_change_pct"], 0.0204, places=6)
        self.assertEqual(snap["market_state"], "REGULAR")
        self.assertEqual(snap["price_currency"], "USD")

    def test_falls_back_to_regular_market_price(self):
        snap = _live_price_snapshot({"regularMarketPrice": 50.25, "previousClose": 49.0})
        self.assertEqual(snap["last_price"], 50.25)
        self.assertEqual(snap["previous_close"], 49.0)
        # Change is derived when regularMarketChange is absent.
        self.assertAlmostEqual(snap["last_change"], 1.25, places=6)
        self.assertAlmostEqual(snap["last_change_pct"], 1.25 / 49.0, places=6)

    def test_returns_none_for_missing_values(self):
        snap = _live_price_snapshot({})
        self.assertIsNone(snap["last_price"])
        self.assertIsNone(snap["previous_close"])
        self.assertIsNone(snap["last_change"])
        self.assertIsNone(snap["last_change_pct"])
        self.assertIsNone(snap["market_state"])
        self.assertEqual(snap["price_currency"], "USD")  # default fallback

    def test_currency_fallback_uses_arg(self):
        snap = _live_price_snapshot({}, currency="EUR")
        self.assertEqual(snap["price_currency"], "EUR")

    def test_market_state_uppercased(self):
        snap = _live_price_snapshot({"marketState": "pre"})
        self.assertEqual(snap["market_state"], "PRE")


class TestFinancialsLiveAttachment(unittest.TestCase):
    """Stock Price (31/12) row receives the live price; it sits at the top."""

    def _build(self, info=None, live_price=None):
        years = pd.to_datetime([f"{year}-12-31" for year in range(2013, 2024)])
        income = pd.DataFrame(
            [[1_000_000_000 * (1.12 ** i) for i in range(11)]],
            index=["Total Revenue"],
            columns=years,
        )
        balance = pd.DataFrame(
            [[500_000_000 * (1.10 ** i) for i in range(11)]],
            index=["Stockholders Equity"],
            columns=years,
        )
        cashflow = pd.DataFrame(
            [[130_000_000 * (1.11 ** i) for i in range(11)]],
            index=["Operating Cash Flow"],
            columns=years,
        )
        prices = pd.Series({year: 20 * (1.18 ** i) for i, year in enumerate(range(2013, 2024))})
        return build_fundamentals_result(
            ticker="TEST",
            info=info or {},
            income=income,
            balance=balance,
            cashflow=cashflow,
            yearly_prices=prices,
            live_price=live_price,
        ).to_dict()

    def test_stock_price_row_is_first(self):
        payload = self._build(info={"currentPrice": 42.0}, live_price=42.0)
        self.assertEqual(payload["financials"][0]["metric"], "Stock Price (31/12)")

    def test_live_value_attached_to_stock_price_row(self):
        payload = self._build(info={"currentPrice": 42.5}, live_price=42.5)
        stock_row = payload["financials"][0]
        self.assertIn("live_value", stock_row)
        self.assertEqual(stock_row["live_value"], 42.5)

    def test_live_value_absent_when_no_quote(self):
        payload = self._build(info={}, live_price=None)
        stock_row = payload["financials"][0]
        self.assertNotIn("live_value", stock_row)

    def test_total_row_count_unchanged(self):
        payload = self._build(info={"currentPrice": 1.0}, live_price=1.0)
        self.assertEqual(len(payload["financials"]), 13)


if __name__ == "__main__":
    unittest.main()