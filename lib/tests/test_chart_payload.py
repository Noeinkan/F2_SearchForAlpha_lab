"""Tests for lib.dash.chart_payload — the Python→client chart contract.

The payload crosses a JSON boundary into JavaScript, so the failure modes are
quiet ones: a numpy scalar that will not serialise, a NaN that becomes an
invalid literal, a timestamp in the wrong unit that puts every bar in 1970.
These pin the parts a browser would only report as a blank canvas.
"""

import json

import numpy as np
import pandas as pd
import pytest

from lib.dash.chart_payload import (
    _volume_alpha,
    build_chart_payload,
    empty_payload,
    encode_times,
)
from lib.dash.dash_config import DEFAULT_INDICATOR_SETTINGS, get_theme
from lib.dash.signal_markers import trigger_counts

THEME = get_theme()


def _frame(n=120, freq="B", start="2024-01-02"):
    idx = pd.date_range(start, periods=n, freq=freq)
    rng = np.random.default_rng(3)
    close = pd.Series(100 + np.cumsum(rng.normal(0, 1, n)), index=idx)
    df = pd.DataFrame({
        "Open": close + rng.normal(0, 0.2, n),
        "High": close + 1.5,
        "Low": close - 1.5,
        "Close": close,
        "Volume": rng.integers(1_000_000, 5_000_000, n).astype(float),
    }, index=idx)
    ma = close.rolling(10, min_periods=1).mean()
    df["RSI_Oversold_Buy"] = (close < ma).astype(int)
    df["RSI_Overbought_Sell"] = (close > ma).astype(int)
    return df


def _config(**overrides):
    config = {
        "selected_plots": ["candlestick", "volume", "rsi", "cci", "macd"],
        "show_candlesticks": True,
        "show_bollinger": False,
        "show_sma": False,
        "show_ema": False,
        "show_buy_sell_signals": True,
        "selected_signals": ["buy", "sell"],
        "buy_signal_columns": ["RSI_Oversold_Buy"],
        "sell_signal_columns": ["RSI_Overbought_Sell"],
        "consecutive_signal_mode": "edge",
        "cooldown_bars": 0,
        "signal_logic": "or",
        "signal_window": 0,
        "indicator_settings": DEFAULT_INDICATOR_SETTINGS,
        "ticker": "TSLA",
    }
    config.update(overrides)
    return config


# ------------------------------------------------------------ time encoding

def test_daily_times_are_date_strings():
    idx = pd.date_range("2024-01-02", periods=3, freq="B")
    assert encode_times(idx, False) == ["2024-01-02", "2024-01-03", "2024-01-04"]


@pytest.mark.parametrize("unit", ["ns", "us", "s"])
def test_intraday_times_are_epoch_seconds_at_any_resolution(unit):
    """pandas 3 builds DatetimeIndex at microsecond resolution by default.

    Dividing the raw int64 by a hard-coded 1e9 therefore lands 1000x off and
    puts every bar in 1970 — a silent, total corruption of the chart.
    """
    idx = pd.DatetimeIndex(
        pd.date_range("2024-08-05 09:30", periods=3, freq="h").astype(f"datetime64[{unit}]")
    )
    stamps = encode_times(idx, True)
    assert all(isinstance(s, int) for s in stamps)
    rendered = [pd.Timestamp(s, unit="s", tz="UTC").strftime("%H:%M") for s in stamps]
    assert rendered == ["09:30", "10:30", "11:30"]


def test_intraday_times_read_the_wall_clock_as_utc():
    """Lightweight Charts renders numeric time as UTC and offers no timezone.

    Frames are tz-naive exchange-local, so the wall clock is taken as UTC —
    otherwise a US session would display shifted by the local offset.
    """
    idx = pd.DatetimeIndex(pd.date_range("2024-08-05 09:30", periods=1, freq="h"))
    stamp = encode_times(idx, True)[0]
    assert pd.Timestamp(stamp, unit="s", tz="UTC").strftime("%Y-%m-%d %H:%M") == "2024-08-05 09:30"


