"""
Dashboard Callbacks
All Dash callback functions for the trading dashboard.
"""

import logging
import re
from datetime import datetime
from typing import Tuple, List, Any, Dict

import pandas as pd
from dash import html, dash_table, callback_context, dcc
from dash.dependencies import Input, Output, State, ALL
from dash.exceptions import PreventUpdate
import plotly.graph_objs as go

from dash_tvlwc import Tvlwc

from lib.dash.dash_config import (
    DEFAULT_THEME, FONT_SIZES, FONT_MONO, BORDER_RADIUS, get_theme
)
from lib.dash.state import dashboard_state
from lib.dash.styles import get_styles
from lib.dash.chart_builder import create_chart, create_empty_chart
from lib.dash.tv_chart_builder import (
    convert_df_to_tv_format,
    convert_volume_to_tv_format,
    get_tv_chart_options
)
from lib.dash.components import build_alert, build_metric_card, build_progress_bar
from lib.dash.helpers import (
    fetch_data_with_cache, format_df_for_display,
    extract_signals, generate_signal_combinations, evaluate_signal_combination
)

from lib.data_processing import get_all_tickers, create_backtest_results
from lib.signals.indicators import add_indicators, generate_signals
from lib.strategy import run_backtest

logger = logging.getLogger(__name__)

SIGNAL_DESCRIPTIONS: Dict[str, str] = {
    # Bollinger Bands
    "BB_Breakout_Buy": "Price breaks above upper Bollinger Band (momentum breakout).",
    "BB_Breakout_Sell": "Price breaks below lower Bollinger Band (momentum breakdown).",
    "BB_MeanReversion_Buy": "Price crosses back above lower band (mean reversion).",
    "BB_MeanReversion_Sell": "Price crosses back below upper band (mean reversion).",
    "BB_Squeeze_Buy": "Post-squeeze breakout above upper band after narrow bands.",
    "BB_Squeeze_Sell": "Post-squeeze breakdown below lower band after narrow bands.",
    "BB_DoubleBottom_Buy": "Two lower-band touches with a rebound (double bottom).",
    "BB_DoubleTop_Sell": "Two upper-band touches with a drop (double top).",
    # MACD
    "MACD_ZeroCross_Buy": "MACD crosses above zero line (trend shifts bullish).",
    "MACD_ZeroCross_Sell": "MACD crosses below zero line (trend shifts bearish).",
    "MACD_SignalCross_Buy": "MACD crosses above its signal line.",
    "MACD_SignalCross_Sell": "MACD crosses below its signal line.",
    "MACD_Histogram_Buy": "Histogram flips positive (momentum turning up).",
    "MACD_Histogram_Sell": "Histogram flips negative (momentum turning down).",
    # RSI
    "RSI_Oversold_Buy": "RSI < 30 (oversold; potential rebound).",
    "RSI_Overbought_Sell": "RSI > 70 (overbought; potential pullback).",
    "RSI_Bullish_Divergence": "Price makes new low while RSI rises (bullish divergence).",
    "RSI_Bearish_Divergence": "Price makes new high while RSI falls (bearish divergence).",
    # CCI
    "CCI_Oversold_Buy": "CCI < -100 (oversold; potential rebound).",
    "CCI_Overbought_Sell": "CCI > 100 (overbought; potential pullback).",
    "CCI_Reversal_Buy": "CCI rebounds from extreme low (< -180).",
    "CCI_Reversal_Sell": "CCI reverses down from extreme high (> 180).",
    "CCI_ZeroCross_Buy": "CCI crosses above zero (trend turns positive).",
    "CCI_ZeroCross_Sell": "CCI crosses below zero (trend turns negative).",
    # SMA
    "SMA_TripleCross_Buy": "Short > medium > long SMAs (bullish alignment).",
    "SMA_TripleCross_Sell": "Short < medium < long SMAs (bearish alignment).",
    "SMA_PriceCross_Buy": "Price crosses above medium SMA.",
    "SMA_PriceCross_Sell": "Price crosses below medium SMA.",
    "SMA_TrendFollow_Buy": "Price above long SMA with short/medium/long aligned.",
    "SMA_TrendFollow_Sell": "Price below long SMA with short/medium/long aligned.",
    # EMA
    "EMA_TripleCross_Buy": "Short > medium > long EMAs (bullish alignment).",
    "EMA_TripleCross_Sell": "Short < medium < long EMAs (bearish alignment).",
    "EMA_Distance_Buy": "Bullish EMA alignment with strong separation.",
    "EMA_Distance_Sell": "Bearish EMA alignment with strong separation.",
    "EMA_Momentum_Buy": "Bullish EMA alignment with rising EMA slope.",
    "EMA_Momentum_Sell": "Bearish EMA alignment with falling EMA slope.",
    "EMA_ValueZone_Buy": "Price between long and medium EMA (value zone).",
    "EMA_ValueZone_Sell": "Price between long and medium EMA (value zone).",
    "EMA_Divergence_Buy": "Price low falls while short EMA rises (divergence).",
    "EMA_Divergence_Sell": "Price high rises while short EMA falls (divergence).",
    "EMA_Volatility_Buy": "Bullish EMA alignment during high volatility.",
    "EMA_Volatility_Sell": "Bearish EMA alignment during high volatility.",
}


def _format_signal_label(col_name: str) -> str:
    return col_name.replace("_", " ")


def _describe_signal(col_name: str) -> str:
    description = SIGNAL_DESCRIPTIONS.get(col_name)
    if description:
        return description
    base = _format_signal_label(col_name)
    return f"Signal generated from {base}."


def _normalize_timestamp(value: Any) -> pd.Timestamp | None:
    """Normalize timestamps to timezone-naive UTC for comparisons."""
    ts = pd.to_datetime(value, errors='coerce', utc=True)
    if pd.isna(ts):
        return None
    return ts.tz_convert(None)


def _figure_dict(fig: Any) -> Dict[str, Any]:
    """Return a dict representation for read-only access."""
    if hasattr(fig, "to_dict"):
        return fig.to_dict()
    return fig


def _apply_layout_updates(fig: Any, updates: Dict[str, Any]) -> None:
    """Apply layout updates to either Figure or dict."""
    if not updates:
        return
    if hasattr(fig, "update_layout"):
        fig.update_layout(**updates)
        return
    layout = fig.setdefault('layout', {})
    for axis_key, axis_values in updates.items():
        axis_layout = layout.setdefault(axis_key, {})
        axis_layout.update(axis_values)


