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
    "Open interest by strike — calls up, puts down. "
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


def hvl_from_ladder(ladder: Sequence[Mapping[str, Any]]) -> float | None:
    """Strike with max combined call+put volume; None if no volume."""
    if not ladder:
        return None
    best = max(
        ladder,
        key=lambda r: int(r.get("call_vol") or 0) + int(r.get("put_vol") or 0),
    )
    total = int(best.get("call_vol") or 0) + int(best.get("put_vol") or 0)
    return float(best["strike"]) if total > 0 else None


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
        height=320,
        showlegend=False,
    )
    return fig


def _level_shape(x: float, color: str, *, dash: str = "dash", width: float = 1.5) -> dict:
    return {
        "type": "line",
        "xref": "x",
        "x0": x,
        "x1": x,
        "yref": "paper",
        "y0": 0,
        "y1": 1,
        "line": {"color": color, "width": width, "dash": dash},
    }


def _level_annotation(x: float, text: str, color: str) -> dict:
    return {
        "xref": "x",
        "x": x,
        "yref": "paper",
        "y": 1.02,
        "text": text,
        "showarrow": False,
        "font": {"size": 9, "color": color, "family": FONT_FAMILY},
        "xanchor": "center",
        "yanchor": "bottom",
    }


def _legend_line_trace(name: str, color: str, *, dash: str = "dash") -> go.Scatter:
    """Invisible trace so level lines appear in the Plotly legend."""
    return go.Scatter(
        x=[None],
        y=[None],
        mode="lines",
        name=name,
        line={"color": color, "width": 1.5, "dash": dash},
        hoverinfo="skip",
        showlegend=True,
    )


def build_inventory_figure(
    ladder: Sequence[Mapping[str, Any]] | None,
    spot: float,
    meta: Mapping[str, Any] | None = None,
    *,
    metric: str = "oi",
    theme: dict | None = None,
) -> go.Figure:
    """Vertical bars: calls up (positive), puts down (negative); level lines on x."""
    theme = theme or {}
    rows = filter_ladder_window(list(ladder or []), float(spot or 0))
    if not rows:
        return _empty_figure(theme, "No strike inventory for this expiry")

    use_vol = str(metric).lower() in {"vol", "volume"}
    call_key = "call_vol" if use_vol else "call_oi"
    put_key = "put_vol" if use_vol else "put_oi"
    y_label = "Contract volume" if use_vol else "Open interest (contracts)"

    strikes = [r["strike"] for r in rows]
    call_vals = [float(r[call_key]) for r in rows]
    put_vals = [-float(r[put_key]) for r in rows]  # below zero

    green = theme.get("accent_green", "#3fb950")
    red = theme.get("accent_red", "#f85149")
    cyan = theme.get("accent_cyan", "#58a6ff")
    yellow = theme.get("accent_yellow", "#f0c674")
    white = theme.get("text_primary", "#e6edf3")
    text_sec = theme.get("text_secondary", "#8b949e")
    text_ter = theme.get("text_tertiary", "#6e7681")
    border = theme.get("border_primary", "#30363d")
    bg_plot = theme.get("bg_primary", "#0d1117")
    bg_paper = theme.get("bg_tertiary") or theme.get("bg_panel", "#161b22")

    hover_calls = [
        f"Strike ${s:,.2f}<br>Calls {('vol' if use_vol else 'OI')}: {v:,.0f}"
        for s, v in zip(strikes, call_vals)
    ]
    hover_puts = [
        f"Strike ${s:,.2f}<br>Puts {('vol' if use_vol else 'OI')}: {abs(v):,.0f}"
        for s, v in zip(strikes, put_vals)
    ]

    fig = go.Figure()
    fig.add_trace(go.Bar(
        x=strikes,
        y=put_vals,
        name="Puts",
        marker_color=red,
        hovertext=hover_puts,
        hoverinfo="text",
        width=None,
    ))
    fig.add_trace(go.Bar(
        x=strikes,
        y=call_vals,
        name="Calls",
        marker_color=green,
        hovertext=hover_calls,
        hoverinfo="text",
        width=None,
    ))

    meta = dict(meta or {})
    hvl = meta.get("hvl")
    if hvl is None:
        hvl = hvl_from_ladder(rows)
        if hvl is not None:
            meta["hvl"] = hvl

    shapes: list[dict] = []
    annotations: list[dict] = []

    def _add_level(
        value: Any,
        *,
        color: str,
        short: str,
        legend_name: str,
        dash: str = "dash",
        width: float = 1.5,
    ) -> None:
        try:
            x = float(value)
        except (TypeError, ValueError):
            return
        shapes.append(_level_shape(x, color, dash=dash, width=width))
        annotations.append(_level_annotation(x, short, color))
        fig.add_trace(_legend_line_trace(legend_name, color, dash=dash))

    if spot and spot > 0:
        _add_level(spot, color=yellow, short=f"{spot:,.0f}", legend_name="Spot", dash="dash")

    if meta.get("call_wall") is not None:
        _add_level(
            meta["call_wall"],
            color=red,
            short="CR",
            legend_name="Call Resistance",
            dash="dash",
        )
    if meta.get("put_wall") is not None:
        _add_level(
            meta["put_wall"],
            color=green,
            short="PS",
            legend_name="Put Support",
            dash="dash",
        )
    if meta.get("hvl") is not None:
        _add_level(
            meta["hvl"],
            color=white,
            short="HVL",
            legend_name="HVL",
            dash="dot",
            width=1.25,
        )
    if meta.get("max_pain") is not None:
        _add_level(
            meta["max_pain"],
            color=cyan,
            short="MP",
            legend_name="Max pain",
            dash="dot",
            width=1,
        )

    fig.update_layout(
        barmode="relative",
        paper_bgcolor=bg_paper,
        plot_bgcolor=bg_plot,
        margin={"l": 56, "r": 24, "t": 52, "b": 48},
        font={"family": FONT_FAMILY, "size": 11, "color": text_sec},
        legend={
            "orientation": "h",
            "yanchor": "bottom",
            "y": 1.08,
            "xanchor": "right",
            "x": 1,
            "font": {"size": 10},
        },
        shapes=shapes,
        annotations=annotations,
        height=360,
        bargap=0.15,
        xaxis={
            "title": {"text": "Strike", "font": {"size": 11, "color": text_ter}},
            "gridcolor": border,
            "tickfont": {"size": 10},
            "tickformat": ",.0f",
            "type": "linear",
        },
        yaxis={
            "title": {"text": y_label, "font": {"size": 11, "color": text_ter}},
            "zeroline": True,
            "zerolinecolor": border,
            "zerolinewidth": 1,
            "gridcolor": border,
            "tickfont": {"size": 10},
            "tickformat": ",.0f",
        },
        hovermode="closest",
    )

    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.02,
        y=0.98,
        text="CALLS",
        showarrow=False,
        font={"size": 10, "color": green, "family": FONT_FAMILY},
        xanchor="left",
        yanchor="top",
    )
    fig.add_annotation(
        xref="paper",
        yref="paper",
        x=0.02,
        y=0.02,
        text="PUTS",
        showarrow=False,
        font={"size": 10, "color": red, "family": FONT_FAMILY},
        xanchor="left",
        yanchor="bottom",
    )

    return fig


