"""The metric-name registry: one place that knows what each metric is called,
what unit it is in, and how to render it.

Three vocabularies meet here, and the registry is the translation table:

``key``
    Canonical snake_case, identical to the :class:`~lib.metrics.engine.BacktestMetrics`
    field. This is what the CLI JSON contract, the trial store and the
    optimisers speak. Values are in **canonical units**: fractions, positive
    drawdown.
``ui_key``
    The ``Title_Case`` column name used in optimizer result rows, the
    leaderboard, the sort dropdown and the run-history store. Values are in
    **UI units**: percents, and drawdown carrying its conventional minus sign.
label
    What a human reads on screen.

The ``ui_key`` strings are deliberately **unchanged** from what the dashboard
already used. ``lib/dash/optimizer_history.py`` writes them into a
``storage_type='local'`` store and ``layout/optimizer_workspace.py`` uses them
as dropdown ``value=``s persisted in ``optimization-state``; renaming them would
silently void saved history for no gain. Centralising them here is the point,
not renaming them.

Pick the formatter that matches what you are holding:

* :func:`format_canonical` — a value straight off ``BacktestMetrics`` or its
  ``as_dict()`` (a fraction). Converts and renders.
* :func:`format_ui` — a value already inside an optimizer result row (a
  percent). Renders only.
* :func:`ui_row` — a whole ``BacktestMetrics``, converted to the ``Title_Case``
  row the optimizer tables expect.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Optional

from lib.metrics.engine import BacktestMetrics

# How a metric's canonical value maps onto its displayed value.
#   fraction -> multiply by 100 and append '%'
#   ratio    -> render as-is
#   count    -> integer, thousands-separated
#   currency -> thousands-separated with 2dp
UNITS = ("fraction", "ratio", "count", "currency")


@dataclass(frozen=True)
class MetricSpec:
    key: str
    ui_key: str
    label: str
    unit: str
    blurb: str
    precision: int = 2
    signed: bool = False
    # Drawdown is stored as a positive magnitude but shown with the minus sign
    # traders expect. This is the only metric that flips.
    negate_for_display: bool = False

    def to_display(self, value: Any) -> Optional[float]:
        """Canonical value -> displayed value (percent conversion, sign flip).

        Returns None for anything non-numeric, so a missing metric renders as a
        placeholder rather than as a plausible-looking zero.
        """
        try:
            out = float(value)
        except (TypeError, ValueError):
            return None
        if self.negate_for_display:
            out = -out
        if self.unit == "fraction":
            out *= 100.0
        return out


_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec(
        key="total_return", ui_key="Total_Return_%", label="Total Return",
        unit="fraction", signed=True,
        blurb="Percent gain or loss on the starting capital over the whole window.",
    ),
    MetricSpec(
        key="cagr", ui_key="CAGR_%", label="CAGR",
        unit="fraction", signed=True,
        blurb="Total return restated as a compound annual rate.",
    ),
    MetricSpec(
        key="sharpe", ui_key="Sharpe_Ratio", label="Sharpe",
        unit="ratio",
        blurb="Return per unit of volatility, annualised. Above 1 is respectable.",
    ),
    MetricSpec(
        key="sortino", ui_key="Sortino", label="Sortino",
        unit="ratio",
        blurb="Like Sharpe, but only downside volatility counts against you.",
    ),
    MetricSpec(
        key="calmar", ui_key="Calmar", label="Calmar",
        unit="ratio",
        blurb="Compound annual growth divided by the worst drawdown it cost.",
    ),
    MetricSpec(
        key="max_drawdown", ui_key="Max_Drawdown_%", label="Max DD",
        unit="fraction", negate_for_display=True,
        blurb="Largest peak-to-trough fall in portfolio value.",
    ),
    MetricSpec(
        key="num_trades", ui_key="Trades", label="Trades",
        unit="count", precision=0,
        blurb="Completed round trips — an entry and its matching exit. "
              "A position still open at the end is not counted here.",
    ),
    MetricSpec(
        key="num_fills", ui_key="Fills", label="Fills",
        unit="count", precision=0,
        blurb="Individual executions. One round trip is at least two fills, more if scaled in.",
    ),
    MetricSpec(
        key="open_trades", ui_key="Open_Trades", label="Open",
        unit="count", precision=0,
        blurb="Positions still held on the final bar, marked to market.",
    ),
    MetricSpec(
        key="win_rate", ui_key="Win_Rate_%", label="Win Rate",
        unit="fraction", precision=1,
        blurb="Share of closed round trips that made money.",
    ),
    MetricSpec(
        key="profit_factor", ui_key="Profit_Factor", label="Profit Factor",
        unit="ratio",
        blurb="Gross profit divided by gross loss. Above 1 means the winners paid for the losers.",
    ),
    MetricSpec(
        key="avg_win", ui_key="Avg_Win", label="Avg Win",
        unit="currency", signed=True,
        blurb="Mean profit of a winning round trip, after fees.",
    ),
    MetricSpec(
        key="avg_loss", ui_key="Avg_Loss", label="Avg Loss",
        unit="currency", signed=True,
        blurb="Mean loss of a losing round trip, after fees.",
    ),
    MetricSpec(
        key="expectancy", ui_key="Expectancy", label="Expectancy",
        unit="currency", signed=True,
        blurb="Average result per round trip — what one more trade is worth on average.",
    ),
    MetricSpec(
        key="avg_holding_bars", ui_key="Avg_Holding_Bars", label="Avg Hold",
        unit="ratio", precision=1,
        blurb="Mean bars held per closed round trip. Bars, not calendar time.",
    ),
    MetricSpec(
        key="avg_holding_sessions", ui_key="Avg_Holding_Sessions", label="Avg Sessions",
        unit="ratio", precision=1,
        blurb="Mean session boundaries a round trip crossed. 0 means it opened "
              "and closed the same session; 1 means it was held overnight.",
    ),
    MetricSpec(
        key="total_fees", ui_key="Total_Fees", label="Fees",
        unit="currency",
        blurb="Commission, FX fee and slippage paid across every fill.",
    ),
    MetricSpec(
        key="exposure", ui_key="Exposure_%", label="Exposure",
        unit="fraction", precision=1,
        blurb="Share of bars spent holding a position rather than in cash.",
    ),
    MetricSpec(
        key="turnover", ui_key="Turnover", label="Turnover",
        unit="ratio",
        blurb="Gross traded notional over mean equity. Higher means busier, and costlier.",
    ),
)

BY_KEY: dict[str, MetricSpec] = {s.key: s for s in _SPECS}
BY_UI_KEY: dict[str, MetricSpec] = {s.ui_key: s for s in _SPECS}

# Row columns the optimizer produces that are not BacktestMetrics fields. They
# still need consistent formatting, so they get specs without a canonical key.
_EXTRA_SPECS: tuple[MetricSpec, ...] = (
    MetricSpec(
        key="", ui_key="Final_Value", label="Final Value", unit="currency",
        blurb="Portfolio value on the last bar.",
    ),
    MetricSpec(
        key="", ui_key="BuyHold_Return_%", label="Buy & Hold", unit="fraction",
        signed=True,
        blurb="What simply holding the symbol over the same window returned.",
    ),
    MetricSpec(
        key="", ui_key="Alpha_%", label="Alpha", unit="fraction", signed=True,
        blurb="Strategy return minus buy-and-hold return, in percentage points.",
    ),
    MetricSpec(
        key="", ui_key="Robustness_Score", label="Score", unit="ratio",
        blurb="Risk-adjusted performance discounted by how few trades backed it up.",
    ),
)
for _spec in _EXTRA_SPECS:
    BY_UI_KEY[_spec.ui_key] = _spec

# These three carry no canonical key, so they never pass through ``to_display``
# — the optimizer stores them already multiplied out. ``unit='fraction'`` here
# means "render with a % suffix", not "multiply me".

# Default sort key for the optimizer leaderboard. One definition, so
# ``layout/shell.py``'s store default and ``callbacks/optimization.py``'s
# fallback cannot drift apart again.
DEFAULT_SORT_KEY = "Robustness_Score"


def spec_for(key: str) -> Optional[MetricSpec]:
    """Look a spec up by canonical key or by UI key."""
    return BY_KEY.get(key) or BY_UI_KEY.get(key)


def _render(spec: Optional[MetricSpec], display_value: Any, unit: str) -> str:
    try:
        value = float(display_value)
    except (TypeError, ValueError):
        return "—"
    precision = spec.precision if spec else 2
    sign = "+" if (spec and spec.signed) else ""
    if unit == "count":
        return f"{int(round(value)):,}"
    if unit == "currency":
        return f"{value:{sign},.{precision}f}"
    if unit == "fraction":
        return f"{value:{sign}.{precision}f}%"
    return f"{value:{sign}.{precision}f}"


def format_canonical(key: str, value: Any) -> str:
    """Format a value held in **canonical** units (a fraction, positive drawdown).

    Use this on anything read off ``BacktestMetrics`` or its ``as_dict()``.
    """
    spec = spec_for(key)
    if spec is None:
        return _render(None, value, "ratio")
    return _render(spec, spec.to_display(value), spec.unit)


def format_ui(ui_key: str, value: Any) -> str:
    """Format a value already in **UI** units (a percent, signed drawdown).

    Use this on cells of an optimizer result row.
    """
    spec = BY_UI_KEY.get(ui_key)
    if spec is None:
        return _render(None, value, "ratio")
    return _render(spec, value, spec.unit)


def ui_row(metrics: BacktestMetrics) -> dict[str, Any]:
    """Convert a ``BacktestMetrics`` into the ``Title_Case`` optimizer row.

    Percent metrics are multiplied by 100 and drawdown carries its minus sign,
    matching what the leaderboard, the sort dropdown and the persisted run
    history have always contained.
    """
    row: dict[str, Any] = {}
    for spec in _SPECS:
        value = getattr(metrics, spec.key, None)
        if value is None:
            continue
        row[spec.ui_key] = int(value) if spec.unit == "count" else spec.to_display(value)
    return row


# Column order of the optimizer results table. Explicit rather than derived
# from ``_SPECS`` order, so adding a metric to the registry cannot silently
# reshuffle a table users read left to right. The two signal columns are not
# metrics and are prepended by the caller.
LEADERBOARD_ORDER = (
    "Total_Return_%", "Alpha_%", "Sharpe_Ratio", "Sortino", "Calmar",
    "Max_Drawdown_%", "Win_Rate_%", "Profit_Factor", "Trades",
)

# Sort dropdown, in the order the control has always listed them.
SORT_ORDER = (
    DEFAULT_SORT_KEY, "Total_Return_%", "Sharpe_Ratio", "Calmar",
    "Max_Drawdown_%", "Trades",
)

_SORT_LABELS = {
    "Robustness_Score": "SCORE",
    "Total_Return_%": "RET",
    "Max_Drawdown_%": "DD",
}


def leaderboard_columns() -> list[str]:
    """UI keys for the optimizer results table, in display order."""
    return list(LEADERBOARD_ORDER)


def sort_options() -> list[dict[str, str]]:
    """Dash dropdown options for the leaderboard sort control."""
    out = []
    for ui_key in SORT_ORDER:
        spec = BY_UI_KEY.get(ui_key)
        label = _SORT_LABELS.get(ui_key) or (spec.label.upper() if spec else ui_key)
        out.append({"label": label, "value": ui_key})
    return out


def blurbs() -> dict[str, str]:
    """UI key -> one-line explanation, for tooltips and the glossary."""
    return {s.ui_key: s.blurb for s in (*_SPECS, *_EXTRA_SPECS)}


__all__ = [
    "MetricSpec", "BY_KEY", "BY_UI_KEY", "DEFAULT_SORT_KEY", "spec_for",
    "format_canonical", "format_ui", "ui_row", "leaderboard_columns",
    "sort_options", "blurbs",
]
