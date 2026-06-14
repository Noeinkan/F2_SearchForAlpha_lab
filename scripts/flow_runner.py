"""Subprocess wrapper for flow_scanner.py (used by Dash dashboard)."""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
SCANNER = REPO_ROOT / "scripts" / "flow_scanner.py"


def run_flow_scan(
    tickers: list[str],
    output_path: str | Path,
    *,
    quiet: bool = True,
    expirations: int = 3,
    timeout: int = 180,
) -> tuple[int, str]:
    """Run flow_scanner.py; return (returncode, tail_of_combined_output)."""
    cmd = [
        sys.executable,
        str(SCANNER),
        *tickers,
        "--output",
        str(output_path),
        "--expirations",
        str(expirations),
    ]
    if quiet:
        cmd.append("--quiet")

    try:
        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=timeout,
            cwd=str(REPO_ROOT),
        )
        tail = (result.stdout or "") + (result.stderr or "")
        return result.returncode, tail[-500:]
    except subprocess.TimeoutExpired:
        return 124, "Scan timed out (>180s)"
    except FileNotFoundError as exc:
        return 127, str(exc)
