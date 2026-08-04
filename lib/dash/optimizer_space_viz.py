"""
Plotly / HTML builders for Optimizer Grid Search visuals.
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go
from dash import html

from lib.dash.dash_config import FONT_FAMILY, FONT_SIZES
from lib.walkforward.spaces import discretize_dimension


def build_combo_estimate_card(
    total: int,
    max_combos: int,
    theme: dict,
    *,
    space_keys: list[str] | None = None,
) -> html.Div:
    """Pill showing cartesian size vs hard cap."""
    within = int(total) <= int(max_combos)
    badge_class = "sfa-grid-estimate-ok" if within else "sfa-grid-estimate-over"
    badge_label = "within cap" if within else "over cap"
    keys_note = ""
    if space_keys:
        keys_note = f" · {len(space_keys)} dims"
    return html.Div(
        [
            html.Div(
                [
                    html.Span(f"{int(total):,} combos", className="sfa-grid-estimate-count"),
                    html.Span(
                        f"cap {int(max_combos):,}",
                        className="sfa-grid-estimate-cap",
                    ),
                    html.Span(badge_label, className=f"sfa-grid-estimate-badge {badge_class}"),
                ],
                className="sfa-grid-estimate-row",
            ),
            html.Div(
                f"{'Ready to run' if within else 'Narrow --params or raise max-combos'}{keys_note}",
                className="sfa-grid-estimate-hint",
                style={"color": theme["text_tertiary"]},
            ),
        ],
        className="sfa-grid-estimate",
    )


def _empty_figure(theme: dict, message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=theme["bg_panel"],
        plot_bgcolor=theme["bg_primary"],
        margin={"l": 40, "r": 12, "t": 8, "b": 36},
        font={"family": FONT_FAMILY, "size": 11, "color": theme["text_secondary"]},
        annotations=[{
            "text": message,
            "xref": "paper",
            "yref": "paper",
            "x": 0.5,
            "y": 0.5,
            "showarrow": False,
            "font": {"color": theme["text_tertiary"], "size": 12},
        }],
        xaxis={"visible": False},
        yaxis={"visible": False},
        height=200,
        showlegend=False,
    )
    return fig


def build_param_range_figure(
    space_slice: dict[str, dict[str, Any]] | None,
    theme: dict,
) -> go.Figure:
    """Horizontal bars from floor→ceiling for each selected search-space key."""
    space = space_slice or {}
    if not space:
        return _empty_figure(theme, "Select parameters to preview ranges")

    names: list[str] = []
    lows: list[float] = []
    spans: list[float] = []
    hover: list[str] = []

    for name, descriptor in space.items():
        kind = str(descriptor.get("type", "float")).lower()
        if kind == "categorical":
            choices = list(descriptor.get("choices") or [])
            names.append(name)
            lows.append(0.0)
            spans.append(float(max(len(choices), 1)))
            hover.append(f"{name}<br>choices: {', '.join(str(c) for c in choices)}")
            continue
        if kind not in {"int", "float"}:
            continue
        low = float(descriptor["low"])
        high = float(descriptor["high"])
        step = descriptor.get("step")
        try:
            n_vals = len(discretize_dimension(name, descriptor))
        except Exception:
            n_vals = 0
        names.append(name)
        lows.append(low)
        spans.append(max(high - low, 1e-9))
        step_txt = f", step={step}" if step is not None else ""
        hover.append(f"{name}<br>floor={low} → ceiling={high}{step_txt}<br>{n_vals} grid values")

    if not names:
        return _empty_figure(theme, "No numeric/categorical ranges to show")

    # Base (transparent offset) + span so bars start at floor.
    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=names,
        x=lows,
        orientation="h",
        marker={"color": "rgba(0,0,0,0)"},
        hoverinfo="skip",
        showlegend=False,
    ))
    fig.add_trace(go.Bar(
        y=names,
        x=spans,
        orientation="h",
        marker={"color": theme["accent_cyan"], "opacity": 0.75},
        text=hover,
        hovertemplate="%{text}<extra></extra>",
        showlegend=False,
    ))
    fig.update_layout(
        barmode="stack",
        paper_bgcolor=theme["bg_panel"],
        plot_bgcolor=theme["bg_primary"],
        margin={"l": 110, "r": 12, "t": 8, "b": 36},
        font={"family": FONT_FAMILY, "size": 11, "color": theme["text_secondary"]},
        xaxis={
            "title": "Value range",
            "gridcolor": theme["chart_grid"],
            "zeroline": False,
            "showline": True,
            "linecolor": theme["border_primary"],
        },
        yaxis={
            "autorange": "reversed",
            "gridcolor": theme["chart_grid"],
            "showline": True,
            "linecolor": theme["border_primary"],
        },
        height=max(160, 36 * len(names) + 50),
        showlegend=False,
    )
    return fig


def _numeric_keys(space_keys: list[str], trials: list[dict[str, Any]]) -> list[str]:
    if not trials:
        return []
    sample = trials[0].get("params") or {}
    out = []
    for key in space_keys:
        if key not in sample:
            continue
        val = sample[key]
        if isinstance(val, (int, float)) and not isinstance(val, bool):
            out.append(key)
    return out


def build_param_landscape_figure(
    trials: list[dict[str, Any]] | None,
    space_keys: list[str] | None,
    metric: str,
    theme: dict,
) -> go.Figure:
    """
    1 numeric dim → bar of metric vs param.
    2 numeric dims → heatmap of mean metric.
    Else → scatter of trial index vs metric.
    """
    rows = list(trials or [])
    keys = list(space_keys or [])
    if not rows:
        return _empty_figure(theme, "Run Grid Search to populate the landscape")

    metric_label = (metric or "score").capitalize()
    numeric = _numeric_keys(keys, rows)

    if len(numeric) == 1:
        key = numeric[0]
        xs = [float((r.get("params") or {}).get(key)) for r in rows]
        ys = [float(r.get("value", 0)) for r in rows]
        fig = go.Figure(go.Bar(
            x=xs,
            y=ys,
            marker={"color": theme["accent_blue"], "opacity": 0.8},
            hovertemplate=f"{key}=%{{x}}<br>{metric_label}=%{{y:.4f}}<extra></extra>",
        ))
        fig.update_layout(
            paper_bgcolor=theme["bg_panel"],
            plot_bgcolor=theme["bg_primary"],
            margin={"l": 48, "r": 12, "t": 8, "b": 40},
            font={"family": FONT_FAMILY, "size": 11, "color": theme["text_secondary"]},
            xaxis={"title": key, "gridcolor": theme["chart_grid"]},
            yaxis={"title": metric_label, "gridcolor": theme["chart_grid"]},
            height=220,
            showlegend=False,
        )
        return fig

    if len(numeric) >= 2:
        kx, ky = numeric[0], numeric[1]
        # Aggregate mean score on discrete grid cells.
        bucket: dict[tuple[Any, Any], list[float]] = {}
        for r in rows:
            p = r.get("params") or {}
            cell = (p.get(kx), p.get(ky))
            bucket.setdefault(cell, []).append(float(r.get("value", 0)))
        xs = sorted({c[0] for c in bucket})
        ys = sorted({c[1] for c in bucket})
        z = []
        for yv in ys:
            row_z = []
            for xv in xs:
                vals = bucket.get((xv, yv))
                row_z.append(sum(vals) / len(vals) if vals else None)
            z.append(row_z)
        fig = go.Figure(go.Heatmap(
            x=[str(v) for v in xs],
            y=[str(v) for v in ys],
            z=z,
            colorscale=[
                [0.0, theme["accent_red"]],
                [0.5, theme["bg_tertiary"]],
                [1.0, theme["accent_green"]],
            ],
            colorbar={"title": metric_label, "thickness": 12},
            hovertemplate=f"{kx}=%{{x}}<br>{ky}=%{{y}}<br>{metric_label}=%{{z:.4f}}<extra></extra>",
        ))
        fig.update_layout(
            paper_bgcolor=theme["bg_panel"],
            plot_bgcolor=theme["bg_primary"],
            margin={"l": 48, "r": 12, "t": 8, "b": 40},
            font={"family": FONT_FAMILY, "size": 11, "color": theme["text_secondary"]},
            xaxis={"title": kx},
            yaxis={"title": ky},
            height=240,
        )
        return fig

    # Fallback: trial index vs score
    xs = [int(r.get("index", i)) for i, r in enumerate(rows)]
    ys = [float(r.get("value", 0)) for r in rows]
    best_i = max(range(len(ys)), key=lambda i: ys[i]) if ys else 0
    fig = go.Figure()
    fig.add_trace(go.Scatter(
        x=xs,
        y=ys,
        mode="markers",
        marker={"size": 8, "color": theme["accent_blue"], "opacity": 0.75},
        name="Combos",
        hovertemplate=f"trial=%{{x}}<br>{metric_label}=%{{y:.4f}}<extra></extra>",
    ))
    if ys:
        fig.add_trace(go.Scatter(
            x=[xs[best_i]],
            y=[ys[best_i]],
            mode="markers",
            marker={
                "size": 14,
                "color": theme["accent_green"],
                "symbol": "star",
                "line": {"width": 1, "color": theme["text_primary"]},
            },
            name="Best",
            hovertemplate=f"best<br>{metric_label}=%{{y:.4f}}<extra></extra>",
        ))
    fig.update_layout(
        paper_bgcolor=theme["bg_panel"],
        plot_bgcolor=theme["bg_primary"],
        margin={"l": 48, "r": 12, "t": 8, "b": 40},
        font={"family": FONT_FAMILY, "size": 11, "color": theme["text_secondary"]},
        xaxis={"title": "Trial index", "gridcolor": theme["chart_grid"]},
        yaxis={"title": metric_label, "gridcolor": theme["chart_grid"]},
        height=220,
        showlegend=False,
    )
    return fig


def build_grid_progress(done: int, total: int, theme: dict, *, stopping: bool = False) -> html.Div:
    pct = 0 if total <= 0 else int(100 * done / total)
    label = "Stopping…" if stopping else f"Grid {done}/{total} ({pct}%)"
    return html.Div(
        [
            html.Div(label, style={
                "fontSize": FONT_SIZES["xs"],
                "color": theme["text_secondary"],
                "marginBottom": "4px",
            }),
            html.Div(
                className="sfa-grid-progress-bar",
                children=html.Div(
                    className="sfa-grid-progress-fill",
                    style={"width": f"{pct}%", "backgroundColor": theme["accent_blue"]},
                ),
            ),
        ],
        className="sfa-grid-progress",
    )
