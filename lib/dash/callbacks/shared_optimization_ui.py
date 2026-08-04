"""Optimizer result tables and best-strategy highlight."""

from __future__ import annotations

import pandas as pd
from dash import dash_table, html

from lib.dash.dash_config import FONT_SIZES, FONT_FAMILY


OPTIMIZATION_BATCH_SIZE = 5


def _create_best_strategy_highlight(best_row: pd.Series, theme: dict) -> html.Div:
    """Create highlight card for the best strategy."""
    total_return = best_row.get('Total_Return_%', 0)
    sharpe = best_row.get('Sharpe_Ratio', 0)
    drawdown = best_row.get('Max_Drawdown_%', 0)
    sortino = best_row.get('Sortino', 0)
    calmar = best_row.get('Calmar', 0)
    win_rate = best_row.get('Win_Rate_%', 0)
    profit_factor = best_row.get('Profit_Factor', 0)
    trades = best_row.get('Trades', 0)
    alpha = best_row.get('Alpha_%', None)
    buy_hold = best_row.get('BuyHold_Return_%', None)
    low_sample = bool(best_row.get('Low_Sample', False))

    sub_style = {'color': theme['text_secondary'], 'fontSize': FONT_SIZES['xs'], 'marginLeft': '8px'}

    title_children = [
        html.Span("\U0001f3c6 ", style={'fontSize': '16px'}),
        html.Span("Best Strategy", style={
            'color': theme['text_secondary'],
            'fontSize': FONT_SIZES['sm'],
            'fontWeight': '600'
        }),
    ]
    if low_sample:
        title_children.append(
            html.Span("LOW SAMPLE", style={
                'marginLeft': '8px',
                'padding': '1px 6px',
                'borderRadius': '4px',
                'fontSize': '9px',
                'fontWeight': '700',
                'letterSpacing': '0.5px',
                'color': theme['accent_orange'],
                'border': f'1px solid {theme["accent_orange"]}80',
            })
        )

    detail_children = [
        html.Div([
            html.Span("Buy: ", style={'color': theme['text_secondary'], 'fontSize': FONT_SIZES['xs']}),
            html.Span(str(best_row.get('Buy_Signals', '')), style={
                'color': theme['accent_green'],
                'fontSize': FONT_SIZES['xs']
            }),
        ], style={'marginBottom': '4px'}),
        html.Div([
            html.Span("Sell: ", style={'color': theme['text_secondary'], 'fontSize': FONT_SIZES['xs']}),
            html.Span(str(best_row.get('Sell_Signals', '')), style={
                'color': theme['accent_red'],
                'fontSize': FONT_SIZES['xs']
            }),
        ], style={'marginBottom': '8px'}),
        html.Div([
            html.Span(f"{total_return:+.1f}% return", style={
                'color': theme['accent_green'] if total_return > 0 else theme['accent_red'],
                'fontWeight': '600',
                'fontSize': FONT_SIZES['base'],
                'fontFamily': FONT_FAMILY
            }),
            html.Span(f" | Sharpe: {sharpe:.2f}", style=sub_style),
            html.Span(f" | DD: {drawdown:.1f}%", style=sub_style),
        ]),
        html.Div([
            html.Span(f"Sortino: {sortino:.2f}", style={'color': theme['text_secondary'], 'fontSize': FONT_SIZES['xs']}),
            html.Span(f" | Calmar: {calmar:.2f}", style=sub_style),
            html.Span(f" | Win: {win_rate:.0f}%", style=sub_style),
            html.Span(f" | PF: {profit_factor:.2f}", style=sub_style),
            html.Span(f" | {int(trades)} trades", style=sub_style),
        ], style={'marginTop': '4px'}),
    ]

    if alpha is not None and buy_hold is not None:
        alpha_color = theme['accent_green'] if alpha >= 0 else theme['accent_red']
        detail_children.append(
            html.Div([
                html.Span("vs Buy & Hold: ", style={'color': theme['text_secondary'], 'fontSize': FONT_SIZES['xs']}),
                html.Span(f"{alpha:+.1f}% alpha", style={
                    'color': alpha_color, 'fontSize': FONT_SIZES['xs'], 'fontWeight': '600'
                }),
                html.Span(f" (B&H {buy_hold:+.1f}%)", style=sub_style),
            ], style={'marginTop': '4px'})
        )

    return html.Div([
        html.Div(title_children, style={'marginBottom': '8px'}),
        html.Div(detail_children),
    ], style={
        'backgroundColor': theme['bg_tertiary'],
        'padding': '12px',
        'borderRadius': '6px',
        'marginBottom': '12px',
        'border': f'1px solid {theme["accent_green"]}40'
    })


