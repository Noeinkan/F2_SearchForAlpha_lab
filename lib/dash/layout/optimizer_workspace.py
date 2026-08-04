"""
Full-screen Optimizer workspace overlay.

Holds the live optimizer control IDs (run/stop, search knobs, results) so the
right-rail Optimizer tab can stay a thin teaser that deep-links here.
"""

from __future__ import annotations

import dash_bootstrap_components as dbc
from dash import dcc, html

from lib.dash.dash_config import BORDER_RADIUS, FONT_FAMILY, FONT_SIZES
from lib.dash.components import dense_input, ticker_pill


def _card_style(theme: dict) -> dict:
    return {
        'backgroundColor': theme['bg_tertiary'],
        'borderRadius': BORDER_RADIUS['sm'],
        'padding': '8px 10px',
        'marginBottom': '10px',
        'border': f'1px solid {theme["border_primary"]}',
    }


def _create_optimize_config_rail(styles: dict, theme: dict) -> html.Div:
    """Left rail: preview, conditions, search knobs."""
    card_style = _card_style(theme)
    help_icon_style = styles['help_icon']

    return html.Div([
        html.Div([
            html.Div([
                html.Div("SIGNAL PREVIEW", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_tertiary'],
                    'fontWeight': '600',
                    'letterSpacing': '0.5px',
                }),
                html.Span("?", id='help-signal-preview', style=help_icon_style),
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'space-between',
                'marginBottom': '8px',
            }),
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
        ], style=card_style),

        html.Div([
            html.Div([
                html.Div("RUN CONDITIONS", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_tertiary'],
                    'fontWeight': '600',
                    'letterSpacing': '0.5px',
                }),
                html.Span("?", id='help-optimizer-conditions', style=help_icon_style),
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'space-between',
                'marginBottom': '6px',
            }),
            html.Div(
                id='optimizer-run-conditions',
                children="Load data to see interval, capital, window and signals.",
                style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'lineHeight': '1.45',
                    'fontFamily': 'ui-monospace, SFMono-Regular, Menlo, Consolas, monospace',
                },
            ),
        ], style=card_style),

        html.Div([
            html.Div([
                html.Label("Max Signals per Side", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'marginBottom': 0,
                    'display': 'block',
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
                marks={i: {'label': str(i), 'style': {'color': theme['text_secondary']}} for i in range(1, 6)},
            ),
        ], style={'marginBottom': '20px'}),

        html.Div([
            html.Div([
                html.Label("Max Combinations", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'marginBottom': 0,
                    'display': 'block',
                }),
                html.Span("?", id='help-max-combos', style=help_icon_style),
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'space-between',
                'marginBottom': '4px',
            }),
            dense_input(
                id='max-combos-input',
                type='number',
                value=100,
                min=10, max=1000,
                style=styles['input'],
            ),
        ], style={'marginBottom': '16px'}),

        html.Div([
            html.Div([
                html.Label("Min Trades", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'marginBottom': 0,
                    'display': 'block',
                }),
                html.Span("?", id='help-min-trades', style=help_icon_style),
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'space-between',
                'marginBottom': '4px',
            }),
            dense_input(
                id='min-trades-input',
                type='number',
                value=10,
                min=1, max=500,
                style=styles['input'],
            ),
        ], style={'marginBottom': '16px'}),

        html.Div([
            html.Div([
                html.Label("Sort Results By", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'marginBottom': 0,
                    'display': 'block',
                }),
                html.Span("?", id='help-sort-metric', style=help_icon_style),
            ], style={
                'display': 'flex',
                'alignItems': 'center',
                'justifyContent': 'space-between',
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
        ], style={'marginBottom': '16px'}),

        dbc.Tooltip(
            "Counts available signals and estimated combinations.",
            target='help-signal-preview',
            placement='right',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "What the optimizer will search: chart interval, Backtest capital "
            "and test window, plus buy/sell signal columns on the loaded frame. "
            "Chart overlays are display-only — only signal columns enter combos.",
            target='help-optimizer-conditions',
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
    """Main pane: progress, leaderboard, apply."""
    return html.Div([
        html.Div(id='optimization-progress', style={'marginBottom': '12px'}),
        html.Div(id='optimization-results', style={'flex': '1 1 auto', 'minHeight': 0}),
        html.Div(id='apply-strategy-container', children=[
            html.Button(
                "Apply Best Strategy",
                id='apply-strategy-btn',
                style={
                    **styles['button_primary'],
                    'width': '100%',
                    'marginTop': '12px',
                    'backgroundColor': theme['accent_green'],
                },
                n_clicks=0,
            ),
            dbc.Tooltip(
                "Copy the winner into the Backtest panel and return to the terminal.",
                target='apply-strategy-btn',
                placement='top',
            ),
        ], style={'display': 'none', 'flex': '0 0 auto'}),
    ], id='optimize-results-pane', style={
        'flex': '1 1 auto',
        'minWidth': 0,
        'minHeight': 0,
        'overflowY': 'auto',
        'padding': '16px',
        'display': 'flex',
        'flexDirection': 'column',
    })


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