def test_tz_aware_index_is_stripped_not_converted():
    aware = pd.DatetimeIndex(
        pd.date_range("2024-08-05 09:30", periods=1, freq="h", tz="America/New_York")
    )
    stamp = encode_times(aware, True)[0]
    assert pd.Timestamp(stamp, unit="s", tz="UTC").strftime("%H:%M") == "09:30"


# ------------------------------------------------------------- invariants

def test_candle_times_are_strictly_ascending_and_unique():
    """LWC corrupts silently on unordered or duplicated timestamps."""
    payload = build_chart_payload(_frame(), _config(), THEME)
    times = [c["time"] for c in payload["candles"]]
    assert times == sorted(times)
    assert len(set(times)) == len(times)


def test_unsorted_duplicated_input_is_normalised():
    df = _frame(40)
    scrambled = pd.concat([df.iloc[20:], df.iloc[:25]])   # out of order + overlap
    payload = build_chart_payload(scrambled, _config(), THEME)
    times = [c["time"] for c in payload["candles"]]
    assert times == sorted(times)
    assert len(set(times)) == len(times)


def test_markers_are_time_ordered():
    payload = build_chart_payload(_frame(), _config(), THEME)
    times = [m["time"] for m in payload["markers"]]
    assert times == sorted(times)


def test_payload_is_json_serialisable_with_all_panes():
    config = _config(
        selected_plots=["candlestick", "volume", "rsi", "cci", "macd",
                        "vwap", "adx", "atr", "obv"],
        show_bollinger=True, show_sma=True, show_ema=True,
    )
    blob = json.dumps(build_chart_payload(_frame(200), config, THEME))
    # json.dumps writes NaN/Infinity as bare literals that JSON.parse rejects.
    assert "NaN" not in blob
    assert "Infinity" not in blob


def test_indicator_warmup_is_dropped_not_nulled():
    """A NaN warm-up must not reach the client as a null-valued point."""
    payload = build_chart_payload(_frame(200), _config(), THEME)
    rsi = next(s for s in payload["series"] if s["id"].startswith("rsi:"))
    assert len(rsi["data"]) < len(payload["candles"])
    assert all(p["value"] is not None for p in rsi["data"])


def test_every_series_names_an_existing_pane():
    """The glue looks panes up by key; an unknown key silently drops the series."""
    config = _config(selected_plots=["candlestick", "volume", "rsi", "macd"])
    payload = build_chart_payload(_frame(), config, THEME)
    keys = {p["key"] for p in payload["panes"]}
    assert all(s["pane"] in keys for s in payload["series"])


def test_panes_follow_selected_plots_order():
    config = _config(selected_plots=["candlestick", "macd", "rsi"])
    payload = build_chart_payload(_frame(), config, THEME)
    # price is always first; the rest keep the canonical stacking order.
    assert [p["key"] for p in payload["panes"]] == ["price", "rsi", "macd"]


# --------------------------------------------------------------- markers

def test_marker_count_matches_the_trigger_counter():
    """The TRIG/REJ pills and the markers share one engine, so they cannot drift."""
    df = _frame(200)
    config = _config()
    payload = build_chart_payload(df, config, THEME)
    counts = trigger_counts(
        df, config["selected_signals"],
        config["buy_signal_columns"], config["sell_signal_columns"],
        logic=config["signal_logic"], window=config["signal_window"],
        mode=config["consecutive_signal_mode"], cooldown=config["cooldown_bars"],
    )
    assert len(payload["markers"]) == counts["accepted"] + counts["rejected"]


def test_no_markers_when_signals_are_disabled():
    payload = build_chart_payload(_frame(), _config(show_buy_sell_signals=False), THEME)
    assert payload["markers"] == []


def test_markers_use_bar_relative_positions():
    """LWC anchors markers to the bar, so no Close*1.5% offset arithmetic."""
    payload = build_chart_payload(_frame(), _config(), THEME)
    positions = {m["position"] for m in payload["markers"]}
    assert positions <= {"aboveBar", "belowBar"}


# ------------------------------------------------------------------- meta

def test_meta_reports_interval_and_ticker():
    payload = build_chart_payload(_frame(), _config(interval="1d"), THEME)
    assert payload["meta"]["ticker"] == "TSLA"
    assert payload["meta"]["interval"] == "1d"
    assert payload["meta"]["subdaily"] is False


