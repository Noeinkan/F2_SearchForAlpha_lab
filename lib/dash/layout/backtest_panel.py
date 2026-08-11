"""
Backtest tab: accordion controls, results, execution-mode cards.

Kept as one builder so accordion section IDs and tooltips stay co-located.
Composed into the right panel via ``right_panel._create_right_panel``.
"""

import dash_bootstrap_components as dbc
from dash import dcc, html

from lib.dash.dash_config import (
    FONT_SIZES, FONT_FAMILY, BORDER_RADIUS, DEFAULT_SIGNAL_WINDOW,
    DEFAULT_OFF_SIGNAL_CATEGORIES, INITIAL_CAPITAL, TEST_WINDOW_PRESETS,
)
from lib.dash.components import dense_input
from lib.dash.bootstrap import BootstrapSnapshot
from lib.dash.execution_glossary import MODE_ORDER, MODE_SPECS
from lib.dash.execution_view import mode_accent, render_fingerprint, render_mode_preview
from lib.signals.indicators import get_signal_categories


def _strategy_mode_options(theme: dict, help_icon_style: dict) -> list[dict]:
    """Build the three execution-mode cards from the glossary + live engine runs.

    Every card carries: the mode's honest caption, a sparkline "fingerprint" of
    how it behaves on the shared demo tape, and a preview line stating what the
    first buy signal actually does in dollars. The preview is re-rendered by
    ``callbacks/execution_help.py`` whenever capital or the sizing knobs change —
    the id here is what that callback targets.
    """
    options = []
    for mode in MODE_ORDER:
        spec = MODE_SPECS[mode]
        accent = mode_accent(theme, mode)
        options.append({
            'label': html.Div([
                html.Div([
                    html.Div([
                        html.Span(spec['name'], style={
                            'fontWeight': '600',
                            'fontSize': FONT_SIZES['sm'],
                            'color': accent,
                        }),
                        html.Span(f" - {spec['suffix']}", style={
                            'fontSize': FONT_SIZES['xs'],
                            'color': theme['text_secondary'],
                            'marginLeft': '4px',
                        }),
                    ], style={'display': 'flex', 'alignItems': 'center', 'flexWrap': 'wrap'}),
                    html.Span("?", id=f'help-strategy-{mode}', n_clicks=0,
                              style=help_icon_style,
                              title=f"How {spec['name']} works"),
                ], style={'display': 'flex', 'alignItems': 'center',
                          'justifyContent': 'space-between'}),
                html.Div(spec['caption'], style={
                    'fontSize': '10px',
                    'color': theme['text_tertiary'],
                    'marginTop': '2px',
                }),
                html.Div(render_mode_preview(theme, mode), id=f'preview-mode-{mode}'),
                render_fingerprint(theme, mode),
            ], className='strategy-mode-card'),
            'value': mode,
        })
    return options


def _trade_setup_field_label(
    text: str,
    help_id: str,
    help_icon_style: dict,
    theme: dict,
    unit: str | None = None,
) -> html.Div:
    """Label + ? row matching Signals / Transaction Costs / optimizer panels."""
    title_row = [
        html.Span(text, style={
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_secondary'],
            'fontWeight': '600',
        }),
    ]
    if unit:
        title_row.append(html.Span(f" {unit}", style={
            'fontSize': FONT_SIZES['xs'],
            'color': theme['text_tertiary'],
            'fontWeight': '500',
        }))
    return html.Div([
        html.Div(title_row, style={'display': 'flex', 'alignItems': 'baseline', 'gap': '2px'}),
        html.Span("?", id=help_id, style=help_icon_style),
    ], style={
        'display': 'flex',
        'alignItems': 'center',
        'justifyContent': 'space-between',
        'marginBottom': '4px',
    })


def _trade_setup_panel_style(theme: dict, *, visible: bool = False) -> dict:
    """Neutral field block — show/hide only; no rainbow accent cards."""
    return {
        'marginBottom': '10px',
        'display': 'block' if visible else 'none',
        'padding': '0 0 10px 0',
        'backgroundColor': 'transparent',
        'borderRadius': BORDER_RADIUS['sm'],
        'border': 'none',
        'borderBottom': f'1px solid {theme["border_primary"]}',
        'color': theme['text_primary'],
    }


