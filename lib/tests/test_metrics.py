"""Contract tests for lib.metrics — the one metrics engine.

Four implementations of Sharpe drifted apart in this repo because nothing ever
pinned a *value*. The old tests checked annualisation relationships and
finiteness, which every one of the four variants satisfied while disagreeing
about the risk-free rate. So the tests here compute the reference number by
hand, from the definition, and compare.

The rest guard the two things a consolidation can silently get wrong: the unit
and sign of each metric, and where trade statistics come from. Trade figures
must be read from the engine's round-trip ledger — reconstructing them by
scanning the ``Units`` column is what this work removed, and a scale-in is the
case where the two disagree.
"""

from __future__ import annotations

import logging

import numpy as np
import pandas as pd
import pytest

from lib.metrics import (
    BacktestMetrics,
    compute_metrics,
    format_canonical,
    format_ui,
    leaderboard_columns,
    round_trip_stats,
    sharpe_ratio,
    sortino_ratio,
    ui_row,
)
from lib.metrics.core import PROFIT_FACTOR_SENTINEL
from lib.metrics.ledger import TRADE_COLUMNS, trades_to_frame
from lib.metrics.names import BY_UI_KEY, _SPECS
from lib.strategy import backtest

FEE = 0.001
FX = 0.002
SLIP = 0.0005


def _frame(close, buy=None, sell=None):
    """Minimal OHLCV + signal frame, matching the house builder in
    ``test_strategy_engine.py`` so failures point at metrics, never at data."""
    close = np.asarray(close, dtype=float)
    n = len(close)
    df = pd.DataFrame(
        {
            "Open": close,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": 1_000_000,
            "Buy_Signal": np.zeros(n, dtype=int) if buy is None else np.asarray(buy, dtype=int),
            "Sell_Signal": np.zeros(n, dtype=int) if sell is None else np.asarray(sell, dtype=int),
        },
        index=pd.bdate_range("2022-01-03", periods=n),
    )
    return df


def _run(df, **kwargs):
    params = dict(
        initial_capital=10_000.0,
        position_sizing_strategy="percentage_of_portfolio",
        position_sizing_params={"percent": 0.5},
        buy_indicators=["Buy_Signal"],
        sell_indicators=["Sell_Signal"],
        position_scaling=1.0,
        min_holding_period=0,
        commission_per_trade=0.0,
        slippage_pct=0.0,
        fx_fee_pct=0.0,
    )
    params.update(kwargs)
    return backtest(df=df, **params)


def _run_all_in(df, **kwargs):
    """``_run`` with a sizer far larger than the account, so every sell clamps
    to the whole position and each signal pair is one unambiguous round trip."""
    kwargs.setdefault("position_sizing_params", {"percent": 5.0})
    kwargs.setdefault("trailing_stop_loss", 0.9)
    return _run(df, **kwargs)


# --------------------------------------------------------------------------- #
# 3.11.1 — one implementation, pinned against hand-computed references
# --------------------------------------------------------------------------- #

