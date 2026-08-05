"""Estimated Net GEX / DEX strike chart for the Flow Scanner."""

from __future__ import annotations

from typing import Any, Mapping, Sequence

import plotly.graph_objects as go
from dash import dcc, html

from lib.dash.dash_config import FONT_FAMILY, FONT_SIZES
from lib.dash.flow_glossary import DISCLAIMER, GEX_PANEL, TERM_DEFINITIONS
from lib.dash.flow_inventory import STRIKE_WINDOW_PCT, filter_ladder_window
from lib.options.greeks import ALL_EXPIRIES_KEY

GEX_CAPTION = GEX_PANEL["caption"]


def default_gex_expiry(ladders: Mapping[str, Any] | None) -> str | None:
    """Prefer All Expirations when present; else nearest dated expiry."""
    if not ladders:
        return None
    if ALL_EXPIRIES_KEY in ladders:
        return ALL_EXPIRIES_KEY
    keys = sorted(str(k) for k in ladders.keys() if k != ALL_EXPIRIES_KEY)
    return keys[0] if keys else None


def _fmt_gex(value: float) -> str:
    abs_v = abs(value)
    sign = "-" if value < 0 else ""
    if abs_v >= 1_000_000_000:
        return f"{sign}{abs_v / 1_000_000_000:.1f}B"
    if abs_v >= 1_000_000:
        return f"{sign}{abs_v / 1_000_000:.1f}M"
    if abs_v >= 1_000:
        return f"{sign}{abs_v / 1_000:.1f}K"
    return f"{value:,.0f}"


