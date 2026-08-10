"""Robinhood-style option chain panel for the Flow Scanner."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from dash import dcc, html

from lib.dash.dash_config import FONT_FAMILY, FONT_SIZES
from lib.dash.flow_inventory import nearest_expiry

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


def _side_flagged(side: Mapping[str, Any] | None) -> bool:
    return bool(side and side.get("flagged"))


def _row_is_flagged(row: Mapping[str, Any]) -> bool:
    call = row.get("call") if isinstance(row.get("call"), Mapping) else None
    put = row.get("put") if isinstance(row.get("put"), Mapping) else None
    return _side_flagged(call) or _side_flagged(put)


def filter_chain_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    flagged_only: bool = False,
) -> list[dict]:
    """Optionally keep only strikes with a flagged call or put side."""
    out = [dict(r) for r in rows]
    if not flagged_only:
        return out
    return [r for r in out if _row_is_flagged(r)]


def _side_cells(side: Mapping[str, Any] | None, *, cp: str) -> list[Any]:
    if not side:
        return [html.Td("—", className="sfa-flow-chain-empty") for _ in range(5)]

    flagged = _side_flagged(side)
    values = [
        _fmt_int(side.get("volume")),
        _fmt_int(side.get("open_interest")),
        _fmt_price(side.get("bid")),
        _fmt_price(side.get("ask")),
        _fmt_iv(side.get("iv")),
    ]
    keys = ("vol", "oi", "bid", "ask", "iv")
    cells: list[Any] = []
    for key, text in zip(keys, values, strict=True):
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


def _spot_divider_index(rows: Sequence[Mapping[str, Any]], spot: float) -> int | None:
    """Insert spot divider after the last strike strictly below spot."""
    if not rows or spot <= 0:
        return None
    insert_at: int | None = None
    for i, row in enumerate(rows):
        try:
            strike = float(row.get("strike") or 0)
        except (TypeError, ValueError):
            continue
        if strike < spot:
            insert_at = i + 1
        else:
            break
    return insert_at


def build_chain_table(
    rows: Sequence[Mapping[str, Any]],
    spot: float,
    theme: dict,
) -> html.Table:
    """Build the call | strike | put HTML table for one expiry."""
    _ = theme
    atm_i = atm_strike_index(rows, spot)
    divider_at = _spot_divider_index(rows, spot)

    header = html.Thead(
        html.Tr(
            [
                html.Th("Vol", className="sfa-flow-chain-call"),
                html.Th("OI", className="sfa-flow-chain-call"),
                html.Th("Bid", className="sfa-flow-chain-call"),
                html.Th("Ask", className="sfa-flow-chain-call"),
                html.Th("IV%", className="sfa-flow-chain-call"),
                html.Th("Strike", className="sfa-flow-chain-strike-h"),
                html.Th("Bid", className="sfa-flow-chain-put"),
                html.Th("Ask", className="sfa-flow-chain-put"),
                html.Th("IV%", className="sfa-flow-chain-put"),
                html.Th("OI", className="sfa-flow-chain-put"),
                html.Th("Vol", className="sfa-flow-chain-put"),
            ]
        )
    )

    body_rows: list[Any] = []

    def _append_spot_divider() -> None:
        body_rows.append(
            html.Tr(
                [
                    html.Td(
                        f"Spot {spot:,.2f}",
                        colSpan=11,
                        className="sfa-flow-chain-spot-divider-cell",
                    )
                ],
                className="sfa-flow-chain-spot-divider",
            )
        )

    for i, row in enumerate(rows):
        if divider_at is not None and i == divider_at:
            _append_spot_divider()

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
        if _row_is_flagged(row):
            row_classes.append("sfa-flow-chain-row-flagged")

        strike_label = f"{strike:,.2f}".rstrip("0").rstrip(".")
        strike_cell = html.Td(strike_label, className="sfa-flow-chain-strike")

        # Puts mirror call column order: Bid Ask IV OI Vol
        put_cells: list[Any]
        if not put:
            put_cells = [html.Td("—", className="sfa-flow-chain-empty") for _ in range(5)]
        else:
            flagged = _side_flagged(put)
            put_vals = [
                (_fmt_price(put.get("bid")), "bid"),
                (_fmt_price(put.get("ask")), "ask"),
                (_fmt_iv(put.get("iv")), "iv"),
                (_fmt_int(put.get("open_interest")), "oi"),
                (_fmt_int(put.get("volume")), "vol"),
            ]
            put_cells = []
            for text, key in put_vals:
                classes = f"sfa-flow-chain-p sfa-flow-chain-{key}"
                if flagged:
                    classes += " sfa-flow-chain-flagged"
                put_cells.append(html.Td(text, className=classes))

        body_rows.append(
            html.Tr(
                [
                    *_side_cells(call, cp="C"),
                    strike_cell,
                    *put_cells,
                ],
                className=" ".join(row_classes),
            )
        )

    if divider_at is not None and divider_at >= len(rows):
        _append_spot_divider()

    return html.Table(
        [header, html.Tbody(body_rows)],
        className="sfa-flow-chain-table",
    )


def table_from_report(
    report: Mapping[str, Any],
    *,
    expiry: str | None,
    theme: dict,
    flagged_only: bool = False,
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
    rows = filter_chain_rows(rows, flagged_only=flagged_only)
    spot = float(report.get("spot") or 0)

    if not rows:
        msg = (
            f"No flagged strikes for expiry {exp or '—'}."
            if flagged_only
            else f"No chain rows for expiry {exp or '—'}."
        )
        return [html.Div(msg, className="sfa-flow-section-empty")]

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
    """Expiry + filter controls and Robinhood-style chain grid for one ticker."""
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
                    html.Div(
                        [
                            dcc.Dropdown(
                                id={"type": "flow-chain-expiry", "index": ticker},
                                options=expiry_options,
                                value=expiry,
                                clearable=False,
                                searchable=False,
                                className="sfa-flow-chain-expiry",
                                style={"minWidth": "140px", "fontSize": "12px"},
                            ),
                            dcc.RadioItems(
                                id={"type": "flow-chain-filter", "index": ticker},
                                options=[
                                    {"label": "All strikes", "value": "all"},
                                    {"label": "Flagged only", "value": "flagged"},
                                ],
                                value="all",
                                inline=True,
                                className="sfa-flow-chain-filter",
                                style={
                                    "fontFamily": FONT_FAMILY,
                                    "fontSize": FONT_SIZES["xs"],
                                    "color": theme["text_secondary"],
                                },
                                inputStyle={"marginRight": "4px"},
                                labelStyle={"marginRight": "12px", "cursor": "pointer"},
                            ),
                        ],
                        className="sfa-flow-chain-controls",
                    ),
                ],
                className="sfa-flow-chain-header",
            ),
            html.P(
                "Calls left · strike center · puts right. Spot divider marks the money. "
                "Flagged unusual sides are highlighted. Data from last RESCAN (not live).",
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
                table_from_report(report, expiry=expiry, theme=theme, flagged_only=False),
                id={"type": "flow-chain-body", "index": ticker},
                className="sfa-flow-chain-table-wrap",
            ),
        ],
        className="sfa-flow-chain",
    )
