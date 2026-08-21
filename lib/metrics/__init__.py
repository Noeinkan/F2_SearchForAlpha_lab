"""The metrics engine.

One implementation of every performance metric in the project, one risk-free
convention, one definition of a trade, and one registry of what each metric is
called. Nothing else in the repo should compute a Sharpe ratio.

Typical use::

    from lib.metrics import compute_metrics
    m = compute_metrics(result_df, initial_capital, interval="1h")

The units are documented on :class:`~lib.metrics.engine.BacktestMetrics` and
pinned by ``lib/tests/test_metrics.py``. Read them before comparing a number
here with a number from somewhere else: rates are fractions, ratios are
annualised at the bar interval, and ``max_drawdown`` is a positive magnitude.
"""

from lib.metrics.core import (
    DEFAULT_RISK_FREE_RATE,
    PROFIT_FACTOR_SENTINEL,
    RoundTripStats,
    cagr,
    calmar_ratio,
    count_fills,
    exposure,
    max_drawdown,
    resolve_risk_free_rate,
    round_trip_stats,
    sharpe_ratio,
    sortino_ratio,
    total_return,
    turnover,
)
from lib.metrics.engine import BacktestMetrics, compute_metrics
from lib.metrics.ledger import EXIT_REASONS, TRADE_COLUMNS, trades_to_frame
from lib.metrics.names import (
    DEFAULT_SORT_KEY,
    MetricSpec,
    blurbs,
    format_canonical,
    format_ui,
    leaderboard_columns,
    sort_options,
    spec_for,
    ui_row,
)

__all__ = [
    # engine
    "BacktestMetrics",
    "compute_metrics",
    # ledger
    "EXIT_REASONS",
    "TRADE_COLUMNS",
    "trades_to_frame",
    # primitives
    "DEFAULT_RISK_FREE_RATE",
    "PROFIT_FACTOR_SENTINEL",
    "RoundTripStats",
    "cagr",
    "calmar_ratio",
    "count_fills",
    "exposure",
    "max_drawdown",
    "resolve_risk_free_rate",
    "round_trip_stats",
    "sharpe_ratio",
    "sortino_ratio",
    "total_return",
    "turnover",
    # names
    "DEFAULT_SORT_KEY",
    "MetricSpec",
    "blurbs",
    "format_canonical",
    "format_ui",
    "leaderboard_columns",
    "sort_options",
    "spec_for",
    "ui_row",
]
