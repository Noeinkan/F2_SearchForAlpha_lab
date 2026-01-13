# SearchForAlpha Lab 📈

A comprehensive Python-based algorithmic trading research platform for backtesting, signal generation, and strategy optimization. This project provides tools to analyze financial markets, test trading strategies using technical indicators, and visualize results through an interactive dashboard.

## 🎯 Features

- **Multiple Technical Indicators**: Built-in support for popular indicators:
  - Bollinger Bands (BB)
  - Relative Strength Index (RSI)
  - Moving Average Convergence Divergence (MACD)
  - Commodity Channel Index (CCI)
  - Simple Moving Average (SMA)
  - Exponential Moving Average (EMA)
  - Average Directional Index (ADX)
  - Average True Range (ATR)
  - On-Balance Volume (OBV)

- **Flexible Backtesting Engine**: 
  - Configurable position sizing strategies
  - Signal strength weighting
  - Trailing stop-loss support
  - Volatility-based position sizing
  - Minimum holding period constraints

- **Strategy Optimization**:
  - Grid search parameter optimization
  - Walk-forward optimization
  - Signal combination optimization
  - Weight optimization for indicator combinations

- **Interactive Dashboard**: 
  - Built with Dash and Plotly
  - Real-time chart visualization
  - Candlestick charts with overlay indicators
  - Data table view for detailed analysis
  - Configurable buy/sell signal display

- **Performance Metrics**:
  - Total Return
  - Sharpe Ratio
  - Maximum Drawdown
  - Win Rate
  - Profit Factor
  - Average Trade Duration

## 📁 Project Structure

```
F2_SearchForAlpha_lab/
├── Main.ipynb                    # Main entry point - launches dashboard
├── params_optimisation.ipynb     # Parameter optimization notebook
├── Signal_combination_Tester.ipynb # Signal testing notebook
├── ML_tester.ipynb               # Machine learning experiments
├── AEC_IDE.ipynb                 # Additional testing notebook
│
├── lib/                          # Core library modules
│   ├── data_processing.py        # Data fetching & preprocessing
│   ├── strategy.py               # Backtesting engine
│   ├── visualization.py          # Matplotlib chart generation
│   ├── utils.py                  # Utility functions
│   ├── params_optimasation.py    # Parameter optimization logic
│   ├── signal_combo_optimisation.py # Signal combination optimizer
│   ├── weights_optimasation.py   # Weight optimization for signals
│   │
│   ├── dash/                     # Dashboard components
│   │   ├── integrated_dashboard.py # Main Dash application
│   │   ├── chart_utils.py        # Plotly chart utilities
│   │   └── dash_config.py        # Dashboard configuration
│   │
│   ├── signals/                  # Trading signal generators
│   │   ├── indicators.py         # Main indicator module
│   │   ├── signals_BB.py         # Bollinger Bands strategies
│   │   ├── signals_RSI.py        # RSI strategies
│   │   ├── signals_MACD.py       # MACD strategies
│   │   ├── signals_CCI.py        # CCI strategies
│   │   ├── signals_SMA.py        # SMA strategies
│   │   └── signals_EMA.py        # EMA strategies
│   │
│   ├── tests/                    # Unit tests
│   └── WIP/                      # Work in progress modules
│
├── SS/                           # Strategy sandbox notebooks
├── export/                       # Exported results
├── results/                      # Backtest results
└── Notes/                        # Project notes
```

## 🚀 Getting Started

### Prerequisites

- Python 3.8+
- pip or conda package manager

### Installation

1. Clone the repository:
```bash
git clone https://github.com/yourusername/SearchForAlpha_lab.git
cd SearchForAlpha_lab
```

2. Install required dependencies:
```bash
pip install numpy pandas yfinance plotly dash dash-bootstrap-components mplfinance ta matplotlib adjustText tqdm
```

### Quick Start

1. Open `Main.ipynb` in Jupyter Notebook or VS Code
2. Run all cells to launch the interactive dashboard
3. The dashboard will open in your browser automatically

