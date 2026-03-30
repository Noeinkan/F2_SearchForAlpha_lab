"""
Shared overlay metadata and helpers for Plotly and TradingView chart builders.
"""

from __future__ import annotations

from typing import Dict, List

OVERLAY_KEYS = ('bollinger', 'sma', 'ema')


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
    specs: List[dict] = []

    if overlay_visibility.get('bollinger'):
        bollinger_specs = [
            ('BB_upper', 'BB UPPER', theme['accent_green']),
            ('BB_lower', 'BB LOWER', theme['accent_red']),
            ('BB_middle', 'BB MIDDLE', theme['text_secondary']),
        ]
        for column, label, color in bollinger_specs:
            if column in df.columns:
                specs.append({
                    'column': column,
                    'name': label,
                    'line': {'color': color, 'width': 1, 'dash': 'dot'},
                    'opacity': 0.7,
                })

    if overlay_visibility.get('sma'):
        sma_specs = [
            ('SMA_short', 'SMA SHORT', theme['accent_red']),
            ('SMA_medium', 'SMA MEDIUM', theme['accent_green']),
            ('SMA_long', 'SMA LONG', theme['accent_blue']),
            ('SMA_trend', 'SMA TREND', theme['accent_purple']),
        ]
        for column, label, color in sma_specs:
            if column in df.columns:
                specs.append({
                    'column': column,
                    'name': label,
                    'line': {'color': color, 'width': 1.5},
                    'opacity': 1.0,
                })

    if overlay_visibility.get('ema'):
        ema_specs = [
            ('EMA_short', 'EMA SHORT', theme['accent_orange']),
            ('EMA_medium', 'EMA MEDIUM', theme['accent_cyan']),
            ('EMA_long', 'EMA LONG', theme['accent_purple']),
        ]
        for column, label, color in ema_specs:
            if column in df.columns:
                specs.append({
                    'column': column,
                    'name': label,
                    'line': {'color': color, 'width': 1.5},
                    'opacity': 1.0,
                })

    return specs


def get_tv_overlay_specs(df, theme: dict, overlay_visibility: Dict[str, bool]) -> List[dict]:
    """Build TradingView line series specs for enabled overlays."""
    specs: List[dict] = []

    plotly_specs = get_plotly_overlay_specs(df, theme, overlay_visibility)
    for spec in plotly_specs:
        line = spec.get('line', {})
        specs.append({
            'column': spec['column'],
            'title': spec['name'],
            'color': line.get('color', theme['accent_blue']),
            'lineWidth': line.get('width', 1.5),
        })

    return specs
