"""
Render a regime-slicing payload (``lib.regimes``) for the optimizer workspace.

Pure: payload + theme in, Dash components out, so it is testable without a
running app.
"""

from __future__ import annotations

from typing import Any

from dash import dash_table, html

from lib.dash.dash_config import FONT_SIZES
from lib.metrics import format_canonical
from lib.metrics.names import spec_for

_STATUS_TEXT = {
    "pass": "PASSES REGIME RULE",
    "fail": "FAILS REGIME RULE",
    "inconclusive": "INCONCLUSIVE",
}


def _status_color(status: str, theme: dict) -> str:
    return {
        "pass": theme["accent_green"],
        "fail": theme["accent_red"],
    }.get(status, theme["accent_orange"])


def _rule_sentence(rule: dict[str, Any], labels: dict[str, str]) -> str:
    spec = spec_for(rule.get("metric", ""))
    name = spec.label if spec else str(rule.get("metric"))
    required = [labels.get(r, r) for r in rule.get("required") or []]
    text = (
        f"Rule: {name} above {float(rule.get('threshold', 0)):g} in at least "
        f"{int(rule.get('min_passing', 0))} regimes"
    )
    if required:
        text += ", including " + " and ".join(required)
    return text + ". Each regime is backtested on its own, from flat, with fresh capital."


def _cell(metrics: dict[str, Any] | None, key: str) -> str:
    if not metrics:
        return "—"
    return format_canonical(key, metrics.get(key, 0))


def render_regime_panel(payload: dict[str, Any], theme: dict) -> html.Div:
    verdict = payload.get("verdict") or {}
    rule = payload.get("rule") or {}
    rows = payload.get("regimes") or []
    status = str(verdict.get("status", "inconclusive"))
    metric = str(rule.get("metric", "sortino"))
    spec = spec_for(metric)
    metric_label = spec.label if spec else metric
    labels = {r["id"]: r["label"] for r in rows}

    table_rows = []
    for r in rows:
        m = r.get("metrics")
        table_rows.append({
            "Result": {True: "✓", False: "✗"}.get(r.get("passed"), "n/a"),
            "Regime": r.get("label", ""),
            "Period": f"{r.get('from', '')} → {r.get('to', '')}",
            metric_label: _cell(m, metric),
            "Return": _cell(m, "total_return"),
            "Buy & Hold": _cell(m, "benchmark_return"),
            "Max DD": _cell(m, "max_drawdown"),
            "Trades": str(int(m.get("num_trades", 0))) if m else "—",
            "Data": r.get("coverage", ""),
        })
    columns = ["Result", "Regime", "Period", metric_label, "Return", "Buy & Hold", "Max DD", "Trades", "Data"]

    return html.Div([
        html.Div("Regime slicing", style={
            "fontSize": FONT_SIZES["xs"],
            "color": theme["text_tertiary"],
            "fontWeight": "600",
            "letterSpacing": "0.5px",
            "marginBottom": "8px",
        }),
        html.Div([
            html.Span(
                _STATUS_TEXT.get(status, status.upper()),
                style={"color": _status_color(status, theme), "fontWeight": "600", "marginRight": "12px"},
            ),
            html.Span(
                f"{int(verdict.get('passing', 0))} of {int(verdict.get('evaluated', 0))} regimes pass"
                f" · {payload.get('ticker', '')} {payload.get('interval', '')}",
                style={"color": theme["text_primary"]},
            ),
        ], style={"fontSize": FONT_SIZES["xs"], "marginBottom": "4px"}),
        html.Div(verdict.get("reason", ""), style={
            "fontSize": FONT_SIZES["xs"],
            "color": theme["text_secondary"],
            "marginBottom": "4px",
        }),
        html.Div(_rule_sentence(rule, labels), style={
            "fontSize": FONT_SIZES["xs"],
            "color": theme["text_tertiary"],
            "marginBottom": "8px",
        }),
        dash_table.DataTable(
            columns=[{"name": c, "id": c} for c in columns],
            data=table_rows,
            style_table={"overflowX": "auto"},
            style_header={
                "backgroundColor": theme["bg_tertiary"],
                "color": theme["text_secondary"],
                "fontSize": FONT_SIZES["xs"],
                "border": f"1px solid {theme['border_primary']}",
            },
            style_cell={
                "backgroundColor": theme["bg_primary"],
                "color": theme["text_primary"],
                "fontSize": FONT_SIZES["xs"],
                "border": f"1px solid {theme['border_primary']}",
                "padding": "4px 8px",
                "fontFamily": "ui-monospace, monospace",
                "whiteSpace": "nowrap",
            },
            style_data_conditional=[
                {"if": {"filter_query": '{Result} = "✓"', "column_id": "Result"},
                 "color": theme["accent_green"]},
                {"if": {"filter_query": '{Result} = "✗"', "column_id": "Result"},
                 "color": theme["accent_red"]},
                {"if": {"filter_query": '{Data} != "full"'},
                 "color": theme["text_tertiary"]},
            ],
        ) if table_rows else html.Div(),
        html.Div(
            "Rows marked partial or none lack data for the whole period (Yahoo intraday "
            "history reaches back ~2 years; young tickers start mid-calendar). They are "
            "shown but not counted.",
            style={"fontSize": FONT_SIZES["xs"], "color": theme["text_tertiary"], "marginTop": "6px"},
        ) if any(r.get("coverage") != "full" for r in rows) else html.Div(),
    ])
