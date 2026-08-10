"""
Shared overlay metadata and helpers for Plotly and TradingView chart builders.

Overlay hues are Okabe–Ito identity colors (CVD-safe), not theme P&L greens/reds.
Period hierarchy is encoded with line width and dash, not directional meaning.
"""

from __future__ import annotations

from typing import Dict, List

OVERLAY_KEYS = ('bollinger', 'sma', 'ema')

# Okabe–Ito identity palette — theme-agnostic so bloomberg's amber-as-blue
# accent does not collide with SMA/EMA identity.
_BB = '#56B4E9'
_SMA_SHORT = '#56B4E9'
_SMA_MEDIUM = '#0072B2'
_SMA_LONG = '#009E73'
_SMA_TREND = '#8A8A8A'
_EMA_SHORT = '#F0E442'
_EMA_MEDIUM = '#E69F00'
_EMA_LONG = '#D55E00'

# LWC LineStyle: 0 solid, 1 dotted (mirrors assets/10-sfa-chart.js).
_LWC_SOLID = 0
_LWC_DOTTED = 1


def build_overlay_visibility(
    chart_elements: List[str] | None = None,
    legacy_flags: Dict[str, bool] | None = None,
) -> Dict[str, bool]:
    """Resolve overlay visibility from chart elements with legacy fallback flags."""
    visibility = {key: False for key in OVERLAY_KEYS}

    for key in chart_elements or []:
        if key in visibility:
            visibility[key] = True

    # Backward compatibility for legacy chart config keys.
    legacy_flags = legacy_flags or {}
    visibility['bollinger'] = visibility['bollinger'] or bool(legacy_flags.get('show_bollinger', False))
    visibility['sma'] = visibility['sma'] or bool(legacy_flags.get('show_sma', False))
    visibility['ema'] = visibility['ema'] or bool(legacy_flags.get('show_ema', False))

    return visibility


def get_plotly_overlay_specs(df, theme: dict, overlay_visibility: Dict[str, bool]) -> List[dict]:
    """Build plotly line trace specs for enabled overlays."""
    del theme  # identity palette is theme-agnostic (see module docstring)
    specs: List[dict] = []

    if overlay_visibility.get('bollinger'):
        bollinger_specs = [
            ('BB_upper', 'BB UPPER', _BB, 1, None),
            ('BB_lower', 'BB LOWER', _BB, 1, None),
            ('BB_middle', 'BB MIDDLE', _BB, 1, 'dot'),
        ]
        for column, label, color, width, dash in bollinger_specs:
            if column in df.columns:
                line = {'color': color, 'width': width}
                if dash:
                    line['dash'] = dash
                specs.append({
                    'column': column,
                    'name': label,
                    'line': line,
                    'opacity': 0.7,
                })

    if overlay_visibility.get('sma'):
        sma_specs = [
            ('SMA_short', 'SMA SHORT', _SMA_SHORT, 2, None),
            ('SMA_medium', 'SMA MEDIUM', _SMA_MEDIUM, 1.5, None),
            ('SMA_long', 'SMA LONG', _SMA_LONG, 1.2, None),
            ('SMA_trend', 'SMA TREND', _SMA_TREND, 1, 'dot'),
        ]
        for column, label, color, width, dash in sma_specs:
            if column in df.columns:
                line = {'color': color, 'width': width}
                if dash:
                    line['dash'] = dash
                specs.append({
                    'column': column,
                    'name': label,
                    'line': line,
                    'opacity': 1.0,
                })

    if overlay_visibility.get('ema'):
        ema_specs = [
            ('EMA_short', 'EMA SHORT', _EMA_SHORT, 2, None),
            ('EMA_medium', 'EMA MEDIUM', _EMA_MEDIUM, 1.5, None),
            ('EMA_long', 'EMA LONG', _EMA_LONG, 1.2, None),
        ]
        for column, label, color, width, dash in ema_specs:
            if column in df.columns:
                line = {'color': color, 'width': width}
                if dash:
                    line['dash'] = dash
                specs.append({
                    'column': column,
                    'name': label,
                    'line': line,
                    'opacity': 1.0,
                })

    return specs


def get_tv_overlay_specs(df, theme: dict, overlay_visibility: Dict[str, bool]) -> List[dict]:
    """Build TradingView line series specs for enabled overlays."""
    specs: List[dict] = []

    plotly_specs = get_plotly_overlay_specs(df, theme, overlay_visibility)
    for spec in plotly_specs:
        line = spec.get('line', {})
        dash = line.get('dash')
        dotted = dash in ('dot', 'dotted', 'dash')
        specs.append({
            'column': spec['column'],
            'title': spec['name'],
            'color': line.get('color', _BB),
            'lineWidth': line.get('width', 1.5),
            'lineStyle': _LWC_DOTTED if dotted else _LWC_SOLID,
            'style': 'dotted' if dotted else None,
        })

    return specs
