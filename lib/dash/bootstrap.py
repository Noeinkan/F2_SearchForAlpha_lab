"""
Default session bootstrap — preload TSLA before the first page render.

Every dashboard start (local or server) should open with the default ticker
fetched, indicators computed, and the chart ready. Browser-side autoload is
kept as a fallback when bootstrap fails (e.g. offline / yfinance error).
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date
from typing import Any

from dash import html

from lib.dash.chart_builder import create_chart
from lib.dash.dash_config import (
    DEFAULT_INDICATOR_SETTINGS,
    DEFAULT_TICKER,
    START_DATE,
    get_theme,
    merge_indicator_settings,
)
from lib.dash.helpers import fetch_data_with_cache, format_df_for_display
from lib.dash.state import dashboard_state
from lib.signals.indicators import (
    add_indicators,
    classify_signal_columns,
    format_strategy_order_debug_text,
    generate_signals,
)

logger = logging.getLogger(__name__)

# Matches default sidebar toggles in layout/sidebar.py
DEFAULT_SELECTED_PLOTS = ['candlestick', 'volume', 'rsi', 'cci', 'macd']
DEFAULT_CHART_ELEMENTS = ['candlesticks', 'signals', 'bollinger']


def build_default_chart_config(indicator_settings: dict | None = None) -> dict:
    """Chart display config aligned with the default sidebar checkboxes."""
    return {
        'selected_plots': list(DEFAULT_SELECTED_PLOTS),
        'show_candlesticks': 'candlesticks' in DEFAULT_CHART_ELEMENTS,
        'show_bollinger': 'bollinger' in DEFAULT_CHART_ELEMENTS,
        'show_sma': 'sma' in DEFAULT_CHART_ELEMENTS,
        'show_ema': 'ema' in DEFAULT_CHART_ELEMENTS,
        'show_buy_sell_signals': 'signals' in DEFAULT_CHART_ELEMENTS,
        'show_legend': 'legend' in DEFAULT_CHART_ELEMENTS,
        'selected_signals': [],
        'buy_signal_columns': [],
        'sell_signal_columns': [],
        'consecutive_signal_mode': 'scale_in',
        'cooldown_bars': 0,
        'signal_logic': 'or',
        'signal_window': 0,
        'title': '',
        'indicator_settings': indicator_settings or DEFAULT_INDICATOR_SETTINGS,
    }


@dataclass(frozen=True)
class BootstrapSnapshot:
    """Layout seed values after a successful default session load."""

    ticker: str
    data_status: str
    strategy_order: str
    chart_title: str
    chart_subtitle: Any
    header_symbol: str
    header_price: str
    header_change: Any
    buy_options: list
    sell_options: list
    unified_rows: list
    data_table: Any
    chart_figure: Any


def load_market_session(
    ticker: str,
    start_date: str,
    end_date: str,
    indicator_settings: dict | None = None,
) -> BootstrapSnapshot:
    """
    Fetch OHLCV, compute indicators/signals, and populate dashboard_state.

    Raises on fetch/processing failure. Used by server bootstrap and the
    Load Data callback.
    """
    from lib.dash.callbacks.shared import (
        _build_signal_options,
        _build_unified_signal_rows,
        _create_data_table,
        _create_price_subtitle,
        clear_enriched_cache,
    )

    theme = get_theme()
    effective_settings = merge_indicator_settings(indicator_settings or DEFAULT_INDICATOR_SETTINGS)

    df = fetch_data_with_cache(ticker, start_date, end_date)
    if df.empty:
        raise ValueError(f"No data available for {ticker}")

    df = add_indicators(df, effective_settings)
    df, _ = generate_signals(df, effective_settings)
    clear_enriched_cache()
    dashboard_state.df = df

    classified = classify_signal_columns(df.columns.tolist())
    buy_columns = classified['buy']
    sell_columns = classified['sell']
    buy_options = _build_signal_options(buy_columns)
    sell_options = _build_signal_options(sell_columns)
    unified_rows = _build_unified_signal_rows(buy_columns, sell_columns)

    display_df = format_df_for_display(df.tail(50)).reset_index()
    data_table = _create_data_table(display_df, theme)
    subtitle = _create_price_subtitle(df, theme)

    latest_close = df['Close'].iloc[-1]
    prev_close = df['Close'].iloc[-2] if len(df) > 1 else latest_close
    change = latest_close - prev_close
    change_pct = (change / prev_close) * 100 if prev_close else 0
    change_prefix = '\u25b2' if change >= 0 else '\u25bc'
    change_sign = '+' if change >= 0 else ''
    change_color = theme['accent_green'] if change >= 0 else theme['accent_red']

    chart_figure = create_chart(
        df,
        build_default_chart_config(effective_settings),
        theme,
    )

    symbol = (ticker or DEFAULT_TICKER).upper()
    return BootstrapSnapshot(
        ticker=ticker,
        data_status=f"{len(df)} ROWS",
        strategy_order=format_strategy_order_debug_text(),
        chart_title=ticker,
        chart_subtitle=subtitle,
        header_symbol=symbol,
        header_price=f"${latest_close:.2f}",
        header_change=html.Span(
            f"{change_prefix} {change_sign}{change:.2f} ({change_sign}{change_pct:.2f}%)",
            className='num',
            style={'color': change_color},
        ),
        buy_options=buy_options,
        sell_options=sell_options,
        unified_rows=unified_rows,
        data_table=data_table,
        chart_figure=chart_figure,
    )


def try_bootstrap_default_session() -> BootstrapSnapshot | None:
    """Preload DEFAULT_TICKER (TSLA) at process start; None on failure."""
    try:
        snapshot = load_market_session(
            DEFAULT_TICKER,
            START_DATE,
            date.today().isoformat(),
        )
        logger.info(
            "Bootstrapped default session: %s (%s)",
            snapshot.header_symbol,
            snapshot.data_status,
        )
        return snapshot
    except Exception as exc:
        logger.warning("Default session bootstrap failed: %s", exc)
        return None
