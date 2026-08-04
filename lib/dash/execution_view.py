"""Pure render functions for the Execution Type explainer (native Dash components).

Every figure rendered here is pulled from :mod:`lib.dash.execution_sim`, which
runs the real backtest engine. Nothing in this module computes position sizes.
"""

from __future__ import annotations

from typing import Any, Mapping, Sequence
from urllib.parse import quote

from dash import dcc, html

from lib.dash.dash_config import BORDER_RADIUS, FONT_FAMILY, FONT_MONO, FONT_SIZES
from lib.dash.execution_glossary import (
    ACTIVE_CONTROLS,
    CELL_TONES,
    DISCLAIMER,
    EXECUTION_SECTIONS,
    MECHANICS_ROWS,
    MODE_ORDER,
    MODE_SPECS,
    PREDICT_QUESTIONS,
)
from lib.dash.execution_sim import (
    SANDBOX_CAPITAL,
    LedgerRow,
    SandboxRun,
    default_params,
    first_entry_summary,
    simulate,
)

_SPARK_W = 96
_SPARK_H = 22


def mode_accent(theme: Mapping[str, Any], mode: str) -> str:
    """Themed accent for *mode*, falling back to primary text."""
    key = MODE_SPECS.get(mode, {}).get('accent_key', 'text_primary')
    return theme.get(key, theme['text_primary'])


# --------------------------------------------------------------------------- #
# Fingerprints — each mode's equity curve on the shared tape
# --------------------------------------------------------------------------- #

