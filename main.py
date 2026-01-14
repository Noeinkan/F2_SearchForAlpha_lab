"""
Main entry point for the trading strategy application.
"""

import os
import sys
import importlib
import webbrowser
from threading import Timer
import socket

# Setup dell'ambiente
current_dir = os.getcwd()
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)


def reload_modules() -> None:
    """Ricarica i moduli necessari."""
    modules_to_reload = [
        'lib.data_processing', 'lib.visualization',
        'lib.signal_combination', 'lib.strategy', 'lib.utils',
        'lib.dash.integrated_dashboard',
        'lib.signals.indicators', 'lib.signals.signals_BB', 'lib.signals.signals_CCI', 
        'lib.signals.signals_EMA', 'lib.signals.signals_MACD', 'lib.signals.signals_RSI', 
        'lib.signals.signals_SMA'
    ]
    for module in modules_to_reload:
        if module in sys.modules:
            importlib.reload(sys.modules[module])


# Import necessary modules (explicit imports, no star imports)
from lib.signals.indicators import add_indicators, generate_signals
from lib.data_processing import fetch_data, get_all_tickers, create_backtest_results
from lib.visualization import plot_financial_chart
from lib.utils import TradingStrategyInput, get_user_input, export_priceaction_to_excel
from lib.strategy import backtest, run_backtest, percentage_of_portfolio
from lib.signal_combo_optimisation import generate_ordered_combinations, test_combination

from lib.signals.signals_BB import BB_TradingStrategy
from lib.signals.signals_CCI import CCI_TradingStrategy
from lib.signals.signals_EMA import EMA_TradingStrategy
from lib.signals.signals_MACD import MACD_TradingStrategy
from lib.signals.signals_RSI import RSI_TradingStrategy
from lib.signals.signals_SMA import SMA_TradingStrategy

from lib.dash.integrated_dashboard import run_dashboard


def main():
    """Main entry point for the application."""
    reload_modules()
    # Re-import after reload to get the fresh module
    from lib.dash.integrated_dashboard import run_dashboard as dashboard
    dashboard()


if __name__ == "__main__":
    main()
