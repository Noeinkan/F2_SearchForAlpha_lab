"""Pure render helpers for the Optimizer LEARN modal (native Dash components)."""

from __future__ import annotations

from typing import Any

from dash import html

from lib.dash.dash_config import FONT_FAMILY, FONT_SIZES
from lib.dash.optimizer_glossary import (
    ANALYSIS_ORDER,
    ANALYSIS_SPECS,
    DISCLAIMER,
    LEARN_SECTIONS,
    QUICK_START_STEPS,
)


def _section_title(text: str, theme: dict) -> html.H4:
    return html.H4(
        text,
        style={
            "margin": "0 0 6px",
            "fontSize": FONT_SIZES["sm"],
            "fontFamily": FONT_FAMILY,
            "color": theme["text_primary"],
            "fontWeight": 700,
            "letterSpacing": "0.04em",
            "textTransform": "uppercase",
        },
    )


def _body_p(text: str, theme: dict, *, margin_bottom: str = "14px") -> html.P:
    return html.P(
        text,
        style={
            "margin": f"0 0 {margin_bottom}",
            "fontSize": FONT_SIZES["xs"],
            "lineHeight": "1.45",
            "color": theme["text_secondary"],
            "fontFamily": FONT_FAMILY,
        },
    )


def _quick_start_block(theme: dict) -> html.Div:
    items = [
        html.Li(
            step,
            style={
                "marginBottom": "4px",
                "fontSize": FONT_SIZES["xs"],
                "lineHeight": "1.4",
                "color": theme["text_secondary"],
                "fontFamily": FONT_FAMILY,
            },
        )
        for step in QUICK_START_STEPS
    ]
    return html.Div(
        [
            _section_title("Quick start", theme),
            html.Ol(
                items,
                style={
                    "margin": "0 0 16px",
                    "paddingLeft": "18px",
                },
            ),
        ],
        className="sfa-opt-learn-section",
    )


def _analysis_table(theme: dict) -> html.Div:
    header = html.Div(
        [
            html.Span("Tool", className="sfa-opt-learn-th"),
            html.Span("Use when…", className="sfa-opt-learn-th"),
            html.Span("You get…", className="sfa-opt-learn-th"),
        ],
        className="sfa-opt-learn-tr sfa-opt-learn-tr-head",
    )
    rows: list[Any] = [header]
    for key in ANALYSIS_ORDER:
        spec = ANALYSIS_SPECS[key]
        rows.append(
            html.Div(
                [
                    html.Div(
                        [
                            html.Div(
                                spec["name"],
                                style={
                                    "fontWeight": 600,
                                    "color": theme["text_primary"],
                                    "fontSize": FONT_SIZES["xs"],
                                },
                            ),
                            html.Div(
                                f'{spec["aka"]} · {spec["button"]}',
                                style={
                                    "fontSize": FONT_SIZES["xs"],
                                    "color": theme["text_tertiary"],
                                    "marginTop": "2px",
                                },
                            ),
                        ],
                        className="sfa-opt-learn-td",
                    ),
                    html.Span(spec["when"], className="sfa-opt-learn-td"),
                    html.Span(spec["output"], className="sfa-opt-learn-td"),
                ],
                className="sfa-opt-learn-tr",
            )
        )
    return html.Div(
        [
            _section_title("Which analysis should I run?", theme),
            _body_p(
                "Four tools live in this workspace. They are not interchangeable — "
                "pick the job, then the button.",
                theme,
                margin_bottom="8px",
            ),
            html.Div(rows, className="sfa-opt-learn-table"),
            html.Div(style={"height": "14px"}),
        ],
        className="sfa-opt-learn-section",
    )


def render_optimizer_learn_content(theme: dict) -> html.Div:
    """Body for the Optimizer 101 LEARN modal."""
    sections: list[Any] = [
        _quick_start_block(theme),
        _analysis_table(theme),
    ]
    for section in LEARN_SECTIONS:
        sections.append(
            html.Div(
                [
                    html.H4(
                        section["title"],
                        style={
                            "margin": "0 0 4px",
                            "fontSize": FONT_SIZES["sm"],
                            "fontFamily": FONT_FAMILY,
                            "color": theme["text_primary"],
                        },
                    ),
                    _body_p(section["body"], theme),
                ],
                className="sfa-opt-learn-section",
            )
        )
    sections.append(
        html.P(
            DISCLAIMER,
            style={
                "margin": "4px 0 0",
                "fontSize": FONT_SIZES["xs"],
                "color": theme["text_tertiary"],
                "fontFamily": FONT_FAMILY,
            },
        )
    )
    return html.Div(sections, className="sfa-opt-learn-body")


def render_optimizer_empty_state(theme: dict) -> html.Div:
    """Beginner empty state for the results board (before first run)."""
    steps = [
        html.Li(
            step,
            style={
                "marginBottom": "3px",
                "color": theme["text_tertiary"],
            },
        )
        for step in QUICK_START_STEPS
    ]
    return html.Div(
        [
            html.Div(
                "No results yet — start with a signal-combo grid search.",
                style={
                    "fontSize": FONT_SIZES["sm"],
                    "color": theme["text_secondary"],
                    "fontWeight": "600",
                    "marginBottom": "6px",
                },
            ),
            html.Div(
                ANALYSIS_SPECS["combinatorial"]["one_liner"],
                style={
                    "fontSize": FONT_SIZES["xs"],
                    "color": theme["text_tertiary"],
                    "lineHeight": "1.45",
                    "maxWidth": "560px",
                    "marginBottom": "10px",
                },
            ),
            html.Ol(
                steps,
                style={
                    "margin": "0",
                    "paddingLeft": "18px",
                    "fontSize": FONT_SIZES["xs"],
                    "lineHeight": "1.4",
                    "maxWidth": "560px",
                },
            ),
            html.Div(
                "Tip: workflow is Combos → Tune (bundle) → Validate. Open LEARN "
                "in the header for Bayesian vs Param Grid and an honesty note.",
                style={
                    "fontSize": FONT_SIZES["xs"],
                    "color": theme["text_tertiary"],
                    "lineHeight": "1.4",
                    "marginTop": "10px",
                    "fontStyle": "italic",
                    "maxWidth": "560px",
                },
            ),
        ],
        id="optimizer-empty-state",
        className="sfa-optimize-empty",
    )
