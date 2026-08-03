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

from lib.dash.chart_payload import build_chart_payload, empty_payload, encode_times
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
