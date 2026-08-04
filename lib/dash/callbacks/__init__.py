"""
Callback registry for the dashboard.
"""

from .startup import register_startup_callbacks
from .presets import register_preset_callbacks
from .data_loading import register_data_loading_callbacks
from .test_window import register_test_window_callbacks
from .data_table import register_data_table_callbacks
from .strategy_ui import register_strategy_callbacks
from .execution_help import register_execution_help_callbacks
from .signals import register_signal_callbacks
from .chart import register_chart_callbacks
from .backtest import register_backtest_callbacks
from .optimization import register_optimization_callbacks
from .optimize_workspace import register_optimize_workspace_callbacks
from .optimizer_sync import register_optimizer_sync_callbacks
from .fundamentals import register_fundamentals_callbacks
from .flow import register_flow_callbacks
from .routing import register_routing_callbacks
from .misc_ui import register_misc_callbacks
from .layout import register_layout_callbacks
from .command_palette import register_command_palette_callbacks
from .symbol_search import register_symbol_search_callbacks
from .status import register_status_callbacks


def register_callbacks(app) -> None:
    """Register all callbacks for the dashboard application."""
    register_startup_callbacks(app)
    register_preset_callbacks(app)
    register_data_loading_callbacks(app)
    register_test_window_callbacks(app)
    register_data_table_callbacks(app)
    register_strategy_callbacks(app)
    register_execution_help_callbacks(app)
    register_signal_callbacks(app)
    register_chart_callbacks(app)
    register_backtest_callbacks(app)
    register_optimization_callbacks(app)
    register_optimize_workspace_callbacks(app)
    register_optimizer_sync_callbacks(app)
    register_routing_callbacks(app)
    register_fundamentals_callbacks(app)
    register_flow_callbacks(app)
    register_misc_callbacks(app)
    register_layout_callbacks(app)
    register_command_palette_callbacks(app)
    register_symbol_search_callbacks(app)
    register_status_callbacks(app)
