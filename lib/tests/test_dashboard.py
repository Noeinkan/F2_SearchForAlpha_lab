"""
Tests for Dashboard Components
Tests state management, chart creation, and component builders.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import date, timedelta

from lib.dash.state import DashboardState
from lib.dash.chart_builder import create_chart, create_empty_chart
from lib.dash.components import (
    build_metric_card, build_status_badge, build_alert, build_progress_bar
)
from lib.dash.helpers import (
    format_df_for_display, extract_signals,
    generate_signal_combinations, evaluate_signal_combination
)
from lib.dash.dash_config import DEFAULT_THEME, get_theme, THEMES


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

class TestChartBuilder:
    """Tests for chart building functions."""

    def test_create_empty_chart(self, dark_theme):
        """Test empty chart creation."""
        fig = create_empty_chart(dark_theme)
        assert fig is not None
        assert len(fig.data) == 0
        assert len(fig.layout.annotations) == 1

    def test_create_empty_chart_custom_message(self, dark_theme):
        """Test empty chart with custom message."""
        fig = create_empty_chart(dark_theme, message="Custom message")
        assert fig.layout.annotations[0]['text'] == "Custom message"

    def test_create_chart_candlestick_only(self, sample_df, dark_theme):
        """Test chart with candlestick only."""
        config = {
            'selected_plots': ['candlestick'],
            'show_candlesticks': True,
            'show_bollinger': False,
            'show_sma': False,
            'show_ema': False,
            'show_buy_sell_signals': False,
            'show_legend': False,
            'selected_signals': [],
            'title': 'Test Chart',
        }
        fig = create_chart(sample_df, config, dark_theme)
        assert fig is not None
        assert len(fig.data) > 0

    def test_create_chart_with_indicators(self, sample_df, dark_theme):
        """Test chart with multiple indicators."""
        config = {
            'selected_plots': ['candlestick', 'volume', 'rsi', 'macd'],
            'show_candlesticks': True,
            'show_bollinger': True,
            'show_sma': True,
            'show_ema': False,
            'show_buy_sell_signals': True,
            'show_legend': True,
            'selected_signals': ['buy', 'sell'],
            'title': 'Full Chart',
        }
        fig = create_chart(sample_df, config, dark_theme)
        assert fig is not None
        # Should have multiple traces
        assert len(fig.data) > 4

    def test_create_chart_empty_plots(self, sample_df, dark_theme):
        """Test chart with no plots selected."""
        config = {
            'selected_plots': [],
            'show_candlesticks': False,
            'show_bollinger': False,
            'show_sma': False,
            'show_ema': False,
            'show_buy_sell_signals': False,
            'show_legend': False,
            'selected_signals': [],
            'title': '',
        }
        fig = create_chart(sample_df, config, dark_theme)
        assert fig is not None
        assert len(fig.data) == 0

    def test_chart_theme_colors(self, sample_df, dark_theme, light_theme):
        """Test that chart uses theme colors."""
        config = {
            'selected_plots': ['candlestick'],
            'show_candlesticks': True,
            'show_bollinger': False,
            'show_sma': False,
            'show_ema': False,
            'show_buy_sell_signals': False,
            'show_legend': False,
            'selected_signals': [],
            'title': '',
        }

        dark_fig = create_chart(sample_df, config, dark_theme)
        light_fig = create_chart(sample_df, config, light_theme)

        # Background colors should differ
        assert dark_fig.layout.plot_bgcolor != light_fig.layout.plot_bgcolor


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

    def test_build_metric_card_negative(self, dark_theme):
        """Test metric card with negative indicator."""
        card = build_metric_card("Drawdown", "-5%", is_positive=False, theme=dark_theme)
        assert card is not None

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
