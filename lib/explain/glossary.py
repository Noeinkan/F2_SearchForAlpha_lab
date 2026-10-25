"""The project's own definitions, sent to Gemini with every question
(only the part that concerns the clicked thing: ``glossary_for``).

Without them a model explains "alpha" or "max drawdown" in the textbook sense,
which is wrong here in small ways that matter (alpha is Jensen's, not the gap
to buy-and-hold; drawdown is stored positive; "trades" are round trips). The
metric lines are built from ``lib.metrics.names``, the registry the dashboard
itself renders from, so they cannot drift from what is on screen.
"""

from __future__ import annotations

import re
from functools import lru_cache

CONVENTIONS = """\
Conventions in this app (SearchForAlpha Lab, a backtesting research dashboard):
- Prices are Yahoo Finance OHLCV, split- and dividend-adjusted.
- A backtest fills market orders at the bar's close by default; limit/stop orders fill against a later bar's High/Low, or at the Open if the bar gapped through.
- Rates are shown as percents; ratios (Sharpe, Sortino, Info Ratio) are annualised at the bar interval (1h has 7 bars per session, 252 sessions per year).
- The benchmark is buy-and-hold of the same symbol over the same window.
- Signal names look like INDICATOR_CONDITION_Buy / _Sell (e.g. RSI_Oversold_Buy).
- Regime analysis runs a separate backtest per market regime; a regime without full data is shown but not counted, so "inconclusive" is a normal verdict on intraday data.
- Fundamentals come from SEC filings; quarterly Q4 and cash-flow quarters are derived from year-to-date totals.
- The Flow Scanner reads the options chain (open interest, volume, put/call)."""


MAX_DD_NOTE = "- Max DD is displayed with a minus sign but means the size of the worst fall."
INDICATOR_HEADING = (
    "Indicator default parameters (config/strategy_config.yaml; the user can override them "
    "with the gear icon next to each indicator):"
)
SIGNAL_HEADING = "Signals each indicator can generate (column name: rule):"

# Words on screen that name an indicator, beyond its config key.
INDICATOR_ALIASES = {
    "bollinger_bands": ("bollinger", "bb", "bands"),
    "stoch": ("stochastic", "stoch"),
    "macd": ("macd",),
    "vwap": ("vwap",),
    "obv": ("obv", "balance"),
}
# Signal column prefix -> indicator config key, where they differ.
SIGNAL_PREFIX = {"bb": "bollinger_bands"}


def _flatten(prefix: str, value) -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for key, inner in value.items():
            out += _flatten(f"{prefix}.{key}" if prefix else str(key), inner)
        return out
    return [f"{prefix}={value}"]


@lru_cache(maxsize=1)
def _indicators() -> dict[str, str]:
    """Indicator config key -> its glossary line, from config/strategy_config.yaml."""
    try:
        from lib.config_loader import get_config

        strategies = get_config().get("strategies", {}) or {}
    except Exception:
        return {}
    out = {}
    for name, block in strategies.items():
        params = ", ".join(_flatten("", block)) if isinstance(block, dict) else str(block)
        out[str(name)] = f"- {name}: {params}"
    return out


@lru_cache(maxsize=1)
def _signals() -> dict[str, str]:
    """Signal column -> what it means, from the registered strategies."""
    try:
        from lib.signals.indicators import get_signal_descriptions

        return {str(k): f"- {k}: {v}" for k, v in get_signal_descriptions().items()}
    except Exception:
        return {}


def _metrics() -> dict[str, tuple[str, str]]:
    """UI key -> (label, glossary line)."""
    from lib.metrics.names import BY_UI_KEY

    return {key: (spec.label, f"- {spec.label} / {key}: {spec.blurb}") for key, spec in BY_UI_KEY.items()}


def indicator_lines() -> list[str]:
    return list(_indicators().values())


def signal_lines() -> list[str]:
    return list(_signals().values())


def _signal_indicator(column: str) -> str:
    prefix = column.split("_", 1)[0].lower()
    return SIGNAL_PREFIX.get(prefix, prefix)


def _assemble(metric_lines, indicator_lines_, signal_lines_, extra=()) -> str:
    lines = [CONVENTIONS]
    if metric_lines:
        lines += ["", "Metric definitions (label / column name: meaning):", *metric_lines, MAX_DD_NOTE]
    if indicator_lines_:
        lines += ["", INDICATOR_HEADING, *indicator_lines_]
    if signal_lines_:
        lines += ["", SIGNAL_HEADING, *signal_lines_]
    lines += list(extra)
    return "\n".join(lines)


@lru_cache(maxsize=1)
def glossary_text() -> str:
    """Everything: every metric, every indicator default, every signal rule."""
    metric_lines = [line for _, line in _metrics().values()]
    return _assemble(metric_lines, indicator_lines(), signal_lines())


def glossary_for(selection: str, context: str = "") -> str:
    """Only the glossary lines the clicked thing is about.

    The full glossary is ~2,800 tokens on every question; a click on RSI needs
    the RSI line and the RSI signals, not the other ten indicators. Matching is
    plain word search over the selection and its context. When nothing
    matches, Gemini gets the conventions plus the bare vocabulary (metric and
    indicator names), which is enough for a control like "Min Holding".
    """
    low = f"{selection} {context}".lower()
    words = set(re.findall(r"[a-z0-9%]+", low))

    metric_lines = [
        line for key, (label, line) in _metrics().items()
        if key.lower() in low or re.search(r"(?<![a-z])" + re.escape(label.lower()) + r"(?![a-z])", low)
    ]
    indicators = _indicators()
    picked = {
        name for name in indicators
        if name in words or name in low or any(alias in words for alias in INDICATOR_ALIASES.get(name, ()))
    }
    signals = _signals()
    signal_hits = [
        line for column, line in signals.items()
        if _signal_indicator(column) in picked or column.lower() in low
    ]
    picked |= {_signal_indicator(c) for c in signals if c.lower() in low} & set(indicators)

    if metric_lines or picked or signal_hits:
        return _assemble(metric_lines, [indicators[n] for n in indicators if n in picked], signal_hits)
    vocabulary = [
        "",
        "Metrics the app shows: " + ", ".join(label for label, _ in _metrics().values()) + ".",
        "Indicators the app offers: " + ", ".join(indicators) + ".",
    ]
    return _assemble([], [], [], vocabulary)
