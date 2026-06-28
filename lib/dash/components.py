"""
Dashboard UI Components
Reusable component builders for the trading dashboard.
"""

from typing import Any

from dash import dcc, html
import dash_bootstrap_components as dbc

from lib.dash.dash_config import (
    FONT_SIZES, FONT_FAMILY, FONT_WEIGHT_NUMERIC, BORDER_RADIUS, get_theme
)
from lib.dash.styles import get_styles


def _normalize_children(children: Any) -> list[Any]:
    """Return Dash children as a list without splitting strings into characters."""
    if children is None:
        return []
    if isinstance(children, (list, tuple)):
        return list(children)
    return [children]


def bloomberg_section(
    title: Any,
    children: Any,
    *,
    collapsible: bool = False,
    accent_dot: bool = False,
    open: bool = True,
    summary: Any = None,
    theme: dict = None,
    body_style: dict | None = None,
    className: str = '',
) -> html.Div:
    """Build a Bloomberg-style section container, optionally collapsible."""
    if theme is None:
        theme = get_theme()

    title_node = title if hasattr(title, 'to_plotly_json') else html.Span(title)
    title_row = html.Div(
        [
            html.Div(
                [
                    html.Span(className='dot dot-amber') if accent_dot else None,
                    title_node,
                ],
                style={'display': 'flex', 'alignItems': 'center', 'gap': '6px'}
            ),
            html.Span(summary, className='num muted') if summary is not None else None,
        ],
        style={
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
            'gap': '8px',
            'width': '100%',
        }
    )
    body = html.Div(_normalize_children(children), className='bbg-section-body', style=body_style or {})
    section_class = 'bbg-section'
    if open:
        section_class += ' expanded'
    if className:
        section_class += f' {className}'

    if collapsible:
        return html.Details(
            [html.Summary(title_row, className='bbg-section-header'), body],
            open=open,
            className=section_class,
        )

    return html.Div([
        html.Div(title_row, className='bbg-section-header'),
        body,
    ], className=section_class)


def kpi_cell(
    label: str,
    value: str,
    *,
    delta: str | None = None,
    delta_color: str | None = None,
    mono: bool = True,
    theme: dict = None,
    info_text: str | None = None,
    is_positive: bool | None = None,
) -> html.Div:
    """Build a terminal-style KPI cell.

    Phase 4: never rely on color alone for P&L. Pass ``is_positive`` to
    enable both the green/red color and a redundant ▲/▼ glyph plus a
    sign on the value. The delta row is always text-based (e.g.
    "ROBUST" / "WEAK", "ABOVE 50%" / "BELOW 50%") so it already carries
    the state by itself; this addition protects the value column.
    """
    if theme is None:
        theme = get_theme()

    value_style = {
        'color': theme['text_primary'],
        'fontWeight': '600',
    }
    if mono:
        value_style.update({
            'fontFamily': FONT_FAMILY,
            'fontVariantNumeric': 'tabular-nums',
            'fontWeight': FONT_WEIGHT_NUMERIC,
        })

    if is_positive is True:
        value_style['color'] = theme['accent_green']
        # Strip a single leading sign so we don't render "+" twice when
        # the caller already added one (e.g. f"{total_return:+.2f}%").
        raw = str(value).lstrip()
        if raw[:1] in ('+', '-'):
            value_str = f"\u25b2 {raw[1:].lstrip()}"
        else:
            value_str = f"\u25b2 {raw}"
    elif is_positive is False:
        value_style['color'] = theme['accent_red']
        raw = str(value).lstrip()
        if raw[:1] in ('+', '-'):
            value_str = f"\u25bc {raw[1:].lstrip()}"
        else:
            value_str = f"\u25bc {raw}"
    else:
        value_str = value

    delta_style = {
        'color': delta_color or theme['text_secondary'],
        'fontFamily': FONT_FAMILY,
        'fontVariantNumeric': 'tabular-nums',
    }

    return html.Div(
        [
            html.Div(label, className='bbg-kpi-label'),
            html.Div(value_str, className='bbg-kpi-value', style=value_style),
            html.Div(delta or ' ', className='bbg-kpi-delta', style=delta_style),
        ],
        className='bbg-kpi',
        title=info_text or None,
    )


