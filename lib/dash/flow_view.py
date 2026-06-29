"""Pure render functions for the in-app Flow Scanner (native Dash components)."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

from dash import dash_table, html

from lib.dash.dash_config import FONT_FAMILY, FONT_SIZES
from lib.dash.flow_glossary import (
    DISCLAIMER,
    FLAG_DEFINITIONS,
    TERM_DEFINITIONS,
    fmt_premium,
    fmt_strike,
    interpretive_banner,
    score_breakdown,
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
    }


def render_glossary_panel(theme: dict) -> html.Details:
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
        html.Summary(
            "What do these terms mean?",
            style={
                "cursor": "pointer",
                "fontWeight": "600",
                "color": theme["text_primary"],
                "fontFamily": FONT_FAMILY,
                "fontSize": FONT_SIZES["sm"],
            },
        ),
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
    ], style={
        "backgroundColor": theme["bg_tertiary"],
        "border": f'1px solid {theme["border_primary"]}',
        "borderRadius": "8px",
        "padding": "10px 14px",
        "marginBottom": "12px",
    })


def render_summary_cards(reports: Sequence[Mapping[str, Any]], theme: dict) -> html.Div:
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

    return html.Div([
        _card(f"Tickers: {len(reports)}"),
        _card(f"Unusual contracts: {total_unusual}"),
        _card(f"Block premium flagged: {fmt_premium(total_premium)}"),
        _card(f"Repeat-call tickers: {', '.join(repeat_tickers) or '—'}"),
    ], style={"display": "flex", "gap": "12px", "flexWrap": "wrap", "marginBottom": "12px"})


def _format_contract_row(contract: Mapping[str, Any]) -> dict[str, str]:
    strike = fmt_strike(float(contract.get("strike", 0)))
    otm = contract.get("is_otm", False)
    strike_disp = f"{strike} {'OTM' if otm else 'ITM'}"
    cp = str(contract.get("cp", ""))
    expiry = str(contract.get("expiry", ""))
    if contract.get("is_weekly"):
        expiry = f"{expiry} weekly"

    flags = contract.get("flags") or []
    flag_parts = []
    for f in flags:
        kind = str(f.get("kind", ""))
        fd = FLAG_DEFINITIONS.get(kind)
        if fd:
            flag_parts.append(fd["label"])
    flags_disp = " ".join(flag_parts)

    return {
        "strike": strike_disp,
        "type": cp,
        "last": f'{float(contract.get("last", 0)):.2f}',
        "bid": f'{float(contract.get("bid", 0)):.2f}',
        "ask": f'{float(contract.get("ask", 0)):.2f}',
        "vol": f'{int(contract.get("volume", 0)):,}',
        "oi": f'{int(contract.get("open_interest", 0)):,}',
        "iv": f'{float(contract.get("iv", 0)) * 100:.1f}%',
        "premium": fmt_premium(float(contract.get("premium", 0))),
        "expiry": expiry,
        "flags": flags_disp,
    }


def _contract_tooltips(contract: Mapping[str, Any]) -> dict[str, str]:
    flags = contract.get("flags") or []
    flag_tips = "; ".join(str(f.get("message", "")) for f in flags if f.get("message"))
    otm = contract.get("is_otm", False)
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
    }


def _contracts_table(contracts: Sequence[Mapping[str, Any]], table_id: str, theme: dict) -> dash_table.DataTable:
    rows = [_format_contract_row(c) for c in contracts[:50]]
    tooltips = [_contract_tooltips(c) for c in contracts[:50]]
    columns = [{"name": label, "id": key} for label, key in _TABLE_COLUMNS]

    type_style = [
        {
            "if": {"filter_query": f'{{type}} = "{cp}"', "column_id": "type"},
            "color": theme["accent_green"] if cp == "C" else theme["accent_red"],
            "fontWeight": "600",
        }
        for cp in ("C", "P")
    ]

    return dash_table.DataTable(
        id=table_id,
        columns=columns,
        data=rows,
        tooltip_data=tooltips,
        tooltip_duration=None,
        sort_action="native",
        page_size=50,
        fill_width=True,
        style_table={"overflowX": "auto", "width": "100%"},
        style_cell=_table_cell_style(theme),
        style_header=_table_header_style(theme),
        style_data_conditional=type_style,
    )


def render_ticker_card(report: Mapping[str, Any], theme: dict, *, index: int = 0) -> html.Div:
    ticker = str(report.get("ticker", ""))
    if report.get("error"):
        return html.Div([
            html.H3(ticker, style={"color": theme["text_primary"], "margin": 0}),
            html.P(str(report["error"]), style={"color": theme["accent_red"]}),
        ], style={
            "backgroundColor": theme["bg_tertiary"],
            "border": f'1px solid {theme["border_primary"]}',
            "borderRadius": "8px",
            "padding": "14px",
            "marginBottom": "12px",
        })

    repeat = any(f.get("kind") == "repeat_call" for f in (report.get("flags") or []))
    score_tip = score_breakdown(report)
    interp = interpretive_banner(report)

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

    return html.Div([
        html.Div([
            html.Div(header_children, style={"display": "flex", "alignItems": "center", "flexWrap": "wrap"}),
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
        ], style={
            "display": "flex",
            "justifyContent": "space-between",
            "alignItems": "center",
            "flexWrap": "wrap",
            "gap": "8px",
            "marginBottom": "8px",
        }),
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
        html.P(
            interp,
            style={
                "fontSize": FONT_SIZES["xs"],
                "color": theme["accent_cyan"],
                "margin": "0 0 8px",
                "lineHeight": "1.4",
            },
        ) if interp else None,
        _contracts_table(report.get("contracts") or [], f"flow-table-{index}-{ticker}", theme),
    ], style={
        "backgroundColor": theme["bg_tertiary"],
        "border": f'1px solid {theme["border_primary"]}',
        "borderRadius": "8px",
        "padding": "14px",
        "marginBottom": "12px",
    })


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

    return html.Div(children, style={"padding": "8px", "overflowY": "auto", "height": "100%"})
