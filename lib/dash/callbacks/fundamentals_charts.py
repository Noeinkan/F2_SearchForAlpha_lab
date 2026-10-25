"""Growth band: one small line chart per metric (ROIC, Equity, EPS, ...)."""

from __future__ import annotations

from typing import Any, Sequence

from dash import dcc, html
import plotly.graph_objects as go

from lib.dash.dash_config import FONT_FAMILY
from lib.dash.flow_view import wrap_flow_diagram

# Payloads written before the rename (demo fixtures, old caches) still carry
# the long label; the card shows the short one either way.
CHART_DISPLAY_LABELS = {'Earning per share': 'EPS'}

# Above this many points even the sparse labels crowd (40 SEC quarters since
# ROADMAP 7.6), so they give way to the hover readout.
CHART_LABEL_MAX_POINTS = 12


def chart_display_label(label: str) -> str:
    return CHART_DISPLAY_LABELS.get(label, label)


def _chart_card(label: str, values: list[float | None], years: list[Any], theme: dict) -> html.Div:
    shown = chart_display_label(label)
    card = html.Div(
        [
            html.Div([
                html.Span(shown, className='sfa-fundamentals-chart-title'),
                html.Span(_latest_text(label, values), className='num sfa-fundamentals-chart-last'),
            ], className='sfa-fundamentals-chart-head'),
            dcc.Graph(
                figure=_metric_figure(label, values, years, theme),
                config={'displayModeBar': False, 'responsive': True},
                style={'height': 'clamp(150px, 19vh, 200px)'},
            ),
        ],
        style={
            'backgroundColor': theme['bg_panel'],
            'border': f'1px solid {theme["border_primary"]}',
            'padding': '6px',
            'minWidth': 0,
        },
        className='sfa-fundamentals-panel sfa-fundamentals-chart',
    )
    return wrap_flow_diagram(card, index=f'fundamentals-{label}', theme=theme)


def _latest_text(label: str, values: list[float | None]) -> str:
    """Most recent value, shown beside the card title."""
    for value in reversed(values or []):
        if value is not None:
            return _chart_text(value * 100 if label == 'ROIC' else value, label)
    return '--'


def _label_indices(values: Sequence[float | None]) -> set[int]:
    """Points worth a printed value: first, last, highest and lowest.

    Labelling every point stacked neighbours on top of each other
    (70.5% 71.0% 71.7% on AAPL's ROIC); the rest stay on hover.
    """
    present = [(i, v) for i, v in enumerate(values) if v is not None]
    if not present:
        return set()
    picks = {present[0][0], present[-1][0]}
    picks.add(max(present, key=lambda p: p[1])[0])
    picks.add(min(present, key=lambda p: p[1])[0])
    return picks


def _metric_figure(label: str, values: list[float | None], years: list[Any], theme: dict) -> go.Figure:
    fig = go.Figure()
    is_pct = label == 'ROIC'
    y_values = [value * 100 if is_pct and value is not None else value for value in values]
    labelled = len(y_values) <= CHART_LABEL_MAX_POINTS
    picks = _label_indices(y_values) if labelled else set()
    fig.add_trace(go.Scatter(
        x=years,
        y=y_values,
        mode='lines+markers+text' if labelled else 'lines+markers',
        line={'color': theme['accent_blue'], 'width': 2},
        marker={'size': 6 if labelled else 4, 'color': theme['accent_blue']},
        text=[_chart_text(v, label) if i in picks else '' for i, v in enumerate(y_values)] if labelled else None,
        textposition='top center',
        textfont={'size': 10, 'color': theme['text_primary']},
        cliponaxis=False,
        hovertemplate='%{x}: %{y:,.2f}' + ('%' if is_pct else '') + '<extra></extra>',
    ))
    _add_trendline(fig, years, y_values, theme)
    fig.update_layout(
        paper_bgcolor=theme['bg_panel'],
        plot_bgcolor=theme['bg_primary'],
        margin={'l': 40, 'r': 10, 't': 14, 'b': 24},
        font={'family': FONT_FAMILY, 'size': 11, 'color': theme['text_secondary']},
        xaxis={'gridcolor': theme['chart_grid'], 'showline': True, 'linecolor': theme['border_primary'],
               'type': 'category', 'nticks': 6},
        yaxis={'gridcolor': theme['chart_grid'], 'showline': True, 'linecolor': theme['border_primary'],
               'ticksuffix': '%' if is_pct else '', 'nticks': 5},
        showlegend=False,
    )
    return fig


def _add_trendline(fig: go.Figure, years: list[Any], values: list[float | None], theme: dict) -> None:
    pairs = [(index, value) for index, value in enumerate(values) if value is not None]
    if len(pairs) < 2:
        return
    x_values = [pair[0] for pair in pairs]
    y_values = [pair[1] for pair in pairs]
    slope, intercept = _linear_fit(x_values, y_values)
    fig.add_trace(go.Scatter(
        x=[years[index] for index in x_values],
        y=[slope * index + intercept for index in x_values],
        mode='lines',
        line={'color': theme['text_secondary'], 'width': 1.5, 'dash': 'dot'},
        hoverinfo='skip',
    ))


def _linear_fit(x_values: Sequence[float], y_values: Sequence[float]) -> tuple[float, float]:
    x_mean = sum(x_values) / len(x_values)
    y_mean = sum(y_values) / len(y_values)
    denominator = sum((x - x_mean) ** 2 for x in x_values)
    if denominator == 0:
        return 0.0, y_mean
    slope = sum((x - x_mean) * (y - y_mean) for x, y in zip(x_values, y_values)) / denominator
    return slope, y_mean - slope * x_mean


def _chart_text(value: float | None, label: str) -> str:
    if value is None:
        return ''
    if label == 'ROIC':
        return f'{value:.1f}%'
    return f'{value:,.0f}' if abs(value) >= 100 else f'{value:,.2f}'
