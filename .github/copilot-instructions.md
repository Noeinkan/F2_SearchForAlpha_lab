# SearchForAlpha Lab - Copilot Instructions

## Architecture Overview

This is a Python-based algorithmic trading research platform with three main layers:

1. **Signal Generation** (`lib/signals/`) - Technical indicator strategies inheriting from `BaseTradingStrategy`
2. **Backtesting Engine** (`lib/strategy.py`) - Portfolio simulation with position sizing, trailing stops, signal strength weighting
3. **Interactive Dashboard** (`lib/dash/`) - Dash/Plotly visualization with `DashboardState` for thread-safe state management

**Data Flow**: `data_processing.py` (Yahoo Finance fetch) → `indicators.py` (aggregates signals) → `strategy.py` (backtest) → `integrated_dashboard.py` (visualize)

## Running the Application

```bash
# Activate venv first
.venv/Scripts/python.exe main.py   # Launches Dash dashboard on auto-detected port
```

Entry point is `main.py` which calls `reload_modules()` for hot-reloading during development, then `run_dashboard()`.

## Adding New Indicators/Strategies

All signal strategies follow this pattern in `lib/signals/`:

1. **Inherit from `BaseTradingStrategy`** (see [base_strategy.py](lib/signals/base_strategy.py))
2. **Define `DEFAULT_CONFIG` dict** with nested parameter groups
3. **Implement required methods**:
   - `add_indicators(df)` - Add indicator columns to DataFrame
   - `generate_signals(df)` - Return DataFrame with buy/sell signal columns (integers: 0/1)
4. **Register in** [indicators.py](lib/signals/indicators.py) `generate_signals()` strategies list

Example structure from [signals_RSI.py](lib/signals/signals_RSI.py):
```python
class RSI_TradingStrategy(BaseTradingStrategy):
    DEFAULT_CONFIG = {'rsi': {'window': 14}, 'overbought_oversold': {'upper_threshold': 70, 'lower_threshold': 30}}
    def add_indicators(self, df): ...
    def generate_signals(self, df): ...  # Returns df with 'RSI_Oversold_Buy', 'RSI_Overbought_Sell' columns
```

## Configuration System

- **Strategy parameters**: [config/strategy_config.yaml](config/strategy_config.yaml) - Modify indicator windows, thresholds without code changes
- **Dashboard settings**: [lib/dash/dash_config.py](lib/dash/dash_config.py) - Colors, sizes, default values
- **Config loading**: `ConfigLoader` singleton in [config_loader.py](lib/config_loader.py) loads YAML at runtime

## Key Conventions

- **Signal column naming**: `{Indicator}_{Strategy}_{Buy|Sell}` (e.g., `RSI_Oversold_Buy`, `BB_Squeeze_Sell`)
- **DataFrames always include**: OHLCV columns (`Open`, `High`, `Low`, `Close`, `Volume`)
- **Custom exceptions**: Use `ValidationError`, `BacktestError`, `DataFetchError` for specific error types
- **Logging**: Each module has `logger = logging.getLogger(__name__)`

## Testing

Tests are in `lib/tests/`. Run with:
```bash
.venv/Scripts/python.exe -m pytest lib/tests/ -v
```

Tests use `unittest` with `setUp()` fixtures creating synthetic DataFrames. See [test_strategy.py](lib/tests/test_strategy.py) for backtest validation patterns.

## Important Dependencies

- `ta` - Technical analysis library for indicator calculations
- `yfinance` - Yahoo Finance data fetching
- `dash`, `dash-bootstrap-components`, `plotly` - Dashboard UI
- `pandas`, `numpy` - Data manipulation
- `openpyxl`, `win32com` - Excel export functionality (Windows-specific)

## Notebooks

- `params_optimisation.ipynb` - Grid search/walk-forward optimization
- `Signal_combination_Tester.ipynb` - Test indicator combinations
- `ML_tester.ipynb` - Machine learning experiments (WIP)
- `SS/` folder contains iterative strategy sandbox versions