class TestRatioValues:
    def test_sharpe_matches_the_definition(self):
        r = np.array([0.01, -0.005, 0.02, 0.0, -0.01, 0.015, 0.003, -0.002])
        expected = np.sqrt(252) * r.mean() / r.std(ddof=1)
        assert sharpe_ratio(r, periods_per_year=252, risk_free_rate=0.0) == pytest.approx(
            expected, rel=1e-12
        )

    def test_sharpe_subtracts_the_per_bar_share_of_the_risk_free_rate(self):
        r = np.array([0.01, -0.005, 0.02, 0.0, -0.01, 0.015, 0.003, -0.002])
        excess = r - 0.03 / 252
        expected = np.sqrt(252) * excess.mean() / excess.std(ddof=1)
        assert sharpe_ratio(r, periods_per_year=252, risk_free_rate=0.03) == pytest.approx(
            expected, rel=1e-12
        )

    def test_a_positive_risk_free_rate_lowers_sharpe(self):
        r = np.array([0.01, -0.005, 0.02, 0.0, -0.01, 0.015, 0.003, -0.002])
        at_zero = sharpe_ratio(r, periods_per_year=252, risk_free_rate=0.0)
        at_two_pct = sharpe_ratio(r, periods_per_year=252, risk_free_rate=0.02)
        assert at_two_pct < at_zero

    def test_sortino_divides_by_downside_deviation_only(self):
        r = np.array([0.01, -0.005, 0.02, 0.0, -0.01, 0.015, 0.003, -0.002])
        downside = r[r < 0]
        expected = np.sqrt(252) * r.mean() / downside.std(ddof=1)
        assert sortino_ratio(r, periods_per_year=252, risk_free_rate=0.0) == pytest.approx(
            expected, rel=1e-12
        )

    def test_sortino_exceeds_sharpe_when_upside_is_the_noisier_side(self):
        r = np.array([0.05, -0.001, 0.04, -0.002, 0.06, -0.001, 0.03, -0.002])
        assert sortino_ratio(r, periods_per_year=252) > sharpe_ratio(r, periods_per_year=252)

    def test_annualisation_scales_with_the_square_root_of_the_bar_count(self):
        r = np.array([0.01, -0.005, 0.02, 0.0, -0.01, 0.015, 0.003, -0.002])
        daily = sharpe_ratio(r, periods_per_year=252, risk_free_rate=0.0)
        weekly = sharpe_ratio(r, periods_per_year=52, risk_free_rate=0.0)
        assert daily == pytest.approx(weekly * np.sqrt(252 / 52), rel=1e-12)

    def test_a_flat_return_series_has_no_ratio_rather_than_a_nan(self):
        flat = np.zeros(20)
        assert sharpe_ratio(flat, periods_per_year=252) == 0.0
        assert sortino_ratio(flat, periods_per_year=252) == 0.0

    def test_calmar_is_annual_growth_over_the_drawdown_that_paid_for_it(self):
        # 253 bars is exactly one year at 252 ppy, so CAGR == total return.
        close = np.concatenate([np.linspace(100.0, 80.0, 100), np.linspace(80.0, 150.0, 153)])
        m = compute_metrics(_run_all_in(_frame(close, buy=[1] + [0] * 252)), periods_per_year=252)
        assert m.cagr == pytest.approx(m.total_return, rel=1e-9)
        assert m.calmar == pytest.approx(m.cagr / m.max_drawdown, rel=1e-12)


# --------------------------------------------------------------------------- #
# Units and signs — the contract every consumer relies on
# --------------------------------------------------------------------------- #

class TestUnitContract:
    def test_max_drawdown_is_a_positive_magnitude(self):
        close = np.array([100.0, 110.0, 90.0, 95.0, 100.0])
        m = compute_metrics(_run_all_in(_frame(close, buy=[1, 0, 0, 0, 0])))
        assert m.max_drawdown > 0

    def test_max_drawdown_of_a_monotonic_climb_is_zero(self):
        close = np.linspace(100.0, 150.0, 40)
        m = compute_metrics(_run_all_in(_frame(close, buy=[1] + [0] * 39)))
        assert m.max_drawdown == pytest.approx(0.0, abs=1e-12)

    def test_rates_are_fractions_not_percentages(self):
        close = np.linspace(100.0, 200.0, 60)
        m = compute_metrics(_run_all_in(_frame(close, buy=[1] + [0] * 59)))
        # Roughly a doubling: ~1.0 as a fraction, not ~100.
        assert 0.5 < m.total_return < 1.5
        assert 0.0 <= m.win_rate <= 1.0
        assert 0.0 <= m.exposure <= 1.0

    def test_an_empty_frame_reports_zeroes_rather_than_raising(self):
        m = compute_metrics(pd.DataFrame())
        assert m == BacktestMetrics()
        assert m.total_return == 0.0
        assert m.num_trades == 0

    def test_every_metric_is_finite(self):
        close = np.array([100.0, 100.0, 100.0, 100.0, 100.0, 100.0])
        m = compute_metrics(_run_all_in(_frame(close)))
        for key, value in m.as_dict().items():
            assert np.isfinite(value), f"{key} is not finite"

    def test_initial_capital_defaults_to_the_first_bar_of_the_curve(self):
        close = np.linspace(100.0, 120.0, 30)
        result = _run_all_in(_frame(close, buy=[1] + [0] * 29), initial_capital=25_000.0)
        assert compute_metrics(result).total_return == pytest.approx(
            compute_metrics(result, 25_000.0).total_return
        )


# --------------------------------------------------------------------------- #
# 3.11.2 / 3.11.3 — trades come from the ledger, and 'trade' means round trip
# --------------------------------------------------------------------------- #

