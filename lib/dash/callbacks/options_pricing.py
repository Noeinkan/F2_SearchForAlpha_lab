"""Offline options calculator callbacks."""

from dash import Input, Output, State, ctx, html
from dash.exceptions import PreventUpdate
import plotly.graph_objects as go

from lib.options.pricing import Leg, MULTIPLIER, payoff_at, payoff_summary, price_option, strategy_legs
from lib.dash.routes import extract_path_ticker


def _legs_from_rows(rows):
    legs = []
    for row in rows or []:
        quantity = float(row['quantity'])
        if not quantity.is_integer():
            raise ValueError('Quantity must be a whole number')
        legs.append(Leg(int(quantity), str(row['kind']), float(row['strike']),
                        float(row['premium']), float(row['iv']) / 100))
    return legs


def _money(value):
    return 'Unbounded' if value is None else f'${value:,.2f}'


def register_options_pricing_callbacks(app) -> None:
    @app.callback(Output('options-ticker', 'children'), Input('app-url', 'pathname'))
    def show_ticker(pathname):
        symbol = extract_path_ticker(pathname)
        return f'· {symbol} · manual spot' if symbol else '· manual spot'

    @app.callback(Output('options-legs', 'data'),
                  Input('options-preset', 'value'), Input('options-add-leg', 'n_clicks'),
                  State('options-spot', 'value'), State('options-days', 'value'),
                  State('options-rate', 'value'), State('options-yield', 'value'),
                  State('options-legs', 'data'), prevent_initial_call=False)
    def populate_legs(preset, _add, spot, days, rate, yield_pct, rows):
        if ctx.triggered_id == 'options-add-leg':
            return (rows or []) + [{'quantity': 1, 'kind': 'call', 'strike': spot or 100,
                                     'premium': 0, 'iv': 20}]
        if not preset:
            raise PreventUpdate
        try:
            legs = strategy_legs(preset, float(spot or 100))
            return [{'quantity': leg.quantity, 'kind': leg.kind, 'strike': leg.strike,
                     'premium': round(float(price_option(spot=float(spot or 100), strike=leg.strike,
                         days=float(days or 0), iv=leg.iv, kind=leg.kind,
                         rate=float(rate or 0) / 100,
                         yield_rate=float(yield_pct or 0) / 100)['value']), 2),
                     'iv': leg.iv * 100} for leg in legs]
        except (ValueError, TypeError):
            raise PreventUpdate

    @app.callback(Output('options-payoff', 'figure'), Output('options-summary', 'children'),
                  Output('options-greeks', 'children'), Output('options-error', 'children'),
                  Input('options-legs', 'data'), Input('options-spot', 'value'),
                  Input('options-days', 'value'), Input('options-rate', 'value'),
                  Input('options-yield', 'value'), Input('theme-store', 'data'))
    def compute(rows, spot, days, rate, yield_pct, _theme):
        try:
            if spot is None or days is None or rate is None or yield_pct is None:
                raise ValueError('Enter spot, days, rate and dividend yield')
            spot, days = float(spot), float(days)
            legs = _legs_from_rows(rows)
            summary = payoff_summary(legs)
            priced = [price_option(spot=spot, strike=leg.strike, days=days, iv=leg.iv,
                                   kind=leg.kind, rate=float(rate) / 100,
                                   yield_rate=float(yield_pct) / 100) for leg in legs]
            high = max(spot * 1.6, max(leg.strike for leg in legs) * 1.25)
            xs = [high * i / 160 for i in range(161)]
            ys = [payoff_at(x, legs) for x in xs]
            fig = go.Figure(go.Scatter(x=xs, y=ys, mode='lines', name='Expiry P/L',
                                       line={'color': '#FFA726', 'width': 3}))
            fig.add_hline(y=0, line_color='#87909a', line_width=1)
            fig.add_vline(x=spot, line_color='#5ba9e6', line_dash='dash',
                          annotation_text='Spot')
            fig.update_layout(template='plotly_dark', paper_bgcolor='#11161c',
                              plot_bgcolor='#11161c', margin={'l': 50, 'r': 20, 't': 20, 'b': 45},
                              xaxis_title='Underlying at expiry ($)', yaxis_title='Profit / loss ($)',
                              height=410)
            summary_ui = html.Div([
                html.Div(f"Max profit: {_money(summary['max_profit'])}"),
                html.Div(f"Max loss: {_money(summary['max_loss'])}"),
                html.Div('Break-even: ' + (', '.join(f'${x:,.2f}' for x in summary['break_evens'])
                           or 'None'))], className='sfa-options-metrics')
            names = ('delta', 'gamma', 'theta', 'vega', 'rho')
            undefined = any(p['delta'] is None for p in priced)
            totals = {name: sum(p[name] * MULTIPLIER * leg.quantity
                                for p, leg in zip(priced, legs)) for name in names} if not undefined else {}
            greeks_ui = html.Div([
                html.Div('Greeks undefined at expiry or zero volatility' if undefined else
                         'Portfolio: ' + ' · '.join(f'{name.title()} {value:+.3f}'
                         for name, value in totals.items())),
                html.Table([html.Thead(html.Tr([html.Th(x) for x in
                    ('Leg', 'Theoretical', 'Delta', 'Gamma', 'Theta/day', 'Vega/1%', 'Rho/1%')])),
                    html.Tbody([html.Tr([html.Td(f'{leg.quantity:+d} {leg.kind} {leg.strike:g}'),
                        html.Td(f"${p['value']:.2f}"),
                        *[html.Td('—' if p[name] is None else
                                  f'{p[name] * MULTIPLIER * leg.quantity:+.3f}') for name in names]])
                        for leg, p in zip(legs, priced)])], className='sfa-options-greeks-table'),
            ])
            return fig, summary_ui, greeks_ui, ''
        except (ValueError, TypeError, KeyError, OverflowError) as exc:
            return go.Figure(), '', '', str(exc)