def test_meta_flags_subdaily_frames():
    payload = build_chart_payload(
        _frame(100, freq="h", start="2024-08-05 09:30"), _config(interval="1h"), THEME
    )
    assert payload["meta"]["subdaily"] is True
    assert isinstance(payload["candles"][0]["time"], int)


def test_empty_payload_is_serialisable():
    json.dumps(empty_payload(THEME, "nothing to see"))


def test_a_failing_indicator_pane_does_not_blank_the_chart():
    """One bad column should cost its pane, not the whole render."""
    df = _frame().drop(columns=["Volume"])
    payload = build_chart_payload(
        df, _config(selected_plots=["candlestick", "volume", "rsi"]), THEME
    )
    assert payload["candles"]
    assert "volume" not in {p["key"] for p in payload["panes"]}


# -------------------------------------------------------- volume RVOL color

@pytest.mark.parametrize(
    "rvol,alpha",
    [
        (None, "99"),
        (float("nan"), "99"),
        (0.5, "55"),
        (0.74, "55"),
        (0.75, "99"),
        (1.0, "99"),
        (1.24, "99"),
        (1.25, "CC"),
        (1.9, "CC"),
        (2.0, "FF"),
        (5.0, "FF"),
    ],
)
def test_volume_alpha_bands(rvol, alpha):
    assert _volume_alpha(rvol) == alpha


def test_volume_bars_use_rvol_alpha_and_direction_hue():
    """Quiet down-bars fade; extreme up-bars go solid up-color."""
    n = 25
    idx = pd.date_range("2024-01-02", periods=n, freq="B")
    vol = np.full(n, 1_000_000.0)
    vol[-2] = 500_000.0   # dry (~0.5x)
    vol[-1] = 3_000_000.0  # extreme (~2.7x vs ~1.04M avg)
    open_ = np.full(n, 100.0)
    close = np.full(n, 101.0)  # up by default
    open_[-2] = 101.0
    close[-2] = 100.0       # down on the dry bar
    df = pd.DataFrame({
        "Open": open_,
        "High": np.maximum(open_, close) + 1,
        "Low": np.minimum(open_, close) - 1,
        "Close": close,
        "Volume": vol,
    }, index=idx)
    # Minimal signal cols so markers path is happy
    df["RSI_Oversold_Buy"] = 0
    df["RSI_Overbought_Sell"] = 0

    settings = dict(DEFAULT_INDICATOR_SETTINGS)
    settings["volume"] = {"ma_period": 20}
    payload = build_chart_payload(
        df,
        _config(
            selected_plots=["candlestick", "volume"],
            show_buy_sell_signals=False,
            indicator_settings=settings,
        ),
        THEME,
    )
    vol_series = next(s for s in payload["series"] if s["id"] == "volume")
    colors = [b["color"] for b in vol_series["data"]]
    up, down = THEME["chart_candle_up"], THEME["chart_candle_down"]

    assert colors[-2] == down + "55"
    assert colors[-1] == up + "FF"
    assert all(c.startswith("#") and len(c) == 9 for c in colors)
    json.dumps(payload)  # colors must stay JSON-safe


def test_volume_alpha_falls_back_when_ma_is_zero():
    """Zero MA must not divide-by-zero; alpha stays normal."""
    idx = pd.date_range("2024-01-02", periods=3, freq="B")
    df = pd.DataFrame({
        "Open": [10.0, 10.0, 10.0],
        "High": [11.0, 11.0, 11.0],
        "Low": [9.0, 9.0, 9.0],
        "Close": [10.5, 10.5, 10.5],
        "Volume": [0.0, 0.0, 0.0],
        "RSI_Oversold_Buy": [0, 0, 0],
        "RSI_Overbought_Sell": [0, 0, 0],
    }, index=idx)
    payload = build_chart_payload(
        df,
        _config(selected_plots=["candlestick", "volume"], show_buy_sell_signals=False),
        THEME,
    )
    vol_series = next(s for s in payload["series"] if s["id"] == "volume")
    up = THEME["chart_candle_up"]
    assert all(b["color"] == up + "99" for b in vol_series["data"])


