"""Regime slicing (ROADMAP 4.15): calendar, slicing, verdict, bundle/combo runners, CLI contract."""

from __future__ import annotations

import json
import re
from datetime import date
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import pytest
from typer.testing import CliRunner

from lib.cli.app import app
from lib.dash.combo_regimes import run_combo_regimes
from lib.dash.combo_walkforward import ComboSpec
from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS
from lib.regimes import (
    COVERAGE_FULL,
    COVERAGE_NONE,
    COVERAGE_PARTIAL,
    STATUS_FAIL,
    STATUS_INCONCLUSIVE,
    STATUS_PASS,
    RegimeCalendarError,
    RegimeRule,
    judge,
    load_calendar,
    parse_calendar,
    score_regimes,
)
from lib.regimes.runner import run_bundle_regimes

REPO = Path(__file__).resolve().parents[2]
TODAY = date(2026, 9, 14)


def _fake_fetch(symbol, start_date, end_date, validate=True, interval="1d"):
    rng = np.random.default_rng(7)
    dates = pd.date_range(start_date, end_date, freq="B")
    n = len(dates)
    close = 100.0 * np.exp(np.cumsum(rng.standard_normal(n) * 0.012))
    return pd.DataFrame(
        {
            "Open": close * 0.999,
            "High": close * 1.01,
            "Low": close * 0.99,
            "Close": close,
            "Volume": rng.integers(1_000_000, 5_000_000, n),
        },
        index=dates,
    )


def _tiny_calendar(**rule):
    return parse_calendar(
        {
            "regimes": [
                {"id": "a", "label": "A", "from": "2024-01-01", "to": "2024-03-31"},
                {"id": "b", "label": "B", "from": "2024-04-01", "to": "2024-06-30"},
                {"id": "c", "label": "C", "from": "2024-07-01", "to": None},
            ],
            "rule": {"metric": "sortino", "threshold": 0.0, "min_passing": 2, **rule},
        }
    )


# --- calendar --------------------------------------------------------------


def test_repo_calendar_loads_with_research_rule():
    cal = load_calendar()
    assert len(cal.regimes) == 7
    assert cal.rule.metric == "sortino"
    assert cal.rule.threshold == 0.0
    assert cal.rule.min_passing == 3
    assert cal.rule.required == ("bear_2022",)
    assert cal.regimes[-1].end is None


def test_repo_calendar_matches_research_md_table():
    """config/regimes.yaml is the code's copy of RESEARCH.md's table; keep them in step."""
    text = (REPO / "RESEARCH.md").read_text(encoding="utf-8")
    rows = re.findall(
        r"^\|\s*(\d{4}-\d{2})\s*→\s*(\d{4}-\d{2}|present)\s*\|\s*([^|]+?)\s*\|",
        text,
        flags=re.MULTILINE,
    )
    assert rows, "regime table not found in RESEARCH.md"
    cal = load_calendar()
    assert len(rows) == len(cal.regimes)
    for (start, end, label), regime in zip(rows, cal.regimes):
        assert regime.start.strftime("%Y-%m") == start, regime.id
        if end == "present":
            assert regime.end is None, regime.id
        else:
            assert regime.end is not None and regime.end.strftime("%Y-%m") == end, regime.id
        assert regime.label == label, regime.id


def test_repo_calendar_regimes_do_not_overlap():
    cal = load_calendar()
    for prev, nxt in zip(cal.regimes, cal.regimes[1:]):
        assert prev.end is not None and prev.end < nxt.start, (prev.id, nxt.id)


@pytest.mark.parametrize(
    "raw, fragment",
    [
        ({"regimes": []}, "no regimes"),
        ({"regimes": [{"id": "a", "from": "2024-02-01", "to": "2024-01-01"}]}, "before"),
        ({"regimes": [{"id": "a", "from": "2024-01-01"}, {"id": "a", "from": "2024-02-01"}]}, "duplicate"),
        ({"regimes": [{"id": "a", "from": "2024-01-01"}], "rule": {"metric": "vibes"}}, "BacktestMetrics"),
        ({"regimes": [{"id": "a", "from": "2024-01-01"}], "rule": {"required": ["zzz"]}}, "unknown regimes"),
        ({"regimes": [{"id": "a", "from": "January"}]}, "YYYY-MM-DD"),
    ],
)
def test_parse_calendar_rejects_malformed(raw, fragment):
    with pytest.raises(RegimeCalendarError, match=fragment):
        parse_calendar(raw)


