"""
Tests for Dashboard Components
Tests state management, chart creation, and component builders.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

from lib.dash.state import DashboardState
from lib.dash.chart_payload import build_chart_payload, empty_payload
from lib.dash.components import (
    build_metric_card, build_status_badge, build_alert, build_progress_bar
)
from lib.dash.helpers import (
    format_df_for_display, extract_signals,
    generate_signal_combinations, evaluate_signal_combination
)
from lib.dash.dash_config import (
    DEFAULT_THEME,
    OVERLAY_ONLY_INDICATOR_KEYS,
    PLOT_INDICATOR_OPTIONS,
    PLOT_OPTIONS,
    CHART_ELEMENT_OPTIONS,
    THEME_BUTTON_LABELS,
    THEME_CYCLE,
    get_theme,
    THEMES,
)


# =============================================================================
# FIXTURES
# =============================================================================

@pytest.fixture
def sample_df():
    """Create a sample DataFrame with OHLCV data and indicators."""
    dates = pd.date_range(start='2023-01-01', periods=100, freq='D')
    np.random.seed(42)

    # Generate realistic price data
    close = pd.Series(100 + np.cumsum(np.random.randn(100) * 2))
    high = close + np.abs(np.random.randn(100))
    low = close - np.abs(np.random.randn(100))
    open_price = close + np.random.randn(100) * 0.5

    df = pd.DataFrame({
        'Open': open_price.values,
        'High': high.values,
        'Low': low.values,
        'Close': close.values,
        'Volume': np.random.randint(1000000, 10000000, 100),
        'RSI': np.random.uniform(20, 80, 100),
        'MACD': np.random.randn(100) * 0.5,
        'MACD_Signal': np.random.randn(100) * 0.3,
        'MACD_Histogram': np.random.randn(100) * 0.2,
        'CCI': np.random.uniform(-150, 150, 100),
        'ADX': np.random.uniform(10, 50, 100),
        'ATR': np.random.uniform(1, 5, 100),
        'OBV': np.cumsum(np.random.randint(-100000, 100000, 100)),
        'BB_upper': close.values + 2,
        'BB_lower': close.values - 2,
        'BB_middle': close.values,
        'SMA_short': close.rolling(10).mean().values,
        'SMA_medium': close.rolling(20).mean().values,
        'SMA_long': close.rolling(50).mean().values,
        'Buy_Position': np.random.choice([0, 1], 100, p=[0.95, 0.05]),
        'Sell_Position': np.random.choice([0, 1], 100, p=[0.95, 0.05]),
        'RSI_buy': np.random.choice([0, 1], 100, p=[0.95, 0.05]),
        'RSI_sell': np.random.choice([0, 1], 100, p=[0.95, 0.05]),
        'MACD_buy': np.random.choice([0, 1], 100, p=[0.95, 0.05]),
        'MACD_sell': np.random.choice([0, 1], 100, p=[0.95, 0.05]),
    }, index=dates)

    return df


@pytest.fixture
def dark_theme():
    """Get dark theme configuration."""
    return get_theme('dark')


@pytest.fixture
def light_theme():
    """Get light theme configuration."""
    return get_theme('light')


@pytest.fixture
def cvd_theme():
    """Get CVD (color-vision-deficiency safe) theme."""
    return get_theme('cvd')


# =============================================================================
# STATE TESTS
# =============================================================================

class TestDashboardState:
    """Tests for DashboardState class."""

    def test_initial_state(self):
        """Test initial state values."""
        state = DashboardState()
        assert state.df is None
        assert state.all_tickers_df is None
        assert state.backtest_results is None
        assert state.theme_name == DEFAULT_THEME

    def test_df_property(self, sample_df):
        """Test DataFrame property setter/getter."""
        state = DashboardState()
        state.df = sample_df
        assert state.df is not None
        assert len(state.df) == 100

    def test_theme_switching(self):
        """Test theme switching."""
        state = DashboardState()
        assert state.theme_name == DEFAULT_THEME

        state.set_theme('light')
        assert state.theme_name == 'light'
        assert state.theme['bg_primary'] == '#ffffff'

        state.set_theme(DEFAULT_THEME)
        assert state.theme_name == DEFAULT_THEME
        assert state.theme['bg_primary'] == THEMES[DEFAULT_THEME]['bg_primary']

    def test_caching(self, sample_df):
        """Test data caching functionality."""
        state = DashboardState(max_cache_size=3)

        # Add items to cache
        state.set_cached_data('key1', sample_df)
        state.set_cached_data('key2', sample_df)
        state.set_cached_data('key3', sample_df)

        assert state.get_cached_data('key1') is not None
        assert state.get_cached_data('key2') is not None
        assert state.get_cached_data('key3') is not None

        # Add fourth item - should evict first
        state.set_cached_data('key4', sample_df)
        assert state.get_cached_data('key1') is None  # Evicted
        assert state.get_cached_data('key4') is not None

    def test_cache_lru_behavior(self, sample_df):
        """Test LRU cache behavior."""
        state = DashboardState(max_cache_size=3)

        state.set_cached_data('key1', sample_df)
        state.set_cached_data('key2', sample_df)
        state.set_cached_data('key3', sample_df)

        # Access key1 to make it recently used
        _ = state.get_cached_data('key1')

        # Add new item - should evict key2 (oldest not accessed)
        state.set_cached_data('key4', sample_df)
        assert state.get_cached_data('key1') is not None  # Still present
        assert state.get_cached_data('key2') is None  # Evicted

    def test_clear_cache(self, sample_df):
        """Test cache clearing."""
        state = DashboardState()
        state.set_cached_data('key1', sample_df)
        state.set_cached_data('key2', sample_df)

        state.clear_cache()
        assert state.get_cached_data('key1') is None
        assert state.get_cached_data('key2') is None

    def test_cache_info(self, sample_df):
        """Test cache info retrieval."""
        state = DashboardState(max_cache_size=10)
        state.set_cached_data('key1', sample_df)
        state.set_cached_data('key2', sample_df)

        info = state.get_cache_info()
        assert info['size'] == 2
        assert info['max_size'] == 10
        assert 'key1' in info['keys']
        assert 'key2' in info['keys']

    def test_reset(self, sample_df):
        """Test state reset."""
        state = DashboardState()
        state.df = sample_df
        state.set_cached_data('key1', sample_df)
        state.set_theme('light')

        state.reset()
        assert state.df is None
        assert state.get_cached_data('key1') is None
        assert state.theme_name == DEFAULT_THEME


# =============================================================================
# CHART BUILDER TESTS
# =============================================================================

class TestChartPayload:
    """Tests for the Lightweight Charts payload builder."""

    def _config(self, plots, **overrides):
        config = {
            'selected_plots': plots,
            'show_candlesticks': True,
            'show_bollinger': False,
            'show_sma': False,
            'show_ema': False,
            'show_buy_sell_signals': False,
            'show_legend': False,
            'selected_signals': [],
            'buy_signal_columns': [],
            'sell_signal_columns': [],
            'title': '',
            'indicator_settings': {},
        }
        config.update(overrides)
        return config

    def test_empty_payload(self, dark_theme):
        payload = empty_payload(dark_theme)
        assert payload['candles'] == []
        assert payload['series'] == []
        assert [p['key'] for p in payload['panes']] == ['price']

    def test_empty_payload_custom_message(self, dark_theme):
        payload = empty_payload(dark_theme, message="Custom message")
        assert payload['meta']['message'] == "Custom message"

    def test_candlestick_only(self, sample_df, dark_theme):
        payload = build_chart_payload(sample_df, self._config(['candlestick']), dark_theme)
        assert len(payload['candles']) == len(sample_df)
        assert set(payload['candles'][0]) == {'time', 'open', 'high', 'low', 'close'}
        assert [p['key'] for p in payload['panes']] == ['price']

    def test_indicator_panes_follow_selected_plots(self, sample_df, dark_theme):
        config = self._config(['candlestick', 'volume', 'rsi', 'macd'],
                              show_bollinger=True, show_sma=True)
        payload = build_chart_payload(sample_df, config, dark_theme)
        assert [p['key'] for p in payload['panes']] == ['price', 'volume', 'rsi', 'macd']
        # Every series must name a pane that exists, or the glue drops it.
        pane_keys = {p['key'] for p in payload['panes']}
        assert all(s['pane'] in pane_keys for s in payload['series'])

    def test_price_pane_is_taller_than_indicator_panes(self, sample_df, dark_theme):
        payload = build_chart_payload(
            sample_df, self._config(['candlestick', 'rsi']), dark_theme
        )
        heights = {p['key']: p['height'] for p in payload['panes']}
        assert heights['price'] > heights['rsi']

    def test_no_plots_still_yields_a_price_pane(self, sample_df, dark_theme):
        """The glue anchors the crosshair legend and markers on the price series."""
        payload = build_chart_payload(sample_df, self._config([]), dark_theme)
        assert [p['key'] for p in payload['panes']] == ['price']
        assert payload['series'] == []
        assert len(payload['candles']) == len(sample_df)

    def test_theme_colors_reach_the_payload(self, sample_df, dark_theme, light_theme):
        config = self._config(['candlestick'])
        dark = build_chart_payload(sample_df, config, dark_theme)
        light = build_chart_payload(sample_df, config, light_theme)
        assert dark['theme']['bg'] != light['theme']['bg']
        assert dark['theme']['up'] == dark_theme['chart_candle_up']

    def test_payload_is_json_serialisable(self, sample_df, dark_theme):
        """numpy scalars and NaN both break json.dumps; the builder must not emit them."""
        import json

        config = self._config(['candlestick', 'volume', 'rsi', 'cci', 'macd'],
                              show_bollinger=True)
        payload = build_chart_payload(sample_df, config, dark_theme)
        json.dumps(payload)   # raises on numpy types / NaN

# =============================================================================
# COMPONENT TESTS
# =============================================================================

class TestComponents:
    """Tests for UI component builders."""

    def test_build_metric_card(self, dark_theme):
        """Test metric card creation."""
        card = build_metric_card("Test Label", "$1,234", theme=dark_theme)
        assert card is not None
        assert len(card.children) == 2  # Label and value

    def test_build_metric_card_positive(self, dark_theme):
        """Test metric card with positive indicator."""
        card = build_metric_card("Return", "+15%", is_positive=True, theme=dark_theme)
        assert card is not None
        # Phase 4: arrow glyph injected so the direction is not color-only.
        value_node = card.children[1]
        assert '\u25b2' in str(value_node.children)  # ▲

    def test_build_metric_card_negative(self, dark_theme):
        """Test metric card with negative indicator."""
        card = build_metric_card("Drawdown", "-5%", is_positive=False, theme=dark_theme)
        assert card is not None
        # Phase 4: arrow glyph injected so the direction is not color-only.
        value_node = card.children[1]
        assert '\u25bc' in str(value_node.children)  # ▼

    def test_build_metric_card_neutral_no_arrow(self, dark_theme):
        """Neutral cards (is_positive=None) must not get an arrow — would be noise."""
        card = build_metric_card("Volume", "1,234", theme=dark_theme)
        value_node = card.children[1]
        assert '\u25b2' not in str(value_node.children)
        assert '\u25bc' not in str(value_node.children)

    def test_build_status_badge(self, dark_theme):
        """Test status badge creation."""
        success_badge = build_status_badge("Success", "success", dark_theme)
        warning_badge = build_status_badge("Warning", "warning", dark_theme)
        error_badge = build_status_badge("Error", "error", dark_theme)

        assert success_badge is not None
        assert warning_badge is not None
        assert error_badge is not None

    def test_build_alert(self, dark_theme):
        """Test alert creation."""
        alert = build_alert("Test message", "success", theme=dark_theme)
        assert alert is not None

    def test_build_alert_types(self, dark_theme):
        """Test different alert types."""
        for alert_type in ['success', 'warning', 'error', 'info']:
            alert = build_alert(f"{alert_type} message", alert_type, theme=dark_theme)
            assert alert is not None

    def test_build_progress_bar(self, dark_theme):
        """Test progress bar creation."""
        progress = build_progress_bar(50, "Loading...", theme=dark_theme)
        assert progress is not None

    def test_build_progress_bar_indeterminate(self, dark_theme):
        """Test indeterminate progress bar."""
        progress = build_progress_bar(0, "Processing...", indeterminate=True, theme=dark_theme)
        assert progress is not None


# =============================================================================
# PHASE 4 — THEME CYCLE / CVD / ACCESSIBILITY TESTS
# =============================================================================

class TestCvdTheme:
    """Phase 4 — color-vision-deficiency safe theme.

    The CVD theme mirrors the bloomberg theme except the up/down pair
    is blue/orange (instead of green/red). Tests guard the structural
    invariant: only ``accent_green`` and ``accent_red`` (plus the
    chart candle colours) should differ between bloomberg and cvd;
    everything else (text, borders, accent_blue) must be identical.
    """

    def test_cvd_theme_registered(self):
        assert 'cvd' in THEMES

    def test_cvd_up_is_blue_not_green(self):
        cvd = get_theme('cvd')
        bloomberg = get_theme('bloomberg')
        # CVD up = #0091EA (blue); bloomberg up = #26C281 (green).
        assert cvd['accent_green'] == '#0091EA'
        assert bloomberg['accent_green'] != cvd['accent_green']

    def test_cvd_down_is_orange_not_red(self):
        cvd = get_theme('cvd')
        bloomberg = get_theme('bloomberg')
        # CVD down = #FF6F00 (orange); bloomberg down = #EF5350 (red).
        assert cvd['accent_red'] == '#FF6F00'
        assert bloomberg['accent_red'] != cvd['accent_red']

    def test_cvd_candle_palette_matches(self, cvd_theme):
        """Candle up/down must mirror the accent_green/accent_red swap."""
        assert cvd_theme['chart_candle_up'] == cvd_theme['accent_green']
        assert cvd_theme['chart_candle_down'] == cvd_theme['accent_red']

    def test_cvd_preserves_bloomberg_chrome(self, cvd_theme, dark_theme):
        """The amber primary, text, and border palette must NOT change."""
        bloomberg = get_theme('bloomberg')
        for key in ('bg_primary', 'bg_secondary', 'bg_tertiary', 'bg_panel',
                    'bg_panel_header', 'text_primary', 'text_secondary',
                    'text_tertiary', 'accent_blue', 'accent_orange',
                    'accent_purple', 'accent_cyan', 'border_primary',
                    'border_secondary', 'border_focus', 'chart_bg'):
            assert cvd_theme[key] == bloomberg[key], f"{key} must match bloomberg"


class TestThemeCycle:
    """Phase 4 — the theme toggle now cycles DARK → CVD → LIGHT → DARK."""

    def test_cycle_includes_cvd(self):
        assert 'cvd' in THEME_CYCLE

    def test_cycle_starts_at_default(self):
        assert THEME_CYCLE[0] == DEFAULT_THEME

    def test_cycle_includes_light(self):
        assert 'light' in THEME_CYCLE

    def test_button_label_for_every_cycle_member(self):
        for theme_name in THEME_CYCLE:
            assert theme_name in THEME_BUTTON_LABELS
            label = THEME_BUTTON_LABELS[theme_name]
            # Phase 4 contract: each label is bracketed uppercase so it
            # visually matches the existing button chrome.
            assert label.startswith('[') and label.endswith(']')
            assert label == label.upper()

    def test_cycle_advances_through_cvd(self):
        """Walking the cycle from default must hit CVD and then LIGHT."""
        idx = THEME_CYCLE.index(DEFAULT_THEME)
        next_theme = THEME_CYCLE[(idx + 1) % len(THEME_CYCLE)]
        assert next_theme == 'cvd'
        next_next = THEME_CYCLE[(idx + 2) % len(THEME_CYCLE)]
        assert next_next == 'light'
        # And wrapping back to default.
        wrapped = THEME_CYCLE[(idx + 3) % len(THEME_CYCLE)]
        assert wrapped == DEFAULT_THEME


class TestAccessibility:
    """Phase 4 — redundant signs/arrows on P&L, focusable splitter."""

    def test_metric_card_injects_sign_aware_value(self, dark_theme):
        """Positive + signed value drops the redundant sign before adding arrow."""
        card = build_metric_card("Return", "+15%", is_positive=True, theme=dark_theme)
        rendered = str(card.children[1].children)
        # We stripped the '+' then prepended the arrow, so the visible
        # text is "▲ 15%" — never "▲ +15%".
        assert '▲ 15%' in rendered

    def test_metric_card_injects_down_arrow_signed(self, dark_theme):
        card = build_metric_card("Drawdown", "-5%", is_positive=False, theme=dark_theme)
        rendered = str(card.children[1].children)
        assert '▼ 5%' in rendered

    def test_metric_card_handles_unsigned_value(self, dark_theme):
        """If the caller passes '15%' (no sign), the arrow is still added."""
        card = build_metric_card("Return", "15%", is_positive=True, theme=dark_theme)
        rendered = str(card.children[1].children)
        assert '▲ 15%' in rendered

    def test_kpi_cell_optional_positive_flag(self, dark_theme):
        """kpi_cell accepts is_positive without breaking existing callers."""
        from lib.dash.components import kpi_cell
        cell_pos = kpi_cell("Return", "+12.50%", is_positive=True, theme=dark_theme)
        cell_neg = kpi_cell("DD", "-5.00%", is_positive=False, theme=dark_theme)
        cell_neu = kpi_cell("Trades", "1,234", theme=dark_theme)
        assert cell_pos is not None
        assert cell_neg is not None
        assert cell_neu is not None
        # The value div is the second child.
        assert '\u25b2' in str(cell_pos.children[1].children)
        assert '\u25bc' in str(cell_neg.children[1].children)
        # Neutral: no arrow.
        assert '\u25b2' not in str(cell_neu.children[1].children)
        assert '\u25bc' not in str(cell_neu.children[1].children)


# =============================================================================
# HELPER FUNCTION TESTS
# =============================================================================

class TestHelpers:
    """Tests for helper functions."""

    def test_format_df_for_display(self, sample_df):
        """Test DataFrame formatting."""
        formatted = format_df_for_display(sample_df)
        # Check that floats are rounded
        assert formatted['Close'].iloc[0] == round(sample_df['Close'].iloc[0], 2)

    def test_extract_signals(self, sample_df):
        """Test signal extraction."""
        buy_signals, sell_signals = extract_signals(sample_df)
        assert len(buy_signals) > 0
        assert len(sell_signals) > 0
        assert all('buy' in s.lower() for s in buy_signals)
        assert all('sell' in s.lower() for s in sell_signals)

    def test_generate_signal_combinations(self):
        """Test signal combination generation."""
        buy_signals = ['buy1', 'buy2', 'buy3']
        sell_signals = ['sell1', 'sell2']

        combos = generate_signal_combinations(buy_signals, sell_signals, max_signals=2)
        assert len(combos) > 0
        # Each combo should be a tuple of (buy_tuple, sell_tuple)
        for buy_combo, sell_combo in combos:
            assert len(buy_combo) <= 2
            assert len(sell_combo) <= 2


# =============================================================================
# THEME TESTS
# =============================================================================

class TestThemes:
    """Tests for theme configuration."""

    def test_dark_theme_exists(self):
        """Test dark theme is available."""
        theme = get_theme('dark')
        assert theme is not None
        assert 'bg_primary' in theme
        assert 'text_primary' in theme

    def test_light_theme_exists(self):
        """Test light theme is available."""
        theme = get_theme('light')
        assert theme is not None
        assert 'bg_primary' in theme

    def test_invalid_theme_fallback(self):
        """Test fallback to dark theme for invalid theme name."""
        theme = get_theme('invalid_theme')
        assert theme == THEMES['dark']

    def test_theme_required_keys(self):
        """Test that themes have all required keys."""
        required_keys = [
            'bg_primary', 'bg_secondary', 'bg_tertiary',
            'text_primary', 'text_secondary',
            'accent_blue', 'accent_green', 'accent_red',
            'border_primary', 'chart_bg', 'chart_candle_up', 'chart_candle_down'
        ]

        for theme_name in ['dark', 'light']:
            theme = get_theme(theme_name)
            for key in required_keys:
                assert key in theme, f"Theme '{theme_name}' missing key '{key}'"


class TestPlotIndicatorOptions:
    """Plot-toggle list must exclude overlay-only indicators."""

    def test_overlay_only_keys_are_isolated(self):
        """OVERLAY_ONLY_INDICATOR_KEYS is the single source of truth."""
        assert OVERLAY_ONLY_INDICATOR_KEYS == frozenset({'bollinger', 'sma', 'ema'})

    def test_plot_indicator_options_excludes_overlay_only(self):
        """Indicators panel must not contain overlay-only keys."""
        keys = {value for _, value in PLOT_INDICATOR_OPTIONS}
        assert keys.isdisjoint(OVERLAY_ONLY_INDICATOR_KEYS), (
            f"Plot indicators should not include overlay-only keys: "
            f"{keys & OVERLAY_ONLY_INDICATOR_KEYS}"
        )

    def test_overlay_only_keys_appear_in_chart_elements(self):
        """Overlay toggles must remain reachable via the overlays panel."""
        overlay_values = {value for _, value in CHART_ELEMENT_OPTIONS}
        assert OVERLAY_ONLY_INDICATOR_KEYS.issubset(overlay_values), (
            f"Overlay-only keys must be present in CHART_ELEMENT_OPTIONS: "
            f"{OVERLAY_ONLY_INDICATOR_KEYS - overlay_values}"
        )

    def test_plot_options_superset_of_plot_indicator_options(self):
        """PLOT_OPTIONS (legacy/back-compat) still contains everything."""
        legacy_keys = {value for _, value in PLOT_OPTIONS}
        plot_keys = {value for _, value in PLOT_INDICATOR_OPTIONS}
        assert plot_keys.issubset(legacy_keys)
        assert legacy_keys - plot_keys == OVERLAY_ONLY_INDICATOR_KEYS

    def test_chart_help_covers_plot_and_overlay_toggles(self):
        """Every Chart Settings toggle has hover explanation copy."""
        from lib.dash.dash_config import CHART_PLOT_HELP, CHART_OVERLAY_HELP

        plot_keys = {value for _, value in PLOT_INDICATOR_OPTIONS}
        overlay_keys = {value for _, value in CHART_ELEMENT_OPTIONS}
        assert plot_keys.issubset(CHART_PLOT_HELP)
        assert overlay_keys.issubset(CHART_OVERLAY_HELP)
        assert all(text.strip() for text in CHART_PLOT_HELP.values())
        assert all(text.strip() for text in CHART_OVERLAY_HELP.values())