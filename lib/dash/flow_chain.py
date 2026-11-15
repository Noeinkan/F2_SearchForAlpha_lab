"""Robinhood-style option chain panel for the Flow Scanner."""

from __future__ import annotations

from datetime import date
from typing import Any, Mapping, Sequence

from dash import dcc, html

from lib.dash.dash_config import FONT_FAMILY, FONT_SIZES
from lib.dash.flow_glossary import FLAG_DEFINITIONS
from lib.dash.flow_inventory import nearest_expiry
from lib.dash.flow_dates import display_date

# Default expiry skips the last few days: a chain about to expire quotes
# near-meaningless IVs (2% on one side, 150% on the other) and almost no OTM size.
DEFAULT_MIN_DAYS_TO_EXPIRY = 7
# "Near spot" view: strikes either side of the at-the-money row.
NEAR_SPOT_STRIKES = 10

CHAIN_VIEWS = ("near", "all", "flagged")
DEFAULT_CHAIN_VIEW = "near"


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


def _side_active(side: Any) -> bool:
    """A side that traded today or carries open interest."""
    if not isinstance(side, Mapping):
        return False
    for key in ("volume", "open_interest"):
        try:
            if int(side.get(key) or 0) > 0:
                return True
        except (TypeError, ValueError):
            continue
    return False


def _row_is_active(row: Mapping[str, Any]) -> bool:
    return _side_active(row.get("call")) or _side_active(row.get("put")) or _row_is_flagged(row)


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


def select_chain_rows(
    rows: Sequence[Mapping[str, Any]],
    *,
    view: str,
    spot: float,
    near: int = NEAR_SPOT_STRIKES,
) -> list[dict]:
    """Rows for one chain view.

    ``flagged`` keeps flagged strikes; ``all`` drops strikes with no volume and no
    open interest on either side (a row of dashes); ``near`` is ``all`` cut to
    ``near`` strikes either side of the one closest to spot.
    """
    if view == "flagged":
        return filter_chain_rows(rows, flagged_only=True)
    active = [dict(r) for r in rows if _row_is_active(r)]
    if view != "near" or not active:
        return active
    atm = atm_strike_index(active, spot)
    if atm is None:
        return active
    return active[max(0, atm - near): atm + near + 1]


def _days_to(expiry: str, today: date) -> int | None:
    try:
        return (date.fromisoformat(str(expiry)[:10]) - today).days
    except ValueError:
        return None


def default_chain_expiry(
    chains: Mapping[str, Any] | None,
    *,
    today: date | None = None,
    min_days: int = DEFAULT_MIN_DAYS_TO_EXPIRY,
) -> str | None:
    """First expiry at least ``min_days`` out; else the furthest one listed.

    The scanner often fetches only the next week's expiries, so "furthest" is
    the least distorted of what is there.
    """
    if not chains:
        return None
    today = today or date.today()
    keys = sorted(str(k) for k in chains.keys())
    for key in keys:
        days = _days_to(key, today)
        if days is not None and days >= min_days:
            return key
    return keys[-1] if keys else nearest_expiry(chains)


def expiry_option_label(expiry: str, rows: Sequence[Mapping[str, Any]], *, today: date | None = None) -> str:
    """Dropdown label: ``2026-11-21 · 6d · 4 flagged``."""
    parts = [display_date(expiry)]
    days = _days_to(expiry, today or date.today())
    if days is not None:
        parts.append("expired" if days < 0 else f"{days}d")
    flagged = sum(1 for r in rows if _row_is_flagged(r))
    if flagged:
        parts.append(f"{flagged} flagged")
    return " · ".join(parts)