# --- verdict ---------------------------------------------------------------


def _row(rid, *, counted=True, passed=True):
    return {"id": rid, "label": rid.upper(), "counted": counted, "passed": passed if counted else None}


def test_judge_pass_when_enough_and_required_passes():
    v = judge([_row("a"), _row("b"), _row("c", passed=False)], RegimeRule(min_passing=2, required=("a",)))
    assert v.status == STATUS_PASS
    assert (v.passing, v.evaluated, v.total) == (2, 3, 3)
    assert v.required_passed is True


def test_judge_fail_when_required_regime_misses_even_with_enough_passes():
    v = judge([_row("a", passed=False), _row("b"), _row("c")], RegimeRule(min_passing=2, required=("a",)))
    assert v.status == STATUS_FAIL
    assert v.required_passed is False
    assert "missed required: A" in v.reason


def test_judge_inconclusive_when_required_regime_has_no_data():
    v = judge([_row("a", counted=False), _row("b"), _row("c")], RegimeRule(min_passing=2, required=("a",)))
    assert v.status == STATUS_INCONCLUSIVE
    assert v.required_passed is None
    assert "no full data for required: A" in v.reason


def test_judge_inconclusive_when_uncovered_regimes_could_still_decide():
    v = judge([_row("a"), _row("b", counted=False), _row("c", counted=False)], RegimeRule(min_passing=2))
    assert v.status == STATUS_INCONCLUSIVE


def test_judge_fail_when_uncovered_regimes_cannot_rescue_it():
    v = judge(
        [_row("a", passed=False), _row("b", passed=False), _row("c", counted=False)],
        RegimeRule(min_passing=2),
    )
    assert v.status == STATUS_FAIL


# --- slicing ---------------------------------------------------------------


def test_score_regimes_coverage_inclusive_end_and_counting():
    # Tape starts mid-regime A, so A is partial; B is fully covered; C (open-ended) too.
    idx = pd.date_range("2024-02-15", "2026-09-11", freq="B")
    tape = pd.DataFrame({"Close": np.linspace(100, 200, len(idx))}, index=idx)
    seen: list[tuple[pd.Timestamp, pd.Timestamp]] = []

    def score(slice_df):
        seen.append((slice_df.index[0], slice_df.index[-1]))
        return {"sortino": 1.0 if slice_df.index[0].month == 4 else -1.0}

    out = score_regimes(tape, calendar=_tiny_calendar(), score=score, today=TODAY)
    by_id = {r["id"]: r for r in out["regimes"]}

    assert by_id["a"]["coverage"] == COVERAGE_PARTIAL
    assert by_id["a"]["counted"] is False and by_id["a"]["passed"] is None
    assert by_id["a"]["metrics"] is not None  # still shown, just not counted

    assert by_id["b"]["coverage"] == COVERAGE_FULL
    assert by_id["b"]["passed"] is True
    # 2024-06-28 is the last business day of June: the inclusive end keeps it.
    assert seen[1][1] == pd.Timestamp("2024-06-28")

    assert by_id["c"]["coverage"] == COVERAGE_FULL
    assert by_id["c"]["to"] == TODAY.isoformat() and by_id["c"]["open_ended"] is True
    assert by_id["c"]["passed"] is False

    # One counted pass (B), one counted fail (C), A uncounted: 1 + 1 >= 2 → could still flip.
    assert out["verdict"]["status"] == STATUS_INCONCLUSIVE
    assert out["rule"]["min_passing"] == 2


def test_score_regimes_no_data_regime_is_not_scored():
    idx = pd.date_range("2024-07-01", "2026-09-11", freq="B")
    tape = pd.DataFrame({"Close": np.ones(len(idx))}, index=idx)
    calls = []
    out = score_regimes(
        tape,
        calendar=_tiny_calendar(),
        score=lambda s: calls.append(len(s)) or {"sortino": 0.5},
        today=TODAY,
    )
    by_id = {r["id"]: r for r in out["regimes"]}
    assert by_id["a"]["coverage"] == COVERAGE_NONE and by_id["a"]["metrics"] is None
    assert by_id["b"]["coverage"] == COVERAGE_NONE
    assert len(calls) == 1


