"""Shared glossary, flag definitions, and interpretive copy for Flow Scanner UI."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

DISCLAIMER = "Educational/research use only. Not financial advice."

TERM_DEFINITIONS: dict[str, str] = {
    "strike": "Price at which the option can be exercised.",
    "type": "C = call (right to buy the stock). P = put (right to sell the stock).",
    "last": "Last traded price per share. Each contract controls 100 shares.",
    "bid": "Highest price a buyer is willing to pay right now.",
    "ask": "Lowest price a seller will accept right now.",
    "vol": "Number of contracts traded today.",
    "oi": "Open interest — contracts outstanding before today. New activity often shows vol > OI.",
    "iv": "Implied volatility — the market's expected annualized price swing, as a percentage.",
    "premium": "Total dollars paid for today's volume: volume × last price × 100.",
    "pc_vol": "Put volume divided by call volume. Above 1.0 means more puts traded; below 1.0 means more calls.",
    "pc_oi": "Put open interest divided by call open interest.",
    "score": "Composite unusual-activity score: 5×HU + 3×B + 2×U + 10×RC.",
    "expiry": "Date the option expires. Short-dated contracts react faster to price moves.",
    "itm": "In the money — the option has intrinsic value at the current stock price.",
    "otm": "Out of the money — the option has no intrinsic value at the current stock price.",
    "weekly": "Expires within 7 days — often used for short-term directional bets.",
}

FLAG_DEFINITIONS: dict[str, dict[str, str]] = {
    "unusual": {
        "label": "U",
        "short": "Unusual",
        "long": "Volume exceeds open interest — likely new positions opening in size.",
        "color": "#a371f7",
    },
    "high_unusual": {
        "label": "HU",
        "short": "High unusual",
        "long": "Out-of-the-money weekly contract with abnormally large volume — often a near-term speculative bet.",
        "color": "#58a6ff",
    },
    "block_premium": {
        "label": "B",
        "short": "Block premium",
        "long": "Total premium crosses the block threshold (default $1M) — institutional-sized flow.",
        "color": "#f0883e",
    },
    "repeat_call": {
        "label": "RC",
        "short": "Repeat calls",
        "long": "Three or more unusual call strikes on the same expiry — coordinated bullish positioning.",
        "color": "#f0c674",
    },
}

FLAG_KINDS = frozenset(FLAG_DEFINITIONS)


def _flag_counts(flags: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {k: 0 for k in FLAG_KINDS}
    for f in flags:
        kind = str(f.get("kind", ""))
        if kind in counts:
            counts[kind] += 1
    return counts


def score_breakdown(report: Mapping[str, Any]) -> str:
    """Format score formula from flag counts on a report dict or TickerReport-like object."""
    flags = report.get("flags") or []
    counts = _flag_counts(flags)
    hu, bp, u, rc = counts["high_unusual"], counts["block_premium"], counts["unusual"], counts["repeat_call"]
    parts: list[str] = []
    if hu:
        parts.append(f"{hu} HU × 5")
    if bp:
        parts.append(f"{bp} B × 3")
    if u:
        parts.append(f"{u} U × 2")
    if rc:
        parts.append(f"{rc} RC × 10")
    if not parts:
        return "No flagged activity"
    total = report.get("unusual_score", 5 * hu + 3 * bp + 2 * u + 10 * rc)
    return " + ".join(parts) + f" = {total}"


def interpretive_banner(report: Mapping[str, Any]) -> str | None:
    """Neutral educational copy from flag patterns. Returns None if nothing notable."""
    flags = report.get("flags") or []
    kinds = {str(f.get("kind", "")) for f in flags}
    messages: list[str] = []

    if "repeat_call" in kinds:
        messages.append(
            "Multiple call strikes are seeing unusual activity — often interpreted as "
            "bullish positioning by large traders."
        )

    pc_vol = float(report.get("pc_vol_ratio") or 0)
    if pc_vol > 1.0:
        messages.append(
            "Put volume exceeds call volume — often interpreted as hedging or bearish positioning."
        )
    elif pc_vol < 0.7 and pc_vol > 0:
        messages.append(
            "Call volume dominates put volume — often interpreted as bullish or speculative interest."
        )

    bp_count = sum(1 for f in flags if f.get("kind") == "block_premium")
    hu_count = sum(1 for f in flags if f.get("kind") == "high_unusual")
    if bp_count >= 2:
        messages.append(
            "Several large-premium trades flagged — institutional-sized flow."
        )
    elif hu_count >= 2:
        messages.append(
            "Multiple short-dated OTM contracts with heavy volume — near-term directional bets."
        )

    if not messages:
        return None
    return " ".join(messages)


def fmt_strike(strike: float) -> str:
    """Format strike as $210 or $210.50."""
    if abs(strike - round(strike)) < 1e-6:
        return f"${strike:.0f}"
    return f"${strike:.2f}"


def fmt_premium(value: float) -> str:
    """Compact premium: $2.27M for large values."""
    if value >= 1_000_000:
        return f"${value / 1_000_000:.2f}M"
    if value >= 1_000:
        return f"${value / 1_000:.1f}K"
    return f"${value:,.0f}"


def contract_signal_weight(flags: Sequence[Mapping[str, Any]]) -> tuple[int, int, int]:
    """Sort key: (HU count, B count, U count) descending."""
    hu = sum(1 for f in flags if f.get("kind") == "high_unusual")
    bp = sum(1 for f in flags if f.get("kind") == "block_premium")
    u = sum(1 for f in flags if f.get("kind") == "unusual")
    return (hu, bp, u)
