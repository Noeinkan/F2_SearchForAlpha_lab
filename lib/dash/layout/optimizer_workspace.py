"""
Full-screen Optimizer workspace overlay.

Holds the live optimizer control IDs (run/stop, search knobs, results) so the
right-rail Optimizer tab can stay a thin teaser that deep-links here.

Capital / window / friction editors are *mirrors* of Backtest SoT IDs — Dash
forbids remounting those IDs. Sync lives in ``callbacks/optimizer_sync.py``.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from lib.dash.dash_config import (
    BORDER_RADIUS,
    FONT_FAMILY,
    FONT_SIZES,
    INITIAL_CAPITAL,
    TEST_WINDOW_PRESETS,
)
from lib.dash.components import dense_input, ticker_pill


def _card_style(theme: dict) -> dict:
    return {
        'backgroundColor': theme['bg_tertiary'],
        'borderRadius': BORDER_RADIUS['sm'],
        'padding': '8px 10px',
        'marginBottom': '10px',
        'border': f'1px solid {theme["border_primary"]}',
    }


def _section_label(text: str, help_id: str | None, help_icon_style: dict, theme: dict) -> html.Div:
    children = [
        html.Div(text, style={
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_tertiary'],
            'fontWeight': '600',
            'letterSpacing': '0.5px',
        }),
    ]
    if help_id:
        children.append(html.Span("?", id=help_id, style=help_icon_style))
    return html.Div(children, style={
        'display': 'flex',
        'alignItems': 'center',
        'justifyContent': 'space-between',
        'marginBottom': '8px',
    })


def _optimizer_empty_state(theme: dict) -> html.Div:
    return html.Div(
        [
            html.Div("Configure the rail, then RUN OPTIMIZER.", style={
                'fontSize': FONT_SIZES['sm'],
                'color': theme['text_secondary'],
                'fontWeight': '600',
                'marginBottom': '6px',
            }),
            html.Div(
                "The chart above shows the same session series and test window "
                "you will search. Idealized ranking is fast; turn on Realistic "
                "ranking to include costs and stops.",
                style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_tertiary'],
                    'lineHeight': '1.45',
                    'maxWidth': '520px',
                },
            ),
        ],
        id='optimizer-empty-state',
        className='sfa-optimize-empty',
    )


def _create_optimize_config_rail(styles: dict, theme: dict) -> html.Div:
    """Left rail: preview, capital/window, universe, search, realistic ranking."""
    card_style = _card_style(theme)
    help_icon_style = styles['help_icon']
    label_style = {
        'fontSize': FONT_SIZES['xs'],
        'color': theme['text_secondary'],
        'marginBottom': '4px',
        'display': 'block',
    }

    return html.Div([
        html.Div([
            _section_label("SIGNAL PREVIEW", 'help-signal-preview', help_icon_style, theme),
            html.Div(id='signal-preview', children=[
                html.Div([
                    ticker_pill('BUY', '0', color='up', value_id='preview-buy-count'),
                    html.Span('│', className='num', style={'color': theme['border_primary']}),
                    ticker_pill('SELL', '0', color='down', value_id='preview-sell-count'),
                    html.Span('│', className='num', style={'color': theme['border_primary']}),
                    ticker_pill('COMBOS', '0', color='amber', value_id='preview-combo-count'),
                    html.Span('│', className='num', style={'color': theme['border_primary']}),
                    ticker_pill('EST', '—', color='neutral', value_id='optimization-cost'),
                ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px', 'flexWrap': 'wrap'}),
            ]),
            html.Div(
                id='optimizer-run-conditions',
                children="Load data to see interval, capital, window and signals.",
                style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'lineHeight': '1.45',
                    'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                    'marginTop': '8px',
                    'whiteSpace': 'pre-wrap',
                },
            ),
        ], style=card_style),

        dbc.Accordion(
            [
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Label("Test Window", style=label_style),
                            dcc.RadioItems(
                                id='opt-test-window-preset',
                                options=TEST_WINDOW_PRESETS,
                                value='max',
                                inline=True,
                                className='bbg-radio-seg sfa-test-window-seg',
                            ),
                            html.Div([
                                html.Div([
                                    html.Label("From", style=label_style),
                                    dcc.DatePickerSingle(
                                        id='opt-test-window-start',
                                        display_format='YYYY-MM-DD',
                                        className='dark-datepicker',
                                        style={'width': '100%'},
                                    ),
                                ], style={'flex': 1}),
                                html.Div([
                                    html.Label("To", style=label_style),
                                    dcc.DatePickerSingle(
                                        id='opt-test-window-end',
                                        display_format='YYYY-MM-DD',
                                        className='dark-datepicker date-picker-end',
                                        style={'width': '100%'},
                                    ),
                                ], style={'flex': 1}),
                            ], style={
                                'display': 'flex',
                                'gap': '8px',
                                'marginTop': '8px',
                                'marginBottom': '12px',
                            }),
                            html.Label("Initial Capital", style=label_style),
                            dense_input(
                                id='opt-initial-capital',
                                type='number',
                                value=INITIAL_CAPITAL,
                                style={**styles['input'], 'textAlign': 'right'},
                            ),
                        ]),
                    ],
                    title="Capital & Window",
                    item_id='opt-capital-window',
                ),
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Label("Buy signals in search", style=label_style),
                            dcc.Dropdown(
                                id='optimizer-buy-universe',
                                options=[],
                                value=None,
                                multi=True,
                                placeholder='All buy signals',
                                className='dark-dropdown',
                                style={'fontSize': FONT_SIZES['xs'], 'marginBottom': '10px'},
                            ),
                            html.Label("Sell signals in search", style=label_style),
                            dcc.Dropdown(
                                id='optimizer-sell-universe',
                                options=[],
                                value=None,
                                multi=True,
                                placeholder='All sell signals',
                                className='dark-dropdown',
                                style={'fontSize': FONT_SIZES['xs']},
                            ),
                            html.Div(
                                "Empty = search all available columns on the loaded frame.",
                                style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_tertiary'],
                                    'marginTop': '6px',
                                },
                            ),
                        ]),
                    ],
                    title="Signal Universe",
                    item_id='opt-universe',
                ),
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Div([
                                html.Label("Max Signals per Side", style={
                                    **label_style, 'marginBottom': 0,
                                }),
                                html.Span("?", id='help-max-signals', style=help_icon_style),
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'space-between',
                                'marginBottom': '8px',
                            }),
                            dcc.Slider(
                                id='max-signals-slider',
                                min=1, max=5, value=2, step=1,
                                marks={
                                    i: {
                                        'label': str(i),
                                        'style': {'color': theme['text_secondary']},
                                    }
                                    for i in range(1, 6)
                                },
                            ),
                            html.Div([
                                html.Label("Max Combinations", style={
                                    **label_style, 'marginBottom': 0,
                                }),
                                html.Span("?", id='help-max-combos', style=help_icon_style),
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'space-between',
                                'marginTop': '12px',
                                'marginBottom': '4px',
                            }),
                            dense_input(
                                id='max-combos-input',
                                type='number',
                                value=100,
                                min=10, max=1000,
                                style=styles['input'],
                            ),
                            html.Div([
                                html.Label("Min Trades", style={
                                    **label_style, 'marginBottom': 0,
                                }),
                                html.Span("?", id='help-min-trades', style=help_icon_style),
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'space-between',
                                'marginTop': '12px',
                                'marginBottom': '4px',
                            }),
                            dense_input(
                                id='min-trades-input',
                                type='number',
                                value=10,
                                min=1, max=500,
                                style=styles['input'],
                            ),
                            html.Div([
                                html.Label("Sort Results By", style={
                                    **label_style, 'marginBottom': 0,
                                }),
                                html.Span("?", id='help-sort-metric', style=help_icon_style),
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'space-between',
                                'marginTop': '12px',
                                'marginBottom': '4px',
                            }),
                            dcc.RadioItems(
                                id='sort-metric-dropdown',
                                options=[
                                    {'label': 'SCORE', 'value': 'Robustness_Score'},
                                    {'label': 'RET', 'value': 'Total_Return_%'},
                                    {'label': 'SHARPE', 'value': 'Sharpe_Ratio'},
                                    {'label': 'CALMAR', 'value': 'Calmar'},
                                    {'label': 'DD', 'value': 'Max_Drawdown_%'},
                                    {'label': 'TRADES', 'value': 'Trades'},
                                ],
                                value='Robustness_Score',
                                inline=True,
                                className='bbg-radio-seg',
                            ),
                            html.Hr(style={
                                'borderColor': theme['border_primary'],
                                'margin': '14px 0 10px',
                            }),
                            html.Label("Max |DD| % (optional)", style=label_style),
                            dense_input(
                                id='opt-max-dd-pct',
                                type='number',
                                value=None,
                                min=0, max=100,
                                placeholder='e.g. 25',
                                style=styles['input'],
                            ),
                            html.Label("Min Sharpe (optional)", style={
                                **label_style, 'marginTop': '10px',
                            }),
                            dense_input(
                                id='opt-min-sharpe',
                                type='number',
                                value=None,
                                step=0.1,
                                placeholder='e.g. 0.5',
                                style=styles['input'],
                            ),
                        ]),
                    ],
                    title="Search & Constraints",
                    item_id='opt-search',
                ),
                dbc.AccordionItem(
                    [
                        html.Div([
                            dcc.Checklist(
                                id='optimizer-realistic-ranking',
                                options=[{
                                    'label': ' Rank with costs / stops / mode',
                                    'value': 'on',
                                }],
                                value=[],
                                style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                    'marginBottom': '10px',
                                },
                            ),
                            html.Div(id='opt-realistic-fields', children=[
                                html.Label("Execution mode", style=label_style),
                                dcc.RadioItems(
                                    id='opt-strategy-mode',
                                    options=[
                                        {'label': 'Trading', 'value': 'trading'},
                                        {'label': 'Accum', 'value': 'accumulation'},
                                        {'label': 'Rebal', 'value': 'rebalancing'},
                                    ],
                                    value='trading',
                                    inline=True,
                                    className='bbg-radio-seg',
                                ),
                                html.Div([
                                    html.Div([
                                        html.Label("Min hold", style=label_style),
                                        dense_input(
                                            id='opt-min-holding-period',
                                            type='number',
                                            value=5,
                                            min=0,
                                            style=styles['input'],
                                        ),
                                    ], style={'flex': 1}),
                                    html.Div([
                                        html.Label("Trail %", style=label_style),
                                        dense_input(
                                            id='opt-trailing-stop-pct',
                                            type='number',
                                            value=5,
                                            min=0,
                                            style=styles['input'],
                                        ),
                                    ], style={'flex': 1}),
                                ], style={
                                    'display': 'flex',
                                    'gap': '8px',
                                    'marginTop': '10px',
                                }),
                                html.Label("Stop mode", style={
                                    **label_style, 'marginTop': '10px',
                                }),
                                dcc.RadioItems(
                                    id='opt-stop-mode',
                                    options=[
                                        {'label': '% TRAIL', 'value': 'percent'},
                                        {'label': 'ATR', 'value': 'atr'},
                                    ],
                                    value='percent',
                                    inline=True,
                                    className='bbg-radio-seg',
                                ),
                                html.Div([
                                    html.Div([
                                        html.Label("FX %", style=label_style),
                                        dense_input(
                                            id='opt-fx-fee-pct',
                                            type='number',
                                            value=0.15,
                                            min=0,
                                            step=0.01,
                                            style=styles['input'],
                                        ),
                                    ], style={'flex': 1}),
                                    html.Div([
                                        html.Label("Slip %", style=label_style),
                                        dense_input(
                                            id='opt-slippage-pct',
                                            type='number',
                                            value=0.05,
                                            min=0,
                                            step=0.01,
                                            style=styles['input'],
                                        ),
                                    ], style={'flex': 1}),
                                    html.Div([
                                        html.Label("Comm %", style=label_style),
                                        dense_input(
                                            id='opt-commission-pct',
                                            type='number',
                                            value=0.0,
                                            min=0,
                                            step=0.01,
                                            style=styles['input'],
                                        ),
                                    ], style={'flex': 1}),
                                ], style={
                                    'display': 'flex',
                                    'gap': '8px',
                                    'marginTop': '10px',
                                }),
                            ]),
                        ]),
                    ],
                    title="Realistic Ranking",
                    item_id='opt-realistic',
                ),
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Label("Strategy bundle", style=label_style),
                            dcc.Dropdown(
                                id='bayesian-strategy-dropdown',
                                options=[],
                                value=None,
                                placeholder='Select agent strategy…',
                                className='dark-dropdown',
                                style={'fontSize': FONT_SIZES['xs'], 'marginBottom': '10px'},
                            ),
                            html.Div([
                                html.Div([
                                    html.Label("Trials", style=label_style),
                                    dense_input(
                                        id='bayesian-trials-input',
                                        type='number',
                                        value=30,
                                        min=5,
                                        max=200,
                                        style=styles['input'],
                                    ),
                                ], style={'flex': 1}),
                                html.Div([
                                    html.Label("Held-out (mo)", style=label_style),
                                    dense_input(
                                        id='bayesian-held-out-input',
                                        type='number',
                                        value=6,
                                        min=1,
                                        max=24,
                                        style=styles['input'],
                                    ),
                                ], style={'flex': 1}),
                            ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                            html.Label("Objective metric", style=label_style),
                            dcc.Dropdown(
                                id='bayesian-metric-dropdown',
                                options=[
                                    {'label': 'Sortino', 'value': 'sortino'},
                                    {'label': 'Sharpe', 'value': 'sharpe'},
                                    {'label': 'Calmar', 'value': 'calmar'},
                                    {'label': 'Composite', 'value': 'composite'},
                                ],
                                value='sortino',
                                clearable=False,
                                className='dark-dropdown',
                                style={'fontSize': FONT_SIZES['xs'], 'marginBottom': '12px'},
                            ),
                            html.Button(
                                "RUN BAYESIAN",
                                id='run-bayesian-btn',
                                style={**styles['button_primary'], 'width': '100%'},
                                n_clicks=0,
                            ),
                            html.Div(id='bayesian-progress', style={'marginTop': '10px'}),
                            html.Div(id='bayesian-results', style={'marginTop': '8px'}),
                            html.Div(
                                id='bayesian-actions',
                                style={'display': 'none', 'marginTop': '10px'},
                                children=[
                                    html.Button(
                                        "APPLY PARAMS",
                                        id='apply-bayesian-btn',
                                        n_clicks=0,
                                        style={
                                            **styles['button_primary'],
                                            'width': '100%',
                                            'marginBottom': '6px',
                                        },
                                    ),
                                    html.Button(
                                        "VALIDATE OOS (BUNDLE)",
                                        id='validate-bayesian-oos-btn',
                                        n_clicks=0,
                                        style={**styles['button_outline'], 'width': '100%'},
                                    ),
                                    dbc.Tooltip(
                                        "Copy best params into Backtest and switch to the terminal.",
                                        target='apply-bayesian-btn',
                                        placement='top',
                                    ),
                                    dbc.Tooltip(
                                        "Rolling walk-forward on the Bayesian winner (5 windows). "
                                        "Click again while running to STOP.",
                                        target='validate-bayesian-oos-btn',
                                        placement='top',
                                    ),
                                ],
                            ),
                        ]),
                    ],
                    title="Bayesian Sweep",
                    item_id='opt-bayesian',
                ),
            ],
            id='optimize-config-accordion',
            className='compact-accordion',
            start_collapsed=False,
            always_open=True,
            flush=True,
            active_item=['opt-capital-window', 'opt-search'],
            style={'marginBottom': '8px'},
        ),

        dbc.Tooltip(
            "Counts available signals and estimated combinations.",
            target='help-signal-preview',
            placement='right',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Limit how many signals can be chosen per side.",
            target='help-max-signals',
            placement='right',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Cap the total combinations to test for speed.",
            target='help-max-combos',
            placement='right',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Combos with fewer trades than this are flagged 'low sample' and "
            "ranked below credible ones — a great ratio on a handful of trades is noise.",
            target='help-min-trades',
            placement='right',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Choose the metric used to rank results. SCORE is a robustness-weighted "
            "blend that rewards risk-adjusted return and penalises too-few trades.",
            target='help-sort-metric',
            placement='right',
            trigger='hover focus',
        ),
    ], id='optimize-config-rail', style={
        'width': '360px',
        'flex': '0 0 360px',
        'minWidth': 0,
        'overflowY': 'auto',
        'padding': '12px',
        'borderRight': f'1px solid {theme["border_primary"]}',
        'backgroundColor': theme['bg_secondary'],
    })


def _create_optimize_results_pane(styles: dict, theme: dict) -> html.Div:
    """Main pane: sticky chart + scrollable / collapsible results stack."""
    return html.Div([
        html.Div(
            id='optimize-chart-slot',
            className='sfa-optimize-chart-slot',
            children=[],
        ),
        html.Div([
            html.Div(id='optimization-progress', className='sfa-optimize-progress'),
            html.Div(
                id='optimization-results',
                className='sfa-optimize-results-board',
                children=_optimizer_empty_state(theme),
            ),
            html.Div(id='optimizer-oos-panel', className='sfa-optimize-oos'),
            dbc.Accordion(
                [
                    dbc.AccordionItem(
                        [
                            dcc.Graph(
                                id='optimizer-landscape-graph',
                                figure={},
                                config={'displayModeBar': False},
                                className='sfa-optimize-landscape-graph',
                                style={'height': '220px'},
                            ),
                        ],
                        title="Return vs Sharpe",
                        item_id='opt-landscape',
                    ),
                    dbc.AccordionItem(
                        [
                            html.Div(
                                id='optimizer-history-panel',
                                className='sfa-optimize-history-body',
                            ),
                        ],
                        title="Run history",
                        item_id='opt-history',
                    ),
                ],
                id='optimize-results-accordion',
                className='compact-accordion sfa-optimize-results-accordion',
                always_open=True,
                flush=True,
                active_item=['opt-landscape'],
            ),
            html.Div(id='apply-strategy-container', children=[
                html.Div([
                    html.Button(
                        "Apply Best Strategy",
                        id='apply-strategy-btn',
                        style={
                            **styles['button_primary'],
                            'flex': '1 1 auto',
                            'backgroundColor': theme['accent_green'],
                        },
                        n_clicks=0,
                    ),
                    html.Button(
                        "VALIDATE OOS",
                        id='validate-oos-btn',
                        style={
                            **styles['button_outline'],
                            'flex': '1 1 auto',
                            'marginLeft': '8px',
                        },
                        n_clicks=0,
                    ),
                ], style={
                    'display': 'flex',
                    'flexDirection': 'row',
                    'gap': '8px',
                    'marginTop': '12px',
                }),
                dbc.Tooltip(
                    "Copy the winner into the Backtest panel and return to the terminal.",
                    target='apply-strategy-btn',
                    placement='top',
                ),
                dbc.Tooltip(
                    "Rolling walk-forward on the current leaderboard winner (5 windows). "
                    "Click again while running to STOP.",
                    target='validate-oos-btn',
                    placement='top',
                ),
            ], style={'display': 'none'}),
        ], id='optimize-scroll-region', className='sfa-optimize-scroll'),
    ], id='optimize-results-pane', className='sfa-optimize-results-pane')


def _create_optimize_overlay(styles: dict, theme: dict) -> html.Div:
    """Full-viewport optimizer workspace (hidden until /optimize route)."""
    return html.Div([
        html.Div([
            html.Div([
                html.Div("OPTIMIZER", style={
                    'fontFamily': FONT_FAMILY,
                    'fontSize': FONT_SIZES['xs'],
                    'letterSpacing': '1.6px',
                    'color': theme['text_secondary'],
                }),
                html.Div(
                    id='optimize-overlay-title',
                    children='Signal combination search',
                    style={
                        'fontFamily': FONT_FAMILY,
                        'fontSize': FONT_SIZES['lg'],
                        'fontWeight': 700,
                        'color': theme['text_primary'],
                        'whiteSpace': 'nowrap',
                        'overflow': 'hidden',
                        'textOverflow': 'ellipsis',
                    },
                ),
            ], style={'minWidth': 0, 'flex': '1 1 auto'}),
            html.Div([
                html.Button(
                    "RUN OPTIMIZER",
                    id='run-optimization-btn',
                    style={**styles['button_primary'], 'padding': '6px 14px'},
                    n_clicks=0,
                ),
                dbc.Tooltip(
                    "Run searches signal combinations; while running, click again to STOP.",
                    target='run-optimization-btn',
                    placement='bottom',
                ),
                html.Button(
                    "CLOSE",
                    id='close-optimize-button',
                    n_clicks=0,
                    style={
                        **styles['button_outline'],
                        'color': theme['accent_red'],
                        'borderColor': theme['accent_red'],
                        'marginLeft': '8px',
                        'padding': '6px 12px',
                    },
                ),
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'gap': '8px',
                'flex': '0 0 auto',
            }),
        ], style={
            'minHeight': '36px',
            'flex': '0 0 auto',
            'padding': '4px 8px',
            'display': 'flex',
            'alignItems': 'center',
            'justifyContent': 'space-between',
            'flexWrap': 'wrap',
            'gap': '8px',
            'backgroundColor': theme['bg_secondary'],
            'borderBottom': f'1px solid {theme["border_primary"]}',
        }),
        html.Div([
            _create_optimize_config_rail(styles, theme),
            _create_optimize_results_pane(styles, theme),
        ], style={
            'flex': '1 1 auto',
            'minHeight': 0,
            'display': 'flex',
            'flexDirection': 'row',
            'overflow': 'hidden',
        }),
        # Clientside reparent writes a tiny status here (layout tick only).
        html.Div(id='optimize-chart-reparent-sync', style={'display': 'none'}),
    ], id='optimize-overlay', style={
        'display': 'none',
        'position': 'fixed',
        'flexDirection': 'column',
        'inset': '44px 6px 24px 6px',
        'zIndex': 20,
        'backgroundColor': theme['bg_primary'],
        'border': f'1px solid {theme["border_primary"]}',
        'boxShadow': '0 18px 60px rgba(0, 0, 0, 0.45)',
        'overflow': 'hidden',
    }, className='sfa-optimize-overlay')
