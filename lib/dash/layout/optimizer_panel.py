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
                "Search hundreds of buy/sell signal combinations on a dedicated "
                "page — room for search knobs, progress, and a full leaderboard. "
                "Capital and test window still come from the Backtest tab.",
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
                "Open the full-screen Optimizer workspace for the current symbol.",
                target='open-optimizer-from-teaser',
                placement='left',
            ),
        ], style=card_style),
        html.Div(
            "Tip: you can also open it from the Backtest tab or the command palette "
            "(Navigate → Open optimizer).",
            style={
                'fontSize': FONT_SIZES['xs'],
                'color': theme['text_tertiary'],
                'lineHeight': '1.4',
                'fontStyle': 'italic',
            },
        ),
    ], style={'display': 'none'})