def _two_trade_tape():
    """One winner then one loser, with known magnitudes."""
    close = np.array(
        [100, 100, 100, 110, 110, 110, 110, 100, 100, 95, 95, 95, 95, 95],
        dtype=float,
    )
    buy = np.zeros(len(close), dtype=int)
    sell = np.zeros(len(close), dtype=int)
    buy[1] = 1     # fill bar 2 @100
    sell[2] = 1    # fill bar 3 @110 -> winner
    buy[7] = 1     # fill bar 8 @100
    sell[8] = 1    # fill bar 9 @95  -> loser
    return _frame(close, buy=buy, sell=sell)


class TestTradeStatistics:
    def test_round_trip_statistics_come_from_the_ledger(self):
        m = compute_metrics(_run_all_in(_two_trade_tape()))
        assert m.num_trades == 2
        assert m.win_rate == pytest.approx(0.5)
        assert m.avg_win > 0 > m.avg_loss
        assert m.profit_factor == pytest.approx(m.avg_win / abs(m.avg_loss))
        assert m.expectancy == pytest.approx((m.avg_win + m.avg_loss) / 2)

    def test_num_trades_counts_round_trips_and_num_fills_counts_executions(self):
        m = compute_metrics(_run_all_in(_two_trade_tape()))
        # Two round trips is four fills: two buys and two sells.
        assert m.num_trades == 2
        assert m.num_fills == 4

    def test_a_scale_in_is_one_round_trip_but_several_fills(self):
        """The Units scan this replaced split a scale-in into several trades."""
        close = np.array([100, 100, 102, 104, 106, 108, 110, 112, 100, 100, 100], dtype=float)
        buy = np.zeros(len(close), dtype=int)
        buy[1] = buy[2] = buy[3] = 1   # three entries, never flat between them
        # The trailing stop closes the *whole* position, so the round trip ends;
        # a signal sell would be sized by the same sizer and only exit part of it.
        result = _run(
            _frame(close, buy=buy),
            position_sizing_params={"percent": 0.3},
            consecutive_signal_mode="scale_in",
            trailing_stop_loss=0.05,
        )
        assert (result["Units_to_buy"] > 0).sum() == 3, "tape did not actually scale in"
        m = compute_metrics(result)
        assert m.num_trades == 1
        assert m.num_fills == 4

    def test_an_open_position_is_excluded_from_realised_statistics(self):
        close = np.linspace(100.0, 140.0, 30)
        buy = np.zeros(len(close), dtype=int)
        buy[5] = 1
        m = compute_metrics(_run_all_in(_frame(close, buy=buy)))
        assert m.num_trades == 0
        assert m.open_trades == 1
        assert m.win_rate == 0.0

    def test_accumulation_never_closes_so_it_reports_no_round_trips(self):
        close = np.linspace(100.0, 130.0, 40)
        buy = np.zeros(len(close), dtype=int)
        buy[::5] = 1
        m = compute_metrics(_run_all_in(_frame(close, buy=buy), strategy_mode="accumulation"))
        assert m.num_trades == 0
        assert m.num_fills > 0
        assert m.open_trades == 1

    def test_profit_factor_uses_a_sentinel_when_there_are_no_losers(self):
        ledger = trades_to_frame([
            {**dict.fromkeys(TRADE_COLUMNS, 0), "exit_reason": "signal", "net_pnl": 50.0},
            {**dict.fromkeys(TRADE_COLUMNS, 0), "exit_reason": "signal", "net_pnl": 25.0},
        ])
        assert round_trip_stats(ledger).profit_factor == PROFIT_FACTOR_SENTINEL

    def test_fees_reach_the_metrics_from_the_ledger(self):
        m = compute_metrics(
            _run_all_in(_two_trade_tape(), commission_per_trade=FEE,
                        slippage_pct=SLIP, fx_fee_pct=FX)
        )
        assert m.total_fees > 0

    def test_total_fees_include_the_open_position(self):
        ledger = trades_to_frame([
            {**dict.fromkeys(TRADE_COLUMNS, 0), "exit_reason": "signal", "net_pnl": 10.0, "fees": 3.0},
            {**dict.fromkeys(TRADE_COLUMNS, 0), "exit_reason": "open", "net_pnl": 5.0, "fees": 2.0},
        ])
        stats = round_trip_stats(ledger)
        assert stats.num_trades == 1
        assert stats.open_trades == 1
        assert stats.total_fees == pytest.approx(5.0)

    def test_a_missing_ledger_warns_instead_of_quietly_reporting_zero(self, caplog):
        result = _run_all_in(_two_trade_tape())
        stripped = result.copy()
        stripped.attrs.pop("trades", None)
        with caplog.at_level(logging.WARNING, logger="lib.metrics.engine"):
            m = compute_metrics(stripped, context="test")
        assert m.num_trades == 0
        assert any("No trade ledger" in r.message for r in caplog.records)


