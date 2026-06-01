"""Tests for fundamentals calculations."""

import unittest

import pandas as pd

from lib.fundamentals import build_fundamentals_result


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


if __name__ == "__main__":
    unittest.main()