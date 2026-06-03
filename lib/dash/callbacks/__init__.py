"""
Callback registry for the dashboard.
"""

from .startup import register_startup_callbacks
from .presets import register_preset_callbacks
from .data_loading import register_data_loading_callbacks
from .strategy_ui import register_strategy_callbacks
from .signals import register_signal_callbacks
from .chart_plotly import register_plotly_callbacks
from .chart_tv import register_tv_callbacks
from .backtest import register_backtest_callbacks
from .optimization import register_optimization_callbacks
from .fundamentals import register_fundamentals_callbacks
from .routing import register_routing_callbacks
from .misc_ui import register_misc_callbacks


def register_callbacks(app) -> None:
    """Register all callbacks for the dashboard application."""
    register_startup_callbacks(app)
    register_preset_callbacks(app)
    register_data_loading_callbacks(app)
    register_strategy_callbacks(app)
    register_signal_callbacks(app)
    register_plotly_callbacks(app)
    register_tv_callbacks(app)
    register_backtest_callbacks(app)
    register_optimization_callbacks(app)
    register_routing_callbacks(app)
    register_fundamentals_callbacks(app)
    register_misc_callbacks(app)
