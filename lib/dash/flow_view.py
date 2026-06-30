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
    TERM_DEFINITIONS,
    contract_signal,
    contract_signal_weight,
    fmt_premium,
    fmt_strike,
    interpretive_insights,
    score_breakdown,
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

    for cp in ("C", "P"):
        styles.append({
            "if": {"filter_query": f'{{type}} = "{cp}"', "column_id": "type"},
            "color": theme["accent_green"] if cp == "C" else theme["accent_red"],
            "fontWeight": "600",
        })

    for kind, fd in FLAG_DEFINITIONS.items():
        label = fd["label"]
        styles.append({
            "if": {"filter_query": f'{{flag_kinds}} contains {label}', "column_id": "flags"},
            "backgroundColor": f'{fd["color"]}33',
            "color": fd["color"],
            "fontWeight": "600",
        })

    premium_tiers = [
        (5_000_000, f'{theme["accent_orange"]}44', theme["accent_orange"]),
        (1_000_000, f'{theme["accent_orange"]}22', theme["accent_orange"]),
        (250_000, f'{theme["accent_orange"]}18', theme["accent_orange"]),
    ]
    for threshold, bg, fg in premium_tiers:
        styles.append({
            "if": {"filter_query": f"{{premium_raw}} >= {threshold}", "column_id": "premium"},
            "backgroundColor": bg,
            "color": fg,
            "fontWeight": "600",
        })

    iv_tiers = [
        (1.5, f'{theme["accent_red"]}22', theme["accent_red"]),
        (0.8, f'{theme["accent_orange"]}18', theme["accent_orange"]),
    ]
    for threshold, bg, fg in iv_tiers:
        styles.append({
            "if": {"filter_query": f"{{iv_raw}} >= {threshold}", "column_id": "iv"},
            "backgroundColor": bg,
            "color": fg,
        })

    styles.append({
        "if": {"filter_query": "{vol_raw} > {oi_raw}"},
        "backgroundColor": theme["bg_hover"],
    })

    styles.append({
        "if": {"filter_query": '{is_otm_raw} = "1"', "column_id": "strike"},
        "color": theme["accent_blue"],
    })
    styles.append({
        "if": {"filter_query": '{is_otm_raw} = "0"', "column_id": "strike"},
        "color": theme["accent_green"],
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
            "color": sig_color,
            "fontWeight": "600",
        })

    return styles


def _contracts_table(contracts: Sequence[Mapping[str, Any]], table_id: str, theme: dict) -> dash_table.DataTable:
    sorted_contracts = sorted(
        contracts,
        key=lambda c: contract_signal_weight(c.get("flags") or []),
        reverse=True,
    )[:50]
    rows = [_format_contract_row(c) for c in sorted_contracts]
    tooltips = [_contract_tooltips(c) for c in sorted_contracts]
    columns = [{"name": label, "id": key} for label, key in _TABLE_COLUMNS]
    header_tips = {key: COLUMN_HEADERS[key] for _, key in _TABLE_COLUMNS if key in COLUMN_HEADERS}

    return dash_table.DataTable(
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
        insight_block,
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