```python
from lib.dash.integrated_dashboard import run_dashboard

if __name__ == "__main__":
    run_dashboard()
```

## 📊 Usage

### Running a Backtest

```python
from lib.data_processing import fetch_data
from lib.signals.indicators import add_indicators, generate_signals
from lib.strategy import backtest

# Fetch historical data
df = fetch_data('SPY', '2020-01-01', '2024-01-01')

# Add technical indicators
df = add_indicators(df)

# Generate trading signals
df, all_signals = generate_signals(df)

# Define buy/sell indicators
buy_indicators = ['RSI_Oversold_Buy', 'BB_Lower_Buy']
sell_indicators = ['RSI_Overbought_Sell', 'BB_Upper_Sell']

# Run backtest
results = backtest(
    df=df,
    initial_capital=100000,
    position_sizing_strategy='percentage_of_portfolio',
    position_sizing_params={'percentage': 0.1},
    buy_indicators=buy_indicators,
    sell_indicators=sell_indicators,
    trailing_stop_loss=0.05
)
```

### Customizing Signal Strategies

Each signal module (e.g., `signals_RSI.py`) contains configurable parameters:

```python
from lib.signals.signals_RSI import RSI_TradingStrategy

# Create strategy with custom configuration
rsi_strategy = RSI_TradingStrategy(config={
    'rsi': {'window': 14},
    'overbought_oversold': {
        'upper_threshold': 70,
        'lower_threshold': 30
    }
})

# Apply to dataframe
df = rsi_strategy.RSI_generate_signals(df)
```

### Parameter Optimization

```python
from lib.params_optimasation import optimize_parameters

param_ranges = {
    'trailing_stop_loss': [0.03, 0.05, 0.07],
    'position_scaling': [0.1, 0.25, 0.5],
    'buy_threshold': [0.3, 0.5, 0.7]
}

best_params, best_return = optimize_parameters(
    df=df,
    initial_capital=100000,
    param_ranges=param_ranges,
    metric='total_return'
)
```

## 📈 Dashboard Features

The integrated dashboard provides:

- **Chart Tab**: Interactive candlestick chart with:
  - Overlay indicators (Bollinger Bands, SMAs, EMAs)
  - Buy/Sell signal markers
  - Volume subplot
  - Technical indicator subplots (RSI, MACD, CCI)

- **Data Table Tab**: Spreadsheet view of all data including:
  - Price data (OHLCV)
  - Indicator values
  - Signal columns
  - Portfolio metrics

- **Controls Panel**:
  - Toggle buy/sell signals
  - Select which plots to display
  - View backtest results summary

## 🔧 Available Signals

| Indicator | Buy Signals | Sell Signals |
|-----------|-------------|--------------|
| RSI | Oversold, Bullish Divergence | Overbought, Bearish Divergence |
| Bollinger Bands | Lower Band Touch, Squeeze | Upper Band Touch |
| MACD | Bullish Crossover, Histogram Rising | Bearish Crossover, Histogram Falling |
| CCI | Oversold Reversal | Overbought Reversal |
| SMA | Golden Cross, Price Above SMA | Death Cross, Price Below SMA |
| EMA | Bullish Crossover | Bearish Crossover |

## 🧪 Testing

Run the test suite:

```bash
python -m pytest lib/tests/
```

## 📝 Notes

- Data is fetched from Yahoo Finance via the `yfinance` library
- Supports S&P 500, NASDAQ-100 stocks, and major ETFs (SPY, QQQ, DIA, IWM, VTI)
- Results can be exported to Excel for further analysis

## ⚠️ Disclaimer

This software is for educational and research purposes only. It is not intended as financial advice. Trading in financial markets involves substantial risk of loss. Past performance is not indicative of future results. Always do your own research and consider consulting with a qualified financial advisor before making investment decisions.

## 📄 License

This project is provided as-is for educational purposes.

## 🤝 Contributing

Contributions are welcome! Please feel free to submit pull requests or open issues for bugs and feature requests.
