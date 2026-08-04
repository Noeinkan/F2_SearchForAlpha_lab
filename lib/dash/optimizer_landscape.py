"""
Return vs Sharpe scatter for combinatorial optimizer results (Plotly).
"""

from __future__ import annotations

from typing import Any

import plotly.graph_objects as go

from lib.dash.dash_config import FONT_FAMILY


def build_return_sharpe_figure(
    records: list[dict[str, Any]] | None,
    theme: dict,
    *,
    highlight_index: int = 0,
) -> go.Figure:
    """Scatter of Total_Return_% vs Sharpe_Ratio; winner highlighted."""
    fig = go.Figure()
    rows = [
        r for r in (records or [])
        if r.get("Total_Return_%") is not None and r.get("Sharpe_Ratio") is not None
    ]
    if not rows:
        fig.update_layout(
            paper_bgcolor=theme["bg_panel"],
            plot_bgcolor=theme["bg_primary"],
            margin={"l": 40, "r": 12, "t": 8, "b": 36},
            font={"family": FONT_FAMILY, "size": 11, "color": theme["text_secondary"]},
            annotations=[{
                "text": "Run the optimizer to populate the landscape",
                "xref": "paper",
                "yref": "paper",
                "x": 0.5,
                "y": 0.5,
                "showarrow": False,
                "font": {"color": theme["text_tertiary"], "size": 12},
            }],
            xaxis={"visible": False},
            yaxis={"visible": False},
        )
        return fig

    xs = [float(r["Sharpe_Ratio"]) for r in rows]
    ys = [float(r["Total_Return_%"]) for r in rows]
    br = "<" + "br>"
    hover = [
        (
            f"Buy: {r.get('Buy_Signals', '')}{br}"
            f"Sell: {r.get('Sell_Signals', '')}{br}"
            f"Return: {float(r['Total_Return_%']):+.1f}%{br}"
            f"Sharpe: {float(r['Sharpe_Ratio']):.2f}{br}"
            f"DD: {float(r.get('Max_Drawdown_%') or 0):.1f}% · "
            f"Trades: {int(r.get('Trades') or 0)}"
        )
        for r in rows
    ]

    fig.add_trace(go.Scatter(
        x=xs,
        y=ys,
        mode="markers",
        marker={
            "size": 8,
            "color": theme["accent_blue"],
            "opacity": 0.75,
            "line": {"width": 0},
        },
        text=hover,
        hovertemplate="%{text}<extra></extra>",
        name="Combos",
    ))

    hi = max(0, min(highlight_index, len(rows) - 1))
    fig.add_trace(go.Scatter(
        x=[xs[hi]],
        y=[ys[hi]],
        mode="markers",
        marker={
            "size": 14,
            "color": theme["accent_green"],
            "symbol": "star",
            "line": {"width": 1, "color": theme["text_primary"]},
        },
        hovertemplate="%{text}<extra>Best</extra>",
        text=[hover[hi]],
        name="Best",
    ))

    fig.update_layout(
        paper_bgcolor=theme["bg_panel"],
        plot_bgcolor=theme["bg_primary"],
        margin={"l": 44, "r": 12, "t": 8, "b": 40},
        font={"family": FONT_FAMILY, "size": 11, "color": theme["text_secondary"]},
        xaxis={
            "title": "Sharpe",
            "gridcolor": theme["chart_grid"],
            "zeroline": True,
            "zerolinecolor": theme["border_primary"],
            "showline": True,
            "linecolor": theme["border_primary"],
        },
        yaxis={
            "title": "Return %",
            "gridcolor": theme["chart_grid"],
            "zeroline": True,
            "zerolinecolor": theme["border_primary"],
            "showline": True,
            "linecolor": theme["border_primary"],
        },
        showlegend=False,
        height=220,
    )
    return fig
