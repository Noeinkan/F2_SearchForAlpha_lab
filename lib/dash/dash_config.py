# config.py
"""
Professional Trading Dashboard Configuration
Bloomberg Terminal-inspired design system
"""

# =============================================================================
# THEME SYSTEM - Professional Dark Theme (Bloomberg-style)
# =============================================================================

import copy
import os

from lib.config_loader import get_strategy_config

THEMES = {
    'bloomberg': {
        # Core colors — modernized amber on near-black
        'bg_primary': '#0A0A0A',       # Near-black canvas
        'bg_secondary': '#111111',     # Header / toolbars
        'bg_tertiary': '#161616',      # Cards / inputs
        'bg_hover': '#1F1F1F',         # Hover states
        'bg_panel': '#0E0E0E',         # Sidebar / right panel
        'bg_panel_header': '#1A1A1A',  # Section headers

        # Text colors
        'text_primary': '#E8E8E8',
        'text_secondary': '#A8A8A8',
        'text_tertiary': '#6E6E6E',

        # Accent colors — amber primary, P&L greens/reds
        'accent_blue': '#FFA726',      # Repurposed: amber primary action
        'accent_green': '#26C281',     # Buy / up
        'accent_red': '#EF5350',       # Sell / down
        'accent_orange': '#FFCA28',    # Warning
        'accent_purple': '#BA68C8',
        'accent_cyan': '#4FC3F7',

        # Border colors
        'border_primary': '#1F1F1F',
        'border_secondary': '#171717',
        'border_focus': '#FFA726',

        # Chart specific
        'chart_bg': '#0A0A0A',
        'chart_grid': 'rgba(60, 60, 60, 0.35)',
        'chart_candle_up': '#26C281',
        'chart_candle_down': '#EF5350',

        # Data table
        'table_header_bg': '#141414',
        'table_row_alt': 'rgba(20, 20, 20, 0.5)',
        'table_row_hover': '#1A1A1A',
    },
    'dark': {
        # Core colors
        'bg_primary': '#0d1117',       # Deep dark background
        'bg_secondary': '#161b22',     # Slightly lighter panels
        'bg_tertiary': '#21262d',      # Cards and elevated surfaces
        'bg_hover': '#30363d',         # Hover states
        'bg_panel': '#1b222c',         # Left/right panel surfaces
        'bg_panel_header': '#202836',  # Panel headers

        # Text colors
        'text_primary': '#e6edf3',     # Primary text
        'text_secondary': '#c9d1d9',   # Secondary/muted text
        'text_tertiary': '#adbac7',    # Disabled/placeholder text

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
        'bg_panel': '#f1f4f7',
        'bg_panel_header': '#e6ebf0',

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
DEFAULT_THEME = 'bloomberg'

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

FONT_FAMILY = '"Source Sans 3", "Segoe UI Variable", "Segoe UI", system-ui, -apple-system, BlinkMacSystemFont, sans-serif'
FONT_MONO = '"IBM Plex Mono", "Cascadia Mono", Consolas, ui-monospace, monospace'

FONT_SIZES = {
    'xs':   '12px',
    'sm':   '13px',
    'base': '14px',
    'lg':   '16px',
    'xl':   '19px',
    '2xl':  '23px',
    '3xl':  '29px',
}

FONT_WEIGHT_NUMERIC = '500'

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
    'sm': '2px',
    'md': '3px',
    'lg': '4px',
    'xl': '6px',
    'full': '9999px',
}

# Panel widths (desktop-first)
MAIN_CONTENT_WIDTH = '75%'
SIDEBAR_WIDTH = '260px'
RIGHT_PANEL_WIDTH = '320px'
HEADER_HEIGHT = '44px'
STATUS_BAR_HEIGHT = '24px'
MIN_PANEL_WIDTH = '260px'

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
# PRESET STORAGE
# =============================================================================

PRESET_FILE_PATH = os.path.join('config', 'ui_presets.json')

# =============================================================================
# SERVER CONFIG
# =============================================================================

START_PORT = 8050
MAX_PORT_TRIES = 100

# Dashboard URL routes (browser refresh uses pathname as source of truth)
ROUTE_TERMINAL = '/'
ROUTE_FUNDAMENTALS = '/fundamentals'
ROUTE_FLOW = '/flow'

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
CHART_ELEMENT_DEFINITIONS = [
    {'label': 'Candlesticks', 'value': 'candlesticks'},
    {'label': 'Bollinger Bands', 'value': 'bollinger'},
    {'label': 'SMA', 'value': 'sma'},
    {'label': 'EMA', 'value': 'ema'},
    {'label': 'Buy/Sell Signals', 'value': 'signals'},
    {'label': 'Legend', 'value': 'legend'},
]

INDICATOR_DEFINITIONS = [
    {
        'key': 'volume',
        'label': 'Volume',
        'defaults': {'ma_period': 20},
        'fields': [
            {'key': 'ma_period', 'label': 'Volume MA Period', 'step': 1, 'min': 1}
        ],
    },
    {
        'key': 'rsi',
        'label': 'RSI',
        'defaults': {'period': 14, 'overbought': 70, 'oversold': 30},
        'fields': [
            {'key': 'period', 'label': 'Period', 'step': 1, 'min': 1},
            {'key': 'overbought', 'label': 'Overbought', 'step': 0.1},
            {'key': 'oversold', 'label': 'Oversold', 'step': 0.1},
        ],
    },
    {
        'key': 'bollinger',
        'label': 'Bollinger Bands',
        'defaults': {
            'window': 20,
            'window_dev': 2,
            'squeeze_threshold': 0.1,
            'double_bottom_threshold': 0.02,
        },
        'fields': [
            {'key': 'window', 'label': 'Window', 'step': 1, 'min': 1},
            {'key': 'window_dev', 'label': 'Std Dev', 'step': 0.1, 'min': 0.1},
            {'key': 'squeeze_threshold', 'label': 'Squeeze Threshold', 'step': 0.01, 'min': 0},
            {'key': 'double_bottom_threshold', 'label': 'Double Top/Bottom Threshold', 'step': 0.001, 'min': 0},
        ],
    },
    {
        'key': 'sma',
        'label': 'SMA',
        'defaults': {'short_window': 5, 'medium_window': 20, 'long_window': 50, 'trend_window': 200},
        'fields': [
            {'key': 'short_window', 'label': 'Short Window', 'step': 1, 'min': 1},
            {'key': 'medium_window', 'label': 'Medium Window', 'step': 1, 'min': 1},
            {'key': 'long_window', 'label': 'Long Window', 'step': 1, 'min': 1},
            {'key': 'trend_window', 'label': 'Trend Window', 'step': 1, 'min': 1},
        ],
    },
    {
        'key': 'ema',
        'label': 'EMA',
        'defaults': {'short_window': 12, 'medium_window': 26, 'long_window': 50, 'atr_window': 14},
        'fields': [
            {'key': 'short_window', 'label': 'Short Window', 'step': 1, 'min': 1},
            {'key': 'medium_window', 'label': 'Medium Window', 'step': 1, 'min': 1},
            {'key': 'long_window', 'label': 'Long Window', 'step': 1, 'min': 1},
            {'key': 'atr_window', 'label': 'ATR Window', 'step': 1, 'min': 1},
        ],
    },
    {
        'key': 'cci',
        'label': 'CCI',
        'defaults': {'period': 20, 'ceiling': 150, 'floor': -150},
        'fields': [
            {'key': 'period', 'label': 'Period', 'step': 1, 'min': 1},
            {'key': 'ceiling', 'label': 'Ceiling', 'step': 0.1},
            {'key': 'floor', 'label': 'Floor', 'step': 0.1},
        ],
    },
    {
        'key': 'macd',
        'label': 'MACD',
        'defaults': {'fast': 12, 'slow': 26, 'signal': 9},
        'fields': [
            {'key': 'fast', 'label': 'Fast EMA', 'step': 1, 'min': 1},
            {'key': 'slow', 'label': 'Slow EMA', 'step': 1, 'min': 1},
            {'key': 'signal', 'label': 'Signal EMA', 'step': 1, 'min': 1},
        ],
    },
    {
        'key': 'vwap',
        'label': 'VWAP',
        'defaults': {'window': 20},
        'fields': [
            {'key': 'window', 'label': 'Window', 'step': 1, 'min': 1}
        ],
    },
    {
        'key': 'adx',
        'label': 'ADX',
        'defaults': {'period': 14, 'threshold': 25},
        'fields': [
            {'key': 'period', 'label': 'Period', 'step': 1, 'min': 1},
            {'key': 'threshold', 'label': 'Trend Threshold', 'step': 0.1},
        ],
    },
    {
        'key': 'atr',
        'label': 'ATR',
        'defaults': {'period': 14},
        'fields': [
            {'key': 'period', 'label': 'Period', 'step': 1, 'min': 1}
        ],
    },
    {
        'key': 'obv',
        'label': 'OBV',
        'defaults': {'ma_period': 20},
        'fields': [
            {'key': 'ma_period', 'label': 'OBV MA Period', 'step': 1, 'min': 1}
        ],
    },
]

PLOT_OPTIONS = [('Candlestick', 'candlestick')] + [
    (definition['label'], definition['key'])
    for definition in INDICATOR_DEFINITIONS
]

CHART_ELEMENT_OPTIONS = [
    (definition['label'], definition['value'])
    for definition in CHART_ELEMENT_DEFINITIONS
]

SIGNAL_OPTIONS = [
    ('Buy', 'buy'),
    ('Sell', 'sell')
]

# =============================================================================
# INDICATOR SETTINGS
# =============================================================================

_BASE_INDICATOR_SETTINGS = {
    definition['key']: copy.deepcopy(definition['defaults'])
    for definition in INDICATOR_DEFINITIONS
}

INDICATOR_SETTING_SCHEMA = {
    definition['key']: {
        'label': definition['label'],
        'fields': copy.deepcopy(definition['fields']),
    }
    for definition in INDICATOR_DEFINITIONS
}


def _deep_update(base: dict, updates: dict) -> dict:
    for key, value in (updates or {}).items():
        if isinstance(value, dict) and isinstance(base.get(key), dict):
            _deep_update(base[key], value)
        else:
            base[key] = value
    return base


def _strategy_yaml_indicator_defaults() -> dict:
    rsi_cfg = get_strategy_config('rsi')
    cci_cfg = get_strategy_config('cci')
    macd_cfg = get_strategy_config('macd')
    bb_cfg = get_strategy_config('bollinger_bands')
    sma_cfg = get_strategy_config('sma')
    ema_cfg = get_strategy_config('ema')
    vwap_cfg = get_strategy_config('vwap')

    return {
        'rsi': {
            'period': rsi_cfg.get('rsi', {}).get('window', 14),
            'overbought': rsi_cfg.get('overbought_oversold', {}).get('upper_threshold', 70),
            'oversold': rsi_cfg.get('overbought_oversold', {}).get('lower_threshold', 30)
        },
        'cci': {
            'period': cci_cfg.get('cci', {}).get('window', 20),
            'ceiling': cci_cfg.get('overbought_oversold', {}).get('upper_threshold', 150),
            'floor': cci_cfg.get('overbought_oversold', {}).get('lower_threshold', -150)
        },
        'macd': {
            'fast': macd_cfg.get('macd', {}).get('fast_period', 12),
            'slow': macd_cfg.get('macd', {}).get('slow_period', 26),
            'signal': macd_cfg.get('macd', {}).get('signal_period', 9)
        },
        'bollinger': {
            'window': bb_cfg.get('bollinger_bands', {}).get('window', 20),
            'window_dev': bb_cfg.get('bollinger_bands', {}).get('window_dev', 2),
            'squeeze_threshold': bb_cfg.get('squeeze_strategy', {}).get('squeeze_threshold', 0.1),
            'double_bottom_threshold': bb_cfg.get('double_bottom_top_strategy', {}).get('threshold', 0.02)
        },
        'sma': {
            'short_window': sma_cfg.get('sma', {}).get('short_window', 5),
            'medium_window': sma_cfg.get('sma', {}).get('medium_window', 20),
            'long_window': sma_cfg.get('sma', {}).get('long_window', 50),
            'trend_window': sma_cfg.get('sma', {}).get('trend_window', 200)
        },
        'ema': {
            'short_window': ema_cfg.get('ema', {}).get('short_window', 12),
            'medium_window': ema_cfg.get('ema', {}).get('medium_window', 26),
            'long_window': ema_cfg.get('ema', {}).get('long_window', 50)
        },
        'vwap': {
            'window': vwap_cfg.get('vwap', {}).get('window', 20)
        }
    }


def merge_indicator_settings(runtime_settings: dict | None = None) -> dict:
    merged = copy.deepcopy(_BASE_INDICATOR_SETTINGS)
    _deep_update(merged, _strategy_yaml_indicator_defaults())
    _deep_update(merged, runtime_settings or {})
    return merged


DEFAULT_INDICATOR_SETTINGS = merge_indicator_settings()

# Optimization methods
OPTIMIZATION_METHODS = [
    {'label': 'Walk-Forward Optimization', 'value': 'walk_forward'}
]