def ticker_pill(
    label: str,
    value: Any,
    *,
    color: str = 'neutral',
    value_id: str | None = None,
    className: str = '',
) -> html.Div:
    """Build a compact pill for counters and tape-style metrics."""
    pill_class = 'bbg-pill'
    if color in {'up', 'down', 'amber'}:
        pill_class += f' {color}'
    if className:
        pill_class += f' {className}'
    value_props = {'className': 'bbg-pill-value num'}
    if value_id is not None:
        value_props['id'] = value_id
    return html.Div(
        [
            html.Span(label),
            html.Span(value, **value_props),
        ],
        className=pill_class,
    )


def dense_input(
    *,
    id: str,
    value: Any = None,
    type: str = 'text',
    placeholder: str | None = None,
    style: dict | None = None,
    className: str = '',
    **kwargs,
) -> dcc.Input:
    """Build a dense monospace input with the shared Bloomberg styling."""
    input_class = 'bbg-input'
    if className:
        input_class += f' {className}'
    return dcc.Input(
        id=id,
        value=value,
        type=type,
        placeholder=placeholder,
        className=input_class,
        style=style or {},
        **kwargs,
    )


def build_metric_card(
    label: str,
    value: str,
    is_positive: bool = None,
    theme: dict = None,
    animated: bool = True,
    info_text: str = None
) -> html.Div:
    """
    Build a metric display card with optional animation.

    Phase 4: never rely on color alone. When ``is_positive`` is set we
    prepend an arrow (▲ for positive, ▼ for negative) so the P&L
    direction is also conveyed by shape, not just hue. This is critical
    for users with red/green color-vision deficiency and survives
    black-and-white printouts.

    Args:
        label: Metric label text
        value: Metric value text
        is_positive: True for green, False for red, None for neutral
        theme: Theme configuration dict
        animated: Whether to apply animation class

    Returns:
        html.Div containing the metric card
    """
    if theme is None:
        theme = get_theme()

    styles = get_styles(theme)
    value_style = styles['metric_value'].copy()

    if is_positive is not None:
        if is_positive:
            value_style.update(styles['metric_positive'])
            # Phase 4: redundant sign — never rely on color alone for P&L.
            # The existing value text is already prefixed with a sign
            # (e.g. "+15%"); we add an up-arrow so the direction is
            # communicated by glyph + sign + color.
            arrow_prefix = '\u25b2'  # ▲
        else:
            value_style.update(styles['metric_negative'])
            arrow_prefix = '\u25bc'  # ▼
        # Prepend the arrow. Strip a leading sign on the value so we
        # don't render "+" or "-" twice when the caller already added it.
        # This is best-effort: callers that pass "+15%" get "▲ 15%" and
        # callers that pass "15%" get "▲ 15%".
        raw_value = str(value).lstrip()
        if raw_value[:1] in ('+', '-'):
            value_str = f"{arrow_prefix} {raw_value[1:].lstrip()}"
        else:
            value_str = f"{arrow_prefix} {raw_value}"
        value_node = html.Div(value_str, style=value_style, **{'aria-label': label})
    else:
        value_node = html.Div(value, style=value_style)

    card_style = styles['metric_card'].copy()

    return html.Div(
        [
            html.Div(label, style=styles['metric_label']),
            value_node,
        ],
        style=card_style,
        className='metric-card-animated' if animated else '',
        title=info_text or None,
    )


def build_status_badge(text: str, status: str, theme: dict = None) -> html.Span:
    """
    Build a status badge.

    Args:
        text: Badge text
        status: Status type ('success', 'warning', 'error')
        theme: Theme configuration dict

    Returns:
        html.Span containing the badge
    """
    if theme is None:
        theme = get_theme()

    styles = get_styles(theme)
    badge_style = styles['status_badge'].copy()

    status_styles = {
        'success': styles['status_success'],
        'warning': styles['status_warning'],
        'error': styles['status_error'],
    }
    badge_style.update(status_styles.get(status, {}))

    return html.Span(text, style=badge_style)


