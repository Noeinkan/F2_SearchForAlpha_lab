"""
Main entry point for the trading strategy application.
"""

import os
import sys

# Setup dell'ambiente
current_dir = os.getcwd()
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)


def main():
    """Main entry point for the application."""
    from lib.dash.integrated_dashboard import run_dashboard as dashboard
    dev_mode = os.getenv("DASH_DEV", "1") == "1"
    dashboard(dev_mode=dev_mode)


if __name__ == "__main__":
    main()
