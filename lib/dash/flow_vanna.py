"""OI Vanna Model (Delta Notional vs Strike) chart for the Flow Scanner."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import plotly.graph_objects as go
from dash import dcc, html

from lib.dash.dash_config import FONT_FAMILY, FONT_SIZES
from lib.dash.flow_glossary import (
    DISCLAIMER,
    TERM_DEFINITIONS,
    VANNA_PANEL,
    VANNA_REGION_TIPS,
)
from lib.dash.flow_inventory import nearest_expiry

VANNA_CAPTION = VANNA_PANEL["footer"]

_MUTED_PALETTE = ("#8b949e", "#6e7681", "#58a6ff", "#f0883e", "#3fb950")


def _fmt_notional(value: float) -> str:
    abs_v = abs(value)
    sign = "-" if value < 0 else ""
    if abs_v >= 1_000_000_000_000:
        return f"{sign}${abs_v / 1_000_000_000_000:.2f}T"
    if abs_v >= 1_000_000_000:
        return f"{sign}${abs_v / 1_000_000_000:.2f}B"
    if abs_v >= 1_000_000:
        return f"{sign}${abs_v / 1_000_000:.1f}M"
    if abs_v >= 1_000:
        return f"{sign}${abs_v / 1_000:.1f}K"
    return f"{sign}${abs_v:,.0f}"


def _notional_axis_scale(values: Sequence[float]) -> tuple[float, str]:
    """Return (divisor, unit suffix) for axis tick formatting."""
    peak = max((abs(float(v)) for v in values), default=0.0)
    if peak >= 1_000_000_000_000:
        return 1_000_000_000_000.0, "T"
    if peak >= 1_000_000_000:
        return 1_000_000_000.0, "B"
    if peak >= 1_000_000:
        return 1_000_000.0, "M"
    if peak >= 1_000:
        return 1_000.0, "K"
    return 1.0, ""


def _empty_figure(theme: dict, message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=theme.get("bg_tertiary") or theme.get("bg_panel", "#161b22"),
        plot_bgcolor=theme.get("bg_primary", "#0d1117"),
        margin={"l": 64, "r": 24, "t": 36, "b": 48},
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
        height=300,
        showlegend=False,
    )
    return fig


def build_vanna_figure(
    vanna_model: Mapping[str, Any] | None,
    spot: float,
    active_expiries: Sequence[str] | None,
    *,
    theme: dict | None = None,
) -> go.Figure:
    """Multi-expiry Delta Notional vs Strike lines; nearest active uses accent."""
    theme = theme or {}
    model = dict(vanna_model or {})
    if not model:
        return _empty_figure(theme, "No vanna model for this scan")

    active = [str(e) for e in (active_expiries or []) if str(e) in model]
    if not active:
        return _empty_figure(theme, "Select an expiry to display")

    nearest = nearest_expiry({k: model[k] for k in active})
    all_vals: list[float] = []
    for key in active:
        curve = model.get(key) or {}
        all_vals.extend(float(v) for v in (curve.get("delta_notional") or []))
    divisor, unit = _notional_axis_scale(all_vals)
    y_title = f"Delta Notional (${unit})" if unit else "Delta Notional ($)"

    bg_paper = theme.get("bg_tertiary") or theme.get("bg_panel", "#161b22")
    bg_plot = theme.get("bg_primary", "#0d1117")
    text_sec = theme.get("text_secondary", "#8b949e")
    text_ter = theme.get("text_tertiary", "#6e7681")
    border = theme.get("border_primary", "#30363d")
    accent = theme.get("accent_purple") or theme.get("accent_cyan") or "#a371f7"
    spot_color = theme.get("accent_yellow") or "#f0c674"

    fig = go.Figure()
    muted_i = 0
    for key in sorted(active):
        curve = model.get(key) or {}
        strikes = [float(s) for s in (curve.get("strikes") or [])]
        raw = [float(v) for v in (curve.get("delta_notional") or [])]
        if not strikes or len(strikes) != len(raw):
            continue
        ys = [v / divisor for v in raw]
        is_primary = key == nearest
        color = accent if is_primary else _MUTED_PALETTE[muted_i % len(_MUTED_PALETTE)]
        if not is_primary:
            muted_i += 1
        fig.add_trace(
            go.Scatter(
                x=strikes,
                y=ys,
                mode="lines",
                name=key,
                line={
                    "color": color,
                    "width": 2.5 if is_primary else 1.5,
                    "dash": "solid" if is_primary else "dot",
                },
                opacity=1.0 if is_primary else 0.65,
                hovertemplate=(
                    f"{key}<br>Strike %{{x:,.0f}}<br>"
                    "Delta Notional %{customdata}<extra></extra>"
                ),
                customdata=[_fmt_notional(v) for v in raw],
            )
        )

    if not fig.data:
        return _empty_figure(theme, "No vanna model for this scan")

    shapes: list[dict] = []
    annotations: list[dict] = []
    if spot and spot > 0:
        shapes.append({
            "type": "line",
            "x0": spot,
            "x1": spot,
            "y0": 0,
            "y1": 1,
            "yref": "paper",
            "line": {"color": spot_color, "width": 1.5, "dash": "dash"},
        })
        annotations.append({
            "x": spot,
            "y": 1.02,
            "yref": "paper",
            "text": "Spot",
            "showarrow": False,
            "font": {"size": 10, "color": spot_color, "family": FONT_FAMILY},
            "xanchor": "center",
        })

    fig.update_layout(
        paper_bgcolor=bg_paper,
        plot_bgcolor=bg_plot,
        margin={"l": 64, "r": 24, "t": 40, "b": 48},
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
        height=320,
        xaxis={
            "title": {"text": "Strike", "font": {"size": 11, "color": text_ter}},
            "gridcolor": border,
            "tickfont": {"size": 10},
            "tickformat": ",.0f",
            "zeroline": False,
        },
        yaxis={
            "title": {"text": y_title, "font": {"size": 11, "color": text_ter}},
            "gridcolor": border,
            "tickfont": {"size": 10},
            "zeroline": True,
            "zerolinecolor": border,
            "zerolinewidth": 1,
        },
        hovermode="closest",
    )
    return fig


def vanna_caption_for_model(
    vanna_model: Mapping[str, Any] | None,
    spot: float,
    active_expiries: Sequence[str] | None,
) -> str:
    """One-line status under the chart."""
    model = dict(vanna_model or {})
    active = [str(e) for e in (active_expiries or []) if str(e) in model]
    parts = ["OI Vanna Model — estimated dealer delta notional vs strike."]
    if active:
        nearest = nearest_expiry({k: model[k] for k in active})
        if nearest:
            parts.append(f"Primary {nearest}.")
        if len(active) > 1:
            parts.append(f"{len(active)} expiries overlaid.")
    if spot and spot > 0:
        parts.append(f"Spot ${float(spot):,.2f}.")
    parts.append("Dealer short-OI heuristic.")
    return " ".join(parts)


def render_vanna_panel(report: Mapping[str, Any], theme: dict) -> html.Div | None:
    """Expiry checklist + Plotly Vanna Model chart for one ticker report."""
    model = report.get("vanna_model") or {}
    if not model:
        return None

    ticker = str(report.get("ticker") or "UNK").upper()
    spot = float(report.get("spot") or 0)
    expiry_keys = sorted(str(k) for k in model.keys())
    if not expiry_keys:
        return None

    # Default: all expiries visible; nearest is primary accent in the figure.
    active = list(expiry_keys)
    figure = build_vanna_figure(model, spot, active, theme=theme)
    caption = vanna_caption_for_model(model, spot, active)

    tip_row = html.Div(
        [
            html.Span(
                "Trough",
                title=VANNA_REGION_TIPS.get("trough", ""),
                className="sfa-flow-vanna-tip",
                style={"marginRight": "10px", "cursor": "help"},
            ),
            html.Span(
                "Left wing",
                title=VANNA_REGION_TIPS.get("left_wing", ""),
                className="sfa-flow-vanna-tip",
                style={"marginRight": "10px", "cursor": "help"},
            ),
            html.Span(
                "Right wing",
                title=VANNA_REGION_TIPS.get("right_wing", ""),
                className="sfa-flow-vanna-tip",
                style={"cursor": "help"},
            ),
        ],
        className="sfa-flow-vanna-tips",
        style={
            "fontFamily": FONT_FAMILY,
            "fontSize": FONT_SIZES["xs"],
            "color": theme["text_tertiary"],
            "marginBottom": "4px",
        },
    )

    bullets = [
        html.Li(
            b,
            style={"marginBottom": "2px"},
        )
        for b in VANNA_PANEL.get("bullets", ())
    ]

    return html.Div(
        [
            html.Div(
                [
                    html.Div(
                        [
                            html.Span(
                                VANNA_PANEL["title"],
                                title=TERM_DEFINITIONS.get("vanna_flow", ""),
                                style={
                                    "fontFamily": FONT_FAMILY,
                                    "fontSize": FONT_SIZES["sm"],
                                    "fontWeight": 600,
                                    "color": theme["text_primary"],
                                },
                            ),
                            html.Span(
                                VANNA_PANEL.get("subtitle", ""),
                                title=TERM_DEFINITIONS.get("delta_notional", ""),
                                style={
                                    "display": "block",
                                    "fontFamily": FONT_FAMILY,
                                    "fontSize": FONT_SIZES["xs"],
                                    "color": theme["text_tertiary"],
                                    "marginTop": "2px",
                                },
                            ),
                        ],
                    ),
                    html.Div(
                        dcc.Checklist(
                            id={"type": "flow-vanna-expiry", "index": ticker},
                            options=[{"label": k, "value": k} for k in expiry_keys],
                            value=active,
                            inline=True,
                            className="sfa-flow-vanna-expiry",
                            style={
                                "fontFamily": FONT_FAMILY,
                                "fontSize": FONT_SIZES["xs"],
                                "color": theme["text_secondary"],
                            },
                            inputStyle={"marginRight": "4px"},
                            labelStyle={"marginRight": "12px", "cursor": "pointer"},
                        ),
                        title=TERM_DEFINITIONS.get("dealer_hedging", ""),
                    ),
                ],
                className="sfa-flow-vanna-header",
            ),
            html.P(
                VANNA_PANEL.get("caption", ""),
                title=TERM_DEFINITIONS.get("vanna", ""),
                style={
                    "fontFamily": FONT_FAMILY,
                    "fontSize": FONT_SIZES["xs"],
                    "color": theme["text_secondary"],
                    "margin": "4px 0 6px",
                    "lineHeight": 1.4,
                    "maxWidth": "72ch",
                },
            ),
            tip_row,
            dcc.Graph(
                id={"type": "flow-vanna-graph", "index": ticker},
                figure=figure,
                config={"displayModeBar": False, "responsive": True},
                className="sfa-flow-vanna-graph",
            ),
            html.Ul(
                bullets,
                style={
                    "fontFamily": FONT_FAMILY,
                    "fontSize": FONT_SIZES["xs"],
                    "color": theme["text_tertiary"],
                    "margin": "6px 0 4px",
                    "paddingLeft": "18px",
                    "lineHeight": 1.4,
                    "maxWidth": "72ch",
                },
            ),
            html.P(
                caption,
                id={"type": "flow-vanna-caption", "index": ticker},
                className="sfa-flow-vanna-caption",
                style={
                    "fontFamily": FONT_FAMILY,
                    "fontSize": FONT_SIZES["xs"],
                    "color": theme["text_tertiary"],
                    "margin": "4px 0 0",
                    "lineHeight": 1.4,
                },
            ),
            html.P(
                VANNA_CAPTION or DISCLAIMER,
                className="sfa-flow-vanna-disclaimer",
                style={
                    "fontFamily": FONT_FAMILY,
                    "fontSize": "10px",
                    "color": theme["text_tertiary"],
                    "margin": "2px 0 8px",
                    "opacity": 0.85,
                },
            ),
        ],
        className="sfa-flow-vanna",
        style={"marginBottom": "10px"},
    )


def figure_from_vanna_report(
    report: Mapping[str, Any],
    *,
    active_expiries: Sequence[str] | None,
    theme: dict,
) -> tuple[go.Figure, str]:
    """Rebuild figure + caption for callback updates."""
    model = report.get("vanna_model") or {}
    spot = float(report.get("spot") or 0)
    if not model:
        return _empty_figure(theme, "No vanna model"), "No vanna data."
    active = list(active_expiries) if active_expiries else sorted(model.keys())
    fig = build_vanna_figure(model, spot, active, theme=theme)
    caption = vanna_caption_for_model(model, spot, active)
    return fig, caption
