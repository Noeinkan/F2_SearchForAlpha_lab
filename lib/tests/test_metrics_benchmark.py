"""Contract tests for the benchmark-relative and confidence metrics.

Same discipline as ``test_metrics.py``: the reference numbers are computed here
from the definition, by hand, so a rewrite that keeps the shape but changes the
formula fails loudly.

Two pairs are easy to conflate, and each has a test that pins them apart:

* ``excess_return`` (arithmetic difference against buy-and-hold) versus
  ``alpha`` (annualised Jensen's alpha, net of beta). A levered long has plenty
  of the first and none of the second.
* ``psr`` (is the Sharpe positive at all?) versus ``deflated_sharpe`` (is it
  positive once you account for how many configurations were tried?). They are
  the same number for a single trial and diverge as the search widens.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from lib.metrics import compute_metrics, with_deflated_sharpe
from lib.metrics.benchmark import (
    alpha,
    benchmark_stats,
    beta,
    compound_return,
    down_capture,
    information_ratio,
    tracking_error,
    up_capture,
)
from lib.metrics.deflated import (
    NORMAL_KURTOSIS,
    deflated_sharpe_ratio,
    expected_max_sharpe,
    probabilistic_sharpe_ratio,
    sample_moments,
    trial_sharpe_std,
)

PPY = 252


def _market(n: int = 200, seed: int = 7) -> np.ndarray:
    """A reproducible benchmark return series with both up and down bars."""
    rng = np.random.default_rng(seed)
    return rng.normal(0.0004, 0.011, n)


class TestBenchmarkPrimitives:
    def test_beta_of_a_doubled_series_is_two(self):
        b = _market()
        assert beta(2.0 * b, b) == pytest.approx(2.0)

    def test_beta_of_an_uncorrelated_series_is_near_zero(self):
        b = _market()
        independent = _market(seed=99)
        assert beta(independent, b) == pytest.approx(0.0, abs=0.15)

    def test_a_levered_long_earns_excess_return_but_no_alpha(self):
        """The distinction the old combo-search 'Alpha %' could not make.

        Doubling the market doubles the return. It adds no skill, so Jensen's
        alpha is zero while the arithmetic excess is large and positive. The
        seed here is one where the market rose — leverage on a market that fell
        produces an equally large *negative* excess, and still no alpha.
        """
        b = _market(seed=6)
        levered = 2.0 * b
        stats = benchmark_stats(levered, b, periods_per_year=PPY, risk_free_rate=0.0)

        assert stats.beta == pytest.approx(2.0)
        assert stats.alpha == pytest.approx(0.0, abs=1e-9)
        assert stats.excess_return > 0.05

    def test_alpha_is_the_annualised_per_bar_intercept(self):
        """A constant edge of c per bar on top of the market is c * bars/year."""
        b = _market()
        edge = 0.0002
        stats = benchmark_stats(b + edge, b, periods_per_year=PPY, risk_free_rate=0.0)

        assert stats.beta == pytest.approx(1.0)
        assert stats.alpha == pytest.approx(edge * PPY)

    def test_tracking_error_and_information_ratio_vanish_when_tracking_exactly(self):
        b = _market()
        assert tracking_error(b, b, periods_per_year=PPY) == 0.0
        assert information_ratio(b, b, periods_per_year=PPY) == 0.0

    def test_tracking_error_is_the_annualised_active_deviation(self):
        b = _market()
        r = _market(seed=13)
        expected = float(np.std(r - b, ddof=1) * math.sqrt(PPY))
        assert tracking_error(r, b, periods_per_year=PPY) == pytest.approx(expected)

    def test_information_ratio_is_active_return_over_tracking_error(self):
        b = _market()
        r = _market(seed=13)
        active = r - b
        expected = float(math.sqrt(PPY) * active.mean() / active.std(ddof=1))
        assert information_ratio(r, b, periods_per_year=PPY) == pytest.approx(expected)

    def test_matching_the_benchmark_captures_all_of_it_both_ways(self):
        b = _market()
        assert up_capture(b, b) == pytest.approx(1.0)
        assert down_capture(b, b) == pytest.approx(1.0)

    def test_sitting_in_cash_captures_nothing(self):
        b = _market()
        flat = np.zeros_like(b)
        assert up_capture(flat, b) == pytest.approx(0.0)
        assert down_capture(flat, b) == pytest.approx(0.0)

    def test_down_capture_goes_negative_when_the_strategy_gains_on_red_bars(self):
        """Short the market and the down-capture ratio flips sign, as it should."""
        b = _market()
        assert down_capture(-b, b) < 0

    def test_compound_return_survives_a_wipeout_bar(self):
        """A bar worse than -100% is clamped: equity floors at zero, not below."""
        assert compound_return([0.1, -1.5, 0.2]) == pytest.approx(-1.0)

    def test_excess_return_prefers_the_equity_curve_over_recompounding(self):
        """Fees land on bars with no position, so the two disagree — and the
        equity curve is the authority."""
        b = np.array([0.01, -0.02, 0.03])
        r = np.array([0.01, 0.0, 0.03])
        stats = benchmark_stats(
            r, b, periods_per_year=PPY, strategy_total_return=0.5
        )
        assert stats.excess_return == pytest.approx(0.5 - compound_return(b))

    def test_a_series_too_short_to_measure_reports_zeros_not_nan(self):
        stats = benchmark_stats([0.01], [0.02], periods_per_year=PPY)
        assert stats.alpha == 0.0
        assert stats.beta == 0.0
        assert stats.information_ratio == 0.0
        assert stats.benchmark_return == pytest.approx(0.02)


class TestProbabilisticSharpe:
    def test_psr_at_its_own_sharpe_is_a_coin_flip(self):
        assert probabilistic_sharpe_ratio(
            1.5, n_obs=500, benchmark_sharpe=1.5, periods_per_year=PPY
        ) == pytest.approx(0.5)

    def test_psr_matches_the_hand_computed_normal_case(self):
        from statistics import NormalDist

        annual_sharpe, n = 1.2, 505
        sr = annual_sharpe / math.sqrt(PPY)
        variance = 1.0 + ((NORMAL_KURTOSIS - 1.0) / 4.0) * sr * sr
        expected = NormalDist().cdf(sr * math.sqrt(n - 1) / math.sqrt(variance))

        assert probabilistic_sharpe_ratio(
            annual_sharpe, n_obs=n, periods_per_year=PPY
        ) == pytest.approx(expected)

    def test_negative_skew_and_fat_tails_cost_you_confidence(self):
        """The whole point of PSR over a t-test: the shape of the returns counts."""
        normal = probabilistic_sharpe_ratio(1.2, n_obs=505, periods_per_year=PPY)
        ugly = probabilistic_sharpe_ratio(
            1.2, n_obs=505, skew=-1.5, kurtosis=9.0, periods_per_year=PPY
        )
        assert ugly < normal

    def test_a_longer_sample_earns_more_confidence(self):
        short = probabilistic_sharpe_ratio(1.0, n_obs=60, periods_per_year=PPY)
        long = probabilistic_sharpe_ratio(1.0, n_obs=2520, periods_per_year=PPY)
        assert long > short

    def test_a_sample_too_short_to_judge_reports_no_confidence(self):
        assert probabilistic_sharpe_ratio(3.0, n_obs=1, periods_per_year=PPY) == 0.0

    def test_sample_moments_recognise_a_normal_shaped_series(self):
        rng = np.random.default_rng(3)
        n, skew, kurtosis = sample_moments(rng.normal(0, 0.01, 5000))
        assert n == 5000
        assert skew == pytest.approx(0.0, abs=0.1)
        assert kurtosis == pytest.approx(NORMAL_KURTOSIS, abs=0.2)


class TestDeflatedSharpe:
    def test_one_trial_has_nothing_to_deflate(self):
        psr = probabilistic_sharpe_ratio(1.2, n_obs=505, periods_per_year=PPY)
        dsr = deflated_sharpe_ratio(
            1.2, n_obs=505, num_trials=1, sharpe_std=0.8, periods_per_year=PPY
        )
        assert dsr == pytest.approx(psr)

    def test_expected_max_sharpe_grows_with_the_number_of_trials(self):
        assert expected_max_sharpe(1, 0.5) == 0.0
        wide = expected_max_sharpe(1000, 0.5)
        narrow = expected_max_sharpe(10, 0.5)
        assert wide > narrow > 0

    def test_expected_max_sharpe_scales_with_the_spread_of_the_trials(self):
        assert expected_max_sharpe(100, 1.0) == pytest.approx(
            2.0 * expected_max_sharpe(100, 0.5)
        )

    def test_a_wider_search_deflates_the_same_result_further(self):
        kwargs = dict(n_obs=505, sharpe_std=0.6, periods_per_year=PPY)
        few = deflated_sharpe_ratio(1.5, num_trials=5, **kwargs)
        many = deflated_sharpe_ratio(1.5, num_trials=5000, **kwargs)
        assert many < few

    def test_a_search_where_every_trial_scored_alike_cannot_deflate(self):
        """No dispersion, no evidence about how easy a high Sharpe was to hit."""
        psr = probabilistic_sharpe_ratio(1.2, n_obs=505, periods_per_year=PPY)
        assert deflated_sharpe_ratio(
            1.2, n_obs=505, num_trials=900, sharpe_std=0.0, periods_per_year=PPY
        ) == pytest.approx(psr)

    def test_trial_sharpe_std_needs_two_trials(self):
        assert trial_sharpe_std([1.4]) == 0.0
        assert trial_sharpe_std([1.0, 2.0]) == pytest.approx(
            float(np.std([1.0, 2.0], ddof=1))
        )

    def test_every_probability_stays_inside_the_unit_interval(self):
        for sharpe in (-4.0, 0.0, 0.7, 12.0):
            psr = probabilistic_sharpe_ratio(sharpe, n_obs=505, periods_per_year=PPY)
            dsr = deflated_sharpe_ratio(
                sharpe, n_obs=505, num_trials=250, sharpe_std=0.7, periods_per_year=PPY
            )
            assert 0.0 <= psr <= 1.0
            assert 0.0 <= dsr <= 1.0


def _result_frame(strategy: np.ndarray, market: np.ndarray) -> pd.DataFrame:
    """The columns ``compute_metrics`` reads, without running the engine."""
    equity = 10_000.0 * np.cumprod(1.0 + strategy)
    return pd.DataFrame(
        {
            "Close": 100.0 * np.cumprod(1.0 + market),
            "Portfolio_Value": equity,
            "Strategy_Returns": strategy,
            "Returns": market,
            "Units": np.ones_like(strategy),
        },
        index=pd.bdate_range("2022-01-03", periods=len(strategy)),
    )


class TestComputeMetricsIntegration:
    def test_the_benchmark_column_reaches_the_metrics_object(self):
        """3.10.1: ``Returns`` was on every result frame and never rendered."""
        market = _market(300)
        df = _result_frame(2.0 * market, market)
        m = compute_metrics(df, 10_000.0, interval="1d")

        assert m.benchmark_return == pytest.approx(compound_return(market))
        assert m.beta == pytest.approx(2.0)
        assert m.alpha == pytest.approx(0.0, abs=1e-9)
        assert m.excess_return == pytest.approx(m.total_return - m.benchmark_return)

    def test_the_sample_behind_the_ratios_is_carried_on_the_result(self):
        market = _market(300)
        df = _result_frame(market, market)
        m = compute_metrics(df, 10_000.0, interval="1d")

        assert m.num_bars == 300
        assert m.periods_per_year == 252
        assert m.num_trials == 1
        assert m.deflated_sharpe == pytest.approx(m.psr)

    def test_an_intraday_interval_annualises_the_new_ratios_too(self):
        from lib.timeframes import periods_per_year

        market = _market(300)
        df = _result_frame(market + 0.0001, market)
        m = compute_metrics(df, 10_000.0, interval="1h")
        assert m.periods_per_year == periods_per_year("1h")
        assert m.alpha == pytest.approx(0.0001 * periods_per_year("1h"))

    def test_a_caller_can_supply_its_own_benchmark(self):
        market = _market(300)
        other = _market(300, seed=42)
        df = _result_frame(market, market)
        m = compute_metrics(df, 10_000.0, interval="1d", benchmark_returns=other)
        assert m.benchmark_return == pytest.approx(compound_return(other))

    def test_a_frame_with_no_benchmark_column_reports_zeros(self):
        market = _market(120)
        df = _result_frame(market, market).drop(columns=["Returns"])
        m = compute_metrics(df, 10_000.0, interval="1d")
        assert m.benchmark_return == 0.0
        assert m.beta == 0.0

    def test_the_trial_count_can_be_folded_in_after_the_fact(self):
        """3.10.4: one backtest cannot know how many others it was picked from."""
        market = _market(400)
        df = _result_frame(market + 0.0003, market)
        m = compute_metrics(df, 10_000.0, interval="1d")

        deflated = with_deflated_sharpe(m, num_trials=800, trial_sharpe_std=0.7)
        assert deflated.num_trials == 800
        assert deflated.deflated_sharpe < m.deflated_sharpe
        # Nothing else about the run changed.
        assert deflated.sharpe == m.sharpe
        assert deflated.psr == m.psr

    def test_the_registry_renders_every_new_metric(self):
        from lib.metrics import format_canonical
        from lib.metrics.names import BY_KEY

        for key in (
            "benchmark_return", "excess_return", "alpha", "beta",
            "information_ratio", "tracking_error", "up_capture", "down_capture",
            "psr", "deflated_sharpe", "num_trials", "num_bars",
            "returns_skew", "returns_kurtosis", "periods_per_year",
        ):
            assert key in BY_KEY, f"{key} has no registry entry"
            assert isinstance(format_canonical(key, 0.5), str)

    def test_psr_renders_as_a_percentage(self):
        from lib.metrics import format_canonical

        assert format_canonical("psr", 0.9312) == "93.1%"


class TestLeaderboardDeflation:
    def _leaderboard(self, sharpes: list[float]) -> pd.DataFrame:
        return pd.DataFrame(
            {
                "Sharpe_Ratio": sharpes,
                "Bars": [505] * len(sharpes),
                "Skew": [0.0] * len(sharpes),
                "Kurtosis": [NORMAL_KURTOSIS] * len(sharpes),
                "Periods_Per_Year": [252] * len(sharpes),
                "DSR_%": [99.0] * len(sharpes),
            }
        )

    def test_the_search_size_replaces_the_single_trial_figure(self):
        from lib.dash.helpers import apply_deflated_sharpe

        df = self._leaderboard([2.1, 1.4, 0.9, 0.2, -0.4])
        deflated = apply_deflated_sharpe(df, num_trials=4000)

        assert (deflated["Trials"] == 4000).all()
        assert (deflated["DSR_%"] < 99.0).all()
        # Still ordered by merit: the best Sharpe keeps the best DSR.
        assert deflated["DSR_%"].iloc[0] == deflated["DSR_%"].max()

    def test_attempts_that_produced_no_row_still_count_against_the_winner(self):
        from lib.dash.helpers import apply_deflated_sharpe

        df = self._leaderboard([2.1, 1.4, 0.9])
        counted = apply_deflated_sharpe(df, num_trials=3)
        honest = apply_deflated_sharpe(df, num_trials=900)
        assert honest["DSR_%"].iloc[0] < counted["DSR_%"].iloc[0]

    def test_an_empty_leaderboard_is_left_alone(self):
        from lib.dash.helpers import apply_deflated_sharpe

        assert apply_deflated_sharpe(pd.DataFrame(), num_trials=10).empty


class TestStudyDeflation:
    """The Optuna path deflates against the trials store, not the row count."""

    def _trial(self, sharpe: float, **extra) -> object:
        from lib.store.trials import TrialRecord

        metrics = {
            "sharpe": sharpe,
            "num_bars": 505,
            "returns_skew": 0.0,
            "returns_kurtosis": NORMAL_KURTOSIS,
            "periods_per_year": 252,
            "deflated_sharpe": 0.99,
            "num_trials": 1,
        }
        metrics.update(extra)
        return TrialRecord(
            trial_id=1, study_id="s", strategy_name="x", optuna_trial_number=0,
            metric="sharpe", objective_value=sharpe, params={}, metrics=metrics,
            seed=1, wall_seconds=0.1, git_commit=None, created_at="now",
        )

    def test_the_winner_is_deflated_by_the_whole_study(self):
        from lib.bayesian_optimization import deflate_against_study

        study = [self._trial(s) for s in (2.2, 1.7, 1.1, 0.4, -0.3)]
        best = study[0].metrics
        out = deflate_against_study(best, study)

        assert out["num_trials"] == 5
        assert out["deflated_sharpe"] < best["deflated_sharpe"]
        # The single-trial figure it replaced is not mutated in place.
        assert best["deflated_sharpe"] == 0.99

    def test_a_resumed_study_counts_the_trials_it_already_had(self):
        from lib.bayesian_optimization import deflate_against_study

        short = [self._trial(s) for s in (2.2, 1.7, 1.1)]
        resumed = short + [self._trial(s) for s in (0.9, 0.4, 0.1, -0.3, -0.6)]
        assert (
            deflate_against_study(short[0].metrics, resumed)["deflated_sharpe"]
            < deflate_against_study(short[0].metrics, short)["deflated_sharpe"]
        )

    def test_a_trial_predating_the_sample_fields_is_left_alone(self):
        """Rows written before 3.10 carry no ``num_bars`` — do not zero them."""
        from lib.bayesian_optimization import deflate_against_study

        legacy = {"sharpe": 1.4}
        study = [self._trial(1.4), self._trial(0.2)]
        assert deflate_against_study(legacy, study) == legacy


class TestOverfittingNote:
    def _theme(self) -> dict:
        from lib.dash.dash_config import get_theme

        return get_theme()

    def _text(self, component) -> str:
        return str(component.children)

    def test_the_caption_reports_the_computed_number(self):
        """3.10.6: a measured probability, not a general warning about searching."""
        from lib.dash.callbacks.shared_optimization_ui import build_overfitting_note

        note = build_overfitting_note(
            pd.Series({"DSR_%": 12.5, "Sharpe_Ratio": 1.83}), 240, self._theme()
        )
        text = self._text(note)
        assert "Deflated Sharpe 12%" in text
        assert "240 combos" in text
        assert "1.83" in text

    def test_a_credible_winner_reads_differently_from_a_coin_flip(self):
        from lib.dash.callbacks.shared_optimization_ui import build_overfitting_note

        theme = self._theme()
        strong = self._text(
            build_overfitting_note(pd.Series({"DSR_%": 98.0, "Sharpe_Ratio": 2.4}), 50, theme)
        )
        weak = self._text(
            build_overfitting_note(pd.Series({"DSR_%": 3.0, "Sharpe_Ratio": 2.4}), 50, theme)
        )
        assert "survives" in strong
        assert "not distinguishable" in weak

    def test_a_row_without_a_dsr_falls_back_to_the_general_warning(self):
        from lib.dash.callbacks.shared_optimization_ui import build_overfitting_note

        note = build_overfitting_note(pd.Series({"Sharpe_Ratio": 1.0}), 12, self._theme())
        assert "Ranked from 12 combos" in self._text(note)

    def test_a_nan_dsr_does_not_read_as_a_failed_result(self):
        from lib.dash.callbacks.shared_optimization_ui import build_overfitting_note

        note = build_overfitting_note(
            pd.Series({"DSR_%": float("nan"), "Sharpe_Ratio": 1.0}), 12, self._theme()
        )
        assert "Ranked from 12 combos" in self._text(note)
