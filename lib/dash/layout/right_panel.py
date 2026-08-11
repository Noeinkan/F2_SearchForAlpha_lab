"""
Right panel shell: Backtest-only rail.
"""

from dash import html

from lib.dash.bootstrap import BootstrapSnapshot
from .backtest_panel import _create_backtest_panel


def _create_right_panel(styles: dict, theme: dict, bootstrap: BootstrapSnapshot | None = None) -> html.Aside:
    """Create the right panel with backtest controls and results."""
    return html.Aside([
        html.Div(
            # Glyph is re-set per state by the layout clientside callback; this
            # is just the expanded-by-default first paint.
            html.Button(">>", id='right-panel-toggle-btn', n_clicks=0, className='sfa-panel-toggle',
                        title='Collapse panel', **{'aria-label': 'Toggle backtest panel'}),
            className='sfa-panel-toggle-wrap',
        ),
        html.Div([
            html.Div([
                _create_backtest_panel(styles, theme, bootstrap=bootstrap),
            ], style=styles['panel_content']),
        ], className='sfa-right-panel-inner'),
    ], style=styles['right_panel'], className='sfa-right-panel')
