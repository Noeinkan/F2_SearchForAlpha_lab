# config.py
"""
Professional Trading Dashboard Configuration
Bloomberg Terminal-inspired design system
"""

# =============================================================================
# THEME SYSTEM - Professional Dark Theme (Bloomberg-style)
# =============================================================================

THEMES = {
    'dark': {
        # Core colors
        'bg_primary': '#0d1117',       # Deep dark background
        'bg_secondary': '#161b22',     # Slightly lighter panels
        'bg_tertiary': '#21262d',      # Cards and elevated surfaces
        'bg_hover': '#30363d',         # Hover states

        # Text colors
        'text_primary': '#e6edf3',     # Primary text
        'text_secondary': '#8b949e',   # Secondary/muted text
        'text_tertiary': '#6e7681',    # Disabled/placeholder text

        # Accent colors
        'accent_blue': '#58a6ff',      # Primary actions
        'accent_green': '#3fb950',     # Positive/success/buy
        'accent_red': '#f85149',       # Negative/error/sell
        'accent_orange': '#d29922',    # Warnings
        'accent_purple': '#a371f7',    # Special highlights
        'accent_cyan': '#39c5cf',      # Info/secondary actions

        # Border colors
        'border_primary': '#30363d',   # Standard borders
        'border_secondary': '#21262d', # Subtle borders
        'border_focus': '#58a6ff',     # Focus states

        # Chart specific
        'chart_bg': '#0d1117',
        'chart_grid': 'rgba(48, 54, 61, 0.6)',
        'chart_candle_up': '#3fb950',
        'chart_candle_down': '#f85149',

        # Data table
        'table_header_bg': '#161b22',
        'table_row_alt': 'rgba(22, 27, 34, 0.5)',
        'table_row_hover': '#21262d',
    },
    'light': {
        # Core colors
        'bg_primary': '#ffffff',
        'bg_secondary': '#f6f8fa',
        'bg_tertiary': '#eaeef2',
        'bg_hover': '#d0d7de',

        # Text colors
        'text_primary': '#1f2328',
        'text_secondary': '#656d76',
        'text_tertiary': '#8c959f',

        # Accent colors
        'accent_blue': '#0969da',
        'accent_green': '#1a7f37',
        'accent_red': '#cf222e',
        'accent_orange': '#9a6700',
        'accent_purple': '#8250df',
        'accent_cyan': '#0598bc',

        # Border colors
        'border_primary': '#d0d7de',
        'border_secondary': '#eaeef2',
        'border_focus': '#0969da',

        # Chart specific
        'chart_bg': '#ffffff',
        'chart_grid': 'rgba(208, 215, 222, 0.6)',
        'chart_candle_up': '#1a7f37',
        'chart_candle_down': '#cf222e',

        # Data table
        'table_header_bg': '#f6f8fa',
        'table_row_alt': 'rgba(246, 248, 250, 0.5)',
        'table_row_hover': '#eaeef2',
    }
}

# Default theme
DEFAULT_THEME = 'dark'

# Active theme colors (for backwards compatibility)
def get_theme(theme_name: str = DEFAULT_THEME) -> dict:
    return THEMES.get(theme_name, THEMES['dark'])

# Legacy color mappings (backwards compatibility)
_theme = get_theme()
BACKGROUND_COLOR = _theme['bg_primary']
TEXT_COLOR = _theme['text_primary']
BORDER_COLOR = _theme['border_primary']
CHART_BACKGROUND_COLOR = _theme['bg_secondary']

# =============================================================================
# TYPOGRAPHY
# =============================================================================

FONT_FAMILY = '-apple-system, BlinkMacSystemFont, "Segoe UI", "Noto Sans", Helvetica, Arial, sans-serif'
FONT_MONO = 'ui-monospace, SFMono-Regular, "SF Mono", Menlo, Consolas, monospace'

FONT_SIZES = {
    'xs': '11px',
    'sm': '12px',
    'base': '14px',
    'lg': '16px',
    'xl': '20px',
    '2xl': '24px',
    '3xl': '32px',
}

# =============================================================================
# SPACING & LAYOUT
# =============================================================================

SPACING = {
    '0': '0',
    '1': '4px',
    '2': '8px',
    '3': '12px',
    '4': '16px',
    '5': '20px',
    '6': '24px',
    '8': '32px',
    '10': '40px',
    '12': '48px',
}

BORDER_RADIUS = {
    'sm': '4px',
    'md': '6px',
    'lg': '8px',
    'xl': '12px',
    'full': '9999px',
}

# Panel widths (desktop-first)
MAIN_CONTENT_WIDTH = '75%'
SIDEBAR_WIDTH = '25%'
MIN_PANEL_WIDTH = '300px'

# Chart
CHART_HEIGHT = '65vh'
CHART_HEIGHT_COMPACT = '45vh'
INDICATOR_HEIGHT = '120px'

# =============================================================================
# BACKTEST DEFAULTS
# =============================================================================

DEFAULT_TICKER = 'SPY'
INITIAL_CAPITAL = 10000
START_DATE = '2018-01-01'
DEFAULT_SIGNAL_WINDOW = 4

# =============================================================================
# SERVER CONFIG
# =============================================================================

START_PORT = 8050
MAX_PORT_TRIES = 100

# =============================================================================
# OPTIMIZATION
# =============================================================================

OPTIMIZATION_PERCENT = 0.1
OPTIMIZATION_DELAY = 1

# =============================================================================
# CHART CONSTANTS
# =============================================================================

# Row heights for subplots
CHART_ROW_HEIGHT_MAIN = 4.5      # Height multiplier for main candlestick chart
CHART_ROW_HEIGHT_INDICATOR = 1   # Height multiplier for indicator panels

