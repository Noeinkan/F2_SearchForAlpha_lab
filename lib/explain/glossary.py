"""The project's own definitions, sent to Gemini with every question.

Without them a model explains "alpha" or "max drawdown" in the textbook sense,
which is wrong here in small ways that matter (alpha is Jensen's, not the gap
to buy-and-hold; drawdown is stored positive; "trades" are round trips). The
metric lines are built from ``lib.metrics.names``, the registry the dashboard
itself renders from, so they cannot drift from what is on screen.
"""

from __future__ import annotations

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


def _flatten(prefix: str, value) -> list[str]:
    if isinstance(value, dict):
        out: list[str] = []
        for key, inner in value.items():
            out += _flatten(f"{prefix}.{key}" if prefix else str(key), inner)
        return out
    return [f"{prefix}={value}"]


def indicator_lines() -> list[str]:
    """Default indicator parameters from config/strategy_config.yaml, one line per indicator."""
    try:
        from lib.config_loader import get_config

        strategies = get_config().get("strategies", {}) or {}
    except Exception:
        return []
    lines = []
    for name, block in strategies.items():
        params = ", ".join(_flatten("", block)) if isinstance(block, dict) else str(block)
        lines.append(f"- {name}: {params}")
    return lines


def signal_lines() -> list[str]:
    """What each Buy/Sell signal column means, from the registered strategies."""
    try:
        from lib.signals.indicators import get_signal_descriptions

        descriptions = get_signal_descriptions()
    except Exception:
        return []
    return [f"- {key}: {text}" for key, text in descriptions.items()]


@lru_cache(maxsize=1)
def glossary_text() -> str:
    from lib.metrics.names import BY_UI_KEY

    lines = [CONVENTIONS, "", "Metric definitions (label / column name: meaning):"]
    for ui_key, spec in BY_UI_KEY.items():
        lines.append(f"- {spec.label} / {ui_key}: {spec.blurb}")
    lines.append("- Max DD is displayed with a minus sign but means the size of the worst fall.")

    indicators = indicator_lines()
    if indicators:
        lines += [
            "",
            "Indicator default parameters (config/strategy_config.yaml; the user can override them with the gear icon next to each indicator):",
            *indicators,
        ]
    signals = signal_lines()
    if signals:
        lines += ["", "Signals each indicator can generate (column name: rule):", *signals]
    return "\n".join(lines)
