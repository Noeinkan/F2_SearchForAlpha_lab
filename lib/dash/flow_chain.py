"""Robinhood-style option chain panel for the Flow Scanner detail pane."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from dash import dcc, html

from lib.dash.dash_config import FONT_FAMILY, FONT_SIZES
from lib.dash.flow_inventory import nearest_expiry

_SIDE_COLS = ("bid", "ask", "iv", "vol", "oi")


def _fmt_price(val: Any) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "—"
    if v <= 0:
        return "—"
    return f"{v:.2f}"


def _fmt_int(val: Any) -> str:
    try:
        return f"{int(val):,}"
    except (TypeError, ValueError):
        return "—"


def _fmt_iv(val: Any) -> str:
    try:
        v = float(val)
    except (TypeError, ValueError):
        return "—"
    if v <= 0:
        return "—"
    # Yahoo IV is usually a fraction (0.315 → 31.5%).
    pct = v * 100 if v <= 2 else v
    return f"{pct:.1f}"


def _side_cells(side: Mapping[str, Any] | None, *, cp: str, theme: dict) -> list[Any]:
    if not side:
        return [
            html.Td("—", className="sfa-flow-chain-empty") for _ in _SIDE_COLS
        ]

    flagged = bool(side.get("flagged"))
    values = [
        _fmt_price(side.get("bid")),
        _fmt_price(side.get("ask")),
        _fmt_iv(side.get("iv")),
        _fmt_int(side.get("volume")),
        _fmt_int(side.get("open_interest")),
    ]
    cells: list[Any] = []
    for key, text in zip(_SIDE_COLS, values, strict=True):
        classes = f"sfa-flow-chain-{cp.lower()} sfa-flow-chain-{key}"
        if flagged:
            classes += " sfa-flow-chain-flagged"
        cells.append(html.Td(text, className=classes))
    return cells


def atm_strike_index(rows: Sequence[Mapping[str, Any]], spot: float) -> int | None:
    """Index of the strike closest to spot, or None."""
    if not rows or spot <= 0:
        return None
    best_i = 0
    best_dist = float("inf")
    for i, row in enumerate(rows):
        try:
            strike = float(row.get("strike") or 0)
        except (TypeError, ValueError):
            continue
        dist = abs(strike - spot)
        if dist < best_dist:
            best_dist = dist
            best_i = i
    return best_i


def build_chain_table(
    rows: Sequence[Mapping[str, Any]],
    spot: float,
    theme: dict,
) -> html.Table:
    """Build the call | strike | put HTML table for one expiry."""
    atm_i = atm_strike_index(rows, spot)
    header = html.Thead(
        html.Tr(
            [
                html.Th("Bid", className="sfa-flow-chain-call"),
                html.Th("Ask", className="sfa-flow-chain-call"),
                html.Th("IV%", className="sfa-flow-chain-call"),
                html.Th("Vol", className="sfa-flow-chain-call"),
                html.Th("OI", className="sfa-flow-chain-call"),
                html.Th("Strike", className="sfa-flow-chain-strike-h"),
                html.Th("Bid", className="sfa-flow-chain-put"),
                html.Th("Ask", className="sfa-flow-chain-put"),
                html.Th("IV%", className="sfa-flow-chain-put"),
                html.Th("Vol", className="sfa-flow-chain-put"),
                html.Th("OI", className="sfa-flow-chain-put"),
            ]
        )
    )

    body_rows: list[Any] = []
    for i, row in enumerate(rows):
        try:
            strike = float(row.get("strike") or 0)
        except (TypeError, ValueError):
            continue
        call = row.get("call") if isinstance(row.get("call"), Mapping) else None
        put = row.get("put") if isinstance(row.get("put"), Mapping) else None

        call_itm = spot > 0 and strike < spot
        put_itm = spot > 0 and strike > spot
        is_atm = atm_i is not None and i == atm_i

        row_classes = ["sfa-flow-chain-row"]
        if is_atm:
            row_classes.append("sfa-flow-chain-atm")
        if call_itm:
            row_classes.append("sfa-flow-chain-call-itm")
        if put_itm:
            row_classes.append("sfa-flow-chain-put-itm")

        strike_label = f"{strike:,.2f}".rstrip("0").rstrip(".")
        if is_atm and spot > 0:
            strike_cell = html.Td(
                [
                    html.Span(strike_label, className="sfa-flow-chain-strike-val"),
                    html.Span(
                        f"spot {spot:,.2f}",
                        className="sfa-flow-chain-spot-tag",
                        title="Nearest strike to spot",
                    ),
                ],
                className="sfa-flow-chain-strike",
            )
        else:
            strike_cell = html.Td(strike_label, className="sfa-flow-chain-strike")

        body_rows.append(
            html.Tr(
                [
                    *_side_cells(call, cp="C", theme=theme),
                    strike_cell,
                    *_side_cells(put, cp="P", theme=theme),
                ],
                className=" ".join(row_classes),
            )
        )

    return html.Table(
        [header, html.Tbody(body_rows)],
        className="sfa-flow-chain-table",
    )


def table_from_report(
    report: Mapping[str, Any],
    *,
    expiry: str | None,
    theme: dict,
) -> list[Any]:
    """Return chain table children (side headers + scroll table) for one expiry."""
    chains = report.get("option_chains") or {}
    if not isinstance(chains, Mapping) or not chains:
        return [
            html.Div(
                "Rescan to load the option chain.",
                className="sfa-flow-section-empty",
            )
        ]

    exp = expiry or nearest_expiry(chains)
    rows = list(chains.get(exp) or []) if exp else []
    spot = float(report.get("spot") or 0)

    if not rows:
        return [
            html.Div(
                f"No chain rows for expiry {exp or '—'}.",
                className="sfa-flow-section-empty",
            )
        ]

    return [
        html.Div(
            [
                html.Span("Calls", className="sfa-flow-chain-side-label sfa-flow-chain-calls-label"),
                html.Span("Puts", className="sfa-flow-chain-side-label sfa-flow-chain-puts-label"),
            ],
            className="sfa-flow-chain-side-headers",
        ),
        html.Div(
            build_chain_table(rows, spot, theme),
            className="sfa-flow-chain-scroll",
        ),
    ]


def render_chain_panel(report: Mapping[str, Any], theme: dict) -> html.Div | None:
    """Expiry control + Robinhood-style chain grid for one ticker report."""
    chains = report.get("option_chains") or {}
    if not isinstance(chains, Mapping) or not chains:
        return None

    ticker = str(report.get("ticker") or "UNK").upper()
    expiry = nearest_expiry(chains)
    if not expiry:
        return None

    expiry_options = [{"label": k, "value": k} for k in sorted(chains.keys())]

    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        "Option chain",
                        style={
                            "fontFamily": FONT_FAMILY,
                            "fontSize": FONT_SIZES["sm"],
                            "fontWeight": 600,
                            "color": theme["text_primary"],
                        },
                    ),
                    dcc.Dropdown(
                        id={"type": "flow-chain-expiry", "index": ticker},
                        options=expiry_options,
                        value=expiry,
                        clearable=False,
                        searchable=False,
                        className="sfa-flow-chain-expiry",
                        style={"minWidth": "140px", "fontSize": "12px"},
                    ),
                ],
                className="sfa-flow-chain-header",
            ),
            html.P(
                "Calls left · strike center · puts right. Flagged unusual sides are highlighted. "
                "Data from last RESCAN (not live).",
                className="sfa-flow-chain-caption",
                style={
                    "fontFamily": FONT_FAMILY,
                    "fontSize": FONT_SIZES["xs"],
                    "color": theme["text_tertiary"],
                    "margin": "0 0 8px",
                    "lineHeight": 1.4,
                },
            ),
            html.Div(
                table_from_report(report, expiry=expiry, theme=theme),
                id={"type": "flow-chain-body", "index": ticker},
                className="sfa-flow-chain-table-wrap",
            ),
        ],
        className="sfa-flow-chain",
    )
