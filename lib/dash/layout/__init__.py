"""
Layout builders for the dashboard.

Mirrors the `callbacks/` pattern — each file owns one region of the UI.
`shell.create_dashboard_layout` composes the regions; it is re-exported
from `lib.dash.integrated_dashboard` so existing imports keep working.
"""

from .shell import create_dashboard_layout

__all__ = ["create_dashboard_layout"]