def _trade_setup_input_style(styles: dict) -> dict:
    return {
        **styles['input'],
        'width': '100%',
        'fontFamily': FONT_FAMILY,
        'padding': '10px 12px',
        'fontSize': FONT_SIZES['base'],
    }


def _trade_setup_stepper(input_el) -> html.Div:
    """Wrap a number input with visible − / + buttons (see 25-trade-setup-stepper.js)."""
    return html.Div([
        html.Button(
            "−",
            type='button',
            className='sfa-num-stepper__btn',
            **{'data-dir': '-1'},
        ),
        input_el,
        html.Button(
            "+",
            type='button',
            className='sfa-num-stepper__btn',
            **{'data-dir': '1'},
        ),
    ], className='sfa-num-stepper')


def _tip(text: str, *targets: str) -> list:
    """One tooltip body attached to every target id (help ? and/or field)."""
    return [
        dbc.Tooltip(
            text,
            target=target,
            placement='left',
            trigger='hover focus',
        )
        for target in targets
    ]


def _create_backtest_panel(styles: dict, theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Div:
    """Create the backtest panel content."""

    # Strategy mode cards are styled entirely by `.strategy-mode-card` in
    # dashboard.css. They used to carry an inline style dict too, which silently
    # beat the stylesheet and killed the :hover and :checked rules.
    help_icon_style = styles['help_icon']
    # The mode "?" glyphs open the Execution Type explainer, so they must be
    # clickable Inputs rather than the hover-only cursor:'help' the others use.
    mode_help_style = {**help_icon_style, 'cursor': 'pointer'}

    signal_categories = get_signal_categories()
    # Filter/regime categories are selectable but start unticked — see
    # DEFAULT_OFF_SIGNAL_CATEGORIES in dash_config.
    default_signal_categories = [
        category for category in signal_categories
        if category not in DEFAULT_OFF_SIGNAL_CATEGORIES
    ]

    return html.Div(id='panel-backtest', children=[
        dbc.Accordion(
            [
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Div([
                                html.Span("Test Window", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'fontWeight': '600',
                                }),
                                html.Span("?", id='help-test-window', style=help_icon_style),
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'space-between',
                                'marginBottom': '6px',
                            }),
                            dcc.RadioItems(
                                id='test-window-preset',
                                options=TEST_WINDOW_PRESETS,
                                value='max',
                                inline=True,
                                className='bbg-radio-seg sfa-test-window-seg',
                            ),
                            html.Div([
                                html.Div([
                                    html.Label("From", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_secondary'],
                                        'marginBottom': '4px',
                                        'display': 'block',
                                    }),
                                    dcc.DatePickerSingle(
                                        id='test-window-start',
                                        display_format='YYYY-MM-DD',
                                        className='dark-datepicker',
                                        style={'width': '100%'},
                                    ),
                                ], style={'flex': 1}),
                                html.Div([
                                    html.Label("To", style={
                                        'fontSize': FONT_SIZES['xs'],
                                        'color': theme['text_secondary'],
                                        'marginBottom': '4px',
                                        'display': 'block',
                                    }),
                                    dcc.DatePickerSingle(
                                        id='test-window-end',
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

                            html.Div([
                                html.Label("Initial Capital", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'marginBottom': '4px',
                                    'display': 'block',
                                }),
                                dense_input(
                                    id='initial-capital',
                                    type='number',
                                    value=INITIAL_CAPITAL,
                                    style={**styles['input'], 'textAlign': 'right'},
                                ),
                            ]),
                            dbc.Tooltip(
                                "The period the backtest and optimizer evaluate. Data is always "
                                "fetched in full — this narrows what gets measured, and scrolls "
                                "the chart to match. Changing it needs no re-fetch.",
                                target='help-test-window',
                                placement='left',
                                trigger='hover focus',
                            ),
                        ])
                    ],
                    title=html.Div([
                        html.Span("Test Window"),
                        html.Span(
                            id='summary-test-window',
                            className='accordion-title-summary'
                        )
                    ], className='accordion-title-row'),
                    item_id='backtest-window',
                ),
                dbc.AccordionItem(
                    [
                        html.Div([
                            html.Div([
                                html.Span("Execution Type", style={
                                    'fontSize': FONT_SIZES['xs'],
                                    'color': theme['text_secondary'],
                                    'fontWeight': '600',
                                }),
                                html.Span("?", id='help-strategy-mode', n_clicks=0,
                                          style=mode_help_style,
                                          title='How the execution modes work'),
                            ], style={
                                'display': 'flex',
                                'alignItems': 'center',
                                'justifyContent': 'space-between',
                                'marginBottom': '8px',
                            }),
                            dcc.RadioItems(
                                id='strategy-mode',
                                options=_strategy_mode_options(theme, mode_help_style),
                                value='trading',
                                className='strategy-mode-radio',
                                inputStyle={'display': 'none'},
                                labelStyle={'display': 'block', 'margin': 0, 'padding': 0},
                            ),
                            # Hover gives one true sentence; clicking opens the
                            # explorable. Both come from execution_glossary, so
                            # they cannot drift apart from each other.
                            dbc.Tooltip(
                                "How signals become orders. Click for the full breakdown.",
                                target='help-strategy-mode',
                                placement='left',
                                trigger='hover focus',
                            ),
                            *[
                                dbc.Tooltip(
                                    MODE_SPECS[mode]['one_liner'] + " Click for details.",
                                    target=f'help-strategy-{mode}',
                                    placement='left',
                                    trigger='hover focus',
                                )
                                for mode in MODE_ORDER
                            ],
                            html.Button(
                                "HOW EXECUTION WORKS",
                                id='execution-learn-button',
                                n_clicks=0,
                                className='sfa-exec-learn-btn',
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
                        html.Div([
                            html.Div([
                                html.Span("TRADE SETUP", style=styles['card_header']),
                                html.Span("?", id='help-trade-setup', style=help_icon_style),
                            ], style={'display': 'flex', 'alignItems': 'center'}),
                            html.Div([
                                html.Div(id='preset-options', children=[
                                    _trade_setup_field_label(
                                        "Strategy Preset", 'help-strategy-preset',
                                        help_icon_style, theme,
                                    ),
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
                                ], style=_trade_setup_panel_style(theme, visible=False)),
                                *_tip(
                                    "Quick starting points for hold length and stops. "
                                    "Swing / Position / Trend fill min hold, trailing stop, "
                                    "scale-in and take-profit. Custom keeps your numbers.",
                                    'help-strategy-preset', 'strategy-preset',
                                ),
                                html.Div(id='holding-period-options', children=[
                                    _trade_setup_field_label(
                                        "Min Holding Period", 'help-min-holding',
                                        help_icon_style, theme, unit="bars",
                                    ),
                                    _trade_setup_stepper(dcc.Input(
                                        id='min-holding-period',
                                        type='number',
                                        value=5,
                                        min=0,
                                        step=1,
                                        placeholder='bars to hold',
                                        style=_trade_setup_input_style(styles),
                                    )),
                                ], style=_trade_setup_panel_style(theme, visible=False)),
                                *_tip(
                                    "Force the trade to stay open at least this many candles "
                                    "before a sell or take-profit can fire. Stops jittery "
                                    "in-and-out churn. Trailing stops still work during the wait.",
                                    'help-min-holding', 'min-holding-period',
                                ),
                                html.Div(id='trailing-stop-options', children=[
                                    _trade_setup_field_label(
                                        "Trailing Stop", 'help-trailing-stop',
                                        help_icon_style, theme, unit="%",
                                    ),
                                    _trade_setup_stepper(dcc.Input(
                                        id='trailing-stop-pct',
                                        type='number',
                                        value=5,
                                        min=0,
                                        max=100,
                                        step=0.5,
                                        placeholder='% trail',
                                        style=_trade_setup_input_style(styles),
                                    )),
                                    html.Div([
                                        dcc.RadioItems(
                                            id='stop-mode',
                                            options=[
                                                {'label': '% TRAIL', 'value': 'percent'},
                                                {'label': 'ATR', 'value': 'atr'},
                                            ],
                                            value='percent',
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
                                        'marginTop': '8px',
                                        'backgroundColor': theme['bg_secondary'],
                                        'borderRadius': '4px',
                                        'padding': '2px 4px',
                                        'display': 'inline-block',
                                    }),
                                ], style=_trade_setup_panel_style(theme, visible=False)),
                                *_tip(
                                    "Safety net: auto-sell if price falls this far from the "
                                    "best point since entry. % TRAIL uses the number above; "
                                    "ATR uses a volatility-scaled Chandelier stop (needs ATR "
                                    "signals; falls back to % otherwise).",
                                    'help-trailing-stop', 'trailing-stop-pct', 'stop-mode',
                                ),
                                html.Div(id='position-scaling-options', children=[
                                    _trade_setup_field_label(
                                        "Scale-in", 'help-position-scaling',
                                        help_icon_style, theme, unit="%",
                                    ),
                                    # 100% = one signal buys the whole Kelly-sized entry.
                                    _trade_setup_stepper(dcc.Input(
                                        id='position-scaling-pct',
                                        type='number',
                                        value=100,
                                        min=0,
                                        max=100,
                                        step=1,
                                        placeholder='% of target size per signal',
                                        style=_trade_setup_input_style(styles),
                                    )),
                                ], style=_trade_setup_panel_style(theme, visible=False)),
                                *_tip(
                                    "How much of the full Kelly-sized entry each buy takes. "
                                    "100% = full size on the first signal. Lower values ramp "
                                    "in — and keep stacking on repeats (they do not stop at "
                                    "100% of target).",
                                    'help-position-scaling', 'position-scaling-pct',
                                ),
                                html.Div(id='consecutive-signal-options', children=[
                                    _trade_setup_field_label(
                                        "Consecutive Signals", 'help-consecutive-signals',
                                        help_icon_style, theme,
                                    ),
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
                                    # Hidden sink for strategy_ui mode-help callback.
                                    html.Div(
                                        id='consecutive-signal-help',
                                        style={'display': 'none'},
                                    ),
                                    html.Div(id='signal-cooldown-container', children=[
                                        html.Div([
                                            html.Span("Cooldown bars", style={
                                                'fontSize': FONT_SIZES['xs'],
                                                'color': theme['text_secondary'],
                                                'fontWeight': '600',
                                            }),
                                            html.Span("?", id='help-signal-cooldown',
                                                      style=help_icon_style),
                                        ], style={
                                            'display': 'flex',
                                            'alignItems': 'center',
                                            'justifyContent': 'space-between',
                                            'marginTop': '8px',
                                            'marginBottom': '4px',
                                        }),
                                        _trade_setup_stepper(dcc.Input(
                                            id='signal-cooldown-bars',
                                            type='number',
                                            value=5,
                                            min=0,
                                            step=1,
                                            placeholder='bars between triggers',
                                            style=_trade_setup_input_style(styles),
                                        )),
                                    ], style={'display': 'block'}),
                                ], style={
                                    **_trade_setup_panel_style(theme, visible=True),
                                }),
                                *_tip(
                                    "When the same signal stays on for several bars: "
                                    "Scale-in acts every time; Edge only on 0→1; "
                                    "Cooldown waits N bars; Reset+Cooldown also requires "
                                    "the signal to turn fully off first.",
                                    'help-consecutive-signals', 'consecutive-signal-mode',
                                ),
                                *_tip(
                                    "Bars to wait after a trade before the same side can "
                                    "fire again. Applies to buys and sells. "
                                    "Defaults: cooldown=5, reset+cooldown=5.",
                                    'help-signal-cooldown', 'signal-cooldown-bars',
                                ),
                                html.Div(id='take-profit-options', children=[
                                    _trade_setup_field_label(
                                        "Take Profit", 'help-take-profit',
                                        help_icon_style, theme, unit="%",
                                    ),
                                    _trade_setup_stepper(dcc.Input(
                                        id='take-profit-pct',
                                        type='number',
                                        value=0,
                                        min=0,
                                        max=100,
                                        step=0.5,
                                        placeholder='% target',
                                        style=_trade_setup_input_style(styles),
                                    )),
                                ], style=_trade_setup_panel_style(theme, visible=False)),
                                *_tip(
                                    "Lock in gains: exit the whole position once you're up "
                                    "this % from average entry (after min holding). 0 = off.",
                                    'help-take-profit', 'take-profit-pct',
                                ),
                                html.Div(id='accumulation-options', children=[
                                    _trade_setup_field_label(
                                        "Amount Per Buy", 'help-amount-per-buy',
                                        help_icon_style, theme, unit="$",
                                    ),
                                    _trade_setup_stepper(dcc.Input(
                                        id='amount-per-buy',
                                        type='number',
                                        value=1000,
                                        min=100,
                                        placeholder='$ per buy signal',
                                        style=_trade_setup_input_style(styles),
                                    )),
                                ], style=_trade_setup_panel_style(theme, visible=False)),
                                *_tip(
                                    "Dollar amount spent on each buy signal until cash runs "
                                    "out. This mode only ever buys — sell signals, trailing "
                                    "stop, take profit and min holding are inactive.",
                                    'help-amount-per-buy', 'amount-per-buy',
                                ),
                                # Selecting sell signals in Accumulation is dead config —
                                # populated by callbacks/execution_help.py.
                                html.Div(id='accumulation-sell-warning'),
                                html.Div(id='rebalancing-options', children=[
                                    _trade_setup_field_label(
                                        "Portfolio Weight", 'help-position-size',
                                        help_icon_style, theme, unit="%",
                                    ),
                                    _trade_setup_stepper(dcc.Input(
                                        id='position-size-pct',
                                        type='number',
                                        value=25,
                                        min=1,
                                        max=100,
                                        placeholder='% per trade',
                                        style=_trade_setup_input_style(styles),
                                    )),
                                ], style=_trade_setup_panel_style(theme, visible=False)),
                                *_tip(
                                    "Each signal trades this % of total portfolio value — "
                                    "same size in on a buy and out on a sell. A stop or "
                                    "take-profit still exits the whole position.",
                                    'help-position-size', 'position-size-pct',
                                ),
                                html.Div(id='kelly-options', children=[
                                    _trade_setup_field_label(
                                        "Kelly Criterion", 'help-kelly',
                                        help_icon_style, theme,
                                    ),
                                    html.Div([
                                        html.Div([
                                            html.Span("Win Rate", style={
                                                'fontSize': FONT_SIZES['xs'],
                                                'color': theme['text_secondary'],
                                                'fontWeight': '600',
                                            }),
                                            html.Span("?", id='help-kelly-win-rate',
                                                      style=help_icon_style),
                                        ], style={
                                            'display': 'flex',
                                            'alignItems': 'center',
                                            'justifyContent': 'space-between',
                                            'marginBottom': '4px',
                                        }),
                                        _trade_setup_stepper(dcc.Input(
                                            id='kelly-win-rate',
                                            type='number',
                                            value=0.5,
                                            min=0,
                                            max=1,
                                            step=0.01,
                                            placeholder='0.50',
                                            style=_trade_setup_input_style(styles),
                                        )),
                                    ], style={'marginBottom': '8px'}),
                                    html.Div([
                                        html.Div([
                                            html.Span("Win/Loss Ratio", style={
                                                'fontSize': FONT_SIZES['xs'],
                                                'color': theme['text_secondary'],
                                                'fontWeight': '600',
                                            }),
                                            html.Span("?", id='help-kelly-wl',
                                                      style=help_icon_style),
                                        ], style={
                                            'display': 'flex',
                                            'alignItems': 'center',
                                            'justifyContent': 'space-between',
                                            'marginBottom': '4px',
                                        }),
                                        _trade_setup_stepper(dcc.Input(
                                            id='kelly-win-loss-ratio',
                                            type='number',
                                            value=1.5,
                                            min=0.1,
                                            step=0.1,
                                            placeholder='1.50',
                                            style=_trade_setup_input_style(styles),
                                        )),
                                    ]),
                                ], style=_trade_setup_panel_style(theme, visible=False)),
                                *_tip(
                                    "Bet-sizing formula for entry size. Defaults "
                                    "(0.50 win rate / 1.50 win÷loss) → about 16.7% of the "
                                    "account per full entry. Leave alone unless you know it.",
                                    'help-kelly',
                                ),
                                *_tip(
                                    "Assumed chance a trade wins, from 0 to 1 (0.50 = half the time).",
                                    'help-kelly-win-rate', 'kelly-win-rate',
                                ),
                                *_tip(
                                    "Average win size ÷ average loss size. 1.50 means wins "
                                    "are typically 1.5× larger than losses.",
                                    'help-kelly-wl', 'kelly-win-loss-ratio',
                                ),
                            ], style={'padding': '8px 10px'}),
                            *_tip(
                                "Sizing and exits for the execution mode above. These knobs "
                                "change how trades are sized and closed — not which "
                                "indicator signals fire.",
                                'help-trade-setup',
                            ),
                        ], style=styles['card'])
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
                                        value=default_signal_categories,
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
            active_item=[
                'backtest-window',
                'backtest-strategy',
                'backtest-sizing',
                'backtest-signals',
            ],
            flush=True,
        ),

        html.Button(
            "RUN BACKTEST",
            id='run-backtest-btn',
            style={**styles['button_primary'], 'width': '100%', 'padding': '10px 14px'},
            n_clicks=0
        ),
        dbc.Tooltip("Simulate trading with selected buy/sell signals", target='run-backtest-btn', placement='top'),

        html.Button(
            "OPEN OPTIMIZER",
            id='open-optimizer-button',
            n_clicks=0,
            style={
                **styles['button_outline'],
                'width': '100%',
                'padding': '8px 14px',
                'marginTop': '8px',
            },
        ),
        dbc.Tooltip(
            "Open the full-screen Optimizer to search signal combinations.",
            target='open-optimizer-button',
            placement='top',
        ),
        html.Button(
            "OPEN DATA",
            id='open-data-button',
            n_clicks=0,
            style={
                **styles['button_outline'],
                'width': '100%',
                'padding': '8px 14px',
                'marginTop': '8px',
            },
        ),
        dbc.Tooltip(
            "Open the loaded data table without leaving the current workspace.",
            target='open-data-button',
            placement='top',
        ),

        html.Div(id='backtest-origin-note', style={'marginTop': '10px'}),
        dcc.Loading(
            id='backtest-loading',
            type='circle',
            color=theme['accent_blue'],
            delay_show=200,
            children=html.Div(id='backtest-results', style={'marginTop': '10px'}),
        ),

        # --- Execution Type explainer -----------------------------------------
        # Sandbox UI state is ephemeral (which mode tab, the pending guess, the
        # live slider values); only `explored` persists, so a returning user
        # keeps their progress dots.
        dcc.Store(id='execution-learn-state', data={'mode': 'trading', 'guess': None,
                                                    'revealed': False, 'params': {}}),
        dcc.Store(id='execution-explored-store', storage_type='local', data=[]),
        dbc.Modal(
            [
                dbc.ModalHeader(dbc.ModalTitle("How Execution Type works"), close_button=True),
                dbc.ModalBody(id='execution-learn-modal-body',
                              className='sfa-exec-learn-modal-body'),
                dbc.ModalFooter(
                    html.Button("Close", id='execution-learn-close', n_clicks=0,
                                style={**styles['button_outline'], 'padding': '6px 14px'})
                ),
            ],
            id='execution-learn-modal',
            is_open=False,
            centered=True,
            size='lg',
            backdrop=True,
            keyboard=True,
            scrollable=True,
            className='sfa-exec-learn-modal',
        ),
    ])

