"""
Main entry point for the trading strategy application.
"""

import os
import sys

# Setup dell'ambiente
current_dir = os.getcwd()
parent_dir = os.path.dirname(current_dir)
sys.path.append(parent_dir)


def _load_local_env():
    """Read local secrets such as GEMINI_API_KEY from the repo's git-ignored .env.

    A variable already set in the environment wins, and blank lines like
    ``SFA_STATE_DB=`` are skipped so they cannot replace a default with "".
    """
    from demo import envfile
    try:
        text = envfile.REPO_ENV.read_text(encoding="utf-8-sig")
    except FileNotFoundError:
        return
    for key, value in envfile.parse(text).items():
        if value and key not in os.environ:
            os.environ[key] = value


def main():
    """Main entry point for the application."""
    _load_local_env()

    from lib.dash.integrated_dashboard import run_dashboard as dashboard
    dev_mode = os.getenv("DASH_DEV", "1") == "1"
    dashboard(dev_mode=dev_mode)


if __name__ == "__main__":
    main()
