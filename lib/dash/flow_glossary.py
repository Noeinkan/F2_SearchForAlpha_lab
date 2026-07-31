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
    "signal": "Plain-language read of what this contract's flow may indicate — educational only.",
    "flags": "Activity flags: U = unusual volume, HU = high unusual OTM weekly, B = block premium, RC = repeat calls.",
}

COLUMN_HEADERS: dict[str, str] = {
    "strike": TERM_DEFINITIONS["strike"],
    "type": TERM_DEFINITIONS["type"],
    "last": TERM_DEFINITIONS["last"],
    "bid": TERM_DEFINITIONS["bid"],
    "ask": TERM_DEFINITIONS["ask"],
    "vol": TERM_DEFINITIONS["vol"],
    "oi": TERM_DEFINITIONS["oi"],
    "iv": TERM_DEFINITIONS["iv"],
    "premium": TERM_DEFINITIONS["premium"],
    "expiry": TERM_DEFINITIONS["expiry"],
    "flags": TERM_DEFINITIONS["flags"],
    "signal": TERM_DEFINITIONS["signal"],
}

INSIGHT_CATEGORY_COLORS: dict[str, str] = {
    "Bullish": "#3fb950",
    "Bearish": "#f85149",
    "Institutional": "#f0883e",
    "Speculative": "#58a6ff",
    "Neutral": "#8b949e",
}

