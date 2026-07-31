"""
Phase 8 — tests for the chart_builder performance helpers: OHLCV row-block
downsampling, bar-interval inference, and the toolbar bar-count summary.
"""

import numpy as np
import pandas as pd

from lib.dash.chart_builder import (
    _downsample_ohlcv,
    _prepare_render_df,
    infer_bar_interval,
    is_subdaily,
    bar_count_summary,
    create_chart,
    DOWNSAMPLE_THRESHOLD,
    MAX_RENDER_BARS,
)
from lib.dash.dash_config import get_theme, DEFAULT_THEME


def _make_ohlcv(n: int, freq: str = "B") -> pd.DataFrame:
    idx = pd.date_range("2015-01-01", periods=n, freq=freq)
    x = np.arange(n, dtype=float)
    return pd.DataFrame(
        {
            "Open": x,
            "High": x + 2.0,
            "Low": x - 2.0,
            "Close": x + 1.0,
            "Volume": np.ones(n),
        },
        index=idx,
    )


def test_downsample_reduces_to_target_and_keeps_datetime_index():
    df = _make_ohlcv(8000)
    out = _downsample_ohlcv(df, MAX_RENDER_BARS)
    assert len(out) <= MAX_RENDER_BARS
    assert len(out) > 0
    assert isinstance(out.index, pd.DatetimeIndex)
    assert list(out.columns) == list(df.columns)


def test_downsample_ohlc_aggregation_is_correct():
    df = _make_ohlcv(8000)
    step = int(np.ceil(len(df) / MAX_RENDER_BARS))
    out = _downsample_ohlcv(df, MAX_RENDER_BARS)

    first_block = df.iloc[:step]
    assert out.iloc[0]["Open"] == first_block["Open"].iloc[0]      # first
    assert out.iloc[0]["High"] == first_block["High"].max()        # max
    assert out.iloc[0]["Low"] == first_block["Low"].min()          # min
    assert out.iloc[0]["Close"] == first_block["Close"].iloc[-1]   # last
    assert out.iloc[0]["Volume"] == first_block["Volume"].sum()    # sum
    # anchor timestamp = last bar of the block
    assert out.index[0] == first_block.index[-1]


def test_downsample_is_identity_when_under_target():
    df = _make_ohlcv(100)
    assert _downsample_ohlcv(df, MAX_RENDER_BARS) is df


def test_downsample_boolean_signal_column_uses_any():
    df = _make_ohlcv(8000)
    flags = np.zeros(len(df), dtype=bool)
    flags[3] = True  # somewhere in the first block
    df["Buy_Trigger_Accepted"] = flags
    out = _downsample_ohlcv(df, MAX_RENDER_BARS)
    assert out["Buy_Trigger_Accepted"].iloc[0] == True  # noqa: E712 - block OR
    assert out["Buy_Trigger_Accepted"].dtype == bool


def test_prepare_render_df_noop_below_threshold():
    df = _make_ohlcv(DOWNSAMPLE_THRESHOLD)
    assert _prepare_render_df(df, {}) is df


def test_prepare_render_df_downsamples_above_threshold():
    df = _make_ohlcv(DOWNSAMPLE_THRESHOLD + 3000)
    out = _prepare_render_df(df, {})
    assert len(out) <= MAX_RENDER_BARS


def test_prepare_render_df_slices_to_view_range():
    df = _make_ohlcv(DOWNSAMPLE_THRESHOLD + 3000)
    start = df.index[100].strftime("%Y-%m-%d")
    end = df.index[400].strftime("%Y-%m-%d")
    out = _prepare_render_df(df, {"view_range": {"start": start, "end": end}})
    # the ~300-bar window is under the render cap, so it renders at full detail
    assert out.index.min() >= pd.to_datetime(start)
    assert out.index.max() <= pd.to_datetime(end)
    assert len(out) <= MAX_RENDER_BARS


def test_infer_bar_interval_daily():
    df = _make_ohlcv(500)  # business days
    assert infer_bar_interval(df.index) == "1D"


def test_infer_bar_interval_hourly():
    idx = pd.date_range("2020-01-01", periods=500, freq="h")
    assert infer_bar_interval(idx) == "1H"


def test_infer_bar_interval_4h():
    idx = pd.date_range("2020-01-01", periods=100, freq="4h")
    assert infer_bar_interval(idx) == "4H"


def test_is_subdaily():
    assert is_subdaily(pd.date_range("2020-01-01", periods=40, freq="h"))
    assert is_subdaily(pd.date_range("2020-01-01", periods=40, freq="4h"))
    assert not is_subdaily(pd.date_range("2020-01-01", periods=40, freq="B"))


def test_intraday_chart_has_rangebreaks_and_time_hover():
    df = _make_ohlcv(80, freq="h")
    theme = get_theme(DEFAULT_THEME)
    config = {
        "selected_plots": ["candlestick", "volume"],
        "show_candlesticks": True,
        "show_bollinger": False,
        "show_sma": False,
        "show_ema": False,
        "show_buy_sell_signals": False,
        "show_legend": False,
        "selected_signals": [],
        "buy_signal_columns": [],
        "sell_signal_columns": [],
        "title": "",
        "indicator_settings": {},
    }
    fig = create_chart(df, config, theme)
    # Weekend rangebreaks on at least one x-axis
    layout = fig.layout
    xaxes = [layout[k] for k in layout if str(k).startswith("xaxis")]
    assert any(getattr(ax, "rangebreaks", None) for ax in xaxes)
    # Candlestick hover includes time
    candle = next(tr for tr in fig.data if tr.type == "candlestick")
    assert "%H:%M" in str(candle.hovertemplate)


def test_infer_bar_interval_short_index_is_safe():
    idx = pd.date_range("2020-01-01", periods=2, freq="D")
    assert infer_bar_interval(idx) == "—"


def test_bar_count_summary_full_and_zoomed():
    df = _make_ohlcv(500)
    full = bar_count_summary(df)
    assert full.startswith("500 bars · 1D · ")
    assert "→" in full

    start = df.index[10].strftime("%Y-%m-%d")
    end = df.index[30].strftime("%Y-%m-%d")
    zoomed = bar_count_summary(df, {"start": start, "end": end})
    assert zoomed.startswith("21 bars · 1D · ")  # inclusive window 10..30


def test_bar_count_summary_downsampled_shows_rendered_cap():
    df = _make_ohlcv(DOWNSAMPLE_THRESHOLD + 3000)
    full = bar_count_summary(df)
    assert f"bars (showing {MAX_RENDER_BARS:,})" in full
    assert full.startswith(f"{len(df):,} bars")

    # Zoomed window under the render cap → full-resolution label, no "showing"
    start = df.index[100].strftime("%Y-%m-%d")
    end = df.index[400].strftime("%Y-%m-%d")
    zoomed = bar_count_summary(df, {"start": start, "end": end})
    assert "showing" not in zoomed
    assert zoomed.startswith("301 bars · ")


def test_bar_count_summary_empty_df():
    assert bar_count_summary(pd.DataFrame()) == ""
    assert bar_count_summary(None) == ""
