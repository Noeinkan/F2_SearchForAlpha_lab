"""Pure render functions for the in-app Flow Scanner (native Dash components)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from dash import dash_table, html

from lib.dash.dash_config import FONT_FAMILY, FONT_SIZES
from lib.dash.flow_glossary import (
    COLUMN_HEADERS,
    DISCLAIMER,
    FLAG_DEFINITIONS,
    INSIGHT_CATEGORY_COLORS,
    LEARN_SECTIONS,
    TERM_DEFINITIONS,
    contract_signal,
    contract_signal_weight,
    fmt_premium,
    fmt_strike,
    interpretive_insights,
    score_breakdown,
    score_parts,
    ticker_sentiment,
)

_TABLE_COLUMNS = [
    ("Strike", "strike"),
    ("Type", "type"),
    ("Last", "last"),
    ("Bid", "bid"),
    ("Ask", "ask"),
    ("Vol", "vol"),
    ("OI", "oi"),
    ("IV", "iv"),
    ("Premium", "premium"),
    ("Expiry", "expiry"),
    ("Flags", "flags"),
    ("Signal", "signal"),
]

_HIDDEN_COLUMNS = [
    "premium_raw",
    "iv_raw",
    "vol_raw",
    "oi_raw",
    "flag_kinds",
    "is_otm_raw",
    "is_weekly_raw",
    "signal_color",
]


def _kpi_span(label: str, value: str, tip: str, theme: dict) -> html.Span:
    return html.Span(
        [label, " ", html.Strong(value)],
        title=tip,
        style={
            "fontFamily": FONT_FAMILY,
            "fontSize": FONT_SIZES["xs"],
            "color": theme["text_secondary"],
            "cursor": "help",
        },
    )


def _panel_style(theme: dict) -> dict[str, Any]:
    """Shared card chrome for every collapsible flow panel."""
    return {
        "backgroundColor": theme["bg_tertiary"],
        "border": f'1px solid {theme["border_primary"]}',
        "borderRadius": "8px",
        "padding": "10px 14px",
        "marginBottom": "12px",
    }


def _panel_summary_style(theme: dict) -> dict[str, Any]:
    """Summary row of a collapsible panel (the ▸/▾ marker comes from CSS)."""
    return {
        "display": "flex",
        "alignItems": "center",
        "flexWrap": "wrap",
        "gap": "6px",
        "cursor": "pointer",
        "fontWeight": "600",
        "color": theme["text_primary"],
        "fontFamily": FONT_FAMILY,
        "fontSize": FONT_SIZES["sm"],
    }


def _table_cell_style(theme: dict) -> dict[str, Any]:
    return {
        "backgroundColor": theme["bg_primary"],
        "color": theme["text_primary"],
        "fontFamily": "IBM Plex Mono, monospace",
        "fontSize": FONT_SIZES["xs"],
        "padding": "4px 8px",
        "border": f'1px solid {theme["border_primary"]}',
        "textAlign": "right",
    }


def _table_header_style(theme: dict) -> dict[str, Any]:
    return {
        "backgroundColor": theme["table_header_bg"],
        "color": theme["text_secondary"],
        "fontWeight": "600",
        "fontSize": FONT_SIZES["xs"],
        "border": f'1px solid {theme["border_primary"]}',
        "textAlign": "right",
        "cursor": "help",
    }


def _format_contract_row(contract: Mapping[str, Any]) -> dict[str, Any]:
    strike = fmt_strike(float(contract.get("strike", 0)))
    otm = bool(contract.get("is_otm", False))
    strike_disp = f"{strike} {'OTM' if otm else 'ITM'}"
    cp = str(contract.get("cp", ""))
    expiry = str(contract.get("expiry", ""))
    weekly = bool(contract.get("is_weekly", False))
    if weekly:
        expiry = f"{expiry} weekly"

    flags = contract.get("flags") or []
    flag_parts = []
    flag_kinds: list[str] = []
    for f in flags:
        kind = str(f.get("kind", ""))
        fd = FLAG_DEFINITIONS.get(kind)
        if fd:
            flag_parts.append(fd["label"])
            flag_kinds.append(fd["label"])
    flags_disp = " ".join(flag_parts)

    signal_label, signal_color = contract_signal(contract, flags)
    vol = int(contract.get("volume", 0))
    oi = int(contract.get("open_interest", 0))
    premium = float(contract.get("premium", 0))
    iv = float(contract.get("iv", 0))

    return {
        "strike": strike_disp,
        "type": cp,
        "last": f'{float(contract.get("last", 0)):.2f}',
        "bid": f'{float(contract.get("bid", 0)):.2f}',
        "ask": f'{float(contract.get("ask", 0)):.2f}',
        "vol": f"{vol:,}",
        "oi": f"{oi:,}",
        "iv": f"{iv * 100:.1f}%",
        "premium": fmt_premium(premium),
        "expiry": expiry,
        "flags": flags_disp,
        "signal": signal_label,
        "premium_raw": premium,
        "iv_raw": iv,
        "vol_raw": vol,
        "oi_raw": oi,
        "flag_kinds": " ".join(flag_kinds),
        "is_otm_raw": "1" if otm else "0",
        "is_weekly_raw": "1" if weekly else "0",
        "signal_color": signal_color,
    }


def _contract_tooltips(contract: Mapping[str, Any]) -> dict[str, str]:
    flags = contract.get("flags") or []
    flag_tips = "; ".join(str(f.get("message", "")) for f in flags if f.get("message"))
    otm = contract.get("is_otm", False)
    signal_label, _ = contract_signal(contract, flags)
    return {
        "strike": TERM_DEFINITIONS["strike"] + (" " + TERM_DEFINITIONS["otm" if otm else "itm"]),
        "type": TERM_DEFINITIONS["type"],
        "last": TERM_DEFINITIONS["last"],
        "bid": TERM_DEFINITIONS["bid"],
        "ask": TERM_DEFINITIONS["ask"],
        "vol": TERM_DEFINITIONS["vol"],
        "oi": TERM_DEFINITIONS["oi"],
        "iv": TERM_DEFINITIONS["iv"],
        "premium": TERM_DEFINITIONS["premium"],
        "expiry": TERM_DEFINITIONS["weekly"] if contract.get("is_weekly") else TERM_DEFINITIONS["expiry"],
        "flags": flag_tips or "No flags",
        "signal": f"{TERM_DEFINITIONS['signal']} This row: {signal_label}.",
    }


def _table_conditional_styles(theme: dict) -> list[dict[str, Any]]:
    styles: list[dict[str, Any]] = []
    purple = theme.get("accent_purple", FLAG_DEFINITIONS["unusual"]["color"])

    for cp in ("C", "P"):
        accent = theme["accent_green"] if cp == "C" else theme["accent_red"]
        styles.append({
            "if": {"filter_query": f'{{type}} = "{cp}"', "column_id": "type"},
            "backgroundColor": f"{accent}33",
            "color": accent,
            "fontWeight": "700",
            "textAlign": "center",
        })

    for kind, fd in FLAG_DEFINITIONS.items():
        label = fd["label"]
        styles.append({
            "if": {"filter_query": f'{{flag_kinds}} contains {label}', "column_id": "flags"},
            "backgroundColor": f'{fd["color"]}44',
            "color": fd["color"],
            "fontWeight": "600",
        })

    premium_tiers = [
        (5_000_000, f'{theme["accent_orange"]}55', theme["accent_orange"]),
        (1_000_000, f'{theme["accent_orange"]}33', theme["accent_orange"]),
        (250_000, f'{theme["accent_orange"]}22', theme["accent_orange"]),
    ]
    for threshold, bg, fg in premium_tiers:
        styles.append({
            "if": {"filter_query": f"{{premium_raw}} >= {threshold}", "column_id": "premium"},
            "backgroundColor": bg,
            "color": fg,
            "fontWeight": "600",
        })

    iv_tiers = [
        (1.5, f'{theme["accent_red"]}33', theme["accent_red"]),
        (0.8, f'{theme["accent_orange"]}22', theme["accent_orange"]),
    ]
    for threshold, bg, fg in iv_tiers:
        styles.append({
            "if": {"filter_query": f"{{iv_raw}} >= {threshold}", "column_id": "iv"},
            "backgroundColor": bg,
            "color": fg,
        })

    styles.append({
        "if": {"filter_query": "{vol_raw} > {oi_raw}"},
        "backgroundColor": f"{purple}22",
    })

    styles.append({
        "if": {"filter_query": '{is_otm_raw} = "1"', "column_id": "strike"},
        "color": theme["accent_blue"],
        "fontWeight": "600",
    })
    styles.append({
        "if": {"filter_query": '{is_otm_raw} = "0"', "column_id": "strike"},
        "color": theme["accent_green"],
        "fontWeight": "600",
    })
    styles.append({
        "if": {"filter_query": '{is_weekly_raw} = "1"', "column_id": "expiry"},
        "color": theme["accent_orange"],
        "fontWeight": "600",
    })

    signal_styles = {
        "Block": FLAG_DEFINITIONS["block_premium"]["color"],
        "Speculative": FLAG_DEFINITIONS["high_unusual"]["color"],
        "Bullish bet": INSIGHT_CATEGORY_COLORS["Bullish"],
        "Hedge": INSIGHT_CATEGORY_COLORS["Bearish"],
        "Flow": INSIGHT_CATEGORY_COLORS["Neutral"],
    }
    for signal_name, sig_color in signal_styles.items():
        styles.append({
            "if": {"filter_query": f'{{signal}} = "{signal_name}"', "column_id": "signal"},
            "backgroundColor": f"{sig_color}33",
            "color": sig_color,
            "fontWeight": "600",
        })

    return styles


def _legend_chip(label: str, color: str, theme: dict, *, tip: str = "") -> html.Span:
    return html.Span(
        label,
        title=tip or label,
        className="sfa-flow-legend-chip",
        style={
            "backgroundColor": f"{color}33",
            "color": color,
            "border": f"1px solid {color}66",
            "padding": "1px 7px",
            "borderRadius": "4px",
            "fontSize": FONT_SIZES["xs"],
            "fontWeight": "600",
            "fontFamily": FONT_FAMILY,
            "cursor": "help" if tip else "default",
            "whiteSpace": "nowrap",
        },
    )


def render_color_legend(theme: dict, *, compact: bool = False) -> html.Div:
    """One-line color key for the contracts table (and the how-to-read guide)."""
    purple = theme.get("accent_purple", FLAG_DEFINITIONS["unusual"]["color"])
    chips = [
        _legend_chip("Call (C)", theme["accent_green"], theme, tip=TERM_DEFINITIONS["type"]),
        _legend_chip("Put (P)", theme["accent_red"], theme, tip=TERM_DEFINITIONS["type"]),
        _legend_chip("OTM strike", theme["accent_blue"], theme, tip=TERM_DEFINITIONS["otm"]),
        _legend_chip("ITM strike", theme["accent_green"], theme, tip=TERM_DEFINITIONS["itm"]),
        _legend_chip("Weekly", theme["accent_orange"], theme, tip=TERM_DEFINITIONS["weekly"]),
        _legend_chip("Premium heat", theme["accent_orange"], theme, tip=TERM_DEFINITIONS["premium"]),
        _legend_chip("Vol > OI", purple, theme, tip=TERM_DEFINITIONS["oi"]),
    ]
    for fd in FLAG_DEFINITIONS.values():
        chips.append(_legend_chip(fd["label"], fd["color"], theme, tip=fd["long"]))

    label = "Key:" if compact else "Table colors:"
    return html.Div(
        [
            html.Span(
                label,
                style={
                    "color": theme["text_tertiary"],
                    "fontSize": FONT_SIZES["xs"],
                    "fontFamily": FONT_FAMILY,
                    "marginRight": "6px",
                },
            ),
            *chips,
        ],
        className="sfa-flow-color-legend",
        style={
            "display": "flex",
            "flexWrap": "wrap",
            "alignItems": "center",
            "gap": "6px",
            "marginBottom": "6px" if compact else "8px",
        },
    )


def render_flag_legend(theme: dict) -> html.Div:
    chips = [
        _legend_chip(
            f'{fd["label"]} {fd["short"]}',
            fd["color"],
            theme,
            tip=fd["long"],
        )
        for fd in FLAG_DEFINITIONS.values()
    ]
    return html.Div(
        chips,
        className="sfa-flow-flag-legend",
        style={"display": "flex", "flexWrap": "wrap", "gap": "6px"},
    )


def _otm_itm_diagram(theme: dict) -> html.Div:
    """Pure HTML/CSS spot-line diagram for calls/puts and ITM/OTM."""
    zone = {
        "flex": "1",
        "textAlign": "center",
        "padding": "6px 4px",
        "fontSize": FONT_SIZES["xs"],
        "fontFamily": FONT_FAMILY,
        "borderRadius": "4px",
    }
    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        "OTM puts",
                        title=TERM_DEFINITIONS["otm"],
                        style={**zone, "backgroundColor": f'{theme["accent_red"]}18', "color": theme["accent_red"]},
                    ),
                    html.Div(
                        "ITM puts",
                        title=TERM_DEFINITIONS["itm"],
                        style={**zone, "backgroundColor": f'{theme["accent_red"]}33', "color": theme["accent_red"]},
                    ),
                    html.Div(
                        [
                            html.Div("SPOT", style={"fontWeight": "700", "letterSpacing": "0.08em"}),
                            html.Div("stock price", style={"opacity": 0.8, "fontSize": "10px"}),
                        ],
                        className="sfa-flow-diagram-spot",
                        style={
                            "flex": "0 0 auto",
                            "padding": "6px 10px",
                            "textAlign": "center",
                            "backgroundColor": theme["bg_secondary"],
                            "border": f'2px solid {theme["accent_cyan"]}',
                            "borderRadius": "6px",
                            "color": theme["accent_cyan"],
                            "fontFamily": FONT_FAMILY,
                            "fontSize": FONT_SIZES["xs"],
                        },
                    ),
                    html.Div(
                        "ITM calls",
                        title=TERM_DEFINITIONS["itm"],
                        style={**zone, "backgroundColor": f'{theme["accent_green"]}33', "color": theme["accent_green"]},
                    ),
                    html.Div(
                        "OTM calls",
                        title=TERM_DEFINITIONS["otm"],
                        style={**zone, "backgroundColor": f'{theme["accent_green"]}18', "color": theme["accent_green"]},
                    ),
                ],
                className="sfa-flow-diagram-track",
                style={"display": "flex", "alignItems": "stretch", "gap": "4px", "marginBottom": "6px"},
            ),
            html.P(
                "Calls = right to buy · Puts = right to sell · ITM has intrinsic value · OTM does not",
                style={
                    "margin": 0,
                    "fontSize": FONT_SIZES["xs"],
                    "color": theme["text_secondary"],
                    "fontFamily": FONT_FAMILY,
                },
            ),
        ],
        className="sfa-flow-diagram",
    )


def render_flow_guide(theme: dict) -> html.Details:
    """Always-visible (open by default) how-to-read strip for beginners."""
    return html.Details(
        [
            html.Summary("How to read this page", style=_panel_summary_style(theme)),
            html.Div(
                [
                    _otm_itm_diagram(theme),
                    html.Div(
                        [
                            html.Span(
                                "Activity flags:",
                                style={
                                    "color": theme["text_tertiary"],
                                    "fontSize": FONT_SIZES["xs"],
                                    "fontFamily": FONT_FAMILY,
                                    "marginRight": "6px",
                                },
                            ),
                            render_flag_legend(theme),
                        ],
                        style={
                            "display": "flex",
                            "flexWrap": "wrap",
                            "alignItems": "center",
                            "gap": "6px",
                            "margin": "10px 0 8px",
                        },
                    ),
                    render_color_legend(theme, compact=False),
                    html.P(
                        "Hover any table header or cell for a short definition. "
                        "Open LEARN for a beginner walkthrough. " + DISCLAIMER,
                        style={
                            "margin": "4px 0 0",
                            "fontSize": FONT_SIZES["xs"],
                            "color": theme["text_tertiary"],
                            "fontFamily": FONT_FAMILY,
                        },
                    ),
                ],
                style={"marginTop": "8px"},
            ),
        ],
        open=True,
        className="sfa-flow-guide sfa-flow-panel",
        style=_panel_style(theme),
    )


def render_learn_modal_content(theme: dict) -> html.Div:
    """Body for the Options 101 LEARN modal."""
    sections: list[Any] = []
    for section in LEARN_SECTIONS:
        sections.append(
            html.Div(
                [
                    html.H4(
                        section["title"],
                        style={
                            "margin": "0 0 4px",
                            "fontSize": FONT_SIZES["sm"],
                            "fontFamily": FONT_FAMILY,
                            "color": theme["text_primary"],
                        },
                    ),
                    html.P(
                        section["body"],
                        style={
                            "margin": "0 0 14px",
                            "fontSize": FONT_SIZES["xs"],
                            "lineHeight": "1.45",
                            "color": theme["text_secondary"],
                            "fontFamily": FONT_FAMILY,
                        },
                    ),
                ],
                className="sfa-flow-learn-section",
            )
        )
    sections.append(
        html.P(
            DISCLAIMER,
            style={
                "margin": "4px 0 0",
                "fontSize": FONT_SIZES["xs"],
                "color": theme["text_tertiary"],
                "fontFamily": FONT_FAMILY,
            },
        )
    )
    return html.Div(
        [_otm_itm_diagram(theme), html.Hr(style={"borderColor": theme["border_primary"]}), *sections],
        className="sfa-flow-learn-body",
    )


def _score_chip_row(report: Mapping[str, Any], theme: dict) -> html.Div | None:
    parts = score_parts(report)
    if not parts:
        return None
    chips: list[Any] = [
        html.Span(
            "Score",
            style={
                "color": theme["text_tertiary"],
                "fontSize": FONT_SIZES["xs"],
                "fontFamily": FONT_FAMILY,
                "marginRight": "4px",
            },
        )
    ]
    for i, (label, n, weight, color) in enumerate(parts):
        if i:
            chips.append(
                html.Span("+", style={"color": theme["text_tertiary"], "fontSize": FONT_SIZES["xs"]})
            )
        chips.append(
            _legend_chip(
                f"{n} {label} × {weight}",
                color,
                theme,
                tip=FLAG_DEFINITIONS[
                    next(k for k, fd in FLAG_DEFINITIONS.items() if fd["label"] == label)
                ]["long"],
            )
        )
    total = report.get("unusual_score", sum(n * w for _, n, w, _ in parts))
    chips.append(
        html.Span(
            f"= {total}",
            style={
                "fontWeight": "700",
                "color": theme["text_primary"],
                "fontSize": FONT_SIZES["xs"],
                "fontFamily": "IBM Plex Mono, monospace",
                "marginLeft": "4px",
            },
        )
    )
    return html.Div(
        chips,
        className="sfa-flow-score-chips",
        style={
            "display": "flex",
            "flexWrap": "wrap",
            "alignItems": "center",
            "gap": "6px",
            "marginBottom": "8px",
        },
    )


def _strike_map(report: Mapping[str, Any], theme: dict) -> html.Div | None:
    """Horizontal track: spot marker + top call/put strike dots."""
    spot = float(report.get("spot") or 0)
    if spot <= 0:
        return None
    calls = list(report.get("top_call_strikes") or [])[:5]
    puts = list(report.get("top_put_strikes") or [])[:5]
    strikes = [float(s) for s, _ in calls + puts]
    if not strikes:
        return None
    lo = min([spot, *strikes]) * 0.98
    hi = max([spot, *strikes]) * 1.02
    span = hi - lo or 1.0

    def _pct(price: float) -> float:
        return max(0.0, min(100.0, (price - lo) / span * 100.0))

    markers: list[Any] = []
    for strike, vol in puts:
        markers.append(
            html.Div(
                title=f"Put ${float(strike):.0f} · vol {int(vol):,}",
                className="sfa-flow-strike-dot sfa-flow-strike-put",
                style={
                    "left": f"{_pct(float(strike)):.1f}%",
                    "backgroundColor": theme["accent_red"],
                    "borderColor": theme["bg_tertiary"],
                },
            )
        )
    for strike, vol in calls:
        markers.append(
            html.Div(
                title=f"Call ${float(strike):.0f} · vol {int(vol):,}",
                className="sfa-flow-strike-dot sfa-flow-strike-call",
                style={
                    "left": f"{_pct(float(strike)):.1f}%",
                    "backgroundColor": theme["accent_green"],
                    "borderColor": theme["bg_tertiary"],
                },
            )
        )
    markers.append(
        html.Div(
            title=f"Spot ${spot:,.2f}",
            className="sfa-flow-strike-spot",
            style={
                "left": f"{_pct(spot):.1f}%",
                "backgroundColor": theme["accent_cyan"],
                "borderColor": theme["bg_tertiary"],
            },
        )
    )

    return html.Div(
        [
            html.Div(
                "Strike map (top volume vs spot)",
                style={
                    "fontSize": FONT_SIZES["xs"],
                    "color": theme["text_tertiary"],
                    "fontFamily": FONT_FAMILY,
                    "marginBottom": "4px",
                },
            ),
            html.Div(
                [
                    html.Div(
                        className="sfa-flow-strike-track-line",
                        style={"backgroundColor": theme["border_primary"]},
                    ),
                    *markers,
                ],
                className="sfa-flow-strike-track",
            ),
            html.Div(
                [
                    html.Span("Puts", style={"color": theme["accent_red"]}),
                    html.Span(" · "),
                    html.Span("Spot", style={"color": theme["accent_cyan"]}),
                    html.Span(" · "),
                    html.Span("Calls", style={"color": theme["accent_green"]}),
                ],
                style={
                    "fontSize": "10px",
                    "fontFamily": FONT_FAMILY,
                    "color": theme["text_tertiary"],
                    "marginTop": "4px",
                },
            ),
        ],
        className="sfa-flow-strike-map",
        style={"marginBottom": "8px"},
    )


def _contracts_table(contracts: Sequence[Mapping[str, Any]], table_id: str, theme: dict) -> html.Div:
    sorted_contracts = sorted(
        contracts,
        key=lambda c: contract_signal_weight(c.get("flags") or []),
        reverse=True,
    )[:50]
    rows = [_format_contract_row(c) for c in sorted_contracts]
    tooltips = [_contract_tooltips(c) for c in sorted_contracts]
    columns = [{"name": label, "id": key} for label, key in _TABLE_COLUMNS]
    header_tips = {key: COLUMN_HEADERS[key] for _, key in _TABLE_COLUMNS if key in COLUMN_HEADERS}

    table = dash_table.DataTable(
        id=table_id,
        columns=columns,
        data=rows,
        tooltip_data=tooltips,
        tooltip_header=header_tips,
        tooltip_delay=0,
        tooltip_duration=None,
        hidden_columns=_HIDDEN_COLUMNS,
        sort_action="native",
        page_size=50,
        fill_width=True,
        css=[{"selector": ".dash-table-tooltip", "rule": "font-family: inherit; font-size: 12px;"}],
        style_table={"overflowX": "auto", "width": "100%"},
        style_cell=_table_cell_style(theme),
        style_header=_table_header_style(theme),
        style_data_conditional=_table_conditional_styles(theme),
    )
    return html.Div(
        [render_color_legend(theme, compact=True), table],
        className="sfa-flow-table-wrap",
    )


def _insight_list(insights: Sequence[tuple[str, str]], theme: dict) -> html.Ul | None:
    if not insights:
        return None
    items: list[Any] = []
    for category, message in insights:
        color = INSIGHT_CATEGORY_COLORS.get(category, theme["text_secondary"])
        items.append(html.Li([
            html.Span(
                category.upper(),
                className="sfa-flow-insight-chip",
                style={
                    "backgroundColor": f"{color}33",
                    "color": color,
                    "padding": "1px 6px",
                    "borderRadius": "4px",
                    "fontWeight": "600",
                    "fontSize": FONT_SIZES["xs"],
                    "marginRight": "6px",
                },
            ),
            html.Span(message, style={"color": theme["text_secondary"]}),
        ], style={"marginBottom": "4px", "lineHeight": "1.4"}))
    return html.Ul(
        items,
        className="sfa-flow-insights",
        style={
            "fontSize": FONT_SIZES["xs"],
            "margin": "0 0 8px",
            "paddingLeft": "18px",
            "listStyle": "none",
        },
    )


def render_glossary_panel(theme: dict, *, open: bool = True) -> html.Details:
    """Collapsible glossary matching the standalone HTML legend."""
    term_items: list[Any] = []
    for k, v in TERM_DEFINITIONS.items():
        term_items.extend([
            html.Dt(k.replace("_", " ").title(), style={"color": theme["text_primary"], "marginTop": "6px"}),
            html.Dd(v, style={"color": theme["text_secondary"], "marginLeft": "1rem", "fontSize": FONT_SIZES["xs"]}),
        ])

    flag_items: list[Any] = []
    for fd in FLAG_DEFINITIONS.values():
        flag_items.extend([
            html.Dt([
                html.Span(
                    fd["label"],
                    style={
                        "backgroundColor": f'{fd["color"]}33',
                        "color": fd["color"],
                        "padding": "1px 6px",
                        "borderRadius": "4px",
                        "fontWeight": "600",
                        "marginRight": "6px",
                    },
                ),
                fd["short"],
            ], style={"color": theme["text_primary"], "marginTop": "6px"}),
            html.Dd(fd["long"], style={"color": theme["text_secondary"], "marginLeft": "1rem", "fontSize": FONT_SIZES["xs"]}),
        ])

    return html.Details([
        html.Summary("What do these terms mean?", style=_panel_summary_style(theme)),
        html.Dl(term_items, style={"margin": "8px 0 0"}),
        html.H3(
            "Activity flags",
            style={
                "fontSize": FONT_SIZES["sm"],
                "color": theme["text_primary"],
                "margin": "12px 0 4px",
                "fontFamily": FONT_FAMILY,
            },
        ),
        html.Dl(flag_items, style={"margin": "0"}),
    ], open=open, className="sfa-flow-panel sfa-flow-glossary", style=_panel_style(theme))


def render_summary_cards(reports: Sequence[Mapping[str, Any]], theme: dict) -> html.Details:
    total_unusual = sum(
        1 for r in reports for f in (r.get("flags") or []) if f.get("kind") == "unusual"
    )
    total_premium = sum(
        c.get("premium", 0)
        for r in reports
        for c in (r.get("contracts") or [])
        for f in (c.get("flags") or [])
        if f.get("kind") == "block_premium"
    )
    repeat_tickers = [
        str(r.get("ticker", ""))
        for r in reports
        if any(f.get("kind") == "repeat_call" for f in (r.get("flags") or []))
    ]

    def _card(text: str) -> html.Span:
        return html.Span(text, style={
            "backgroundColor": theme["bg_tertiary"],
            "padding": "8px 14px",
            "borderRadius": "6px",
            "border": f'1px solid {theme["border_primary"]}',
            "fontFamily": FONT_FAMILY,
            "fontSize": FONT_SIZES["xs"],
            "color": theme["text_primary"],
        })

    return html.Details([
        html.Summary("Scan summary", style=_panel_summary_style(theme)),
        html.Div([
            _card(f"Tickers: {len(reports)}"),
            _card(f"Unusual contracts: {total_unusual}"),
            _card(f"Block premium flagged: {fmt_premium(total_premium)}"),
            _card(f"Repeat-call tickers: {', '.join(repeat_tickers) or '—'}"),
        ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginTop": "10px"}),
    ], open=True, className="sfa-flow-panel sfa-flow-summary", style=_panel_style(theme))


def render_ticker_card(report: Mapping[str, Any], theme: dict, *, index: int = 0) -> html.Details:
    ticker = str(report.get("ticker", ""))
    if report.get("error"):
        return html.Details(
            [
                html.Summary(ticker, style={
                    **_panel_summary_style(theme),
                    "fontSize": FONT_SIZES["lg"],
                }),
                html.P(str(report["error"]), style={"color": theme["accent_red"], "margin": "8px 0 0"}),
            ],
            open=True,
            className="sfa-flow-panel sfa-flow-ticker-card",
            style=_panel_style(theme),
        )

    repeat = any(f.get("kind") == "repeat_call" for f in (report.get("flags") or []))
    score_tip = score_breakdown(report)
    insights = interpretive_insights(report)
    sentiment_label, sentiment_color, sentiment_reason = ticker_sentiment(report)

    top_calls = ", ".join(
        f"${s:.0f} ({v:,})" for s, v in (report.get("top_call_strikes") or [])[:5]
    ) or "—"
    top_puts = ", ".join(
        f"${s:.0f} ({v:,})" for s, v in (report.get("top_put_strikes") or [])[:5]
    ) or "—"

    call_pct = float(report.get("call_pct") or 0)
    put_pct = float(report.get("put_pct") or 0)

    header_children: list[Any] = [
        html.H3(
            f"{ticker} ${float(report.get('spot', 0)):,.2f}",
            style={
                "margin": 0,
                "fontFamily": FONT_FAMILY,
                "fontSize": FONT_SIZES["lg"],
                "fontWeight": 700,
                "color": theme["text_primary"],
            },
        ),
        html.Span(
            sentiment_label.upper(),
            className="sfa-flow-sentiment-badge",
            title=sentiment_reason,
            style={
                "backgroundColor": f"{sentiment_color}33",
                "color": sentiment_color,
                "padding": "2px 8px",
                "borderRadius": "4px",
                "fontSize": FONT_SIZES["xs"],
                "fontWeight": 600,
                "marginLeft": "8px",
                "cursor": "help",
            },
        ),
    ]
    if repeat:
        header_children.append(html.Span(
            "REPEAT CALLS",
            style={
                "backgroundColor": f'{FLAG_DEFINITIONS["repeat_call"]["color"]}33',
                "color": FLAG_DEFINITIONS["repeat_call"]["color"],
                "padding": "2px 8px",
                "borderRadius": "4px",
                "fontSize": FONT_SIZES["xs"],
                "fontWeight": 600,
                "marginLeft": "8px",
            },
        ))

    insight_block = _insight_list(insights, theme)
    score_chips = _score_chip_row(report, theme)
    strike_map = _strike_map(report, theme)

    # Score stays visible on the summary row so a collapsed card is still rankable.
    header_children.append(html.Span(
        f"Score {report.get('unusual_score', 0)}",
        title=score_tip,
        style={
            "marginLeft": "auto",
            "fontFamily": FONT_FAMILY,
            "fontSize": FONT_SIZES["xs"],
            "color": theme["text_secondary"],
            "cursor": "help",
        },
    ))

    card_children: list[Any] = [
        html.Div(
            html.A(
                "Open Fundamentals",
                href=f"/fundamentals?ticker={ticker}",
                style={
                    "color": theme["accent_cyan"],
                    "fontSize": FONT_SIZES["xs"],
                    "textDecoration": "none",
                    "fontFamily": FONT_FAMILY,
                },
            ),
            style={
                "display": "flex",
                "justifyContent": "flex-end",
                "margin": "8px 0",
            },
        ),
        html.Div([
            _kpi_span("Prev", f"${float(report.get('prev_close', 0)):,.2f}", "Previous session close", theme),
            _kpi_span(
                "Day",
                f"{float(report.get('day_low', 0)):,.2f}–{float(report.get('day_high', 0)):,.2f}",
                "Today's trading range",
                theme,
            ),
            _kpi_span(
                "52-week",
                f"{float(report.get('wk52_low', 0)):,.2f}–{float(report.get('wk52_high', 0)):,.2f}",
                "52-week high and low",
                theme,
            ),
            _kpi_span(
                "Put/Call vol",
                f"{float(report.get('pc_vol_ratio', 0)):.2f}",
                TERM_DEFINITIONS["pc_vol"],
                theme,
            ),
            _kpi_span("Score", str(report.get("unusual_score", 0)), score_tip, theme),
        ], style={"display": "flex", "flexWrap": "wrap", "gap": "12px", "marginBottom": "8px"}),
    ]
    if score_chips is not None:
        card_children.append(score_chips)
    if strike_map is not None:
        card_children.append(strike_map)
    card_children.extend([
        html.Div([
            html.Span(f"Calls {call_pct:.1f}%", style={"fontSize": FONT_SIZES["xs"], "color": theme["text_secondary"]}),
            html.Div(
                html.Div(style={
                    "width": f"{call_pct:.1f}%",
                    "height": "100%",
                    "backgroundColor": theme["accent_green"],
                }),
                style={
                    "flex": 1,
                    "height": "10px",
                    "backgroundColor": theme["bg_hover"],
                    "borderRadius": "4px",
                    "overflow": "hidden",
                    "maxWidth": "300px",
                },
            ),
            html.Span(f"Puts {put_pct:.1f}%", style={"fontSize": FONT_SIZES["xs"], "color": theme["text_secondary"]}),
        ], style={"display": "flex", "alignItems": "center", "gap": "8px", "marginBottom": "8px"}),
        html.P(
            f"Top calls: {top_calls} | Top puts: {top_puts}",
            style={"fontSize": FONT_SIZES["xs"], "color": theme["text_secondary"], "margin": "0 0 8px"},
        ),
        insight_block,
        _contracts_table(report.get("contracts") or [], f"flow-table-{index}-{ticker}", theme),
    ])

    return html.Details(
        [
            html.Summary(header_children, style={
                **_panel_summary_style(theme),
                "fontSize": FONT_SIZES["lg"],
            }),
            html.Div(card_children),
        ],
        # Top-scoring ticker starts expanded; the rest collapse so long scans stay scannable.
        open=(index == 0),
        className="sfa-flow-panel sfa-flow-ticker-card",
        style=_panel_style(theme),
    )


def render_flow_placeholder(theme: dict, message: str = "No report yet. Click RESCAN NOW.") -> html.Div:
    return html.Div(message, style={
        "fontFamily": FONT_FAMILY,
        "fontSize": FONT_SIZES["sm"],
        "color": theme["text_secondary"],
        "padding": "24px",
        "textAlign": "center",
    })


def render_flow_reports(payload: Mapping[str, Any], theme: dict, *, show_glossary: bool = False) -> html.Div:
    """Compose full flow scanner content from JSON payload."""
    reports = list(payload.get("reports") or [])
    if isinstance(payload, list):
        reports = list(payload)

    sorted_reports = sorted(reports, key=lambda r: r.get("unusual_score", 0), reverse=True)

    children: list[Any] = []
    if show_glossary:
        children.append(render_glossary_panel(theme))
    children.append(render_flow_guide(theme))
    children.append(render_summary_cards(sorted_reports, theme))
    for idx, report in enumerate(sorted_reports):
        children.append(render_ticker_card(report, theme, index=idx))
    children.append(html.P(
        DISCLAIMER,
        style={
            "fontSize": FONT_SIZES["xs"],
            "color": theme["text_tertiary"],
            "textAlign": "center",
            "marginTop": "16px",
        },
    ))

    generated = payload.get("generated_at") if isinstance(payload, Mapping) else None
    if generated:
        children.insert(0, html.P(
            f"Report generated {generated}",
            style={"fontSize": FONT_SIZES["xs"], "color": theme["text_tertiary"], "margin": "0 0 8px"},
        ))

    return html.Div(children, style={"padding": "8px"})