def _create_price_subtitle(df: pd.DataFrame, theme: dict) -> html.Span:
    """Create price change subtitle with last-bar as-of stamp."""
    from lib.dash.chart_meta import infer_bar_interval

    latest_close = df['Close'].iloc[-1]
    prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
    change = latest_close - prev_close
    change_pct = (change / prev_close) * 100
    change_color = theme['accent_green'] if change >= 0 else theme['accent_red']
    change_sign = '+' if change >= 0 else ''

    last_ts = pd.Timestamp(df.index[-1])
    interval = infer_bar_interval(df.index)
    if interval.endswith('H') or (len(interval) > 1 and interval.endswith('m')):
        as_of = last_ts.strftime('%Y-%m-%d %H:%M')
    else:
        as_of = last_ts.strftime('%Y-%m-%d')

    return html.Span([
        html.Span(f"${latest_close:.2f}", className='num', style={'color': theme['text_primary']}),
        html.Span(f" {change_sign}{change:.2f} ({change_sign}{change_pct:.2f}%)",
                 className='num', style={'color': change_color, 'marginLeft': '8px'}),
        html.Span(
            f" · as of {as_of}",
            className='num',
            style={'color': theme['text_tertiary'], 'marginLeft': '8px', 'fontSize': '11px'},
        ),
    ])


def _create_optimization_table_mini(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create compact mini-table for partial results during optimization."""
    return dash_table.DataTable(
        columns=[
            {"name": "Buy Signals", "id": "Buy_Signals"},
            {"name": "Return %", "id": "Total_Return_%"},
        ],
        data=cast(Any, display_df[['Buy_Signals', 'Total_Return_%']].round(1).to_dict('records')),
        style_cell={
            'textAlign': 'left',
            'padding': '4px 6px',
            'backgroundColor': theme['bg_tertiary'],
            'color': theme['text_primary'],
            'fontSize': '10px',
            'border': 'none',
        },
        style_header={'display': 'none'},
    )


def _create_optimization_table(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create enhanced optimization results table with all columns."""
    columns = ['Buy_Signals', 'Sell_Signals', 'Total_Return_%', 'Alpha_%',
               'Sharpe_Ratio', 'Sortino', 'Calmar', 'Max_Drawdown_%',
               'Win_Rate_%', 'Profit_Factor', 'Trades']
    available_cols = [c for c in columns if c in display_df.columns]

    # Grey out low-sample rows so they read as "less trustworthy".
    low_sample_style = []
    if 'Low_Sample' in display_df.columns:
        low_sample_rows = [i for i, v in enumerate(display_df['Low_Sample'].tolist()) if bool(v)]
        low_sample_style = [
            {'if': {'row_index': i}, 'opacity': '0.55', 'fontStyle': 'italic'}
            for i in low_sample_rows
        ]

    return dash_table.DataTable(
        id='optimization-table',
        columns=[{"name": c.replace('_', ' '), "id": c} for c in available_cols],
        data=cast(Any, display_df[available_cols].round(2).to_dict('records')),
        style_cell={
            'textAlign': 'left',
            'padding': '8px',
            'backgroundColor': theme['bg_tertiary'],
            'color': theme['text_primary'],
            'fontSize': '11px',
            'border': f'1px solid {theme["border_secondary"]}',
            'maxWidth': '150px',
            'overflow': 'hidden',
            'textOverflow': 'ellipsis',
        },
        style_header={
            'fontWeight': '600',
            'backgroundColor': theme['bg_secondary'],
            'fontSize': '10px',
            'textTransform': 'uppercase',
        },
        style_data_conditional=cast(Any, [
            {'if': {'row_index': 0}, 'backgroundColor': f'{theme["accent_green"]}15'},
            {'if': {'row_index': 1}, 'backgroundColor': f'{theme["accent_blue"]}10'},
            {'if': {'row_index': 2}, 'backgroundColor': f'{theme["accent_blue"]}05'},
        ] + low_sample_style),
        page_size=10,
    )