def _empty_figure(theme: dict, message: str) -> go.Figure:
    fig = go.Figure()
    fig.update_layout(
        paper_bgcolor=theme.get("bg_tertiary") or theme.get("bg_panel", "#161b22"),
        plot_bgcolor=theme.get("bg_primary", "#0d1117"),
        margin={"l": 56, "r": 80, "t": 28, "b": 40},
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


def _filter_gex_window(
    ladder: Sequence[Mapping[str, Any]],
    spot: float,
    window_pct: float = STRIKE_WINDOW_PCT,
) -> list[dict]:
    """Reuse inventory windowing; keep GEX fields."""
    # filter_ladder_window only preserves OI/vol keys — re-join from source.
    windowed = filter_ladder_window(
        [
            {
                "strike": float(r["strike"]),
                "call_oi": int(r.get("total_oi") or 0),
                "put_oi": 0,
                "call_vol": int(r.get("call_vol") or 0),
                "put_vol": int(r.get("put_vol") or 0),
            }
            for r in ladder
        ],
        spot,
        window_pct,
    )
    if not windowed:
        return []
    by_strike = {float(r["strike"]): r for r in ladder}
    out: list[dict] = []
    for w in windowed:
        src = by_strike.get(float(w["strike"]))
        if src is None:
            continue
        out.append({
            "strike": float(src["strike"]),
            "net_gex": float(src.get("net_gex") or 0),
            "call_gex": float(src.get("call_gex") or 0),
            "put_gex": float(src.get("put_gex") or 0),
            "net_dex": float(src.get("net_dex") or 0),
            "call_vol": int(src.get("call_vol") or 0),
            "put_vol": int(src.get("put_vol") or 0),
            "total_oi": int(src.get("total_oi") or 0),
        })
    return out


def build_gex_figure(
    ladder: Sequence[Mapping[str, Any]] | None,
    spot: float,
    meta: Mapping[str, Any] | None = None,
    *,
    theme: dict | None = None,
) -> go.Figure:
    """Horizontal net-GEX bars + cumulative GEX/DEX profiles + level lines."""
    theme = theme or {}
    rows = _filter_gex_window(list(ladder or []), float(spot or 0))
    if not rows:
        return _empty_figure(theme, "No GEX data for this expiry")

    green = theme.get("accent_green", "#3fb950")
    red = theme.get("accent_red", "#f85149")
    yellow = theme.get("accent_yellow", "#f0c674")
    orange = theme.get("accent_orange", "#f0883e")
    white = theme.get("text_primary", "#e6edf3")
    text_sec = theme.get("text_secondary", "#8b949e")
    text_ter = theme.get("text_tertiary", "#6e7681")
    border = theme.get("border_primary", "#30363d")
    bg_plot = theme.get("bg_primary", "#0d1117")
    bg_paper = theme.get("bg_tertiary") or theme.get("bg_panel", "#161b22")

    strikes = [r["strike"] for r in rows]
    net_gex = [r["net_gex"] for r in rows]
    pos_x = [v if v > 0 else 0.0 for v in net_gex]
    neg_x = [v if v < 0 else 0.0 for v in net_gex]

    cum_gex: list[float] = []
    cum_dex: list[float] = []
    g_run = 0.0
    d_run = 0.0
    for r in rows:
        g_run += float(r["net_gex"])
        d_run += float(r["net_dex"])
        cum_gex.append(g_run)
        cum_dex.append(d_run)

    fig = go.Figure()
    fig.add_trace(go.Bar(
        y=strikes,
        x=pos_x,
        orientation="h",
        name="Positive GEX",
        marker_color=green,
        hovertext=[
            f"Strike ${s:,.2f}<br>Net GEX {_fmt_gex(v)}"
            for s, v in zip(strikes, net_gex)
        ],
        hoverinfo="text",
        width=0.7,
    ))
    fig.add_trace(go.Bar(
        y=strikes,
        x=neg_x,
        orientation="h",
        name="Negative GEX",
        marker_color=red,
        hovertext=[
            f"Strike ${s:,.2f}<br>Net GEX {_fmt_gex(v)}"
            for s, v in zip(strikes, net_gex)
        ],
        hoverinfo="text",
        width=0.7,
        showlegend=True,
    ))
    fig.add_trace(go.Scatter(
        y=strikes,
        x=cum_gex,
        mode="lines",
        name="GEX Profile",
        line={"color": yellow, "width": 2},
        hovertext=[
            f"Strike ${s:,.2f}<br>Cum GEX {_fmt_gex(v)}"
            for s, v in zip(strikes, cum_gex)
        ],
        hoverinfo="text",
    ))
    fig.add_trace(go.Scatter(
        y=strikes,
        x=cum_dex,
        mode="lines",
        name="DEX Profile",
        line={"color": orange, "width": 2},
        hovertext=[
            f"Strike ${s:,.2f}<br>Cum DEX {_fmt_gex(v)}"
            for s, v in zip(strikes, cum_dex)
        ],
        hoverinfo="text",
    ))

    shapes: list[dict] = []
    annotations: list[dict] = []

    def _hline(y: float, color: str, label: str, dash: str = "dash") -> None:
        shapes.append({
            "type": "line",
            "xref": "paper",
            "x0": 0,
            "x1": 1,
            "yref": "y",
            "y0": y,
            "y1": y,
            "line": {"color": color, "width": 1.4, "dash": dash},
        })
        annotations.append({
            "xref": "paper",
            "x": 1.01,
            "y": y,
            "yref": "y",
            "text": label,
            "showarrow": False,
            "font": {"size": 9, "color": color, "family": FONT_FAMILY},
            "xanchor": "left",
        })

    meta = meta or {}
    if spot and spot > 0:
        _hline(float(spot), white, f"Spot {spot:,.0f}")

    for key, color, short in (
        ("call_resistance", red, "CR"),
        ("put_support", green, "PS"),
        ("hvl", yellow, "HVL"),
    ):
        raw = meta.get(key)
        if raw is None:
            continue
        try:
            level = float(raw)
        except (TypeError, ValueError):
            continue
        _hline(level, color, f"{short} {level:,.0f}")

    n = len(strikes)
    height = max(300, min(620, 52 + n * 14))

    fig.update_layout(
        barmode="overlay",
        paper_bgcolor=bg_paper,
        plot_bgcolor=bg_plot,
        margin={"l": 56, "r": 88, "t": 40, "b": 44},
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
            "title": {"text": "GEX (est.)", "font": {"size": 11, "color": text_ter}},
            "zeroline": True,
            "zerolinecolor": border,
            "zerolinewidth": 1,
            "gridcolor": border,
            "tickfont": {"size": 10},
            "tickformat": "~s",
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
    return fig


def gex_caption_for_meta(
    meta: Mapping[str, Any] | None,
    spot: float,
) -> str:
    """One-line status under the GEX chart."""
    parts = ["Estimated Net GEX by strike (BS from Yahoo IV × OI)."]
    meta = meta or {}
    for key, label in (
        ("call_resistance", "Call resistance"),
        ("put_support", "Put support"),
        ("hvl", "HVL"),
    ):
        raw = meta.get(key)
        if raw is None:
            continue
        try:
            parts.append(f"{label} ${float(raw):,.0f}.")
        except (TypeError, ValueError):
            pass
    if spot and spot > 0:
        parts.append(f"Spot ${float(spot):,.2f}.")
    parts.append("Not a vendor GEX feed.")
    return " ".join(parts)


def render_gex_panel(report: Mapping[str, Any], theme: dict) -> html.Div | None:
    """Expiry control + Plotly Net GEX chart for one ticker report."""
    ladders = report.get("gex_ladders") or {}
    if not ladders:
        return None

    ticker = str(report.get("ticker") or "UNK").upper()
    spot = float(report.get("spot") or 0)
    meta_all = report.get("gex_meta") or {}
    expiry = default_gex_expiry(ladders)
    if not expiry:
        return None

    ladder = ladders.get(expiry) or []
    meta = meta_all.get(expiry) or {}
    figure = build_gex_figure(ladder, spot, meta, theme=theme)
    caption = gex_caption_for_meta(meta, spot)

    dated = sorted(k for k in ladders.keys() if k != ALL_EXPIRIES_KEY)
    expiry_options: list[dict[str, str]] = []
    if ALL_EXPIRIES_KEY in ladders:
        expiry_options.append({"label": "All expirations", "value": ALL_EXPIRIES_KEY})
    expiry_options.extend({"label": k, "value": k} for k in dated)

    return html.Div(
        [
            html.Div(
                [
                    html.Span(
                        GEX_PANEL["title"],
                        title=TERM_DEFINITIONS.get("net_gex", ""),
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
                                id={"type": "flow-gex-expiry", "index": ticker},
                                options=expiry_options,
                                value=expiry,
                                clearable=False,
                                searchable=False,
                                className="sfa-flow-gex-expiry",
                                style={"minWidth": "150px", "fontSize": "12px"},
                            ),
                        ],
                        className="sfa-flow-gex-controls",
                    ),
                ],
                className="sfa-flow-gex-header",
            ),
            dcc.Graph(
                id={"type": "flow-gex-graph", "index": ticker},
                figure=figure,
                config={"displayModeBar": False, "responsive": True},
                className="sfa-flow-gex-graph",
            ),
            html.P(
                caption,
                id={"type": "flow-gex-caption", "index": ticker},
                className="sfa-flow-gex-caption",
                style={
                    "fontFamily": FONT_FAMILY,
                    "fontSize": FONT_SIZES["xs"],
                    "color": theme["text_tertiary"],
                    "margin": "4px 0 0",
                    "lineHeight": 1.4,
                },
            ),
            html.P(
                GEX_CAPTION,
                className="sfa-flow-gex-disclaimer",
                title=TERM_DEFINITIONS.get("estimated_greeks", DISCLAIMER),
                style={
                    "fontFamily": FONT_FAMILY,
                    "fontSize": "10px",
                    "color": theme["text_tertiary"],
                    "margin": "2px 0 8px",
                    "opacity": 0.85,
                },
            ),
        ],
        className="sfa-flow-gex",
        style={"marginBottom": "10px"},
    )


def figure_from_gex_report(
    report: Mapping[str, Any],
    *,
    expiry: str | None,
    theme: dict,
) -> tuple[go.Figure, str]:
    """Rebuild figure + caption for callback updates."""
    ladders = report.get("gex_ladders") or {}
    meta_all = report.get("gex_meta") or {}
    spot = float(report.get("spot") or 0)
    key = expiry or default_gex_expiry(ladders)
    if not key or key not in ladders:
        return _empty_figure(theme, "No GEX data"), "No GEX data."
    meta = meta_all.get(key) or {}
    fig = build_gex_figure(ladders[key], spot, meta, theme=theme)
    caption = gex_caption_for_meta(meta, spot)
    return fig, caption