SENTIMENT_COLORS: dict[str, str] = {
    "Bullish": "#3fb950",
    "Bearish": "#f85149",
    "Mixed": "#f0c674",
    "Neutral": "#8b949e",
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

# Score weights used by unusual_score and the visual score chip row.
SCORE_WEIGHTS: dict[str, int] = {
    "high_unusual": 5,
    "block_premium": 3,
    "unusual": 2,
    "repeat_call": 10,
}

# Order shown in score chips / LEARN copy.
_SCORE_KIND_ORDER = ("high_unusual", "block_premium", "unusual", "repeat_call")

LEARN_SECTIONS: list[dict[str, str]] = [
    {
        "title": "Calls vs puts",
        "body": (
            "A call (C) is the right to buy 100 shares at the strike price. "
            "A put (P) is the right to sell 100 shares at the strike. "
            "Heavy call flow is often read as bullish interest; heavy put flow as hedging or bearish interest. "
            "Neither is a guaranteed forecast."
        ),
    },
    {
        "title": "Strike, ITM / OTM, and weeklies",
        "body": (
            "The strike is the exercise price. Relative to today's stock price (spot): "
            "in-the-money (ITM) options already have intrinsic value; out-of-the-money (OTM) do not. "
            "For calls, strikes below spot are ITM; for puts, strikes above spot are ITM. "
            "Weekly contracts expire within about 7 days and often reflect near-term bets."
        ),
    },
    {
        "title": "Volume vs open interest",
        "body": (
            "Volume is contracts traded today. Open interest (OI) is contracts still open from prior days. "
            "When volume exceeds OI, many of today's trades are likely new positions — that is the Unusual (U) flag. "
            "High-unusual (HU) marks large OTM weekly volume that stands out even more."
        ),
    },
    {
        "title": "Premium and block trades",
        "body": (
            "Premium ≈ volume × last price × 100 (dollars paid for today's volume on that contract). "
            "A Block (B) flag means premium crossed the large-trade threshold (default $1M) — "
            "often institutional-sized flow. Color heat on the Premium column scales with size."
        ),
    },
    {
        "title": "How the unusual score is built",
        "body": (
            "Each ticker gets a composite score: 5×HU + 3×B + 2×U + 10×RC. "
            "RC (repeat calls) means three or more unusual call strikes on the same expiry. "
            "Higher scores mean more flagged activity, not a buy or sell recommendation. "
            "Educational/research use only — not financial advice."
        ),
    },
]


def _flag_counts(flags: Sequence[Mapping[str, Any]]) -> dict[str, int]:
    counts = {k: 0 for k in FLAG_KINDS}
    for f in flags:
        kind = str(f.get("kind", ""))
        if kind in counts:
            counts[kind] += 1
    return counts


def score_parts(report: Mapping[str, Any]) -> list[tuple[str, int, int, str]]:
    """Return [(flag_label, count, weight, color), ...] for non-zero score contributors."""
    counts = _flag_counts(report.get("flags") or [])
    parts: list[tuple[str, int, int, str]] = []
    for kind in _SCORE_KIND_ORDER:
        n = counts.get(kind, 0)
        if n:
            fd = FLAG_DEFINITIONS[kind]
            parts.append((fd["label"], n, SCORE_WEIGHTS[kind], fd["color"]))
    return parts


def score_breakdown(report: Mapping[str, Any]) -> str:
    """Format score formula from flag counts on a report dict or TickerReport-like object."""
    parts = score_parts(report)
    if not parts:
        return "No flagged activity"
    pieces = [f"{n} {label} × {w}" for label, n, w, _ in parts]
    total = report.get(
        "unusual_score",
        sum(n * w for _, n, w, _ in parts),
    )
    return " + ".join(pieces) + f" = {total}"


def interpretive_insights(report: Mapping[str, Any]) -> list[tuple[str, str]]:
    """Categorized educational insights from flag patterns and volume skew."""
    flags = report.get("flags") or []
    kinds = {str(f.get("kind", "")) for f in flags}
    insights: list[tuple[str, str]] = []

    if "repeat_call" in kinds:
        insights.append((
            "Bullish",
            "Multiple call strikes are seeing unusual activity — often interpreted as "
            "bullish positioning by large traders.",
        ))

    pc_vol = float(report.get("pc_vol_ratio") or 0)
    if pc_vol > 1.0:
        insights.append((
            "Bearish",
            "Put volume exceeds call volume — often interpreted as hedging or bearish positioning.",
        ))
    elif pc_vol < 0.7 and pc_vol > 0:
        insights.append((
            "Bullish",
            "Call volume dominates put volume — often interpreted as bullish or speculative interest.",
        ))

    bp_count = sum(1 for f in flags if f.get("kind") == "block_premium")
    hu_count = sum(1 for f in flags if f.get("kind") == "high_unusual")
    if bp_count >= 2:
        insights.append((
            "Institutional",
            "Several large-premium trades flagged — institutional-sized flow.",
        ))
    elif hu_count >= 2:
        insights.append((
            "Speculative",
            "Multiple short-dated OTM contracts with heavy volume — near-term directional bets.",
        ))

    if not insights:
        score = int(report.get("unusual_score") or 0)
        if score <= 0:
            insights.append((
                "Neutral",
                "No unusual activity flags detected — flow appears within normal ranges.",
            ))

    return insights


def interpretive_banner(report: Mapping[str, Any]) -> str | None:
    """Neutral educational copy from flag patterns. Returns None if nothing notable."""
    insights = interpretive_insights(report)
    neutral_only = len(insights) == 1 and insights[0][0] == "Neutral"
    if not insights or neutral_only:
        return None
    return " ".join(msg for _, msg in insights)


def ticker_sentiment(report: Mapping[str, Any]) -> tuple[str, str, str]:
    """Returns (label, color, reason). label in Bullish/Bearish/Neutral/Mixed."""
    flags = report.get("flags") or []
    kinds = {str(f.get("kind", "")) for f in flags}
    pc_vol = float(report.get("pc_vol_ratio") or 0)
    call_pct = float(report.get("call_pct") or 50)

    bullish = 0
    bearish = 0
    reasons: list[str] = []

    if "repeat_call" in kinds:
        bullish += 2
        reasons.append("repeat unusual call strikes")
    if pc_vol < 0.7 and pc_vol > 0:
        bullish += 1
        reasons.append("call-heavy volume")
    if call_pct > 65:
        bullish += 1
    if pc_vol > 1.0:
        bearish += 2
        reasons.append("put-heavy volume")
    if call_pct < 35:
        bearish += 1

    bp_count = sum(1 for f in flags if f.get("kind") == "block_premium")
    if bp_count >= 2 and bullish >= bearish:
        reasons.append("institutional call flow")

    if bullish >= 2 and bearish >= 2:
        label = "Mixed"
        reason = "Conflicting bullish and bearish flow signals"
    elif bullish > bearish:
        label = "Bullish"
        reason = "Driven by " + (", ".join(reasons) if reasons else "unusual call activity")
    elif bearish > bullish:
        label = "Bearish"
        reason = "Driven by " + (", ".join(reasons) if reasons else "put-heavy flow")
    else:
        label = "Neutral"
        reason = "No strong directional skew in today's flow"

    return label, SENTIMENT_COLORS[label], reason


def contract_signal(
    contract: Mapping[str, Any],
    flags: Sequence[Mapping[str, Any]] | None = None,
) -> tuple[str, str]:
    """Returns (chip_label, color) for a single contract row."""
    flags = flags if flags is not None else (contract.get("flags") or [])
    kinds = {str(f.get("kind", "")) for f in flags}
    cp = str(contract.get("cp", ""))
    otm = bool(contract.get("is_otm", False))
    weekly = bool(contract.get("is_weekly", False))

    if "block_premium" in kinds:
        return "Block", FLAG_DEFINITIONS["block_premium"]["color"]
    if "high_unusual" in kinds:
        if cp == "C":
            return "Speculative", FLAG_DEFINITIONS["high_unusual"]["color"]
        return "Hedge", INSIGHT_CATEGORY_COLORS["Bearish"]
    if "unusual" in kinds:
        if cp == "C":
            return "Bullish bet", INSIGHT_CATEGORY_COLORS["Bullish"]
        return "Hedge", INSIGHT_CATEGORY_COLORS["Bearish"]
    if otm and weekly and cp == "C":
        return "Speculative", FLAG_DEFINITIONS["high_unusual"]["color"]
    if cp == "P" and otm:
        return "Hedge", INSIGHT_CATEGORY_COLORS["Bearish"]
    return "Flow", INSIGHT_CATEGORY_COLORS["Neutral"]


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