def test_score_regimes_intraday_index_slices_by_bar_date():
    idx = pd.date_range("2024-06-28 09:30", "2024-07-01 15:30", freq="h")
    tape = pd.DataFrame({"Close": np.ones(len(idx))}, index=idx)
    out = score_regimes(tape, calendar=_tiny_calendar(), score=lambda s: {"sortino": 1.0}, today=date(2024, 7, 1))
    by_id = {r["id"]: r for r in out["regimes"]}
    assert by_id["b"]["bars"] == sum(1 for t in idx if t.date() <= date(2024, 6, 30))
    assert by_id["c"]["bars"] == sum(1 for t in idx if t.date() >= date(2024, 7, 1))


# --- runners ---------------------------------------------------------------


def _assert_payload_shape(payload):
    for key in ("kind", "subject", "ticker", "interval", "params", "data", "rule", "regimes", "verdict",
                "regimes_id", "recorded_at"):
        assert key in payload, key
    assert len(payload["regimes"]) == 7
    for row in payload["regimes"]:
        for key in ("id", "label", "character", "from", "to", "open_ended", "coverage", "bars", "counted",
                    "passed", "metrics"):
            assert key in row, key
    for key in ("status", "passing", "evaluated", "total", "min_passing", "required_passed", "reason"):
        assert key in payload["verdict"], key
    assert payload["verdict"]["status"] in {STATUS_PASS, STATUS_FAIL, STATUS_INCONCLUSIVE}


def test_run_bundle_regimes_scores_every_regime_with_full_daily_history():
    with patch("lib.regimes.runner.fetch_data", side_effect=_fake_fetch):
        payload = run_bundle_regimes(strategy_name="mean_reversion_rsi_bb", ticker="SPY", today=TODAY)
    _assert_payload_shape(payload)
    assert payload["kind"] == "bundle" and payload["ticker"] == "SPY"
    assert all(row["coverage"] == COVERAGE_FULL for row in payload["regimes"])
    assert payload["verdict"]["evaluated"] == 7
    assert payload["data"]["from"] < "2019-01-01"  # indicator warmup fetched before the first regime


def test_run_combo_regimes_payload():
    combo = ComboSpec(
        buy_signals=("RSI_Oversold_Buy",),
        sell_signals=("RSI_Overbought_Sell",),
        ticker="tsla",
        indicator_settings=DEFAULT_INDICATOR_SETTINGS,
    )
    with patch("lib.regimes.runner.fetch_data", side_effect=_fake_fetch):
        payload = run_combo_regimes(combo=combo, today=TODAY)
    _assert_payload_shape(payload)
    assert payload["kind"] == "combo"
    assert payload["subject"] == "combo:RSI_Oversold_Buy|RSI_Overbought_Sell"
    assert payload["ticker"] == "TSLA"


# --- dashboard view --------------------------------------------------------


def test_render_regime_panel_marks_verdict_and_uncounted_rows():
    from lib.dash.dash_config import get_theme
    from lib.dash.regime_view import render_regime_panel

    idx = pd.date_range("2024-02-15", "2026-09-11", freq="B")
    tape = pd.DataFrame({"Close": np.ones(len(idx))}, index=idx)
    scored = score_regimes(
        tape,
        calendar=_tiny_calendar(required=["b"]),
        score=lambda s: {"sortino": 0.4, "total_return": 0.05, "benchmark_return": 0.02,
                         "max_drawdown": 0.03, "num_trades": 4},
        today=TODAY,
    )
    payload = {"ticker": "SPY", "interval": "1d", **scored}
    text = str(render_regime_panel(payload, get_theme()))

    assert "PASSES REGIME RULE" in text
    assert "including B" in text
    assert "partial" in text and "not counted" in text  # regime A starts before the tape


# --- CLI contract ----------------------------------------------------------

runner = CliRunner()


def test_cli_regimes_json_contract():
    with patch("lib.regimes.runner.fetch_data", side_effect=_fake_fetch):
        result = runner.invoke(
            app, ["regimes", "--name", "mean_reversion_rsi_bb", "--ticker", "SPY", "--json"]
        )
    assert result.exit_code == 0, result.output
    _assert_payload_shape(json.loads(result.output))


def test_cli_regimes_unknown_strategy():
    result = runner.invoke(app, ["regimes", "--name", "no_such_bundle", "--json"])
    assert result.exit_code == 2
    assert json.loads(result.output)["error"] == "unknown_strategy"


def test_cli_regimes_invalid_params():
    result = runner.invoke(app, ["regimes", "--name", "mean_reversion_rsi_bb", "--params", "[1]", "--json"])
    assert result.exit_code == 2
    assert json.loads(result.output)["error"] == "invalid_params"
