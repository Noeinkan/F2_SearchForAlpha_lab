from datetime import date

import pandas as pd
import pytest

from lib.sector_flows import compare_weeks


def test_weekly_flows_ignore_nav_moves_and_split_quantity():
    dates = pd.bdate_range("2026-11-06", "2026-11-19")
    history = pd.DataFrame({"nav": 100.0, "shares": 1000.0}, index=dates)
    history.loc["2026-11-10":, "nav"] = 110
    history.loc["2026-11-11":, "shares"] = 1100
    history.loc["2026-11-12":, ["nav", "shares"]] = [55, 2200]
    history.loc["2026-11-16":, "shares"] = 2300

    friday, rows = compare_weeks({"XLK": history}, date(2026, 11, 20))

    assert friday == date(2026, 11, 13)
    assert rows[0]["latest"] == pytest.approx((11000, 0.11))


def test_missing_session_is_not_treated_as_zero_flow():
    dates = pd.bdate_range("2026-11-02", "2026-11-20")
    history = pd.DataFrame({"nav": 100.0, "shares": 1000.0}, index=dates)

    friday, rows = compare_weeks(
        {"XLK": history, "XLE": history.drop(pd.Timestamp("2026-11-19"))},
        date(2026, 11, 21),
    )

    assert friday == date(2026, 11, 20)
    assert rows[0]["latest"] == (0, 0)
    assert rows[1]["prior"] == (0, 0)
    assert rows[1]["latest"] is None