def inventory_caption_for_meta(
    meta: Mapping[str, Any] | None,
    spot: float,
    *,
    metric: str = "oi",
    ladder: Sequence[Mapping[str, Any]] | None = None,
) -> str:
    """One-line layman status under the chart."""
    parts: list[str] = []
    use_vol = str(metric).lower() in {"vol", "volume"}
    parts.append("Today's volume by strike." if use_vol else "Open interest by strike.")
    meta = dict(meta or {})
    if meta.get("hvl") is None and ladder is not None:
        hvl = hvl_from_ladder(ladder)
        if hvl is not None:
            meta["hvl"] = hvl

    cw = meta.get("call_wall")
    pw = meta.get("put_wall")
    hvl = meta.get("hvl")
    mp = meta.get("max_pain")
    if cw is not None:
        try:
            parts.append(f"Call Resistance ${float(cw):,.0f}.")
        except (TypeError, ValueError):
            pass
    if pw is not None:
        try:
            parts.append(f"Put Support ${float(pw):,.0f}.")
        except (TypeError, ValueError):
            pass
    if hvl is not None:
        try:
            parts.append(f"HVL ${float(hvl):,.0f}.")
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
    caption = inventory_caption_for_meta(meta, spot, metric="oi", ladder=ladder)

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
                        title=TERM_DEFINITIONS.get("oi_vs_volume", ""),
                    ),
                ],
                className="sfa-flow-inv-header",
            ),
            html.Div(
                [
                    html.Span(
                        "Spot",
                        title=TERM_DEFINITIONS.get("spot", ""),
                        className="sfa-flow-inv-level-tip",
                        style={"marginRight": "10px", "cursor": "help"},
                    ),
                    html.Span(
                        "Call Resistance",
                        title=TERM_DEFINITIONS.get("call_wall", ""),
                        className="sfa-flow-inv-level-tip",
                        style={"marginRight": "10px", "cursor": "help"},
                    ),
                    html.Span(
                        "Put Support",
                        title=TERM_DEFINITIONS.get("put_wall", ""),
                        className="sfa-flow-inv-level-tip",
                        style={"marginRight": "10px", "cursor": "help"},
                    ),
                    html.Span(
                        "HVL",
                        title=TERM_DEFINITIONS.get("hvl", ""),
                        className="sfa-flow-inv-level-tip",
                        style={"cursor": "help"},
                    ),
                ],
                className="sfa-flow-inv-level-tips",
                style={
                    "fontFamily": FONT_FAMILY,
                    "fontSize": FONT_SIZES["xs"],
                    "color": theme["text_tertiary"],
                    "marginBottom": "4px",
                },
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
    ladder = ladders[key]
    fig = build_inventory_figure(ladder, spot, meta, metric=metric, theme=theme)
    caption = inventory_caption_for_meta(meta, spot, metric=metric, ladder=ladder)
    return fig, caption