def _resolve_x_range(relayout_data: Dict[str, Any],
                     df: pd.DataFrame,
                     fig: Dict[str, Any] | None = None) -> Tuple[pd.Timestamp, pd.Timestamp] | None:
    """Resolve the active x-axis range from relayout data."""
    if not relayout_data:
        relayout_data = {}

    if 'xaxis.range[0]' in relayout_data and 'xaxis.range[1]' in relayout_data:
        start = relayout_data['xaxis.range[0]']
        end = relayout_data['xaxis.range[1]']
    elif 'xaxis.range' in relayout_data and isinstance(relayout_data['xaxis.range'], list):
        start, end = relayout_data['xaxis.range'][0], relayout_data['xaxis.range'][1]
    elif relayout_data.get('xaxis.autorange') is True:
        if df is None or df.empty:
            return None
        start, end = df.index.min(), df.index.max()
    else:
        if not fig:
            return None
        fig_dict = _figure_dict(fig)
        layout = fig_dict.get('layout', {})
        xaxis = layout.get('xaxis', {})
        if isinstance(xaxis.get('range'), list) and len(xaxis['range']) >= 2:
            start, end = xaxis['range'][0], xaxis['range'][1]
        elif xaxis.get('autorange') is True:
            if df is None or df.empty:
                return None
            start, end = df.index.min(), df.index.max()
        else:
            return None

    start_ts = _normalize_timestamp(start)
    end_ts = _normalize_timestamp(end)
    if start_ts is None or end_ts is None:
        return None
    return start_ts, end_ts


def _axis_layout_key(axis_id: str) -> str:
    """Convert trace yaxis id ('y', 'y2') to layout key ('yaxis', 'yaxis2')."""
    if axis_id == 'y':
        return 'yaxis'
    return f"yaxis{axis_id[1:]}"


def _compute_y_ranges_by_axis(fig: Dict[str, Any],
                              x_start: pd.Timestamp,
                              x_end: pd.Timestamp,
                              df: pd.DataFrame | None = None) -> Dict[str, Tuple[float, float]]:
    """Compute min/max y ranges per axis for the visible x-range."""
    axis_ranges: Dict[str, Tuple[float, float]] = {}
    fig_dict = _figure_dict(fig)

    if df is not None and not df.empty and {'Low', 'High'}.issubset(df.columns):
        df_index = pd.to_datetime(df.index, errors='coerce', utc=True).tz_convert(None)
        df_mask = (df_index >= x_start) & (df_index <= x_end)
        if hasattr(df_mask, "to_numpy"):
            df_mask = df_mask.to_numpy()
        else:
            df_mask = pd.Series(df_mask).to_numpy()
        if df_mask.any():
            visible_df = df.iloc[df_mask]
            if not visible_df.empty:
                price_min = float(pd.to_numeric(visible_df['Low'], errors='coerce').min())
                price_max = float(pd.to_numeric(visible_df['High'], errors='coerce').max())
                for trace in fig_dict.get('data', []):
                    if trace.get('type') == 'candlestick':
                        axis_id = trace.get('yaxis', 'y')
                        axis_ranges[axis_id] = (price_min, price_max)

    traces = fig_dict.get('data', [])
    for trace in traces:
        if trace.get('visible') == 'legendonly':
            continue

        axis_id = trace.get('yaxis', 'y')
        if trace.get('type') == 'candlestick' and axis_id in axis_ranges:
            continue
        x_values = trace.get('x', [])
        if x_values is None or (hasattr(x_values, "__len__") and len(x_values) == 0):
            continue

        x_series = pd.to_datetime(pd.Series(x_values), errors='coerce', utc=True).dt.tz_convert(None)
        mask = (x_series >= x_start) & (x_series <= x_end)
        mask_values = mask.to_numpy()
        if not mask.any():
            continue

        y_min = y_max = None
        if trace.get('type') == 'candlestick':
            lows = pd.to_numeric(pd.Series(trace.get('low', [])), errors='coerce')
            highs = pd.to_numeric(pd.Series(trace.get('high', [])), errors='coerce')
            values_len = min(len(mask_values), len(lows), len(highs))
            if values_len == 0:
                continue
            low_vals = lows.to_numpy()[:values_len][mask_values[:values_len]]
            high_vals = highs.to_numpy()[:values_len][mask_values[:values_len]]
            if low_vals.size == 0 or high_vals.size == 0:
                continue
            y_min = float(low_vals.min())
            y_max = float(high_vals.max())
        else:
            y_values = pd.to_numeric(pd.Series(trace.get('y', [])), errors='coerce')
            values_len = min(len(mask_values), len(y_values))
            if values_len == 0:
                continue
            y_vals = y_values.to_numpy()[:values_len][mask_values[:values_len]]
            if y_vals.size == 0:
                continue
            y_min = float(y_vals.min())
            y_max = float(y_vals.max())

        if y_min is None or y_max is None:
            continue

        current = axis_ranges.get(axis_id)
        if current:
            axis_ranges[axis_id] = (min(current[0], y_min), max(current[1], y_max))
        else:
            axis_ranges[axis_id] = (y_min, y_max)

    return axis_ranges


def _pad_range(y_min: float, y_max: float, pad_ratio: float = 0.04) -> Tuple[float, float]:
    """Apply a small padding to y ranges for visual breathing room."""
    span = y_max - y_min
    if span <= 0:
        span = max(abs(y_max) * 0.02, 1e-6)
    pad = span * pad_ratio
    return y_min - pad, y_max + pad


def _build_signal_options(columns: List[str]) -> List[Dict[str, Any]]:
    options = []
    for col in columns:
        label = html.Span(
            _format_signal_label(col),
            title=_describe_signal(col),
            style={'marginLeft': '8px'}
        )
        options.append({'label': label, 'value': col})
    return options


def _strip_signal_side(col_name: str) -> str:
    return re.sub(r'_(buy|sell)$', '', col_name, flags=re.IGNORECASE)


def _build_unified_signal_rows(buy_columns: List[str], sell_columns: List[str]) -> List[Dict[str, Any]]:
    rows: Dict[str, Dict[str, Any]] = {}
    for col in buy_columns:
        base = _strip_signal_side(col)
        rows.setdefault(base, {})['buy'] = col
    for col in sell_columns:
        base = _strip_signal_side(col)
        rows.setdefault(base, {})['sell'] = col

    unified_rows = []
    for base, sides in rows.items():
        category = base.split('_')[0].upper() if base else 'OTHER'
        unified_rows.append({
            'label': _format_signal_label(base),
            'category': category,
            'buy': sides.get('buy'),
            'sell': sides.get('sell')
        })

    return sorted(unified_rows, key=lambda row: row['label'].lower())


