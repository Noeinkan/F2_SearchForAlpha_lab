"""Flow Scanner ticker-card summary: score, call/put mix, ranges and top strikes.

Plain-language versions of what the card used to print as codes and run-on text
("27 HU × 5", "Top calls: $400 (26,348), ..."). Pure render functions.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from dash import html

from lib.dash.flow_glossary import FLAG_DEFINITIONS, TERM_DEFINITIONS, score_breakdown, score_parts

_LABEL_TO_KIND = {fd["label"]: kind for kind, fd in FLAG_DEFINITIONS.items()}


def render_score_row(report: Mapping[str, Any]) -> html.Div | None:
    """``Score 882 = 27 high unusual ×5 + 65 block premium ×3 + …`` with hover definitions."""
    parts = score_parts(report)
    if not parts:
        return None
    total = report.get("unusual_score", sum(n * w for _, n, w, _ in parts))
    children: list[Any] = [
        html.Span("Score", className="sfa-flow-score-label"),
        html.Strong(str(total), className="sfa-flow-score-total", title=score_breakdown(report)),
        html.Span("=", className="sfa-flow-score-op"),
    ]
    for i, (label, n, weight, color) in enumerate(parts):
        if i:
            children.append(html.Span("+", className="sfa-flow-score-op"))
        fd = FLAG_DEFINITIONS[_LABEL_TO_KIND[label]]
        children.append(html.Span(
            [
                html.Strong(f"{n:,}"),
                f" {fd['short'].lower()} ",
                html.Span(f"×{weight}", className="sfa-flow-score-weight"),
            ],
            className="sfa-flow-score-chip",
            title=f"{fd['long']} (code {label}; each one adds {weight} points)",
            style={"--chip": color},
        ))
    return html.Div(children, className="sfa-flow-score-chips")


def render_flow_mix(report: Mapping[str, Any]) -> html.Div:
    """Call/put volume split, with the put/call ratio inside the same line."""
    call_pct = float(report.get("call_pct") or 0)
    put_pct = float(report.get("put_pct") or 0)
    ratio = float(report.get("pc_vol_ratio") or 0)
    return html.Div(
        [
            html.Span(f"Calls {call_pct:.1f}%", className="sfa-flow-mix-calls"),
            html.Div(
                html.Div(className="sfa-flow-mix-fill", style={"width": f"{call_pct:.1f}%"}),
                className="sfa-flow-mix-bar",
                title=f"Share of today's option volume: calls {call_pct:.1f}%, puts {put_pct:.1f}%",
            ),
            html.Span(f"Puts {put_pct:.1f}%", className="sfa-flow-mix-puts"),
            html.Span(
                f"P/C {ratio:.2f}",
                className="sfa-flow-mix-ratio",
                title=TERM_DEFINITIONS["pc_vol"],
            ),
        ],
        className="sfa-flow-mix",
    )


def _range_item(label: str, low: float, high: float, spot: float, tip: str) -> html.Span | None:
    if high <= 0 or high <= low:
        return None
    pos = max(0.0, min(100.0, (spot - low) / (high - low) * 100)) if spot > 0 else None
    track: list[Any] = []
    if pos is not None:
        track.append(html.Span(className="sfa-flow-range-dot", style={"left": f"{pos:.1f}%"}))
    return html.Span(
        [
            html.Span(label, className="sfa-flow-range-label"),
            html.Span(f"{low:,.2f}", className="sfa-flow-range-end"),
            html.Span(track, className="sfa-flow-range-track"),
            html.Span(f"{high:,.2f}", className="sfa-flow-range-end"),
        ],
        className="sfa-flow-range",
        title=f"{tip}. The dot is the current price.",
    )


def render_ranges(report: Mapping[str, Any]) -> html.Div | None:
    """Today's range and the 52-week range, each with the price marked on it."""
    spot = float(report.get("spot") or 0)
    items = [
        _range_item("Day", float(report.get("day_low") or 0), float(report.get("day_high") or 0), spot,
                    "Today's trading range"),
        _range_item("52-week", float(report.get("wk52_low") or 0), float(report.get("wk52_high") or 0), spot,
                    "52-week low and high"),
    ]
    items = [i for i in items if i is not None]
    return html.Div(items, className="sfa-flow-ranges") if items else None


def _by_strike(pairs: Sequence[Any], limit: int) -> list[tuple[float, int]]:
    """Sum volume per strike: the scanner lists one entry per (strike, expiry)."""
    totals: dict[float, int] = {}
    for pair in pairs:
        try:
            strike, vol = float(pair[0]), int(pair[1])
        except (TypeError, ValueError, IndexError):
            continue
        totals[strike] = totals.get(strike, 0) + vol
    return sorted(totals.items(), key=lambda kv: kv[1], reverse=True)[:limit]


def _strike_rows(clean: Sequence[tuple[float, int]], spot: float, cp: str) -> list[Any]:
    rows: list[Any] = []
    top = max((v for _, v in clean), default=0) or 1
    for strike, vol in clean:
        if spot > 0:
            dist = (strike - spot) / spot * 100
            otm = strike > spot if cp == "C" else strike < spot
            where = f"{dist:+.1f}% · {'OTM' if otm else 'ITM'}"
        else:
            where = ""
        rows.append(html.Tr([
            html.Td(f"${strike:,.0f}" if strike == int(strike) else f"${strike:,.2f}", className="sfa-flow-top-strike"),
            html.Td(where, className="sfa-flow-top-where"),
            html.Td(
                html.Span(className="sfa-flow-top-bar", style={"width": f"{vol / top * 100:.0f}%"}),
                className="sfa-flow-top-barcell",
            ),
            html.Td(f"{vol:,}", className="sfa-flow-top-vol"),
        ]))
    return rows


def render_top_strikes(report: Mapping[str, Any], *, limit: int = 5) -> html.Div | None:
    """Two small tables: most-traded call and put strikes, with distance from spot."""
    spot = float(report.get("spot") or 0)
    sides = []
    for cp, key, title in (("C", "top_call_strikes", "Most-traded calls"), ("P", "top_put_strikes", "Most-traded puts")):
        rows = _strike_rows(_by_strike(report.get(key) or [], limit), spot, cp)
        if not rows:
            continue
        sides.append(html.Div(
            [
                html.Div(title, className="sfa-flow-top-title"),
                html.Table(
                    [
                        html.Thead(html.Tr([
                            html.Th("Strike"),
                            html.Th("vs spot", title="Distance of the strike from the current price"),
                            html.Th(""),
                            html.Th("Volume", title=TERM_DEFINITIONS["vol"]),
                        ])),
                        html.Tbody(rows),
                    ],
                    className="sfa-flow-top-table",
                ),
            ],
            className=f"sfa-flow-top-side sfa-flow-top-{'calls' if cp == 'C' else 'puts'}",
        ))
    return html.Div(sides, className="sfa-flow-top-strikes") if sides else None
