"""
Tests for the ADX / ATR / OBV chart panes.

The panes used to recompute their indicator locally, which made the ATR pane
plot a series the ATR strategy never compares against and let the OBV pane draw
an MA through the strategy's warmup. These tests pin the fix: when the strategy
columns exist the panes must read them, and the fallback path must still work
on a bare OHLCV frame.
"""

import numpy as np
import pandas as pd
import pytest

from lib.dash.chart_payload import _adx_series, _atr_series, _obv_series
from lib.dash.dash_config import get_theme
from lib.signals.indicators import add_indicators, generate_signals

THEME = get_theme()
CONFIG: dict = {}


def _bare_frame(n: int = 240) -> pd.DataFrame:
    """OHLCV with alternating calm / turbulent regimes.

    The bar range has to *vary* or ATR% sits flat against its own mean and
    neither the expansion nor the compression gate ever opens, leaving the
    threshold-line assertions vacuous.
    """
    idx = pd.date_range('2022-01-03', periods=n, freq='B')
    rng = np.random.default_rng(7)
    # 40-bar blocks alternating between 0.4% and 2.5% daily range.
    sigma = np.where((np.arange(n) // 40) % 2 == 0, 0.004, 0.025)
    close = pd.Series(100 * np.cumprod(1 + rng.normal(0, 1, n) * sigma), index=idx)
    span = close * sigma
    return pd.DataFrame({
        'Open': close * 0.999,
        'High': close + span,
        'Low': close - span,
        'Close': close,
        'Volume': rng.integers(1_000_000, 9_000_000, n),
    }, index=idx)


@pytest.fixture(scope='module')
def enriched() -> pd.DataFrame:
    df, _ = generate_signals(add_indicators(_bare_frame()))
    return df


def _specs(fn, df: pd.DataFrame) -> list[dict]:
    times = [int(ts.timestamp()) for ts in df.index]
    return fn(df, times, CONFIG, THEME)


def _spec(specs: list[dict], title_fragment: str) -> dict:
    for spec in specs:
        if title_fragment in spec['options'].get('title', ''):
            return spec
    raise AssertionError(
        f"no series titled like {title_fragment!r}; "
        f"got {[s['options'].get('title') for s in specs]}"
    )


def _values(spec: dict) -> dict[int, float]:
    """Payload points are NaN-dropped, so key them by time to align series."""
    return {p['time']: p['value'] for p in spec['data']}


def _aligned(df: pd.DataFrame, column: str, spec: dict, scale: float = 1.0):
    """(payload values, expected values) over the times the payload emitted."""
    points = _values(spec)
    expected = {
        int(ts.timestamp()): float(v) * scale
        for ts, v in df[column].items()
        if pd.notna(v)
    }
    assert points, f"{spec['options'].get('title')} emitted no points"
    assert set(points) == set(expected), "payload and column disagree on which bars are valid"
    times = sorted(points)
    return (
        np.array([points[t] for t in times]),
        np.array([expected[t] for t in times]),
    )


class TestAdxPane:
    def test_plots_the_directional_lines(self, enriched):
        """ADX_DICross_* is built from +DI/-DI, so they have to be visible."""
        specs = _specs(_adx_series, enriched)
        assert _spec(specs, '+DI') is not None
        assert _spec(specs, '-DI') is not None

    def test_di_lines_are_the_strategy_columns(self, enriched):
        specs = _specs(_adx_series, enriched)
        got, expected = _aligned(enriched, 'ADX_Pos_DI', _spec(specs, '+DI'))
        np.testing.assert_allclose(got, expected, atol=1e-2)

    def test_draws_both_regime_thresholds(self, enriched):
        """Trend *and* range thresholds — the range gate was previously invisible."""
        specs = _specs(_adx_series, enriched)
        lines = _spec(specs, 'ADX')['priceLines']
        titles = {line['title']: line['price'] for line in lines}
        assert titles == {'TREND': 25, 'RANGE': 20}

    def test_falls_back_on_a_bare_frame(self):
        specs = _specs(_adx_series, _bare_frame())
        assert _spec(specs, 'ADX')['data']
        assert _spec(specs, '+DI')['data']


class TestAtrPane:
    def test_plots_atr_pct_not_raw_atr(self, enriched):
        """The strategy compares ATR%, so the pane must show ATR%."""
        specs = _specs(_atr_series, enriched)
        got, expected = _aligned(enriched, 'ATR_Pct', _spec(specs, 'ATR% ('), scale=100)
        np.testing.assert_allclose(got, expected, atol=1e-3)

    def test_ma_uses_expansion_lookback_not_the_atr_period(self, enriched):
        specs = _specs(_atr_series, enriched)
        got, expected = _aligned(enriched, 'ATR_Pct_MA', _spec(specs, 'ATR% MA'), scale=100)
        np.testing.assert_allclose(got, expected, atol=1e-3)

    def test_expansion_line_marks_where_the_signal_fires(self, enriched):
        """Crossing the plotted expansion line must coincide with the signal."""
        specs = _specs(_atr_series, enriched)
        atr_pct = _values(_spec(specs, 'ATR% ('))
        level = _values(_spec(specs, 'Expansion'))

        fired = enriched.index[
            (enriched['ATR_Expansion_Buy'] | enriched['ATR_Expansion_Sell']).astype(bool)
        ]
        assert len(fired), "fixture produced no expansion signals"
        # Every expansion bar is above the line. (The converse need not hold:
        # the signal also requires a directional close.)
        for ts in fired:
            t = int(ts.timestamp())
            assert atr_pct[t] > level[t]

    def test_compression_line_marks_where_the_gate_opens(self, enriched):
        specs = _specs(_atr_series, enriched)
        atr_pct = _values(_spec(specs, 'ATR% ('))
        level = _values(_spec(specs, 'Compression'))

        compressed = enriched.index[enriched['ATR_Compression_Buy'].astype(bool)]
        assert len(compressed), "fixture produced no compression bars"
        for ts in compressed:
            t = int(ts.timestamp())
            assert atr_pct[t] < level[t]

    def test_falls_back_on_a_bare_frame(self):
        specs = _specs(_atr_series, _bare_frame())
        assert _spec(specs, 'ATR% (')['data']
        assert _spec(specs, 'ATR% MA')['data']


class TestObvPane:
    def test_reads_the_strategy_ma(self, enriched):
        specs = _specs(_obv_series, enriched)
        got, expected = _aligned(enriched, 'OBV_MA', _spec(specs, 'OBV MA'))
        np.testing.assert_allclose(got, expected, rtol=1e-6)

    def test_no_ma_drawn_through_warmup(self):
        """min_periods must match the strategy, or the chart shows a cross it can't see.

        NaN points are dropped from the payload, so the warmup shows up as the
        MA series being 19 points shorter than OBV rather than as leading NaNs.
        """
        df = _bare_frame()
        specs = _specs(_obv_series, df)
        obv = _spec(specs, 'OBV')['data']
        ma = _spec(specs, 'OBV MA')['data']
        assert len(obv) - len(ma) == 19
        assert ma[0]['time'] == int(df.index[19].timestamp())