def register_callbacks(app):
    """
    Register all callbacks for the dashboard application.

    Args:
        app: Dash application instance
    """

    @app.callback(
        Output('ticker-dropdown', 'options'),
        [Input('startup-interval', 'n_intervals')]
    )
    def populate_tickers(_):
        """Populate ticker dropdown on startup."""
        if dashboard_state.all_tickers_df is None:
            try:
                dashboard_state.all_tickers_df = get_all_tickers()
            except Exception as e:
                logger.error(f"Error fetching tickers: {e}")
                return [{'label': 'SPY - SPDR S&P 500 ETF', 'value': 'SPY'}]
        return [
            {'label': f"{row['Symbol']} - {row['Security'][:30]}", 'value': row['Symbol']}
            for _, row in dashboard_state.all_tickers_df.iterrows()
        ]

    @app.callback(
        [Output('data-status', 'children'),
         Output('data-loaded-store', 'data'),
         Output('buy-signals', 'options'),
         Output('sell-signals', 'options'),
         Output('signals-unified-store', 'data'),
         Output('chart-title', 'children'),
         Output('chart-subtitle', 'children'),
         Output('data-table-container', 'children')],
        [Input('load-data-button', 'n_clicks'),
         Input('autoload-interval', 'n_intervals')],
        [State('ticker-dropdown', 'value'),
         State('start-date', 'date'),
         State('end-date', 'date')]
    )
    def load_data(n_clicks, n_intervals, ticker, start_date, end_date):
        """Load market data. Auto-loads SPY on startup."""
        ctx = callback_context
        if not ctx.triggered:
            raise PreventUpdate

        trigger_id = ctx.triggered[0]['prop_id'].split('.')[0]

        # On startup, auto-load default ticker (SPY)
        if trigger_id == 'autoload-interval':
            if n_intervals is None or n_intervals < 1:
                raise PreventUpdate
        elif trigger_id == 'load-data-button':
            if not n_clicks:
                raise PreventUpdate

        theme = get_theme()

        try:
            df = fetch_data_with_cache(ticker, start_date, end_date)
            if df.empty:
                return (
                    html.Div([
                        html.Span("\u26a0", style={'color': theme['accent_orange'], 'marginRight': '6px'}),
                        html.Span("No data available for this symbol",
                                  style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_orange']})
                    ]),
                    False, [], [], [], "No data", "", None
                )

            df = add_indicators(df)
            df, _ = generate_signals(df)
            dashboard_state.df = df

            buy_columns = [col for col in df.columns if 'buy' in col.lower()]
            sell_columns = [col for col in df.columns if 'sell' in col.lower()]
            buy_options = _build_signal_options(buy_columns)
            sell_options = _build_signal_options(sell_columns)
            unified_rows = _build_unified_signal_rows(buy_columns, sell_columns)

            # Create data table
            display_df = format_df_for_display(df.tail(50)).reset_index()
            data_table = _create_data_table(display_df, theme)

            # Calculate subtitle info
            subtitle = _create_price_subtitle(df, theme)

            # Success status with animation
            status = html.Div([
                html.Span("\u2713", style={'color': theme['accent_green'], 'marginRight': '6px', 'fontWeight': 'bold'}),
                html.Span(f"{len(df)} rows loaded", style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_green']})
            ], className='fade-in')

            return status, True, buy_options, sell_options, unified_rows, ticker, subtitle, data_table

        except Exception as e:
            logger.error(f"Error loading data: {e}")
            return (
                html.Div([
                    html.Span("\u2715", style={'color': theme['accent_red'], 'marginRight': '6px', 'fontWeight': 'bold'}),
                    html.Span(str(e)[:40], style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_red']})
                ]),
                False, [], [], [], "Error", "", None
            )

    @app.callback(
        [Output('accumulation-options', 'style'),
         Output('rebalancing-options', 'style')],
        [Input('strategy-mode', 'value')],
        [State('theme-store', 'data')]
    )
    def toggle_strategy_options(strategy_mode, theme_name):
        """Show/hide mode-specific options based on selected strategy mode."""
        theme = get_theme(theme_name or DEFAULT_THEME)

        accumulation_style = {
            'marginBottom': '12px',
            'display': 'block' if strategy_mode == 'accumulation' else 'none',
            'padding': '10px',
            'backgroundColor': f'{theme["accent_green"]}10',
            'borderRadius': BORDER_RADIUS['md'],
            'border': f'1px solid {theme["accent_green"]}40',
        }
        rebalancing_style = {
            'marginBottom': '12px',
            'display': 'block' if strategy_mode == 'rebalancing' else 'none',
            'padding': '10px',
            'backgroundColor': f'{theme["accent_blue"]}10',
            'borderRadius': BORDER_RADIUS['md'],
            'border': f'1px solid {theme["accent_blue"]}40',
        }
        return accumulation_style, rebalancing_style

    @app.callback(
        Output('signals-unified-list', 'children'),
        [Input('signals-unified-store', 'data'),
         Input('signals-search', 'value'),
         Input('signals-category-filter', 'value')],
        [State('buy-signals', 'value'),
         State('sell-signals', 'value')]
    )
    def render_unified_signal_list(signal_rows, search_value, category_values, buy_values, sell_values):
        """Render unified BUY/SELL signal rows."""
        theme = get_theme()
        header = html.Div([
            html.Span("BUY", style={
                'fontSize': FONT_SIZES['xs'],
                'fontWeight': '600',
                'color': theme['accent_green']
            }),
            html.Span("SIGNAL", style={
                'fontSize': FONT_SIZES['xs'],
                'fontWeight': '600',
                'color': theme['text_secondary']
            }),
            html.Span("SELL", style={
                'fontSize': FONT_SIZES['xs'],
                'fontWeight': '600',
                'color': theme['accent_red']
            }),
        ], className='signals-unified-header')
        if not signal_rows:
            return [
                header,
                html.Div(
                    "Load data to view signals.",
                    style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'padding': '6px'}
                )
            ]

        buy_values = set(buy_values or [])
        sell_values = set(sell_values or [])
        search_term = (search_value or '').strip().lower()
        selected_categories = set(category_values or [])
        rows = []
        for row in signal_rows:
            if selected_categories and row.get('category') not in selected_categories:
                continue
            label_text = row.get('label', '')
            if search_term and search_term not in label_text.lower():
                continue
            buy_value = row.get('buy')
            sell_value = row.get('sell')
            description = ''
            if buy_value or sell_value:
                description = _describe_signal(buy_value or sell_value)

            buy_toggle = html.Div('', className='signal-toggle-placeholder')
            if buy_value:
                buy_toggle = dcc.Checklist(
                    id={'type': 'signal-toggle', 'side': 'buy', 'value': buy_value},
                    options=[{'label': '', 'value': buy_value}],
                    value=[buy_value] if buy_value in buy_values else [],
                    className='signal-toggle signal-toggle--buy'
                )

            sell_toggle = html.Div('', className='signal-toggle-placeholder')
            if sell_value:
                sell_toggle = dcc.Checklist(
                    id={'type': 'signal-toggle', 'side': 'sell', 'value': sell_value},
                    options=[{'label': '', 'value': sell_value}],
                    value=[sell_value] if sell_value in sell_values else [],
                    className='signal-toggle signal-toggle--sell'
                )

            rows.append(
                html.Div(
                    [
                        buy_toggle,
                        html.Div(row.get('label', ''), className='signal-name', title=description),
                        sell_toggle,
                    ],
                    className='signal-row'
                )
            )

        if not rows:
            return [
                header,
                html.Div(
                    "No signals match the filter.",
                    style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'padding': '6px'}
                )
            ]

        return [header, *rows]

    @app.callback(
        [Output('buy-signals', 'value'),
         Output('sell-signals', 'value')],
        [Input({'type': 'signal-toggle', 'side': 'buy', 'value': ALL}, 'value'),
         Input({'type': 'signal-toggle', 'side': 'sell', 'value': ALL}, 'value')],
        [State({'type': 'signal-toggle', 'side': 'buy', 'value': ALL}, 'id'),
         State({'type': 'signal-toggle', 'side': 'sell', 'value': ALL}, 'id')]
    )
    def sync_signal_selection(buy_values, sell_values, buy_ids, sell_ids):
        """Sync row toggles to unified buy/sell selections."""
        if not buy_ids and not sell_ids:
            return [], []

        selected_buy = [
            item_id['value']
            for item_id, value in zip(buy_ids, buy_values)
            if value
        ]
        selected_sell = [
            item_id['value']
            for item_id, value in zip(sell_ids, sell_values)
            if value
        ]

        return selected_buy, selected_sell

    @app.callback(
        [Output('summary-strategy-mode', 'children'),
         Output('summary-position-sizing', 'children'),
         Output('summary-signal-settings', 'children')],
        [Input('strategy-mode', 'value'),
         Input('amount-per-buy', 'value'),
         Input('position-size-pct', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('signal-logic-mode', 'value'),
         Input('signal-window', 'value')]
    )
    def update_backtest_panel_summaries(strategy_mode, amount_per_buy, position_size_pct,
                                        buy_signals, sell_signals, signal_logic, signal_window):
        """Update accordion titles with selected options when collapsed."""
        strategy_labels = {
            'trading': 'Trading (Full)',
            'accumulation': 'Accumulation (DCA)',
            'rebalancing': 'Rebalancing (Partial)',
        }
        strategy_summary = strategy_labels.get(strategy_mode, 'Trading (Full)')

        if strategy_mode == 'accumulation':
            if amount_per_buy is None:
                sizing_summary = '$- per buy'
            else:
                sizing_summary = f'${amount_per_buy:,.0f} per buy'
        elif strategy_mode == 'rebalancing':
            if position_size_pct is None:
                sizing_summary = '% per trade'
            else:
                sizing_summary = f'{position_size_pct:.0f}% per trade'
        else:
            sizing_summary = 'N/A'

        buy_signals = buy_signals or []
        sell_signals = sell_signals or []

        def _summarize_signals(values, max_items=2):
            labels = [_format_signal_label(v) for v in values]
            if not labels:
                return 'None'
            if len(labels) <= max_items:
                return ', '.join(labels)
            extra = len(labels) - max_items
            return f"{', '.join(labels[:max_items])} +{extra}"

        if not buy_signals and not sell_signals:
            signals_summary = 'No signals'
        else:
            signals_summary = (
                f"Buy: {_summarize_signals(buy_signals)} | "
                f"Sell: {_summarize_signals(sell_signals)}"
            )
            if signal_logic == 'and':
                if signal_window:
                    signals_summary += f" | AND W={signal_window}"
                else:
                    signals_summary += " | AND"
            else:
                signals_summary += " | OR"

        return strategy_summary, sizing_summary, signals_summary

    @app.callback(
        [Output('plotly-chart-container', 'style'),
         Output('tv-chart-container', 'style')],
        [Input('chart-library-toggle', 'value')]
    )
    def toggle_chart_visibility(chart_library):
        """Show/hide Plotly vs TradingView containers."""
        base_style = {
            'position': 'absolute',
            'inset': 0,
            'height': '100%',
            'width': '100%'
        }
        plotly_style = {**base_style, 'visibility': 'visible', 'opacity': 1, 'pointerEvents': 'auto', 'zIndex': 1}
        tv_style = {**base_style, 'display': 'flex', 'flexDirection': 'column', 'visibility': 'hidden',
                    'opacity': 0, 'pointerEvents': 'none', 'zIndex': 0}
        if chart_library == 'tradingview':
            return {**plotly_style, 'visibility': 'hidden', 'opacity': 0, 'pointerEvents': 'none'}, \
                {**tv_style, 'visibility': 'visible', 'opacity': 1, 'pointerEvents': 'auto', 'zIndex': 2}
        return plotly_style, tv_style

    @app.callback(
        Output('chart-library-toggle', 'value'),
        [Input('plot-checklist', 'value'),
         Input('chart-elements-checklist', 'value')],
        [State('chart-library-toggle', 'value')]
    )
    def enforce_plotly_for_indicators(selected_plots, chart_elements, current_library):
        """Ensure Plotly is used when indicators/overlays are requested."""
        return 'plotly'

    @app.callback(
        Output('financial-chart', 'figure'),
        [Input('data-loaded-store', 'data'),
         Input('plot-checklist', 'value'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('chart-library-toggle', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value'),
         Input('signal-logic-mode', 'value'),
         Input('signal-window', 'value')],
        [State('ticker-dropdown', 'value'),
         State('layout-store', 'data')]
    )
    def update_plotly_chart(data_loaded, selected_plots, chart_elements, selected_signals, chart_library,
                            buy_signals, sell_signals, signal_logic, signal_window, ticker, layout_state):
        """Update the Plotly financial chart."""
        if chart_library == 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return create_empty_chart(theme)

        df = dashboard_state.df
        df = df.copy()

        buy_signals = buy_signals or []
        sell_signals = sell_signals or []

        config = {
            'selected_plots': selected_plots or ['candlestick'],
            'show_candlesticks': 'candlesticks' in (chart_elements or []),
            'show_bollinger': 'bollinger' in (chart_elements or []),
            'show_sma': 'sma' in (chart_elements or []),
            'show_ema': 'ema' in (chart_elements or []),
            'show_buy_sell_signals': 'signals' in (chart_elements or []),
            'show_legend': 'legend' in (chart_elements or []),
            'selected_signals': selected_signals or [],
            'buy_signal_columns': buy_signals,
            'sell_signal_columns': sell_signals,
            'signal_logic': signal_logic or 'or',
            'signal_window': signal_window or 0,
            'title': '',
        }

        fig = create_chart(df, config, theme)
        if layout_state and layout_state.get('x_range'):
            fig.update_xaxes(range=layout_state['x_range'], autorange=False)
            x_start = _normalize_timestamp(layout_state['x_range'][0])
            x_end = _normalize_timestamp(layout_state['x_range'][1])
            if x_start and x_end:
                axis_ranges = _compute_y_ranges_by_axis(fig, x_start, x_end, df)
                layout_updates = {}
                for axis_id, (y_min, y_max) in axis_ranges.items():
                    padded_min, padded_max = _pad_range(y_min, y_max)
                    axis_key = _axis_layout_key(axis_id)
                    layout_updates[axis_key] = {'range': [padded_min, padded_max], 'autorange': False}
                _apply_layout_updates(fig, layout_updates)
        elif layout_state and layout_state.get('autorange'):
            fig.update_xaxes(autorange=True)

        return fig

    @app.callback(
        Output('layout-store', 'data'),
        [Input('financial-chart', 'relayoutData')],
        [State('layout-store', 'data')],
        prevent_initial_call=True
    )
    def persist_timeframe(relayout_data, current_layout):
        """Persist selected timeframe so chart refresh keeps x-range."""
        if not relayout_data:
            raise PreventUpdate

        layout_state = current_layout or {}
        if 'xaxis.range[0]' in relayout_data or 'xaxis.range[1]' in relayout_data:
            start = relayout_data.get('xaxis.range[0]')
            end = relayout_data.get('xaxis.range[1]')
            current_range = layout_state.get('x_range') or [None, None]
            if start is None:
                start = current_range[0]
            if end is None:
                end = current_range[1]
            if start is not None and end is not None:
                layout_state['x_range'] = [start, end]
                layout_state['autorange'] = False
                return layout_state
            layout_state['autorange'] = False
        if 'xaxis.range' in relayout_data and isinstance(relayout_data['xaxis.range'], list):
            layout_state['x_range'] = relayout_data['xaxis.range'][:2]
            layout_state['autorange'] = False
            return layout_state
        if relayout_data.get('xaxis.autorange') is True:
            layout_state['x_range'] = None
            layout_state['autorange'] = True
            return layout_state

        raise PreventUpdate

    @app.callback(
        Output('financial-chart', 'figure', allow_duplicate=True),
        [Input('financial-chart', 'relayoutData')],
        [State('financial-chart', 'figure'),
         State('chart-library-toggle', 'value')],
        prevent_initial_call=True
    )
    def autoscale_chart_to_timerange(relayout_data, fig, chart_library):
        """Autoscale y-axes to the visible x-axis timeframe."""
        if chart_library == 'tradingview':
            raise PreventUpdate
        if not relayout_data or not fig or dashboard_state.df is None:
            raise PreventUpdate

        df = dashboard_state.df
        x_range = _resolve_x_range(relayout_data, df, fig)
        if not x_range:
            raise PreventUpdate

        x_start, x_end = x_range
        axis_ranges = _compute_y_ranges_by_axis(fig, x_start, x_end, df)
        if not axis_ranges:
            raise PreventUpdate

        layout_updates = {}
        for axis_id, (y_min, y_max) in axis_ranges.items():
            padded_min, padded_max = _pad_range(y_min, y_max)
            axis_key = _axis_layout_key(axis_id)
            layout_updates[axis_key] = {'range': [padded_min, padded_max], 'autorange': False}
        _apply_layout_updates(fig, layout_updates)

        return fig

    @app.callback(
        Output('tv-main-chart', 'children'),
        [Input('data-loaded-store', 'data'),
         Input('chart-elements-checklist', 'value'),
         Input('signal-checklist', 'value'),
         Input('chart-library-toggle', 'value'),
         Input('buy-signals', 'value'),
         Input('sell-signals', 'value')],
        [State('ticker-dropdown', 'value')]
    )
    def update_tv_main_chart(data_loaded, chart_elements, selected_signals, chart_library,
                             buy_signals, sell_signals, ticker):
        """Update the TradingView main chart."""
        if chart_library != 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return html.Div("Load data to view chart", style={'color': theme['text_secondary']})

        df = dashboard_state.df
        df = df.copy()

        buy_signals = buy_signals or []
        sell_signals = sell_signals or []

        config = {
            'show_candlesticks': 'candlesticks' in (chart_elements or []),
            'show_bollinger': 'bollinger' in (chart_elements or []),
            'show_sma': 'sma' in (chart_elements or []),
            'show_ema': 'ema' in (chart_elements or []),
            'show_buy_sell_signals': 'signals' in (chart_elements or []),
            'selected_signals': selected_signals or [],
            'buy_signal_columns': buy_signals,
            'sell_signal_columns': sell_signals
        }

        series_data, series_types, series_options, series_markers = convert_df_to_tv_format(df, config, theme)
        if not series_data or not series_types:
            return html.Div("No series selected for TradingView", style={'color': theme['text_secondary']})
        chart_options = get_tv_chart_options(theme)

        return Tvlwc(
            chartOptions=chart_options,
            seriesData=series_data,
            seriesTypes=series_types,
            seriesOptions=series_options,
            seriesMarkers=series_markers,
            height=420,
            width='100%'
        )

    @app.callback(
        Output('tv-volume-chart', 'children'),
        [Input('data-loaded-store', 'data'),
         Input('plot-checklist', 'value'),
         Input('chart-library-toggle', 'value')]
    )
    def update_tv_volume_chart(data_loaded, selected_plots, chart_library):
        """Update the TradingView volume chart."""
        if chart_library != 'tradingview':
            raise PreventUpdate

        theme = get_theme()

        if not data_loaded or dashboard_state.df is None:
            return html.Div()

        if 'volume' not in (selected_plots or []):
            return html.Div()

        df = dashboard_state.df
        series_data, series_type, series_options = convert_volume_to_tv_format(df, theme)
        chart_options = get_tv_chart_options(theme)

        return Tvlwc(
            chartOptions=chart_options,
            seriesData=[series_data],
            seriesTypes=[series_type],
            seriesOptions=[series_options],
            seriesMarkers=[[]],
            height=200,
            width='100%'
        )

    @app.callback(
        Output('backtest-results', 'children'),
        [Input('run-backtest-btn', 'n_clicks')],
        [State('ticker-dropdown', 'value'),
         State('initial-capital', 'value'),
         State('buy-signals', 'value'),
         State('sell-signals', 'value'),
         State('strategy-mode', 'value'),
         State('amount-per-buy', 'value'),
         State('position-size-pct', 'value'),
         State('signal-logic-mode', 'value'),
         State('signal-window', 'value')]
    )
    def run_backtest_callback(n_clicks, ticker, initial_capital, buy_signals, sell_signals,
                               strategy_mode, amount_per_buy, position_size_pct, signal_logic, signal_window):
        """Run backtest and display results."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()

        df = dashboard_state.df
        if df is None:
            return build_alert("Please load market data first", "warning", theme=theme)

        # Validation based on strategy mode
        if not buy_signals:
            return build_alert("Select at least one buy signal", "warning", theme=theme)

        if strategy_mode == 'trading' and not sell_signals:
            return build_alert("Trading mode requires at least one sell signal", "warning", theme=theme)

        # Use empty list for sell signals if not provided in accumulation/rebalancing modes
        sell_signals = sell_signals or []

        try:
            results = run_backtest(
                df, initial_capital, buy_signals, sell_signals,
                strategy_mode=strategy_mode,
                amount_per_buy=amount_per_buy,
                position_size_pct=position_size_pct,
                signal_logic=signal_logic or 'or',
                signal_window=signal_window or 0
            )
            backtest_results = create_backtest_results(results, ticker, initial_capital, buy_signals, sell_signals)
            dashboard_state.backtest_results = backtest_results

            # Calculate metrics
            total_return = backtest_results['total_return']
            is_positive = total_return >= 0
            metric_help = {
                "Portfolio Value": "Final account value after the backtest period.",
                "Total Return": "Percent gain/loss from initial capital.",
                "Sharpe Ratio": "Risk-adjusted return (higher is better).",
                "Max Drawdown": "Largest peak-to-trough loss during the period.",
                "Win Rate": "Percent of trades that were profitable.",
            }

            return html.Div([
                build_alert("Backtest completed successfully!", "success", dismissable=False, theme=theme),
                html.Div([
                    build_metric_card(
                        "Portfolio Value",
                        f"${backtest_results['final_portfolio_value']:,.2f}",
                        None,
                        theme,
                        info_text=metric_help["Portfolio Value"]
                    ),
                    build_metric_card(
                        "Total Return",
                        f"{total_return:+.2f}%",
                        is_positive,
                        theme,
                        info_text=metric_help["Total Return"]
                    ),
                    build_metric_card("Sharpe Ratio", f"{backtest_results['sharpe_ratio']:.2f}",
                                     backtest_results['sharpe_ratio'] > 1, theme,
                                     info_text=metric_help["Sharpe Ratio"]),
                    build_metric_card("Max Drawdown", f"{backtest_results['max_drawdown']:.2f}%",
                                     backtest_results['max_drawdown'] > -20, theme,
                                     info_text=metric_help["Max Drawdown"]),
                    build_metric_card("Win Rate", f"{backtest_results['win_rate']:.1f}%",
                                     backtest_results['win_rate'] > 50, theme,
                                     info_text=metric_help["Win Rate"]),
                ], style={'marginTop': '12px'}),
            ], className='fade-in')

        except Exception as e:
            logger.error(f"Backtest error: {e}")
            return build_alert(f"Backtest failed: {str(e)[:60]}", "error", theme=theme)

    # ==================== OPTIMIZATION CALLBACKS ====================

    @app.callback(
        [Output('preview-buy-count', 'children'),
         Output('preview-sell-count', 'children'),
         Output('preview-combo-count', 'children')],
        [Input('data-loaded-store', 'data'),
         Input('max-signals-slider', 'value'),
         Input('max-combos-input', 'value')]
    )
    def update_signal_preview(data_loaded, max_signals, max_combos):
        """Show preview of available signals and estimated combinations."""
        if not data_loaded or dashboard_state.df is None:
            return "0", "0", "0"

        df = dashboard_state.df
        buy_signals, sell_signals = extract_signals(df)

        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        actual_combos = min(len(combinations), max_combos or 100)

        return str(len(buy_signals)), str(len(sell_signals)), str(actual_combos)

    @app.callback(
        [Output('optimization-state', 'data'),
         Output('optimization-interval', 'disabled'),
         Output('optimization-progress', 'children'),
         Output('run-optimization-btn', 'disabled'),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True)],
        [Input('run-optimization-btn', 'n_clicks')],
        [State('initial-capital', 'value'),
         State('max-signals-slider', 'value'),
         State('max-combos-input', 'value'),
         State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def start_optimization(n_clicks, initial_capital, max_signals, max_combos, current_state):
        """Initialize optimization run and enable interval for progress updates."""
        if not n_clicks:
            raise PreventUpdate

        theme = get_theme()
        df = dashboard_state.df

        if df is None:
            return (
                current_state,
                True,
                build_alert("Please load market data first", "warning", theme=theme),
                False,
                html.Div(),
                {'display': 'none'}
            )

        buy_signals, sell_signals = extract_signals(df)
        combinations = generate_signal_combinations(buy_signals, sell_signals, max_signals)
        combinations = combinations[:max_combos]

        if not combinations:
            return (
                current_state,
                True,
                build_alert("No valid signal combinations found", "warning", theme=theme),
                False,
                html.Div(),
                {'display': 'none'}
            )

        # Convert tuples to lists for JSON serialization
        combinations_serializable = [[list(buy), list(sell)] for buy, sell in combinations]

        # Reset state in dashboard_state
        dashboard_state.reset_optimization()
        dashboard_state.update_optimization_state(
            running=True,
            total_combinations=len(combinations),
            combinations=combinations_serializable,
            initial_capital=initial_capital
        )

        new_state = {
            'running': True,
            'current_index': 0,
            'total_combinations': len(combinations),
            'completed': False,
            'sort_by': 'Total_Return_%',
            'sort_ascending': False
        }

        progress_ui = html.Div([
            build_progress_bar(0, f"Testing 0/{len(combinations)} combinations...", theme=theme),
            html.Div("Starting optimization...",
                     style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginTop': '4px'})
        ])

        return (
            new_state,
            False,  # Enable interval
            progress_ui,
            True,   # Disable button
            html.Div(),  # Clear previous results
            {'display': 'none'}  # Hide apply button
        )

    @app.callback(
        [Output('optimization-state', 'data', allow_duplicate=True),
         Output('optimization-progress', 'children', allow_duplicate=True),
         Output('optimization-results', 'children', allow_duplicate=True),
         Output('optimization-interval', 'disabled', allow_duplicate=True),
         Output('run-optimization-btn', 'disabled', allow_duplicate=True),
         Output('apply-strategy-container', 'style', allow_duplicate=True),
         Output('optimization-results-store', 'data')],
        [Input('optimization-interval', 'n_intervals')],
        [State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def process_optimization_batch(n_intervals, state):
        """Process a batch of combinations on each interval tick."""
        theme = get_theme()

        if not state or not state.get('running'):
            raise PreventUpdate

        df = dashboard_state.df
        if df is None:
            raise PreventUpdate

        opt_state = dashboard_state.optimization_state
        current_idx = opt_state.get('current_index', 0)
        total = opt_state.get('total_combinations', 0)
        combinations = opt_state.get('combinations', [])
        results = opt_state.get('results', [])
        initial_capital = opt_state.get('initial_capital', 10000)

        if not combinations or current_idx >= total:
            raise PreventUpdate

        # Process batch
        end_idx = min(current_idx + OPTIMIZATION_BATCH_SIZE, total)

        for i in range(current_idx, end_idx):
            buy_combo, sell_combo = combinations[i]
            result = evaluate_signal_combination(df, initial_capital, tuple(buy_combo), tuple(sell_combo))
            results.append(result)

        # Update state
        dashboard_state.update_optimization_state(
            current_index=end_idx,
            results=results
        )

        progress_pct = int((end_idx / total) * 100)

        # Check if complete
        if end_idx >= total:
            dashboard_state.update_optimization_state(running=False, completed=True)

            results_df = pd.DataFrame(results)
            if 'Total_Return_%' in results_df.columns:
                results_df = results_df[results_df['Total_Return_%'].notna()]
                results_df = results_df.sort_values(state.get('sort_by', 'Total_Return_%'),
                                                    ascending=state.get('sort_ascending', False))

            if results_df.empty:
                state['running'] = False
                state['completed'] = True
                return (
                    state,
                    build_alert("All combinations failed", "warning", theme=theme),
                    html.Div(),
                    True,
                    False,
                    {'display': 'none'},
                    []
                )

            state['running'] = False
            state['completed'] = True

            final_progress = html.Div([
                html.Span("\u2713 ", style={'color': theme['accent_green']}),
                html.Span(f"Completed! Tested {total} combinations",
                         style={'fontSize': FONT_SIZES['xs'], 'color': theme['accent_green']})
            ])

            results_ui = html.Div([
                _create_best_strategy_highlight(results_df.iloc[0], theme),
                _create_optimization_table(results_df.head(10), theme),
            ], className='fade-in')

            return (
                state,
                final_progress,
                results_ui,
                True,   # Disable interval
                False,  # Re-enable button
                {'display': 'block'},  # Show apply button
                results_df.to_dict('records')
            )

        # Still processing - update progress
        state['current_index'] = end_idx

        progress_ui = html.Div([
            build_progress_bar(progress_pct, f"Testing {end_idx}/{total} combinations...", theme=theme),
            html.Div(f"Found {len([r for r in results if 'Total_Return_%' in r])} valid strategies so far...",
                     style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginTop': '4px'})
        ])

        # Show partial results (top 5 so far)
        valid_results = [r for r in results if 'Total_Return_%' in r]
        partial_results = html.Div()
        if len(valid_results) >= 5:
            partial_df = pd.DataFrame(valid_results).sort_values('Total_Return_%', ascending=False).head(5)
            partial_results = html.Div([
                html.Div("Top strategies so far:",
                        style={'fontSize': FONT_SIZES['xs'], 'color': theme['text_secondary'], 'marginBottom': '8px'}),
                _create_optimization_table_mini(partial_df, theme)
            ], style={'marginTop': '12px'})

        return (
            state,
            progress_ui,
            partial_results,
            False,  # Keep interval enabled
            True,   # Keep button disabled
            {'display': 'none'},
            []
        )

    @app.callback(
        Output('optimization-results', 'children', allow_duplicate=True),
        [Input('sort-metric-dropdown', 'value')],
        [State('optimization-results-store', 'data'),
         State('optimization-state', 'data')],
        prevent_initial_call=True
    )
    def sort_optimization_results(sort_by, results_data, state):
        """Re-sort results when sort metric changes."""
        if not results_data or not state.get('completed'):
            raise PreventUpdate

        theme = get_theme()
        results_df = pd.DataFrame(results_data)

        # Ascending for drawdown (less negative is better), descending for others
        ascending = sort_by == 'Max_Drawdown_%'
        results_df = results_df.sort_values(sort_by, ascending=ascending)

        return html.Div([
            _create_best_strategy_highlight(results_df.iloc[0], theme),
            _create_optimization_table(results_df.head(10), theme),
        ], className='fade-in')

    @app.callback(
        [Output('buy-signals', 'value', allow_duplicate=True),
         Output('sell-signals', 'value', allow_duplicate=True),
         Output('tab-backtest', 'n_clicks', allow_duplicate=True)],
        [Input('apply-strategy-btn', 'n_clicks')],
        [State('optimization-results-store', 'data'),
         State('sort-metric-dropdown', 'value'),
         State('tab-backtest', 'n_clicks')],
        prevent_initial_call=True
    )
    def apply_best_strategy(n_clicks, results_data, sort_by, current_backtest_clicks):
        """Apply the best strategy from optimization to the backtest panel."""
        if not n_clicks or not results_data:
            raise PreventUpdate

        results_df = pd.DataFrame(results_data)
        ascending = sort_by == 'Max_Drawdown_%'
        results_df = results_df.sort_values(sort_by, ascending=ascending)

        best = results_df.iloc[0]

        # Parse signal strings back to lists
        buy_signals = [s.strip() for s in str(best['Buy_Signals']).split(',') if s.strip()]
        sell_signals_str = str(best.get('Sell_Signals', ''))
        sell_signals = [s.strip() for s in sell_signals_str.split(',') if s.strip()]

        # Return values to populate checklists and switch to backtest tab
        return buy_signals, sell_signals, (current_backtest_clicks or 0) + 1

    # ==================== END OPTIMIZATION CALLBACKS ====================

    @app.callback(
        [Output('panel-backtest', 'style'),
         Output('panel-optimizer', 'style'),
         Output('panel-data', 'style'),
         Output('tab-backtest', 'style'),
         Output('tab-optimizer', 'style'),
         Output('tab-data', 'style')],
        [Input('tab-backtest', 'n_clicks'),
         Input('tab-optimizer', 'n_clicks'),
         Input('tab-data', 'n_clicks')]
    )
    def switch_panel(backtest_clicks, optimizer_clicks, data_clicks):
        """Switch between right panel tabs."""
        theme = get_theme()
        styles = get_styles(theme)

        ctx = callback_context
        if not ctx.triggered:
            # Default to backtest tab
            return (
                {'display': 'block'},
                {'display': 'none'},
                {'display': 'none'},
                {**styles['tab'], **styles['tab_active']},
                styles['tab'],
                styles['tab']
            )

        button_id = ctx.triggered[0]['prop_id'].split('.')[0]

        if button_id == 'tab-backtest':
            return (
                {'display': 'block'},
                {'display': 'none'},
                {'display': 'none'},
                {**styles['tab'], **styles['tab_active']},
                styles['tab'],
                styles['tab']
            )
        elif button_id == 'tab-optimizer':
            return (
                {'display': 'none'},
                {'display': 'block'},
                {'display': 'none'},
                styles['tab'],
                {**styles['tab'], **styles['tab_active']},
                styles['tab']
            )
        else:  # tab-data
            return (
                {'display': 'none'},
                {'display': 'none'},
                {'display': 'block'},
                styles['tab'],
                styles['tab'],
                {**styles['tab'], **styles['tab_active']}
            )

    @app.callback(
        Output('header-status', 'children'),
        [Input('startup-interval', 'n_intervals')]
    )
    def update_header_status(_):
        """Update header status."""
        return datetime.now().strftime("%H:%M:%S")

    @app.callback(
        [Output('theme-store', 'data'),
         Output('theme-label', 'children')],
        [Input('theme-toggle', 'n_clicks')],
        [State('theme-store', 'data')]
    )
    def toggle_theme(n_clicks, current_theme):
        """Toggle between dark and light themes."""
        if not n_clicks:
            return DEFAULT_THEME, "\u2600\ufe0f"

        new_theme = 'light' if current_theme == 'dark' else 'dark'
        icon = "\U0001f319" if new_theme == 'light' else "\u2600\ufe0f"
        dashboard_state.set_theme(new_theme)
        return new_theme, icon

    # Register clientside callback for keyboard shortcuts
    app.clientside_callback(
        """
        function(id) {
            document.addEventListener('keydown', function(e) {
                // Ctrl+Enter to load data
                if (e.ctrlKey && e.key === 'Enter') {
                    var loadBtn = document.getElementById('load-data-button');
                    if (loadBtn) {
                        loadBtn.click();
                    }
                }
                // Ctrl+B to run backtest
                if (e.ctrlKey && e.key === 'b') {
                    e.preventDefault();
                    var backtestBtn = document.getElementById('run-backtest-btn');
                    if (backtestBtn) {
                        backtestBtn.click();
                    }
                }
                // Escape to close any modals/alerts
                if (e.key === 'Escape') {
                    var alerts = document.querySelectorAll('.alert-dismissible .btn-close');
                    alerts.forEach(function(btn) { btn.click(); });
                }
            });
            return window.dash_clientside.no_update;
        }
        """,
        Output('keyboard-listener', 'children'),
        Input('startup-interval', 'n_intervals')
    )

    # Clientside callback for synced crosshair across all subplots
    app.clientside_callback(
        """
        function(hoverData, figure) {
            if (!figure || !figure.data || figure.data.length === 0) {
                return window.dash_clientside.no_update;
            }

            // Create a copy of the figure
            var newFigure = JSON.parse(JSON.stringify(figure));

            // Remove previous crosshair shapes (identified by our custom name)
            if (newFigure.layout.shapes) {
                newFigure.layout.shapes = newFigure.layout.shapes.filter(function(shape) {
                    return shape.name !== 'crosshair-vline';
                });
            } else {
                newFigure.layout.shapes = [];
            }

            // If no hover data, return figure without crosshair
            if (!hoverData || !hoverData.points || hoverData.points.length === 0) {
                return newFigure;
            }

            // Get the x value from hover data
            var xValue = hoverData.points[0].x;

            // Add vertical line shape spanning all y axes (yref: 'paper' makes it span full height)
            newFigure.layout.shapes.push({
                type: 'line',
                name: 'crosshair-vline',
                x0: xValue,
                x1: xValue,
                y0: 0,
                y1: 1,
                xref: 'x',
                yref: 'paper',
                line: {
                    color: 'rgba(128, 128, 128, 0.7)',
                    width: 1,
                    dash: 'dot'
                }
            });

            return newFigure;
        }
        """,
        Output('financial-chart', 'figure', allow_duplicate=True),
        Input('financial-chart', 'hoverData'),
        State('financial-chart', 'figure'),
        prevent_initial_call=True
    )


# Helper functions for callbacks

def _create_data_table(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create a styled data table."""
    return dash_table.DataTable(
        columns=[{"name": i, "id": i} for i in display_df.columns],
        data=display_df.to_dict('records'),
        style_table={'height': '400px', 'overflowY': 'auto'},
        style_cell={
            'textAlign': 'right',
            'padding': '8px',
            'backgroundColor': theme['bg_tertiary'],
            'color': theme['text_primary'],
            'border': f'1px solid {theme["border_secondary"]}',
            'fontSize': '11px',
            'fontFamily': FONT_MONO,
        },
        style_header={
            'fontWeight': '600',
            'backgroundColor': theme['bg_secondary'],
            'color': theme['text_secondary'],
            'textTransform': 'uppercase',
            'fontSize': '10px',
        },
        style_data_conditional=[
            {'if': {'row_index': 'odd'}, 'backgroundColor': theme['table_row_alt']}
        ],
        page_size=50,
        fixed_rows={'headers': True}
    )


def _create_price_subtitle(df: pd.DataFrame, theme: dict) -> html.Span:
    """Create price change subtitle."""
    latest_close = df['Close'].iloc[-1]
    prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
    change = latest_close - prev_close
    change_pct = (change / prev_close) * 100
    change_color = theme['accent_green'] if change >= 0 else theme['accent_red']
    change_sign = '+' if change >= 0 else ''

    return html.Span([
        html.Span(f"${latest_close:.2f}", style={'fontFamily': FONT_MONO, 'color': theme['text_primary']}),
        html.Span(f" {change_sign}{change:.2f} ({change_sign}{change_pct:.2f}%)",
                 style={'fontFamily': FONT_MONO, 'color': change_color, 'marginLeft': '8px'}),
    ])


def _create_optimization_table(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create enhanced optimization results table with all columns."""
    columns = ['Buy_Signals', 'Sell_Signals', 'Total_Return_%', 'Sharpe_Ratio', 'Max_Drawdown_%', 'Trades']
    available_cols = [c for c in columns if c in display_df.columns]

    return dash_table.DataTable(
        id='optimization-table',
        columns=[{"name": c.replace('_', ' '), "id": c} for c in available_cols],
        data=display_df[available_cols].round(2).to_dict('records'),
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
        style_data_conditional=[
            {'if': {'row_index': 0}, 'backgroundColor': f'{theme["accent_green"]}15'},
            {'if': {'row_index': 1}, 'backgroundColor': f'{theme["accent_blue"]}10'},
            {'if': {'row_index': 2}, 'backgroundColor': f'{theme["accent_blue"]}05'},
        ],
        page_size=10,
    )


def _create_optimization_table_mini(display_df: pd.DataFrame, theme: dict) -> dash_table.DataTable:
    """Create compact mini-table for partial results during optimization."""
    return dash_table.DataTable(
        columns=[
            {"name": "Buy Signals", "id": "Buy_Signals"},
            {"name": "Return %", "id": "Total_Return_%"},
        ],
        data=display_df[['Buy_Signals', 'Total_Return_%']].round(1).to_dict('records'),
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


def _create_best_strategy_highlight(best_row: pd.Series, theme: dict) -> html.Div:
    """Create highlight card for the best strategy."""
    total_return = best_row.get('Total_Return_%', 0)
    sharpe = best_row.get('Sharpe_Ratio', 0)
    drawdown = best_row.get('Max_Drawdown_%', 0)

    return html.Div([
        html.Div([
            html.Span("\U0001f3c6 ", style={'fontSize': '16px'}),
            html.Span("Best Strategy", style={
                'color': theme['text_secondary'],
                'fontSize': FONT_SIZES['sm'],
                'fontWeight': '600'
            }),
        ], style={'marginBottom': '8px'}),
        html.Div([
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
                    'fontFamily': FONT_MONO
                }),
                html.Span(f" | Sharpe: {sharpe:.2f}", style={
                    'color': theme['text_secondary'],
                    'fontSize': FONT_SIZES['xs'],
                    'marginLeft': '8px'
                }),
                html.Span(f" | DD: {drawdown:.1f}%", style={
                    'color': theme['text_secondary'],
                    'fontSize': FONT_SIZES['xs'],
                    'marginLeft': '8px'
                }),
            ]),
        ]),
    ], style={
        'backgroundColor': theme['bg_tertiary'],
        'padding': '12px',
        'borderRadius': '6px',
        'marginBottom': '12px',
        'border': f'1px solid {theme["accent_green"]}40'
    })


# Batch size for optimization processing (combinations per interval tick)
OPTIMIZATION_BATCH_SIZE = 5
