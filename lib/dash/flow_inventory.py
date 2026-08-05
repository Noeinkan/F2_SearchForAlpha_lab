"""Options inventory (OI/volume by strike) chart for the Flow Scanner."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import plotly.graph_objects as go
from dash import dcc, html

from lib.dash.dash_config import FONT_FAMILY, FONT_SIZES
from lib.dash.flow_glossary import DISCLAIMER, TERM_DEFINITIONS

# Keep strikes within this fraction of spot for readability.
STRIKE_WINDOW_PCT = 0.12

INVENTORY_CAPTION = (
    "Open interest by strike — puts left, calls right. "
    "Not buy/sell flow (Yahoo has no trade direction). " + DISCLAIMER
)


def nearest_expiry(ladders: Mapping[str, Any] | None) -> str | None:
    """Return the chronologically nearest expiry key, or None."""
    if not ladders:
        return None
    keys = sorted(str(k) for k in ladders.keys())
    return keys[0] if keys else None


def filter_ladder_window(
    ladder: Sequence[Mapping[str, Any]],
    spot: float,
    window_pct: float = STRIKE_WINDOW_PCT,
) -> list[dict]:
    """Keep strikes within ±window_pct of spot; fall back to full ladder if empty."""
    rows = [
        {
            "strike": float(r["strike"]),
            "call_oi": int(r.get("call_oi") or 0),
            "put_oi": int(r.get("put_oi") or 0),
            "call_vol": int(r.get("call_vol") or 0),
            "put_vol": int(r.get("put_vol") or 0),
        }
        for r in ladder
    ]
    if spot <= 0 or not rows:
        return rows
    lo = spot * (1.0 - window_pct)
    hi = spot * (1.0 + window_pct)
    filtered = [r for r in rows if lo <= r["strike"] <= hi]
    return filtered if filtered else rows


def _empty_figure(theme: dict, message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=theme.get("bg_tertiary") or theme.get("bg_panel", "#161b22"),
        plot_bgcolor=theme.get("bg_primary", "#0d1117"),
        margin={"l": 56, "r": 72, "t": 28, "b": 40},
        font={"family": FONT_FAMILY, "size": 11, "color": theme.get("text_secondary", "#8b949e")},
        annotations=[{
            "text": message,
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 0.5,
            "showarrow": False,
            "font": {"color": theme.get("text_tertiary", "#6e7681"), "size": 12},
        }],
        xaxis={"visible": False},
        yaxis={"visible": False},
        height=280,
        showlegend=False,
    )
    return fig


def build_inventory_figure(
    ladder: Sequence[Mapping[str, Any]] | None,
    spot: float,
    meta: Mapping[str, Any] | None = None,
    *,
    metric: str = "oi",
    theme: dict | None = None,
) -> go.Figure:
    """Horizontal bars: puts left (negative), calls right (positive)."""
    theme = theme or {}
    rows = filter_ladder_window(list(ladder or []), float(spot or 0))
    if not rows:
        return _empty_figure(theme, "No strike inventory for this expiry")

    use_vol = str(metric).lower() in {"vol", "volume"}
    call_key = "call_vol" if use_vol else "call_oi"
    put_key = "put_vol" if use_vol else "put_oi"
    x_label = "Contract volume" if use_vol else "Open interest (contracts)"

    strikes = [r["strike"] for r in rows]
    call_vals = [float(r[call_key]) for r in rows]
    put_vals = [-float(r[put_key]) for r in rows]  # left of zero

    green = theme.get("accent_green", "#3fb950")
    red = theme.get("accent_red", "#f85149")
    cyan = theme.get("accent_cyan", "#58a6ff")
    yellow = theme.get("accent_yellow", "#f0c674")
    text_sec = theme.get("text_secondary", "#8b949e")
    text_ter = theme.get("text_tertiary", "#6e7681")
    border = theme.get("border_primary", "#30363d")
    bg_plot = theme.get("bg_primary", "#0d1117")
    bg_paper = theme.get("bg_tertiary") or theme.get("bg_panel", "#161b22")

    hover_calls = [
        f"Strike ${s:,.2f}<br>Calls {('vol' if use_vol else 'OI')}: {abs(v):,.0f}"
        for s, v in zip(strikes, call_vals)
    ]
    hover_puts = [
        f"Strike ${s:,.2f}<br>Puts {('vol' if use_vol else 'OI')}: {abs(v):,.0f}"
        for s, v in zip(strikes, put_vals)
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=strikes,
        x=put_vals,
        orientation="h",
        name="Puts",
        marker_color=red,
        hovertext=hover_puts,
        hoverinfo="text",
        width=0.7,
    ))
    fig.add_trace(go.Bar(
        y=strikes,
        x=call_vals,
        orientation="h",
        name="Calls",
        marker_color=green,
        hovertext=hover_calls,
        hoverinfo="text",
        width=0.7,
    ))

    # Spot as horizontal line across the chart (y = price on category... use shape)
    shapes: list[dict] = []
    annotations: list[dict] = []
    if spot and spot > 0:
        shapes.append({
            "type": "line",
            "xref": "paper",
            "x0": 0,
            "x1": 1,
            "yref": "y",
            "y0": spot,
            "y1": spot,
            "line": {"color": yellow, "width": 1.5, "dash": "dash"},
        })
        annotations.append({
            "xref": "paper",
            "x": 1.01,
            "y": spot,
            "yref": "y",
            "text": f"{spot:,.2f}",
            "showarrow": False,
            "font": {"size": 10, "color": yellow, "family": FONT_FAMILY},
            "xanchor": "left",
        })

    meta = meta or {}
    max_pain = meta.get("max_pain")
    if max_pain is not None:
        try:
            mp = float(max_pain)
            shapes.append({
                "type": "line",
                "xref": "paper",
                "x0": 0,
                "x1": 1,
                "yref": "y",
                "y0": mp,
                "y1": mp,
                "line": {"color": cyan, "width": 1, "dash": "dot"},
            })
            annotations.append({
                "xref": "paper",
                "x": 1.01,
                "y": mp,
                "yref": "y",
                "text": f"MP {mp:,.0f}",
                "showarrow": False,
                "font": {"size": 9, "color": cyan, "family": FONT_FAMILY},
                "xanchor": "left",
            })
        except (TypeError, ValueError):
            pass

    n = len(strikes)
    height = max(280, min(560, 48 + n * 14))

    fig.update_layout(
        barmode="overlay",
        paper_bgcolor=bg_paper,
        plot_bgcolor=bg_plot,
        margin={"l": 56, "r": 72, "t": 36, "b": 44},
        font={"family": FONT_FAMILY, "size": 11, "color": text_sec},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.02,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 10},
        },
        shapes=shapes,
        annotations=annotations,
        height=height,
        bargap=0.15,
        xaxis={
            "title": {"text": x_label, "font": {"size": 11, "color": text_ter}},
            "zeroline": True,
            "zerolinecolor": border,
            "zerolinewidth": 1,
            "gridcolor": border,
            "tickfont": {"size": 10},
            "tickformat": ",.0f",
        },
        yaxis={
            "title": {"text": "Strike", "font": {"size": 11, "color": text_ter}},
            "gridcolor": border,
            "tickfont": {"size": 10},
            "tickformat": ",.2f",
            "type": "linear",
        },
        hovermode="closest",
    )

    # Axis subtitle for sold/bought honesty — use annotation at top
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.15,
        y=1.08,
        text="PUTS",
        showarrow=False,
        font={"size": 10, "color": red, "family": FONT_FAMILY},
    )
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.85,
        y=1.08,
        text="CALLS",
        showarrow=False,
        font={"size": 10, "color": green, "family": FONT_FAMILY},
    )

    return fig


def inventory_caption_for_meta(
    meta: Mapping[str, Any] | None,
    spot: float,
    *,
    metric: str = "oi",
) -> str:
    """One-line layman status under the chart."""
    parts: list[str] = []
    use_vol = str(metric).lower() in {"vol", "volume"}
    parts.append("Today's volume by strike." if use_vol else "Open interest by strike.")
    meta = meta or {}
    cw = meta.get("call_wall")
    pw = meta.get("put_wall")
    mp = meta.get("max_pain")
    if cw is not None:
        try:
            parts.append(f"Call wall ${float(cw):,.0f}.")
        except (TypeError, ValueError):
            pass
    if pw is not None:
        try:
            parts.append(f"Put wall ${float(pw):,.0f}.")
        except (TypeError, ValueError):
            pass
    if mp is not None:
        try:
            parts.append(f"Max pain ${float(mp):,.0f}.")
        except (TypeError, ValueError):
            pass
    if spot and spot > 0:
        parts.append(f"Spot ${float(spot):,.2f}.")
    parts.append("Not buy/sell flow.")
    return " ".join(parts)


def render_inventory_panel(report: Mapping[str, Any], theme: dict) -> html.Div | None:
    """Expiry + metric controls + Plotly inventory chart for one ticker report."""
    ladders = report.get("strike_ladders") or {}
    if not ladders:
        return None

    ticker = str(report.get("ticker") or "UNK").upper()
    spot = float(report.get("spot") or 0)
    meta_all = report.get("inventory_meta") or {}
    expiry = nearest_expiry(ladders)
    if not expiry:
        return None

    ladder = ladders.get(expiry) or []
    meta = meta_all.get(expiry) or {}
    figure = build_inventory_figure(ladder, spot, meta, metric="oi", theme=theme)
    caption = inventory_caption_for_meta(meta, spot, metric="oi")

    expiry_options = [{"label": k, "value": k} for k in sorted(ladders.keys())]

    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        "Options inventory",
                        title=TERM_DEFINITIONS.get("inventory", ""),
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
                                id={"type": "flow-inv-expiry", "index": ticker},
                                options=expiry_options,
                                value=expiry,
                                clearable=False,
                                searchable=False,
                                className="sfa-flow-inv-expiry",
                                style={"minWidth": "130px", "fontSize": "12px"},
                            ),
                            dcc.RadioItems(
                                id={"type": "flow-inv-metric", "index": ticker},
                                options=[
                                    {"label": "Open interest", "value": "oi"},
                                    {"label": "Volume", "value": "vol"},
                                ],
                                value="oi",
                                inline=True,
                                className="sfa-flow-inv-metric",
                                style={
                                    "fontFamily": FONT_FAMILY,
                                    "fontSize": FONT_SIZES["xs"],
                                    "color": theme["text_secondary"],
                                },
                                inputStyle={"marginRight": "4px"},
                                labelStyle={"marginRight": "12px", "cursor": "pointer"},
                            ),
                        ],
                        className="sfa-flow-inv-controls",
                    ),
                ],
                className="sfa-flow-inv-header",
            ),
            dcc.Graph(
                id={"type": "flow-inv-graph", "index": ticker},
                figure=figure,
                config={"displayModeBar": False, "responsive": True},
                className="sfa-flow-inv-graph",
            ),
            html.P(
                caption,
                id={"type": "flow-inv-caption", "index": ticker},
                className="sfa-flow-inv-caption",
                style={
                    "fontFamily": FONT_FAMILY,
                    "fontSize": FONT_SIZES["xs"],
                    "color": theme["text_tertiary"],
                    "margin": "4px 0 0",
                    "lineHeight": 1.4,
                },
            ),
            html.P(
                INVENTORY_CAPTION,
                className="sfa-flow-inv-disclaimer",
                style={
                    "fontFamily": FONT_FAMILY,
                    "fontSize": "10px",
                    "color": theme["text_tertiary"],
                    "margin": "2px 0 8px",
                    "opacity": 0.85,
                },
            ),
        ],
        className="sfa-flow-inventory",
        style={"marginBottom": "10px"},
    )


def figure_from_report(
    report: Mapping[str, Any],
    *,
    expiry: str | None,
    metric: str,
    theme: dict,
) -> tuple[go.Figure, str]:
    """Rebuild figure + caption for callback updates."""
    ladders = report.get("strike_ladders") or {}
    meta_all = report.get("inventory_meta") or {}
    spot = float(report.get("spot") or 0)
    key = expiry or nearest_expiry(ladders)
    if not key or key not in ladders:
        return _empty_figure(theme, "No strike inventory"), "No inventory data."
    meta = meta_all.get(key) or {}
    fig = build_inventory_figure(ladders[key], spot, meta, metric=metric, theme=theme)
    caption = inventory_caption_for_meta(meta, spot, metric=metric)
    return fig, caption
