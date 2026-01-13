# config.py

# Colors
BACKGROUND_COLOR = '#FFFFFF'
TEXT_COLOR = '#000000'
BORDER_COLOR = '#2C2C2C'
CHART_BACKGROUND_COLOR = '#FFFFFF'

# Layout
MAIN_CONTENT_WIDTH = '80%'
SIDEBAR_WIDTH = '20%'

# Chart
CHART_HEIGHT = 'calc(100vh - 60px)'

# Backtest
DEFAULT_TICKER = 'SPY'
INITIAL_CAPITAL = 10000
START_DATE = '2018-01-01'

# Port
START_PORT = 8050
MAX_PORT_TRIES = 100

# Optimization
OPTIMIZATION_PERCENT = 0.1
OPTIMIZATION_DELAY = 1

# Checklist options
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

# Optimization methods
OPTIMIZATION_METHODS = [
    {'label': 'Walk-Forward Optimization', 'value': 'walk_forward'}
]