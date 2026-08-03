"""Tests for lib.dash.chart_meta — bar-interval inference and the toolbar summary.

Replaces test_chart_downsample.py. The downsampling helpers it also covered
(``_downsample_ohlcv`` / ``_prepare_render_df``, ``DOWNSAMPLE_THRESHOLD``,
``MAX_RENDER_BARS``) existed only because Plotly could not draw more than a few
thousand bars. Lightweight Charts renders the full series, so they are gone
along with the "(showing 1,500)" suffix they produced.
"""

import pandas as pd

from lib.dash.chart_meta import bar_count_summary, infer_bar_interval, is_subdaily


def _make_ohlcv(n: int, freq: str = "B") -> pd.DataFrame:
    idx = pd.date_range("2015-01-01", periods=n, freq=freq)
    return pd.DataFrame({"Close": range(n)}, index=idx)


def test_infer_bar_interval_daily():
    assert infer_bar_interval(_make_ohlcv(500).index) == "1D"


def test_infer_bar_interval_hourly():
    assert infer_bar_interval(pd.date_range("2020-01-01", periods=500, freq="h")) == "1H"


def test_infer_bar_interval_4h():
    assert infer_bar_interval(pd.date_range("2020-01-01", periods=100, freq="4h")) == "4H"


def test_infer_bar_interval_short_index_is_safe():
    assert infer_bar_interval(pd.date_range("2020-01-01", periods=2, freq="D")) == "—"


def test_is_subdaily():
    assert is_subdaily(pd.date_range("2020-01-01", periods=40, freq="h"))
    assert is_subdaily(pd.date_range("2020-01-01", periods=40, freq="4h"))
    assert not is_subdaily(pd.date_range("2020-01-01", periods=40, freq="B"))


def test_bar_count_summary_full_and_zoomed():
    df = _make_ohlcv(500)
    full = bar_count_summary(df)
    assert full.startswith("500 bars · 1D · ")
    assert "→" in full

    start = df.index[10].strftime("%Y-%m-%d")
    end = df.index[30].strftime("%Y-%m-%d")
    zoomed = bar_count_summary(df, {"start": start, "end": end})
    assert zoomed.startswith("21 bars · 1D · ")  # inclusive window 10..30


def test_bar_count_summary_large_series_is_not_annotated():
    """No downsampling any more, so no "(showing N)" caveat at any size."""
    summary = bar_count_summary(_make_ohlcv(8000))
    assert summary.startswith("8,000 bars · 1D · ")
    assert "showing" not in summary


def test_bar_count_summary_prefers_explicit_interval():
    """The fetched interval wins over inference.

    Inference reads the median gap, which is unreliable for a 4h US session:
    only two bars fall inside regular hours, so the gaps alternate 4h and 20h
    and the median lands on whichever side happens to have more samples. The
    caller knows what it fetched, so it says so.
    """
    idx = pd.DatetimeIndex(
        [ts for day in pd.date_range("2024-01-02", periods=10, freq="B")
         for ts in (day + pd.Timedelta(hours=8), day + pd.Timedelta(hours=12))]
    )
    df = pd.DataFrame({"Close": range(len(idx))}, index=idx)
    assert "4H" in bar_count_summary(df, interval="4h")
    # Explicit interval is used verbatim even where inference disagrees.
    hourly = pd.DataFrame(
        {"Close": range(50)},
        index=pd.date_range("2024-01-02", periods=50, freq="h"),
    )
    assert infer_bar_interval(hourly.index) == "1H"
    assert "4H" in bar_count_summary(hourly, interval="4h")


def test_bar_count_summary_subdaily_shows_time():
    df = _make_ohlcv(80, freq="h")
    assert ":" in bar_count_summary(df).split("·")[-1]


def test_bar_count_summary_empty_df():
    assert bar_count_summary(pd.DataFrame()) == ""
    assert bar_count_summary(None) == ""
