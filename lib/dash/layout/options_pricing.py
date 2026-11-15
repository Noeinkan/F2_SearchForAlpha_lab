"""Manual options pricing workspace."""

from dash import dcc, html, dash_table


def create_options_workspace(theme: dict) -> html.Div:
    def field(label, ident, value):
        return html.Label([html.Span(label), dcc.Input(id=ident, type='number', value=value, debounce=True)], className='sfa-options-field')

    return html.Div([
        html.Div([html.Div([html.Span('OPTIONS PRICING', className='sfa-options-kicker'),
                            html.Span(id='options-ticker', className='sfa-options-ticker'),
                            html.H2('Payoff & Greeks')]),
                  html.Button('BACK TO CHART', id='options-back-button', n_clicks=0,
                              className='sfa-workspace-nav-btn')], className='sfa-options-head'),
        html.P('European theoretical estimates. US equity options can be exercised early, particularly around dividends; these are not tradable quotes.', className='sfa-options-note'),
        html.Div([field('Spot ($)', 'options-spot', 100),
                  field('Days to expiry', 'options-days', 30),
                  field('Risk-free rate (%)', 'options-rate', 5),
                  field('Dividend yield (%)', 'options-yield', 0),
                  html.Label([html.Span('Strategy'), dcc.Dropdown(id='options-preset', value='long_call',
                    clearable=False, options=[{'label': a, 'value': b} for a, b in (
                        ('Long call', 'long_call'), ('Long put', 'long_put'),
                        ('Bull call spread', 'bull_call_spread'), ('Iron condor', 'iron_condor'))])],
                    className='sfa-options-field')], className='sfa-options-controls'),
        html.P('Edit quantities, strikes, premiums and IV. Premium is per share; one contract represents 100 shares.', className='sfa-options-note'),
        dash_table.DataTable(id='options-legs', editable=True, row_deletable=True,
            columns=[{'name': 'Qty (+ long / − short)', 'id': 'quantity', 'type': 'numeric'},
                     {'name': 'Call / put', 'id': 'kind', 'presentation': 'dropdown'},
                     {'name': 'Strike ($)', 'id': 'strike', 'type': 'numeric'},
                     {'name': 'Premium ($/share)', 'id': 'premium', 'type': 'numeric'},
                     {'name': 'IV (%)', 'id': 'iv', 'type': 'numeric'}],
            dropdown={'kind': {'options': [{'label': 'call', 'value': 'call'},
                                          {'label': 'put', 'value': 'put'}]}},
            data=[{'quantity': 1, 'kind': 'call', 'strike': 100, 'premium': 2.5, 'iv': 20}],
            style_table={'overflowX': 'auto'},
            style_cell={'backgroundColor': theme['bg_secondary'], 'color': theme['text_primary'],
                        'border': f"1px solid {theme['border_primary']}", 'textAlign': 'left',
                        'minWidth': '100px'},
            style_header={'backgroundColor': theme['bg_primary'], 'fontWeight': 'bold'}),
        html.Button('ADD LEG', id='options-add-leg', n_clicks=0, className='sfa-workspace-nav-btn'),
        html.Div(id='options-error', className='sfa-options-error'),
        html.Div([dcc.Graph(id='options-payoff', config={'displayModeBar': False}, className='sfa-options-chart'),
                  html.Div([html.H3('Expiry payoff'), html.Div(id='options-summary'),
                            html.H3('Greeks per contract'), html.Div(id='options-greeks')],
                           className='sfa-options-results')], className='sfa-options-output'),
    ], id='options-workspace', className='sfa-options-workspace', style={'display': 'none'})