# Signal marker positioning
SIGNAL_OFFSET_FACTOR = 0.015     # Offset for buy/sell signal markers (% of price)

# Cache settings
MAX_DATA_CACHE_SIZE = 50         # Maximum number of cached DataFrames

# =============================================================================
# CHECKLIST OPTIONS
# =============================================================================
PLOT_OPTIONS = [
    ('Candlestick', 'candlestick'),
    ('Volume', 'volume'),
    ('RSI', 'rsi'),
    ('CCI', 'cci'),
    ('MACD', 'macd'),
    ('ADX', 'adx'),
    ('ATR', 'atr'),
    ('OBV', 'obv')
]

CHART_ELEMENT_OPTIONS = [
    ('Candlesticks', 'candlesticks'),
    ('Bollinger Bands', 'bollinger'),
    ('SMA', 'sma'),
    ('EMA', 'ema'),
    ('Buy/Sell Signals', 'signals'),
    ('Legend', 'legend')
]

SIGNAL_OPTIONS = [
    ('Buy', 'buy'),
    ('Sell', 'sell')
]

# =============================================================================
# INDICATOR SETTINGS
# =============================================================================

DEFAULT_INDICATOR_SETTINGS = {
    'volume': {
        'ma_period': 20
    },
    'rsi': {
        'period': 14,
        'overbought': 70,
        'oversold': 30
    },
    'bollinger': {
        'window': 20,
        'window_dev': 2,
        'squeeze_threshold': 0.1,
        'double_bottom_threshold': 0.02
    },
    'sma': {
        'short_window': 5,
        'medium_window': 20,
        'long_window': 50,
        'trend_window': 200
    },
    'ema': {
        'short_window': 12,
        'medium_window': 26,
        'long_window': 50,
        'atr_window': 14
    },
    'cci': {
        'period': 20,
        'ceiling': 100,
        'floor': -100
    },
    'macd': {
        'fast': 12,
        'slow': 26,
        'signal': 9
    },
    'adx': {
        'period': 14,
        'threshold': 25
    },
    'atr': {
        'period': 14
    },
    'obv': {
        'ma_period': 20
    }
}

INDICATOR_SETTING_SCHEMA = {
    'volume': {
        'label': 'Volume',
        'fields': [
            {'key': 'ma_period', 'label': 'Volume MA Period', 'step': 1, 'min': 1}
        ]
    },
    'rsi': {
        'label': 'RSI',
        'fields': [
            {'key': 'period', 'label': 'Period', 'step': 1, 'min': 1},
            {'key': 'overbought', 'label': 'Overbought', 'step': 0.1},
            {'key': 'oversold', 'label': 'Oversold', 'step': 0.1}
        ]
    },
    'bollinger': {
        'label': 'Bollinger Bands',
        'fields': [
            {'key': 'window', 'label': 'Window', 'step': 1, 'min': 1},
            {'key': 'window_dev', 'label': 'Std Dev', 'step': 0.1, 'min': 0.1},
            {'key': 'squeeze_threshold', 'label': 'Squeeze Threshold', 'step': 0.01, 'min': 0},
            {'key': 'double_bottom_threshold', 'label': 'Double Top/Bottom Threshold', 'step': 0.001, 'min': 0}
        ]
    },
    'sma': {
        'label': 'SMA',
        'fields': [
            {'key': 'short_window', 'label': 'Short Window', 'step': 1, 'min': 1},
            {'key': 'medium_window', 'label': 'Medium Window', 'step': 1, 'min': 1},
            {'key': 'long_window', 'label': 'Long Window', 'step': 1, 'min': 1},
            {'key': 'trend_window', 'label': 'Trend Window', 'step': 1, 'min': 1}
        ]
    },
    'ema': {
        'label': 'EMA',
        'fields': [
            {'key': 'short_window', 'label': 'Short Window', 'step': 1, 'min': 1},
            {'key': 'medium_window', 'label': 'Medium Window', 'step': 1, 'min': 1},
            {'key': 'long_window', 'label': 'Long Window', 'step': 1, 'min': 1},
            {'key': 'atr_window', 'label': 'ATR Window', 'step': 1, 'min': 1}
        ]
    },
    'cci': {
        'label': 'CCI',
        'fields': [
            {'key': 'period', 'label': 'Period', 'step': 1, 'min': 1},
            {'key': 'ceiling', 'label': 'Ceiling', 'step': 0.1},
            {'key': 'floor', 'label': 'Floor', 'step': 0.1}
        ]
    },
    'macd': {
        'label': 'MACD',
        'fields': [
            {'key': 'fast', 'label': 'Fast EMA', 'step': 1, 'min': 1},
            {'key': 'slow', 'label': 'Slow EMA', 'step': 1, 'min': 1},
            {'key': 'signal', 'label': 'Signal EMA', 'step': 1, 'min': 1}
        ]
    },
    'adx': {
        'label': 'ADX',
        'fields': [
            {'key': 'period', 'label': 'Period', 'step': 1, 'min': 1},
            {'key': 'threshold', 'label': 'Trend Threshold', 'step': 0.1}
        ]
    },
    'atr': {
        'label': 'ATR',
        'fields': [
            {'key': 'period', 'label': 'Period', 'step': 1, 'min': 1}
        ]
    },
    'obv': {
        'label': 'OBV',
        'fields': [
            {'key': 'ma_period', 'label': 'OBV MA Period', 'step': 1, 'min': 1}
        ]
    }
}

# Optimization methods
OPTIMIZATION_METHODS = [
    {'label': 'Walk-Forward Optimization', 'value': 'walk_forward'}
]