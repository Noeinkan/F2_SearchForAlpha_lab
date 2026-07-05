"""
Right panel: Backtest / Optimizer / Data tabs.

The backtest accordion is intentionally inline (one giant builder) to keep
the JSX structure of the four accordion sections co-located — splitting it
further would scatter section IDs and tooltips across files and make
edit-and-test slower. The optimizer panel is dense enough to deserve its
own builder; the data tab renders a filterable OHLCV/indicator/signal table.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from lib.dash.dash_config import (
    FONT_SIZES, FONT_FAMILY, BORDER_RADIUS, DEFAULT_SIGNAL_WINDOW,
    DATA_ROW_OPTIONS, DATA_COLUMN_GROUPS,
)
from lib.dash.components import dense_input, ticker_pill
from lib.dash.bootstrap import BootstrapSnapshot
from lib.signals.indicators import get_signal_categories


def _create_right_panel(styles: dict, theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Aside:
    """Create the right panel with backtest controls and results."""
    return html.Aside([
        html.Div(
            html.Button("<<", id='right-panel-toggle-btn', n_clicks=0, className='sfa-panel-toggle'),
            className='sfa-panel-toggle-wrap',
        ),
        html.Div([
            # Tabs
            html.Div([
                html.Button("Backtest", id='tab-backtest', n_clicks=0,
                           style=styles['tab'], className='panel-tab'),
                html.Span('│', className='num', style={'color': theme['border_primary'], 'alignSelf': 'center'}),
                html.Button("Optimizer", id='tab-optimizer', n_clicks=0,
                           style=styles['tab'], className='panel-tab'),
                html.Span('│', className='num', style={'color': theme['border_primary'], 'alignSelf': 'center'}),
                html.Button("Data", id='tab-data', n_clicks=0,
                           style=styles['tab'], className='panel-tab'),
            ], style=styles['panel_header']),

            # Panel Content
            html.Div([
                # Backtest Panel
                _create_backtest_panel(styles, theme, bootstrap=bootstrap),

                # Optimizer Panel
                _create_optimizer_panel(styles, theme),

                # Data Panel
                html.Div(id='panel-data', children=[
                    html.Div([
                        html.Div([
                            html.Label('Rows', style={
                                'fontSize': FONT_SIZES['xs'],
                                'color': theme['text_secondary'],
                                'marginBottom': '4px',
                                'display': 'block',
                            }),
                            dcc.RadioItems(
                                id='data-rows',
                                options=DATA_ROW_OPTIONS,
                                value=50,
                                inline=True,
                                className='bbg-radio-seg',
                            ),
                        ], style={'marginBottom': '10px'}),
                        html.Div([
                            html.Label('Columns', style={
                                'fontSize': FONT_SIZES['xs'],
                                'color': theme['text_secondary'],
                                'marginBottom': '4px',
                                'display': 'block',
                            }),
                            dcc.Checklist(
                                id='data-col-groups',
                                options=DATA_COLUMN_GROUPS,
                                value=['ohlcv', 'indicators', 'signals'],
                                inline=True,
                                inputStyle={'marginRight': '4px'},
                                labelStyle={
                                    'fontSize': FONT_SIZES['xs'],
                                    'marginRight': '10px',
                                    'color': theme['text_primary'],
                                },
                            ),
                        ], style={'marginBottom': '10px'}),
                        html.Div([
                            html.Div([
                                html.Label('From', style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'marginBottom': '4px',
                                    'display': 'block',
                                }),
                                dcc.DatePickerSingle(
                                    id='data-date-start',
                                    display_format='YYYY-MM-DD',
                                    className='dark-datepicker',
                                    style={'width': '100%'},
                                ),
                            ], style={'flex': 1}),
                            html.Div([
                                html.Label('To', style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'marginBottom': '4px',
                                    'display': 'block',
                                }),
                                dcc.DatePickerSingle(
                                    id='data-date-end',
                                    display_format='YYYY-MM-DD',
                                    className='dark-datepicker date-picker-end',
                                    style={'width': '100%'},
                                ),
                            ], style={'flex': 1}),
                        ], style={'display': 'flex', 'gap': '8px', 'marginBottom': '10px'}),
                        html.Button(
                            'EXPORT CSV',
                            id='data-export-btn',
                            style={**styles['button_outline'], 'width': '100%', 'marginBottom': '10px'},
                            n_clicks=0,
                        ),
                        dcc.Download(id='data-download'),
                    ]),
                    html.Div(id='data-summary-strip'),
                    html.Div(id='data-table-container', style={'fontSize': FONT_SIZES['xs']}),
                ], style={'display': 'none'}),

            ], style=styles['panel_content']),
        ], className='sfa-right-panel-inner'),
    ], style=styles['right_panel'], className='sfa-right-panel')


def _create_backtest_panel(styles: dict, theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Div:
    """Create the backtest panel content."""

    # Strategy mode card style
    mode_card_base = {
        'padding': '8px 10px',
        'borderRadius': BORDER_RADIUS['sm'],
        'border': f'1px solid {theme["border_primary"]}',
        'backgroundColor': theme['bg_secondary'],
        'cursor': 'pointer',
        'transition': 'all 0.1s ease',
        'marginBottom': '4px',
    }
    help_icon_style = styles['help_icon']

    signal_categories = get_signal_categories()

    return html.Div(id='panel-backtest', children=[
        dbc.Accordion(
            [
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Div([
                                html.Span("Execution Type", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'fontWeight': '600',
                                }),
                                html.Span("?", id='help-strategy-mode', style=help_icon_style),
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'space-between',
                                'marginBottom': '8px',
                            }),
                            dcc.RadioItems(
                                id='strategy-mode',
                                options=[
                                    {
                                        'label': html.Div([
                                            html.Div([
                                                html.Div([
                                                    html.Span("Trading", style={
                                                        'fontWeight': '600',
                                                        'fontSize': FONT_SIZES['sm'],
                                                        'color': theme['text_primary'],
                                                    }),
                                                    html.Span(" - Full Buy/Sell", style={
                                                        'fontSize': FONT_SIZES['xs'],
                                                        'color': theme['text_secondary'],
                                                        'marginLeft': '4px',
                                                    }),
                                                ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap'}),
                                                html.Span("?", id='help-strategy-trading', style=help_icon_style),
                                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'}),
                                            html.Div("Buy 100%, then sell 100%", style={
                                                'fontSize': '10px',
                                                'color': theme['text_tertiary'],
                                                'marginTop': '2px',
                                            }),
                                        ], className='strategy-mode-card', style=mode_card_base),
                                        'value': 'trading'
                                    },
                                    {
                                        'label': html.Div([
                                            html.Div([
                                                html.Div([
                                                    html.Span("Accumulation", style={
                                                        'fontWeight': '600',
                                                        'fontSize': FONT_SIZES['sm'],
                                                        'color': theme['accent_green'],
                                                    }),
                                                    html.Span(" - DCA", style={
                                                        'fontSize': FONT_SIZES['xs'],
                                                        'color': theme['text_secondary'],
                                                        'marginLeft': '4px',
                                                    }),
                                                ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap'}),
                                                html.Span("?", id='help-strategy-accumulation', style=help_icon_style),
                                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'}),
                                            html.Div("Fixed $ amount per buy signal", style={
                                                'fontSize': '10px',
                                                'color': theme['text_tertiary'],
                                                'marginTop': '2px',
                                            }),
                                        ], className='strategy-mode-card', style=mode_card_base),
                                        'value': 'accumulation'
                                    },
                                    {
                                        'label': html.Div([
                                            html.Div([
                                                html.Div([
                                                    html.Span("Rebalancing", style={
                                                        'fontWeight': '600',
                                                        'fontSize': FONT_SIZES['sm'],
                                                        'color': theme['accent_blue'],
                                                    }),
                                                    html.Span(" - Partial", style={
                                                        'fontSize': FONT_SIZES['xs'],
                                                        'color': theme['text_secondary'],
                                                        'marginLeft': '4px',
                                                    }),
                                                ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap'}),
                                                html.Span("?", id='help-strategy-rebalancing', style=help_icon_style),
                                            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between'}),
                                            html.Div("Trade % of portfolio per signal", style={
                                                'fontSize': '10px',
                                                'color': theme['text_tertiary'],
                                                'marginTop': '2px',
                                            }),
                                        ], className='strategy-mode-card', style=mode_card_base),
                                        'value': 'rebalancing'
                                    },
                                ],
                                value='trading',
                                className='strategy-mode-radio',
                                inputStyle={'display': 'none'},
                                labelStyle={'display': 'block', 'margin': 0, 'padding': 0},
                            ),
                            dbc.Tooltip(
                                "Choose how signals are executed in the backtest.",
                                target='help-strategy-mode',
                                placement='left',
                                trigger='hover focus',
                            ),
                            dbc.Tooltip(
                                "Full buy on signal, full sell on exit.",
                                target='help-strategy-trading',
                                placement='left',
                                trigger='hover focus',
                            ),
                            dbc.Tooltip(
                                "Fixed dollar-cost averaging on each buy signal.",
                                target='help-strategy-accumulation',
                                placement='left',
                                trigger='hover focus',
                            ),
                            dbc.Tooltip(
                                "Trade a percentage of portfolio each signal.",
                                target='help-strategy-rebalancing',
                                placement='left',
                                trigger='hover focus',
                            ),
                        ])
                    ],
                    title=html.Div([
                        html.Span("Execution Type"),
                        html.Span(
                            id='summary-strategy-mode',
                            className='accordion-title-summary'
                        )
                    ], className='accordion-title-row'),
                    item_id='backtest-strategy',
                ),
                dbc.AccordionItem(
                    [
                        html.Div(id='preset-options', children=[
                            html.Div([
                                html.Span("Strategy Preset", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_purple'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Dropdown(
                                id='strategy-preset',
                                options=[
                                    {'label': 'Custom', 'value': 'custom'},
                                    {'label': 'Swing', 'value': 'swing'},
                                    {'label': 'Position', 'value': 'position'},
                                    {'label': 'Trend', 'value': 'trend'},
                                ],
                                value='custom',
                                clearable=False,
                                style={'fontSize': FONT_SIZES['sm']},
                                className='dark-dropdown',
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_purple"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_purple"]}40',
                        }),
                        dbc.Tooltip(
                            "Quick presets for longer-hold strategies (swing/position/trend).",
                            target='strategy-preset',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='holding-period-options', children=[
                            html.Div([
                                html.Span("Min Holding Period", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_orange'],
                                }),
                                html.Span(" bars", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='min-holding-period',
                                type='number',
                                value=5,
                                min=0,
                                step=1,
                                placeholder='bars to hold',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_orange'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_orange"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_orange"]}40',
                        }),
                        dbc.Tooltip(
                            "Minimum number of bars to hold before a sell/exit.",
                            target='min-holding-period',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='trailing-stop-options', children=[
                            html.Div([
                                html.Span("Trailing Stop", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_red'],
                                }),
                                html.Span(" %", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='trailing-stop-pct',
                                type='number',
                                value=5,
                                min=0,
                                max=100,
                                step=0.5,
                                placeholder='% trail',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_red'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_red"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_red"]}40',
                        }),
                        dbc.Tooltip(
                            "Trailing stop percentage applied after entry.",
                            target='trailing-stop-pct',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='position-scaling-options', children=[
                            html.Div([
                                html.Span("Position Scaling", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_cyan'],
                                }),
                                html.Span(" %", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='position-scaling-pct',
                                type='number',
                                value=25,
                                min=0,
                                max=100,
                                step=1,
                                placeholder='% scale per signal',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_cyan'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_cyan"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_cyan"]}40',
                        }),
                        dbc.Tooltip(
                            "Increase position size by this % on repeated buys.",
                            target='position-scaling-pct',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='consecutive-signal-options', children=[
                            html.Div([
                                html.Span("Consecutive Signals", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_purple'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Dropdown(
                                id='consecutive-signal-mode',
                                options=[
                                    {'label': 'Scale-in (default behavior)', 'value': 'scale_in'},
                                    {'label': 'Edge trigger (0→1 only)', 'value': 'edge'},
                                    {'label': 'Cooldown between triggers', 'value': 'cooldown'},
                                    {'label': 'Reset + Cooldown (stricter)', 'value': 'reset_cooldown'},
                                ],
                                value='scale_in',
                                clearable=False,
                                style={'fontSize': FONT_SIZES['sm']},
                                className='dark-dropdown',
                            ),
                            html.Div(
                                id='consecutive-signal-help',
                                children="Controls repeated triggers for BUY and SELL signals.",
                                style={
                                    'fontSize': '10px',
                                    'color': theme['text_tertiary'],
                                    'marginTop': '6px'
                                }
                            ),
                            html.Div(id='signal-cooldown-container', children=[
                                html.Div([
                                    html.Span("Cooldown", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_secondary'],
                                    }),
                                    html.Span(" bars", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_primary'],
                                    }),
                                ], style={'marginTop': '8px', 'marginBottom': '4px'}),
                                dcc.Input(
                                    id='signal-cooldown-bars',
                                    type='number',
                                    value=5,
                                    min=0,
                                    step=1,
                                    placeholder='bars between triggers',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                        'borderColor': theme['accent_purple'],
                                    }
                                ),
                                html.Div("Applies to BUY and SELL signals.", style={
                                    'fontSize': '10px',
                                    'color': theme['text_tertiary'],
                                    'marginTop': '4px'
                                })
                            ], style={'display': 'block'})
                        ], style={
                            'marginBottom': '12px',
                            'display': 'block',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_purple"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_purple"]}40',
                        }),
                        dbc.Tooltip(
                            "Edge = only on 0→1. Cooldown = wait N bars. Reset+Cooldown = wait for reset plus N bars.",
                            target='consecutive-signal-mode',
                            placement='right',
                            trigger='hover focus',
                        ),
                        dbc.Tooltip(
                            "Best practice defaults: edge=0, cooldown=5, reset+cooldown=5.",
                            target='signal-cooldown-bars',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='take-profit-options', children=[
                            html.Div([
                                html.Span("Take Profit", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_green'],
                                }),
                                html.Span(" %", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='take-profit-pct',
                                type='number',
                                value=0,
                                min=0,
                                max=100,
                                step=0.5,
                                placeholder='% target',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_green'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_green"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_green"]}40',
                        }),
                        dbc.Tooltip(
                            "Exit full position when profit target is reached.",
                            target='take-profit-pct',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='accumulation-options', children=[
                            html.Div([
                                html.Span("Amount Per Buy", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_green'],
                                }),
                                html.Span(" $", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='amount-per-buy',
                                type='number',
                                value=1000,
                                min=100,
                                placeholder='$ per buy signal',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_green'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_green"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_green"]}40',
                        }),
                        dbc.Tooltip(
                            "Dollar amount used for each buy signal in Accumulation mode.",
                            target='amount-per-buy',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='rebalancing-options', children=[
                            html.Div([
                                html.Span("Position Size", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_blue'],
                                }),
                                html.Span(" %", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_primary'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            dcc.Input(
                                id='position-size-pct',
                                type='number',
                                value=25,
                                min=1,
                                max=100,
                                placeholder='% per trade',
                                style={
                                    **styles['input'],
                                    'width': '100%',
                                    'fontFamily': FONT_FAMILY,
                                    'padding': '10px 12px',
                                    'fontSize': FONT_SIZES['base'],
                                    'borderColor': theme['accent_blue'],
                                }
                            ),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_blue"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_blue"]}40',
                        }),
                        dbc.Tooltip(
                            "Percentage of portfolio to trade per signal in Rebalancing mode.",
                            target='position-size-pct',
                            placement='right',
                            trigger='hover focus',
                        ),
                        html.Div(id='kelly-options', children=[
                            html.Div([
                                html.Span("Kelly Criterion", style={
                                    'fontSize': FONT_SIZES['sm'],
                                    'fontWeight': '600',
                                    'color': theme['accent_purple'],
                                }),
                            ], style={'marginBottom': '6px'}),
                            html.Div([
                                html.Div([
                                    html.Span("Win Rate", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_secondary'],
                                    }),
                                ], style={'marginBottom': '4px'}),
                                dcc.Input(
                                    id='kelly-win-rate',
                                    type='number',
                                    value=0.5,
                                    min=0,
                                    max=1,
                                    step=0.01,
                                    placeholder='0.50',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                        'borderColor': theme['accent_purple'],
                                    }
                                ),
                            ], style={'marginBottom': '10px'}),
                            html.Div([
                                html.Div([
                                    html.Span("Win/Loss Ratio", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_secondary'],
                                    }),
                                ], style={'marginBottom': '4px'}),
                                dcc.Input(
                                    id='kelly-win-loss-ratio',
                                    type='number',
                                    value=1.5,
                                    min=0.1,
                                    step=0.1,
                                    placeholder='1.50',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                        'borderColor': theme['accent_purple'],
                                    }
                                ),
                            ]),
                        ], style={
                            'marginBottom': '12px',
                            'display': 'none',
                            'padding': '10px',
                            'backgroundColor': f'{theme["accent_purple"]}10',
                            'borderRadius': BORDER_RADIUS['md'],
                            'border': f'1px solid {theme["accent_purple"]}40',
                        }),
                        dbc.Tooltip(
                            "Probability of a winning trade (0-1).",
                            target='kelly-win-rate',
                            placement='right',
                            trigger='hover focus',
                        ),
                        dbc.Tooltip(
                            "Average win/loss ratio used by Kelly sizing.",
                            target='kelly-win-loss-ratio',
                            placement='right',
                            trigger='hover focus',
                        ),
                    ],
                    title=html.Div([
                        html.Span("Trade Setup"),
                        html.Span(
                            id='summary-position-sizing',
                            className='accordion-title-summary'
                        )
                    ], className='accordion-title-row'),
                    item_id='backtest-sizing',
                ),
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Div([
                                html.Div([
                                    html.Span("SIGNALS", style=styles['card_header']),
                                    html.Span("?", id='help-signal-section', style=help_icon_style),
                                ], style={'display': 'flex', 'alignItems': 'center'}),
                                # AND/OR Toggle
                                html.Div([
                                    dcc.RadioItems(
                                        id='signal-logic-mode',
                                        options=[
                                            {'label': 'OR', 'value': 'or'},
                                            {'label': 'AND', 'value': 'and'},
                                        ],
                                        value='or',
                                        inline=True,
                                        inputStyle={'marginRight': '4px'},
                                        labelStyle={
                                            'fontSize': FONT_SIZES['xs'],
                                            'padding': '2px 8px',
                                            'cursor': 'pointer',
                                            'marginRight': '4px',
                                        },
                                        className='signal-logic-toggle'
                                    ),
                                ], style={
                                    'backgroundColor': theme['bg_tertiary'],
                                    'borderRadius': '4px',
                                    'padding': '2px 4px',
                                }),
                            ], style={'display': 'flex', 'justifyContent': 'space-between', 'alignItems': 'center', 'marginBottom': '6px'}),
                            html.Div([
                                html.Div([
                                    html.Label("AND Window", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_secondary'],
                                        'marginBottom': 0,
                                        'display': 'block'
                                    }),
                                    html.Span("?", id='help-signal-window', style=help_icon_style),
                                ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '4px'}),
                                dcc.Slider(
                                    id='signal-window',
                                    min=0,
                                    max=10,
                                    step=1,
                                    value=DEFAULT_SIGNAL_WINDOW,
                                    marks={
                                        0: {'label': '0', 'style': {'color': theme['text_secondary']}},
                                        2: {'label': '2', 'style': {'color': theme['text_secondary']}},
                                        4: {'label': '4', 'style': {'color': theme['text_secondary']}},
                                        6: {'label': '6', 'style': {'color': theme['text_secondary']}},
                                        8: {'label': '8', 'style': {'color': theme['text_secondary']}},
                                        10: {'label': '10', 'style': {'color': theme['text_secondary']}}
                                    }
                                ),
                                html.Div("Signals must occur within this window for AND logic.", style={
                                    'fontSize': '10px',
                                    'color': theme['text_tertiary'],
                                    'marginTop': '4px'
                                })
                            ], id='signal-window-container', style={'marginBottom': '10px'}),
                            html.Div([
                                html.Div([
                                    html.Div("Filters", className='signals-filter-label'),
                                    dcc.Input(
                                        id='signals-search',
                                        type='text',
                                        placeholder='Search signals...',
                                        style=styles['input'],
                                    ),
                                    html.Div("Categories", className='signals-filter-label'),
                                    dcc.Checklist(
                                        id='signals-category-filter',
                                        options=[{'label': cat, 'value': cat} for cat in signal_categories],
                                        value=signal_categories,
                                        inline=True,
                                        className='signals-category-filter'
                                    ),
                                ], className='signals-unified-controls'),
                                dcc.Loading(
                                    id='signals-unified-loading',
                                    type='circle',
                                    color=theme['accent_blue'],
                                    delay_show=200,
                                    children=html.Div(
                                        id='signals-unified-list',
                                        className='signals-unified-list'
                                    ),
                                ),
                                dcc.Checklist(
                                    id='buy-signals',
                                    options=bootstrap.buy_options if bootstrap else [],
                                    value=[],
                                    style={'display': 'none'},
                                ),
                                dcc.Checklist(
                                    id='sell-signals',
                                    options=bootstrap.sell_options if bootstrap else [],
                                    value=[],
                                    style={'display': 'none'},
                                ),
                            ], style={'marginTop': '6px'}),
                            dbc.Tooltip(
                                "Configure how multiple signals combine to create entries.",
                                target='help-signal-section',
                                placement='left',
                                trigger='hover focus',
                            ),
                            dbc.Tooltip(
                                "When using AND, signals must occur within this window.",
                                target='help-signal-window',
                                placement='left',
                                trigger='hover focus',
                            ),
                        ], style=styles['card'])
                    ],
                    title=html.Div([
                        html.Span("Signals"),
                        html.Span(
                            id='summary-signal-settings',
                            className='accordion-title-summary accordion-title-summary--signals'
                        )
                    ], className='accordion-title-row'),
                    item_id='backtest-signals',
                ),
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Div([
                                html.Span("TRANSACTION COSTS", style=styles['card_header']),
                                html.Span("?", id='help-transaction-costs', style=help_icon_style),
                            ], style={'display': 'flex', 'alignItems': 'center'}),
                            html.Div([
                                html.Label("FX Fee (%)", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'marginBottom': '4px',
                                    'display': 'block'
                                }),
                                dcc.Input(
                                    id='fx-fee-pct',
                                    type='number',
                                    value=0.15,
                                    min=0,
                                    step=0.01,
                                    placeholder='0.15',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                    }
                                ),
                            ], style={'marginBottom': '10px'}),
                            html.Div([
                                html.Label("Slippage (%)", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'marginBottom': '4px',
                                    'display': 'block'
                                }),
                                dcc.Input(
                                    id='slippage-pct',
                                    type='number',
                                    value=0.05,
                                    min=0,
                                    step=0.01,
                                    placeholder='0.05',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                    }
                                ),
                            ], style={'marginBottom': '10px'}),
                            html.Div([
                                html.Label("Commission (%)", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'marginBottom': '4px',
                                    'display': 'block'
                                }),
                                dcc.Input(
                                    id='commission-pct',
                                    type='number',
                                    value=0.0,
                                    min=0,
                                    step=0.01,
                                    placeholder='0.00',
                                    style={
                                        **styles['input'],
                                        'width': '100%',
                                        'fontFamily': FONT_FAMILY,
                                        'padding': '10px 12px',
                                        'fontSize': FONT_SIZES['base'],
                                    }
                                ),
                            ], style={'marginBottom': '4px'}),
                            html.Div("Trading 212 UK: 0% commission, 0.15% FX fee.", style={
                                'fontSize': '10px',
                                'color': theme['text_tertiary'],
                                'marginTop': '2px'
                            }),
                            dbc.Tooltip(
                                "Applied on every trade. FX fee assumes cross-currency.",
                                target='help-transaction-costs',
                                placement='left',
                                trigger='hover focus',
                            ),
                        ], style=styles['card'])
                    ],
                    title=html.Div([
                        html.Span("Transaction Costs"),
                        html.Span(
                            id='summary-transaction-costs',
                            className='accordion-title-summary'
                        )
                    ], className='accordion-title-row'),
                    item_id='backtest-costs',
                ),
            ],
            className='compact-accordion',
            always_open=True,
            active_item=['backtest-strategy', 'backtest-signals'],
            flush=True,
        ),

        html.Button(
            "RUN BACKTEST",
            id='run-backtest-btn',
            style={**styles['button_primary'], 'width': '100%', 'padding': '10px 14px'},
            n_clicks=0
        ),
        dbc.Tooltip("Simulate trading with selected buy/sell signals", target='run-backtest-btn', placement='top'),

        dcc.Loading(
            id='backtest-loading',
            type='circle',
            color=theme['accent_blue'],
            delay_show=200,
            children=html.Div(id='backtest-results', style={'marginTop': '10px'}),
        ),
    ])


def _create_optimizer_panel(styles: dict, theme: dict) -> html.Div:
    """Create the optimizer panel content with progress and enhanced controls."""
    card_style = {
        'backgroundColor': theme['bg_tertiary'],
        'borderRadius': BORDER_RADIUS['sm'],
        'padding': '8px 10px',
        'marginBottom': '10px',
        'border': f'1px solid {theme["border_primary"]}'
    }
    help_icon_style = styles['help_icon']

    return html.Div(id='panel-optimizer', children=[
        # Signal Preview Card
        html.Div([
            html.Div([
                html.Div("SIGNAL PREVIEW", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_tertiary'],
                    'fontWeight': '600',
                    'letterSpacing': '0.5px'
                }),
                html.Span("?", id='help-signal-preview', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '8px'}),
            html.Div(id='signal-preview', children=[
                html.Div([
                    ticker_pill('BUY', '0', color='up', value_id='preview-buy-count'),
                    html.Span('│', className='num', style={'color': theme['border_primary']}),
                    ticker_pill('SELL', '0', color='down', value_id='preview-sell-count'),
                    html.Span('│', className='num', style={'color': theme['border_primary']}),
                    ticker_pill('COMBOS', '0', color='amber', value_id='preview-combo-count'),
                ], style={'display': 'flex', 'alignItems': 'center', 'gap': '6px', 'flexWrap': 'wrap'}),
            ]),
        ], style=card_style),

        # Optimization Settings
        html.Div([
            html.Div([
                html.Label("Max Signals per Side", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'marginBottom': 0,
                    'display': 'block'
                }),
                html.Span("?", id='help-max-signals', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '8px'}),
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
                    'display': 'block'
                }),
                html.Span("?", id='help-max-combos', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '4px'}),
            dense_input(
                id='max-combos-input',
                type='number',
                value=100,
                min=10, max=1000,
                style=styles['input']
            ),
        ], style={'marginBottom': '16px'}),

        html.Div([
            html.Div([
                html.Label("Min Trades", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'marginBottom': 0,
                    'display': 'block'
                }),
                html.Span("?", id='help-min-trades', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '4px'}),
            dense_input(
                id='min-trades-input',
                type='number',
                value=10,
                min=1, max=500,
                style=styles['input']
            ),
        ], style={'marginBottom': '16px'}),

        # Sort Options
        html.Div([
            html.Div([
                html.Label("Sort Results By", style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'marginBottom': 0,
                    'display': 'block'
                }),
                html.Span("?", id='help-sort-metric', style=help_icon_style),
            ], style={'display': 'flex', 'alignItems': 'center', 'justifyContent': 'space-between', 'marginBottom': '4px'}),
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
                className='bbg-radio-seg'
            ),
        ], style={'marginBottom': '16px'}),
        dbc.Tooltip(
            "Counts selected signals and estimated combinations.",
            target='help-signal-preview',
            placement='left',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Limit how many signals can be chosen per side.",
            target='help-max-signals',
            placement='left',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Cap the total combinations to test for speed.",
            target='help-max-combos',
            placement='left',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Combos with fewer trades than this are flagged 'low sample' and "
            "ranked below credible ones — a great ratio on a handful of trades is noise.",
            target='help-min-trades',
            placement='left',
            trigger='hover focus',
        ),
        dbc.Tooltip(
            "Choose the metric used to rank results. SCORE is a robustness-weighted "
            "blend that rewards risk-adjusted return and penalises too-few trades.",
            target='help-sort-metric',
            placement='left',
            trigger='hover focus',
        ),

        # Run Button
        html.Button(
            "RUN OPTIMIZER",
            id='run-optimization-btn',
            style={**styles['button_primary'], 'width': '100%'},
            n_clicks=0
        ),
        dbc.Tooltip("Test all signal combinations to find the best strategy", target='run-optimization-btn', placement='top'),

        # Progress Section
        html.Div(id='optimization-progress', style={'marginTop': '12px'}),

        # Results Section
        html.Div(id='optimization-results', style={'marginTop': '16px'}),

        # Apply Strategy Button (hidden initially)
        html.Div(id='apply-strategy-container', children=[
            html.Button(
                "Apply Best Strategy",
                id='apply-strategy-btn',
                style={
                    **styles['button_primary'],
                    'width': '100%',
                    'marginTop': '12px',
                    'backgroundColor': theme['accent_green']
                },
                n_clicks=0,
            ),
            dbc.Tooltip("Apply the best strategy to the Backtest panel", target='apply-strategy-btn', placement='top'),
        ], style={'display': 'none'}),

    ], style={'display': 'none'})