# ------------------------------------------------ semantic vs identity color

def test_buy_sell_markers_use_candle_up_down_colors():
    """Markers are semantic: direction from candle up/down, not identity accents."""
    payload = build_chart_payload(_frame(), _config(), THEME)
    buys = [m for m in payload["markers"] if m.get("text") == "B"]
    sells = [m for m in payload["markers"] if m.get("text") == "S"]
    assert buys
    assert sells
    assert all(m["color"] == THEME["chart_candle_up"] for m in buys)
    assert all(m["color"] == THEME["chart_candle_down"] for m in sells)


def test_overlay_identity_colors_are_not_pnl_green_red():
    """SMA/BB overlays must not reuse accent_green / accent_red (P&L semantics)."""
    df = _frame()
    close = df["Close"]
    df["BB_upper"] = close + 2
    df["BB_lower"] = close - 2
    df["BB_middle"] = close
    df["SMA_short"] = close.rolling(5, min_periods=1).mean()
    df["SMA_medium"] = close.rolling(10, min_periods=1).mean()
    df["SMA_long"] = close.rolling(20, min_periods=1).mean()
    df["SMA_trend"] = close.rolling(50, min_periods=1).mean()

    payload = build_chart_payload(
        df,
        _config(
            show_bollinger=True,
            show_sma=True,
            show_buy_sell_signals=False,
            selected_plots=["candlestick"],
        ),
        THEME,
    )
    overlay_ids = {
        "price:BB UPPER", "price:BB LOWER", "price:BB MIDDLE",
        "price:SMA SHORT", "price:SMA MEDIUM", "price:SMA LONG", "price:SMA TREND",
    }
    colors = {
        s["options"]["color"]
        for s in payload["series"]
        if s["id"] in overlay_ids
    }
    assert colors
    assert THEME["accent_green"] not in colors
    assert THEME["accent_red"] not in colors

    trend = next(s for s in payload["series"] if s["id"] == "price:SMA TREND")
    assert trend["options"].get("lineStyle") == 1  # dotted


def test_rsi_and_macd_use_identity_pane_hues():
    payload = build_chart_payload(
        _frame(),
        _config(selected_plots=["candlestick", "rsi", "macd"], show_buy_sell_signals=False),
        THEME,
    )
    rsi = next(s for s in payload["series"] if s["id"].startswith("rsi:RSI"))
    macd_line = next(s for s in payload["series"] if s["id"].startswith("macd:MACD"))
    assert rsi["options"]["color"] == THEME["accent_purple"]
    assert macd_line["options"]["color"] == THEME["accent_cyan"]


def test_remaining_panes_use_distinct_identity_hues():
    """CCI/ADX/ATR/OBV/Vol-MA: no purple/cyan pile-up, helper MAs are neutral."""
    payload = build_chart_payload(
        _frame(),
        _config(
            selected_plots=["candlestick", "volume", "cci", "adx", "atr", "obv"],
            show_volume_ma=True,
            show_buy_sell_signals=False,
        ),
        THEME,
    )
    by_id = {s["id"]: s for s in payload["series"]}

    cci = next(s for s in payload["series"] if s["id"].startswith("cci:CCI"))
    adx = next(s for s in payload["series"] if s["id"].startswith("adx:ADX"))
    atr = by_id["atr:value"]
    obv = by_id["obv:OBV"]
    assert cci["options"]["color"] == THEME["accent_orange"]
    assert adx["options"]["color"] == THEME["text_primary"]
    assert atr["options"]["lineColor"] == THEME["accent_cyan"]
    assert obv["options"]["color"] == "#56B4E9"

    # Helper MAs are neutral text_secondary, not bloomberg amber accent_blue.
    vol_ma = next(s for s in payload["series"] if s["id"].startswith("volume:Vol MA"))
    atr_ma = next(s for s in payload["series"] if s["id"].startswith("atr:ATR% MA"))
    obv_ma = next(s for s in payload["series"] if s["id"].startswith("obv:OBV MA"))
    for series in (vol_ma, atr_ma, obv_ma):
        assert series["options"]["color"] == THEME["text_secondary"]
        assert series["options"].get("lineStyle") == 1
