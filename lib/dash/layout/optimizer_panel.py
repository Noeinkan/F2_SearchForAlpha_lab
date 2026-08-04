"""
Optimizer right-rail teaser: deep-links to the full-screen /optimize workspace.
"""

from dash import html
import dash_bootstrap_components as dbc

from lib.dash.dash_config import FONT_SIZES, BORDER_RADIUS


def _create_optimizer_panel(styles: dict, theme: dict) -> html.Div:
    """Thin teaser — live controls live on the full-screen Optimizer page."""
    card_style = {
        'backgroundColor': theme['bg_tertiary'],
        'borderRadius': BORDER_RADIUS['sm'],
        'padding': '12px 10px',
        'marginBottom': '10px',
        'border': f'1px solid {theme["border_primary"]}',
    }

    return html.Div(id='panel-optimizer', children=[
        html.Div([
            html.Div("FULL-SCREEN OPTIMIZER", style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_tertiary'],
                'fontWeight': '600',
                'letterSpacing': '0.5px',
                'marginBottom': '8px',
            }),
            html.Div(
                "Full-screen workspace for signal-combo grid search, Bayesian "
                "param sweeps, and walk-forward Validate OOS — with room for "
                "knobs, progress, and a leaderboard. Open LEARN on that page for "
                "a beginner walkthrough.",
                style={
                    'fontSize': FONT_SIZES['xs'],
                    'color': theme['text_secondary'],
                    'lineHeight': '1.45',
                    'marginBottom': '12px',
                },
            ),
            html.Button(
                "OPEN FULL OPTIMIZER",
                id='open-optimizer-from-teaser',
                n_clicks=0,
                style={**styles['button_primary'], 'width': '100%'},
            ),
            dbc.Tooltip(
                "Open the full-screen Optimizer. Start with RUN OPTIMIZER "
                "(combo grid search); use LEARN if the controls feel opaque.",
                target='open-optimizer-from-teaser',
                placement='left',
            ),
        ], style=card_style),
        html.Div(
            "Tip: also open from the Backtest tab or command palette "
            "(Navigate → Open optimizer). New here? Press LEARN in the header.",
            style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_tertiary'],
                'lineHeight': '1.4',
                'fontStyle': 'italic',
            },
        ),
    ], style={'display': 'none'})