def build_alert(
    message: str,
    alert_type: str = 'info',
    dismissable: bool = True,
    theme: dict = None
) -> dbc.Alert:
    """
    Build a styled alert component.

    Args:
        message: Alert message text
        alert_type: Type of alert ('success', 'warning', 'error', 'info')
        dismissable: Whether the alert can be dismissed
        theme: Theme configuration dict

    Returns:
        dbc.Alert component
    """
    if theme is None:
        theme = get_theme()

    color_map = {
        'success': 'success',
        'warning': 'warning',
        'error': 'danger',
        'info': 'info',
    }

    icon_map = {
        'success': '\u2713',  # checkmark
        'warning': '\u26a0',  # warning sign
        'error': '\u2715',    # X mark
        'info': '\u2139',     # info sign
    }

    return dbc.Alert(
        [
            html.Span(
                icon_map.get(alert_type, '\u2139'),
                style={'marginRight': '8px', 'fontWeight': 'bold'}
            ),
            message
        ],
        color=color_map.get(alert_type, 'info'),
        dismissable=dismissable,
        className=f'custom-alert {alert_type}',
        style={'marginBottom': '12px', 'fontSize': FONT_SIZES['sm']}
    )


def build_progress_bar(
    progress: int = 0,
    text: str = '',
    indeterminate: bool = False,
    theme: dict = None
) -> html.Div:
    """
    Build a progress bar component.

    Args:
        progress: Progress percentage (0-100)
        text: Optional label text
        indeterminate: If True, show indeterminate animation
        theme: Theme configuration dict

    Returns:
        html.Div containing the progress bar
    """
    if theme is None:
        theme = get_theme()

    header = None
    if text:
        header = html.Div([
            html.Span(
                text,
                style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary']}
            ),
            html.Span(
                f'{progress}%' if not indeterminate else '',
                style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'fontFamily': FONT_FAMILY
                }
            ),
        ], style={
            'display': 'flex',
            'justifyContent': 'space-between',
            'marginBottom': '4px'
        })

    bar_class = 'progress-bar' + (' indeterminate' if indeterminate else '')
    bar_style = {'width': f'{progress}%'} if not indeterminate else {}

    return html.Div([
        header,
        html.Div([
            html.Div(className=bar_class, style=bar_style)
        ], className='progress-container')
    ])


def build_section_header(title: str, theme: dict = None) -> html.Div:
    """
    Build a section header for the sidebar.

    Args:
        title: Section title text
        theme: Theme configuration dict

    Returns:
        html.Div containing the section header
    """
    if theme is None:
        theme = get_theme()

    return html.Div(
        title,
        style={
            'fontSize': FONT_SIZES['xs'],
            'fontWeight': '600',
            'color': theme['text_secondary'],
            'textTransform': 'uppercase',
            'letterSpacing': '0.5px',
            'marginBottom': '8px',
        }
    )


def build_labeled_input(
    label: str,
    input_component,
    theme: dict = None
) -> html.Div:
    """
    Build a labeled input field.

    Args:
        label: Input label text
        input_component: The input component (dcc.Input, dcc.Dropdown, etc.)
        theme: Theme configuration dict

    Returns:
        html.Div containing label and input
    """
    if theme is None:
        theme = get_theme()

    return html.Div([
        html.Label(
            label,
            style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_secondary'],
                'marginBottom': '4px',
                'display': 'block'
            }
        ),
        input_component
    ])


def build_button_group(buttons: list, gap: str = '8px') -> html.Div:
    """
    Build a horizontal button group.

    Args:
        buttons: List of button components
        gap: Gap between buttons

    Returns:
        html.Div containing the buttons
    """
    return html.Div(
        buttons,
        style={'display': 'flex', 'gap': gap}
    )
