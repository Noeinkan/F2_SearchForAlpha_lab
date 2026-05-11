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
        'lib.signals.indicators'
    ]
    for module in modules_to_reload:
        if module in sys.modules:
            importlib.reload(sys.modules[module])


def main():
    """Main entry point for the application."""
    reload_modules()
    # Re-import after reload to get the fresh module
    from lib.dash.integrated_dashboard import run_dashboard as dashboard
    dev_mode = os.getenv("DASH_DEV", "0") == "1"
    dashboard(dev_mode=dev_mode)


if __name__ == "__main__":
    main()