def sparkline_data_uri(series: Sequence[float], stroke: str) -> str:
    """Encode an equity curve as a standalone SVG data URI.

    Dash has no SVG element and sanitizes ``dcc.Markdown`` HTML, so the sparkline
    ships as an image source instead. Self-contained, themed at render time, and
    cheap enough to sit inside a radio label.
    """
    low, high = min(series), max(series)
    span = (high - low) or 1.0
    step = _SPARK_W / (len(series) - 1)
    points = ' '.join(
        f"{i * step:.1f},{_SPARK_H - ((v - low) / span) * (_SPARK_H - 2) - 1:.1f}"
        for i, v in enumerate(series)
    )
    svg = (
        f'<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 {_SPARK_W} {_SPARK_H}" '
        f'preserveAspectRatio="none">'
        f'<polyline points="{points}" fill="none" stroke="{stroke}" '
        f'stroke-width="1.25" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )
    return 'data:image/svg+xml;utf8,' + quote(svg, safe='')


def render_fingerprint(theme: Mapping[str, Any], mode: str, **params: Any) -> html.Div:
    """Sparkline of the sandbox equity curve, giving each mode a visual identity."""
    run = simulate(mode, **params)
    if len(run.equity) < 2:
        return html.Div(className='sfa-exec-spark')

    return html.Div(
        html.Img(
            src=sparkline_data_uri(run.equity, mode_accent(theme, mode)),
            className='sfa-exec-spark-img',
            alt=f"{MODE_SPECS[mode]['name']} demo equity curve",
        ),
        className='sfa-exec-spark',
        title=(
            f"{MODE_SPECS[mode]['name']} on the shared demo tape: "
            f"{run.total_return_pct:+.1f}%"
        ),
    )


# --------------------------------------------------------------------------- #
# Inline preview shown under each mode card in the panel
# --------------------------------------------------------------------------- #

def render_mode_preview(theme: Mapping[str, Any], mode: str, **params: Any) -> html.Div:
    """The always-visible honest one-liner: what the first signal actually does."""
    return html.Div(
        first_entry_summary(mode, **params),
        className='sfa-exec-preview',
        style={
            'fontSize': '10px',
            'fontFamily': FONT_MONO,
            'color': mode_accent(theme, mode),
            'marginTop': '3px',
            'opacity': 0.85,
        },
    )


# --------------------------------------------------------------------------- #
# Mechanics matrix
# --------------------------------------------------------------------------- #

def _tone_style(theme: Mapping[str, Any], tone: str | None) -> dict:
    if tone == 'off':
        # text_tertiary is already the audited "muted but AA-legible" token —
        # dimming it further pushed these cells under 3:1 on bg_primary.
        return {'color': theme['text_tertiary'], 'textDecoration': 'none'}
    if tone == 'warn':
        return {'color': theme['accent_orange']}
    return {'color': theme['text_secondary']}


def render_mechanics_matrix(theme: Mapping[str, Any]) -> html.Div:
    """Three-column comparison of what each mode does, mechanic by mechanic."""
    cell_base = {
        'padding': '5px 8px',
        'fontSize': FONT_SIZES['xs'],
        'fontFamily': FONT_FAMILY,
        'borderBottom': f'1px solid {theme["border_primary"]}',
        'verticalAlign': 'top',
    }

    header = html.Tr(
        [html.Th('', style={**cell_base, 'width': '22%'})]
        + [
            html.Th(
                MODE_SPECS[mode]['name'],
                style={
                    **cell_base,
                    'color': mode_accent(theme, mode),
                    'fontWeight': '600',
                    'textAlign': 'left',
                },
            )
            for mode in MODE_ORDER
        ]
    )

    body = []
    for row in MECHANICS_ROWS:
        cells = [
            html.Td(
                row['label'],
                style={
                    **cell_base,
                    'color': theme['text_primary'],
                    'fontWeight': '600',
                    'whiteSpace': 'nowrap',
                },
            )
        ]
        for mode in MODE_ORDER:
            tone = CELL_TONES.get((row['label'], mode))
            cells.append(
                html.Td(row[mode], style={**cell_base, **_tone_style(theme, tone)})
            )
        body.append(html.Tr(cells))

    return html.Div(
        html.Table(
            [html.Thead(header), html.Tbody(body)],
            className='sfa-exec-matrix',
            style={'width': '100%', 'borderCollapse': 'collapse'},
        ),
        className='sfa-exec-matrix-wrap',
    )


# --------------------------------------------------------------------------- #
# Predict-then-reveal
# --------------------------------------------------------------------------- #

def _correct_option(mode: str, run: SandboxRun) -> int:
    """Resolve the right answer from the engine run, not from stored copy."""
    spec = PREDICT_QUESTIONS[mode]
    if mode == 'trading':
        value = run.first_entry_value
        thresholds = spec['thresholds']
        return sum(1 for t in thresholds if value >= t)
    if mode == 'accumulation':
        # $10,000 at $1,000 a buy affords 10 buys, so the 11th does nothing.
        return 2
    return 0  # rebalancing: equal weight, same as the first


def render_predict_block(
    theme: Mapping[str, Any],
    mode: str,
    guess: int | None,
    revealed: bool,
    run: SandboxRun,
) -> html.Div:
    """Ask before showing. Being wrong is what makes the mechanic stick."""
    spec = PREDICT_QUESTIONS[mode]
    correct = _correct_option(mode, run)
    accent = mode_accent(theme, mode)

    buttons = []
    for i, label in enumerate(spec['options']):
        state = ''
        if revealed and i == correct:
            state = ' is-correct'
        elif revealed and guess == i:
            state = ' is-wrong'
        elif guess == i:
            state = ' is-picked'
        buttons.append(
            html.Button(
                label,
                id={'type': 'exec-predict-option', 'mode': mode, 'index': i},
                n_clicks=0,
                className=f'sfa-exec-option{state}',
                disabled=revealed,
            )
        )

    children: list[Any] = [
        html.Div(spec['question'], className='sfa-exec-predict-q',
                 style={'color': theme['text_primary']}),
        html.Div(buttons, className='sfa-exec-options'),
    ]

    if revealed:
        verdict = "Correct." if guess == correct else (
            "Not quite." if guess is not None else "Here's what happens."
        )
        children.append(
            html.Div(
                [
                    html.Span(verdict, style={
                        'fontWeight': '700',
                        'color': accent if guess == correct else theme['accent_orange'],
                    }),
                    html.Span(' ' + spec['sting'], style={'color': theme['text_secondary']}),
                ],
                className='sfa-exec-sting fade-in',
            )
        )
    else:
        children.append(
            html.Button(
                'REVEAL',
                id={'type': 'exec-reveal', 'mode': mode},
                n_clicks=0,
                className='sfa-exec-reveal',
                style={'borderColor': accent, 'color': accent},
            )
        )

    return html.Div(children, className='sfa-exec-predict')


# --------------------------------------------------------------------------- #
# Sandbox ledger
# --------------------------------------------------------------------------- #

def _signal_chip(theme: Mapping[str, Any], signal: str) -> Any:
    if signal == 'buy':
        return html.Span('BUY', className='sfa-exec-chip',
                         style={'color': theme['accent_green'],
                                'borderColor': theme['accent_green']})
    if signal == 'sell':
        return html.Span('SELL', className='sfa-exec-chip',
                         style={'color': theme['accent_red'],
                                'borderColor': theme['accent_red']})
    return html.Span('', className='sfa-exec-chip is-empty')


def render_ledger(theme: Mapping[str, Any], run: SandboxRun) -> html.Div:
    """Bar-by-bar table: signal in, order out, cash and equity after."""
    cell = {
        'padding': '3px 7px',
        'fontSize': '11px',
        'fontFamily': FONT_MONO,
        'borderBottom': f'1px solid {theme["border_primary"]}',
        'whiteSpace': 'nowrap',
    }
    head = {**cell, 'color': theme['text_tertiary'], 'fontWeight': '600',
            'textAlign': 'left', 'position': 'sticky', 'top': 0,
            'backgroundColor': theme['bg_secondary'], 'zIndex': 1}

    header = html.Tr([
        html.Th('bar', style=head), html.Th('price', style=head),
        html.Th('signal', style=head), html.Th('order', style=head),
        html.Th('shares', style=head), html.Th('cash', style=head),
        html.Th('equity', style=head),
    ])

    rows = []
    for row in run.rows:
        interesting = row.order_value != 0 or row.note
        if row.order_value > 0:
            order_color = theme['accent_green']
        elif row.order_value < 0:
            order_color = theme['accent_red']
        else:
            order_color = theme['text_tertiary']

        rows.append(html.Tr(
            [
                html.Td(str(row.bar), style={**cell, 'color': theme['text_tertiary']}),
                html.Td(f"${row.price:,.0f}", style={**cell, 'color': theme['text_secondary']}),
                html.Td(_signal_chip(theme, row.signal), style=cell),
                html.Td(
                    row.action if row.order_value else (row.note or '—'),
                    style={**cell, 'color': order_color,
                           'fontStyle': 'italic' if (row.note and not row.order_value) else 'normal'},
                ),
                html.Td(f"{row.units:,.1f}", style={**cell, 'color': theme['text_secondary']}),
                html.Td(f"${row.cash:,.0f}", style={**cell, 'color': theme['text_secondary']}),
                html.Td(f"${row.equity:,.0f}", style={**cell, 'color': theme['text_primary'],
                                                     'fontWeight': '600'}),
            ],
            className='sfa-exec-row' + ('' if interesting else ' is-quiet'),
        ))

    return html.Div(
        html.Table([html.Thead(header), html.Tbody(rows)],
                   className='sfa-exec-ledger',
                   style={'width': '100%', 'borderCollapse': 'collapse'}),
        className='sfa-exec-ledger-wrap',
    )


def _stat(theme: Mapping[str, Any], label: str, value: str, accent: str | None = None) -> html.Div:
    return html.Div(
        [
            html.Div(label, className='sfa-exec-stat-label',
                     style={'color': theme['text_tertiary']}),
            html.Div(value, className='sfa-exec-stat-value',
                     style={'color': accent or theme['text_primary']}),
        ],
        className='sfa-exec-stat',
    )


def render_sandbox_controls(theme: Mapping[str, Any], mode: str, params: Mapping[str, Any]) -> html.Div:
    """The mode's own live knobs — the sandbox mode of the explorable."""
    accent = mode_accent(theme, mode)
    controls: list[Any] = []

    def wrap(label: str, hint: str, control: Any) -> html.Div:
        return html.Div(
            [
                html.Div(
                    [html.Span(label, style={'color': accent, 'fontWeight': '600'}),
                     html.Span(hint, style={'color': theme['text_tertiary'],
                                            'marginLeft': '6px'})],
                    className='sfa-exec-control-label',
                ),
                control,
            ],
            className='sfa-exec-control',
        )

    if mode == 'trading':
        controls.append(wrap('Kelly win rate', 'higher = bigger entries', dcc.Slider(
            id={'type': 'exec-param', 'mode': mode, 'name': 'kelly_win_rate'},
            min=0.3, max=0.8, step=0.05, value=params.get('kelly_win_rate', 0.5),
            marks=None, tooltip={'placement': 'bottom', 'always_visible': True})))
        controls.append(wrap('Scale-in %', 'multiplies every order', dcc.Slider(
            id={'type': 'exec-param', 'mode': mode, 'name': 'position_scaling_pct'},
            min=10, max=100, step=10, value=params.get('position_scaling_pct', 100.0),
            marks=None, tooltip={'placement': 'bottom', 'always_visible': True})))
    elif mode == 'accumulation':
        controls.append(wrap('Amount per buy', 'fixed $ every signal', dcc.Slider(
            id={'type': 'exec-param', 'mode': mode, 'name': 'amount_per_buy'},
            min=250, max=3000, step=250, value=params.get('amount_per_buy', 1_000.0),
            marks=None, tooltip={'placement': 'bottom', 'always_visible': True})))
    else:
        controls.append(wrap('% of portfolio', 'same weight in and out', dcc.Slider(
            id={'type': 'exec-param', 'mode': mode, 'name': 'position_size_pct'},
            min=5, max=100, step=5, value=params.get('position_size_pct', 25.0),
            marks=None, tooltip={'placement': 'bottom', 'always_visible': True})))

    if mode != 'accumulation':
        controls.append(wrap('Trailing stop %', 'exits the whole position', dcc.Slider(
            id={'type': 'exec-param', 'mode': mode, 'name': 'trailing_stop_pct'},
            min=5, max=40, step=5, value=params.get('trailing_stop_pct', 15.0),
            marks=None, tooltip={'placement': 'bottom', 'always_visible': True})))

    return html.Div(controls, className='sfa-exec-controls')


def render_inert_controls_note(theme: Mapping[str, Any], mode: str) -> html.Div:
    """Name the Trade Setup knobs this mode ignores, so none get tuned in vain."""
    active = ACTIVE_CONTROLS.get(mode, ())
    every = sorted({c for controls in ACTIVE_CONTROLS.values() for c in controls})
    inert = [c for c in every if c not in active]
    if not inert:
        return html.Div()
    return html.Div(
        [
            html.Span('Ignored in this mode: ', style={'color': theme['text_tertiary'],
                                                       'fontWeight': '600'}),
            html.Span(', '.join(inert), style={'color': theme['text_tertiary']}),
        ],
        className='sfa-exec-inert',
    )


def render_sandbox(
    theme: Mapping[str, Any],
    mode: str,
    params: Mapping[str, Any] | None = None,
    guess: int | None = None,
    revealed: bool = False,
) -> html.Div:
    """The explorable: fixed tape, live knobs, predict-then-reveal, real ledger."""
    merged = {**default_params(mode), **(params or {})}
    run = simulate(mode, **merged)
    accent = mode_accent(theme, mode)

    stats = html.Div(
        [
            _stat(theme, 'first entry', f"${run.first_entry_value:,.0f}", accent),
            _stat(theme, 'of account', f"{run.first_entry_pct:.1%}", accent),
            _stat(theme, 'buys', str(run.buy_count)),
            _stat(theme, 'sells', str(run.sell_count),
                  theme['text_tertiary'] if run.sell_count == 0 else None),
            _stat(theme, 'stop exits', str(run.stop_exits),
                  theme['text_tertiary'] if run.stop_exits == 0 else None),
            _stat(
                theme, 'end equity', f"${run.final_equity:,.0f}",
                theme['accent_green'] if run.total_return_pct >= 0 else theme['accent_red'],
            ),
        ],
        className='sfa-exec-stats',
    )

    body: list[Any] = [
        html.Div(
            [
                html.Span(MODE_SPECS[mode]['name'], style={'color': accent, 'fontWeight': '700'}),
                html.Span(f" — {MODE_SPECS[mode]['one_liner']}",
                          style={'color': theme['text_secondary']}),
            ],
            className='sfa-exec-mode-intro',
        ),
        render_predict_block(theme, mode, guess, revealed, run),
    ]

    if revealed:
        body.extend([
            html.Div(
                f"$10,000 · 24 bars · {run.buy_count} buy signals · "
                f"{len(run.rows) and sum(1 for r in run.rows if r.signal == 'sell')} sell signals · no fees",
                className='sfa-exec-tape-note',
                style={'color': theme['text_tertiary']},
            ),
            render_sandbox_controls(theme, mode, merged),
            stats,
            render_ledger(theme, run),
            render_inert_controls_note(theme, mode),
        ])

    return html.Div(body, className='sfa-exec-sandbox' + (' is-revealed' if revealed else ''))


# --------------------------------------------------------------------------- #
# Modal body
# --------------------------------------------------------------------------- #

def render_progress_dots(theme: Mapping[str, Any], explored: Sequence[str]) -> html.Div:
    """Quiet completion indicator — a dot per mode understood."""
    dots = []
    for mode in MODE_ORDER:
        done = mode in (explored or [])
        dots.append(html.Span(
            className='sfa-exec-dot' + (' is-done' if done else ''),
            title=f"{MODE_SPECS[mode]['name']}: {'explored' if done else 'not explored yet'}",
            style={'backgroundColor': mode_accent(theme, mode) if done else 'transparent',
                   'borderColor': mode_accent(theme, mode) if done else theme['border_secondary']},
        ))
    return html.Div(dots, className='sfa-exec-dots')


def render_execution_learn_content(
    theme: Mapping[str, Any],
    mode: str = 'trading',
    params: Mapping[str, Any] | None = None,
    guess: int | None = None,
    revealed: bool = False,
    explored: Sequence[str] = (),
) -> html.Div:
    """Body for the Execution Type LEARN modal."""
    tabs = html.Div(
        [
            html.Button(
                [
                    html.Span(MODE_SPECS[m]['name']),
                    html.Span('✓', className='sfa-exec-tab-tick') if m in (explored or []) else None,
                ],
                id={'type': 'exec-mode-tab', 'mode': m},
                n_clicks=0,
                className='sfa-exec-tab' + (' is-active' if m == mode else ''),
                style={'color': mode_accent(theme, m),
                       'borderColor': mode_accent(theme, m) if m == mode else 'transparent'},
            )
            for m in MODE_ORDER
        ],
        className='sfa-exec-tabs',
    )

    sections = []
    for section in EXECUTION_SECTIONS:
        sections.append(
            html.Div(
                [
                    html.H4(section['title'], style={
                        'margin': '0 0 4px',
                        'fontSize': FONT_SIZES['sm'],
                        'fontFamily': FONT_FAMILY,
                        'color': theme['text_primary'],
                    }),
                    html.P(section['body'], style={
                        'margin': '0 0 14px',
                        'fontSize': FONT_SIZES['xs'],
                        'lineHeight': '1.45',
                        'color': theme['text_secondary'],
                        'fontFamily': FONT_FAMILY,
                    }),
                ],
                className='sfa-exec-section',
            )
        )

    return html.Div(
        [
            render_mechanics_matrix(theme),
            html.Hr(style={'borderColor': theme['border_primary'], 'margin': '14px 0 10px'}),
            html.Div(
                [
                    html.Span('TRY IT', className='sfa-exec-kicker',
                              style={'color': theme['text_tertiary']}),
                    render_progress_dots(theme, explored),
                ],
                className='sfa-exec-tryit-head',
            ),
            tabs,
            render_sandbox(theme, mode, params, guess, revealed),
            html.Hr(style={'borderColor': theme['border_primary'], 'margin': '14px 0 10px'}),
            *sections,
            html.P(DISCLAIMER, style={
                'margin': '4px 0 0',
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_tertiary'],
                'fontFamily': FONT_FAMILY,
            }),
        ],
        className='sfa-exec-learn-body',
    )