def flag_reasons(report: Mapping[str, Any], expiry: str | None) -> dict[tuple[float, str], str]:
    """``{(strike, 'C'|'P'): "why it was flagged"}`` for one expiry.

    The chain only carries a ``flagged`` boolean; the reasons live on the
    report's flagged ``contracts``, so they are joined here.
    """
    out: dict[tuple[float, str], str] = {}
    for contract in report.get("contracts") or []:
        if str(contract.get("expiry", ""))[:10] != str(expiry or "")[:10]:
            continue
        try:
            key = (float(contract.get("strike")), str(contract.get("cp", "")).upper())
        except (TypeError, ValueError):
            continue
        lines = []
        for flag in contract.get("flags") or []:
            fd = FLAG_DEFINITIONS.get(str(flag.get("kind", "")))
            name = fd["short"] if fd else str(flag.get("kind", "")).replace("_", " ")
            message = str(flag.get("message") or "").strip()
            lines.append(f"{name}: {message}" if message else name)
        if lines:
            out[key] = "\n".join(lines)
    return out


def _side_cells(side: Mapping[str, Any] | None, *, cp: str, strike: float, reason: str | None = None) -> list[Any]:
    if not side:
        return [html.Td("—", className="sfa-flow-chain-empty") for _ in range(5)]

    flagged = _side_flagged(side)
    values = {
        "vol": _fmt_int(side.get("volume")),
        "oi": _fmt_int(side.get("open_interest")),
        "bid": _fmt_price(side.get("bid")),
        "ask": _fmt_price(side.get("ask")),
        "iv": _fmt_iv(side.get("iv")),
    }
    # Puts mirror the call columns so the strike sits in the middle.
    keys = ("vol", "oi", "bid", "ask", "iv") if cp == "C" else ("bid", "ask", "iv", "oi", "vol")
    title = None
    if flagged:
        side_name = "Call" if cp == "C" else "Put"
        title = f"{side_name} flagged as unusual\n{reason}" if reason else f"{side_name} flagged as unusual"
    cells: list[Any] = []
    for key in keys:
        classes = f"sfa-flow-chain-{cp.lower()} sfa-flow-chain-{key}"
        if flagged:
            classes += " sfa-flow-chain-flagged"
        content: Any = values[key]
        if key in ("bid", "ask") and values[key] != "—" and strike > 0:
            try:
                multiplier = int(side.get("multiplier", 100))
            except (TypeError, ValueError):
                multiplier = 0
            if multiplier > 0:
                content = html.Button(
                    values[key], type="button",
                    className="sfa-flow-chain-price" + (" sfa-flow-chain-quote" if key == "ask" else ""),
                    title=f"Show quote details for this {'call' if cp == 'C' else 'put'}",
                    **{"data-cp": cp, "data-strike": str(strike),
                       "data-field": key, "data-premium": str(side.get("ask") or ""),
                       "data-bid": str(side.get("bid") or ""), "data-ask": str(side.get("ask") or ""),
                       "data-last": str(side.get("last") or ""),
                       "data-volume": str(side.get("volume") or 0),
                       "data-oi": str(side.get("open_interest") or 0),
                       "data-iv": str(side.get("iv") or ""),
                       "data-flagged": "true" if flagged else "false",
                       "data-reason": reason or "", "data-multiplier": str(multiplier)},
                )
        cells.append(html.Td(content, className=classes, title=title))
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
    *,
    reasons: Mapping[tuple[float, str], str] | None = None,
) -> html.Table:
    """Build the call | strike | put HTML table for one expiry."""
    _ = theme
    reasons = reasons or {}
    atm_i = atm_strike_index(rows, spot)
    divider_at = _spot_divider_index(rows, spot)

    header = html.Thead(
        html.Tr(
            [
                html.Th("Vol", className="sfa-flow-chain-call", title="Contracts traded today"),
                html.Th("OI", className="sfa-flow-chain-call", title="Open interest: contracts still open"),
                html.Th("Bid", className="sfa-flow-chain-call"),
                html.Th("Ask", className="sfa-flow-chain-call"),
                html.Th("IV%", className="sfa-flow-chain-call", title="Implied volatility"),
                html.Th("Strike", className="sfa-flow-chain-strike-h"),
                html.Th("Bid", className="sfa-flow-chain-put"),
                html.Th("Ask", className="sfa-flow-chain-put"),
                html.Th("IV%", className="sfa-flow-chain-put", title="Implied volatility"),
                html.Th("OI", className="sfa-flow-chain-put", title="Open interest: contracts still open"),
                html.Th("Vol", className="sfa-flow-chain-put", title="Contracts traded today"),
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
        strike_tip = None
        if spot > 0:
            dist = (strike - spot) / spot * 100
            strike_tip = f"{dist:+.1f}% from spot"
        strike_cell = html.Td(strike_label, className="sfa-flow-chain-strike", title=strike_tip)

        body_rows.append(
            html.Tr(
                [
                    *_side_cells(call, cp="C", strike=strike, reason=reasons.get((strike, "C"))),
                    strike_cell,
                    *_side_cells(put, cp="P", strike=strike, reason=reasons.get((strike, "P"))),
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


def _resolve_view(view: str | None, flagged_only: bool) -> str:
    if view in CHAIN_VIEWS:
        return str(view)
    return "flagged" if flagged_only else "all"


def table_from_report(
    report: Mapping[str, Any],
    *,
    expiry: str | None,
    theme: dict,
    flagged_only: bool = False,
    view: str | None = None,
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

    view = _resolve_view(view, flagged_only)
    exp = expiry or default_chain_expiry(chains)
    all_rows = list(chains.get(exp) or []) if exp else []
    spot = float(report.get("spot") or 0)
    rows = select_chain_rows(all_rows, view=view, spot=spot)

    if not rows:
        msg = (
            f"No flagged strikes for expiry {display_date(exp) if exp else '—'}."
            if view == "flagged"
            else f"No traded strikes for expiry {display_date(exp) if exp else '—'}."
        )
        return [html.Div(msg, className="sfa-flow-section-empty")]

    hidden = sum(1 for r in all_rows if _row_is_active(r)) - len(rows)
    children: list[Any] = [
        html.Div(
            [
                html.Span("Calls", className="sfa-flow-chain-side-label sfa-flow-chain-calls-label"),
                html.Span("Puts", className="sfa-flow-chain-side-label sfa-flow-chain-puts-label"),
            ],
            className="sfa-flow-chain-side-headers",
        ),
        html.Div(
            build_chain_table(rows, spot, theme, reasons=flag_reasons(report, exp)),
            className="sfa-flow-chain-scroll",
            **{"data-expiry": exp or ""},
        ),
        html.Div(
            [
                html.Div([
                    html.Span("EXPIRY PAYOFF", className="sfa-flow-chain-preview-eyebrow"),
                    html.Span("Select a call or put quote to preview one long contract.",
                              className="sfa-flow-chain-preview-prompt"),
                ], className="sfa-flow-chain-preview-empty"),
                html.Div([
                    html.Div([
                        html.Span("EXPIRY PAYOFF · 1 LONG CONTRACT", className="sfa-flow-chain-preview-eyebrow"),
                        html.Strong(className="sfa-flow-chain-preview-contract"),
                    ], className="sfa-flow-chain-preview-heading"),
                    html.Div([
                        html.Div([
                            html.Span("CONTRACT COST", className="sfa-flow-chain-preview-metric-label"),
                            html.Strong(className="sfa-flow-chain-preview-cost"),
                            html.Span(className="sfa-flow-chain-preview-cost-note"),
                        ], className="sfa-flow-chain-preview-metric"),
                        html.Div([
                            html.Span("EXPIRY BREAK-EVEN", className="sfa-flow-chain-preview-metric-label"),
                            html.Strong(className="sfa-flow-chain-preview-breakeven"),
                            html.Span("Underlying price · before fees", className="sfa-flow-chain-preview-metric-note"),
                        ], className="sfa-flow-chain-preview-metric sfa-flow-chain-preview-metric-be"),
                    ], className="sfa-flow-chain-preview-metrics"),
                    html.Div(className="sfa-flow-chain-preview-chart", **{"aria-hidden": "true"}),
                    html.Div([
                        html.Span(className="sfa-flow-chain-preview-premium"),
                        html.Span(className="sfa-flow-chain-preview-multiplier"),
                    ], className="sfa-flow-chain-preview-foot"),
                ], className="sfa-flow-chain-preview-values", hidden=True),
            ], className="sfa-flow-chain-preview", role="status", **{"aria-live": "polite"},
        ),
    ]
    if view == "near" and hidden > 0:
        children.append(
            html.Div(
                f"Showing {len(rows)} strikes around spot · {hidden} more under “All strikes”.",
                className="sfa-flow-chain-more",
            )
        )
    return children


def render_chain_legend() -> html.Div:
    """Key for the chain's shading, so nobody has to guess what purple means."""

    def _item(swatch: str, text: str, tip: str) -> html.Span:
        return html.Span(
            [html.Span(className=f"sfa-flow-key-swatch {swatch}"), text],
            className="sfa-flow-key-item",
            title=tip,
        )

    return html.Div(
        [
            _item("sfa-flow-key-call-itm", "ITM call", "In the money: strike below spot, the call has intrinsic value"),
            _item("sfa-flow-key-put-itm", "ITM put", "In the money: strike above spot, the put has intrinsic value"),
            _item("sfa-flow-key-atm", "Spot / ATM", "The strike closest to the current price"),
            _item(
                "sfa-flow-key-flagged",
                "Flagged unusual — hover for why",
                "Purple numbers: the scanner flagged this side. Hover a purple cell to read the reason.",
            ),
        ],
        className="sfa-flow-chain-key",
    )


def render_chain_panel(report: Mapping[str, Any], theme: dict, *, today: date | None = None) -> html.Div | None:
    """Expiry + view controls and Robinhood-style chain grid for one ticker."""
    chains = report.get("option_chains") or {}
    if not isinstance(chains, Mapping) or not chains:
        return None

    ticker = str(report.get("ticker") or "UNK").upper()
    expiry = default_chain_expiry(chains, today=today)
    if not expiry:
        return None

    expiry_options = [
        {"label": expiry_option_label(k, chains.get(k) or [], today=today), "value": k}
        for k in sorted(chains.keys())
    ]

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
                                style={"minWidth": "230px", "fontSize": "12px"},
                            ),
                            dcc.RadioItems(
                                id={"type": "flow-chain-filter", "index": ticker},
                                options=[
                                    {"label": "Near spot", "value": "near"},
                                    {"label": "All strikes", "value": "all"},
                                    {"label": "Flagged only", "value": "flagged"},
                                ],
                                value=DEFAULT_CHAIN_VIEW,
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
            render_chain_legend(),
            html.Div(
                table_from_report(report, expiry=expiry, theme=theme, view=DEFAULT_CHAIN_VIEW),
                id={"type": "flow-chain-body", "index": ticker},
                className="sfa-flow-chain-table-wrap",
            ),
            html.Details([
                html.Summary("Build a strategy · up to 4 options", className="sfa-flow-strategy-summary"),
                html.Div([
                    html.P("Add quotes from the chain, then choose Buy or Sell and how many contracts. All options must share one expiry.",
                           className="sfa-flow-strategy-help"),
                    html.Div("No options added yet.", className="sfa-flow-strategy-legs"),
                    html.Div(className="sfa-flow-strategy-message", role="status"),
                    html.Div(className="sfa-flow-strategy-results"),
                ], className="sfa-flow-strategy-body"),
            ], className="sfa-flow-strategy"),
        ],
        className="sfa-flow-chain",
        **{"data-ticker": ticker, "data-spot": str(report.get("spot") or "")},
    )