# --------------------------------------------------------------------------- #
# 3.11.4 — annualisation follows the bar interval
# --------------------------------------------------------------------------- #

class TestAnnualisation:
    def test_a_shorter_bar_annualises_more_aggressively(self):
        close = np.linspace(100.0, 130.0, 80)
        result = _run_all_in(_frame(close, buy=[1] + [0] * 79))
        daily = compute_metrics(result, interval="1d")
        hourly = compute_metrics(result, interval="1h")
        assert abs(hourly.sharpe) > abs(daily.sharpe)

    def test_an_explicit_periods_per_year_overrides_the_interval(self):
        close = np.linspace(100.0, 130.0, 80)
        result = _run_all_in(_frame(close, buy=[1] + [0] * 79))
        assert compute_metrics(result, interval="1h").sharpe == pytest.approx(
            compute_metrics(result, periods_per_year=1764).sharpe
        )


# --------------------------------------------------------------------------- #
# 3.11.5 — the name registry
# --------------------------------------------------------------------------- #

class TestNameRegistry:
    def test_every_spec_names_a_real_metrics_field(self):
        fields = set(BacktestMetrics().as_dict())
        for spec in _SPECS:
            assert spec.key in fields, f"{spec.key} is not a BacktestMetrics field"

    def test_every_metrics_field_has_a_spec(self):
        from lib.metrics.names import BY_KEY

        for field in BacktestMetrics().as_dict():
            assert field in BY_KEY, f"{field} has no registry entry"

    def test_ui_row_converts_fractions_to_percents(self):
        m = BacktestMetrics(total_return=0.2015, win_rate=0.55, max_drawdown=0.1824)
        row = ui_row(m)
        assert row["Total_Return_%"] == pytest.approx(20.15)
        assert row["Win_Rate_%"] == pytest.approx(55.0)

    def test_ui_row_flips_drawdown_to_the_negative_convention(self):
        row = ui_row(BacktestMetrics(max_drawdown=0.1824))
        assert row["Max_Drawdown_%"] == pytest.approx(-18.24)

    def test_canonical_and_ui_formatters_agree(self):
        """The same metric renders identically whichever units you hold it in."""
        from lib.metrics.names import BY_KEY

        m = BacktestMetrics(
            total_return=0.2015, max_drawdown=0.1824, win_rate=0.55,
            sharpe=1.42, num_trades=21, expectancy=-5.89,
        )
        row = ui_row(m)
        for key in ("total_return", "max_drawdown", "win_rate", "sharpe",
                    "num_trades", "expectancy"):
            ui_key = BY_KEY[key].ui_key
            assert format_canonical(key, getattr(m, key)) == format_ui(ui_key, row[ui_key])

    def test_drawdown_renders_with_a_real_magnitude_and_a_minus_sign(self):
        """The Backtest tab used to render a 18% drawdown as '-0.18%'."""
        assert format_canonical("max_drawdown", 0.1824) == "-18.24%"

    def test_win_rate_renders_as_a_percentage(self):
        """The Backtest tab used to render a 55% win rate as '0.6%'."""
        assert format_canonical("win_rate", 0.55) == "55.0%"

    def test_every_registry_entry_formats_without_raising(self):
        for spec in _SPECS:
            assert isinstance(format_canonical(spec.key, 0.5), str)
            assert isinstance(format_ui(spec.ui_key, 0.5), str)

    def test_a_non_numeric_value_renders_as_a_placeholder(self):
        assert format_canonical("sharpe", None) == "—"

    def test_leaderboard_columns_are_all_known_names(self):
        for column in leaderboard_columns():
            assert column in BY_UI_KEY
