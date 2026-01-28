# indicators module
"""
Technical indicators and signal aggregation module.
"""

import logging
import numpy as np
import pandas as pd
import yfinance as yf

from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange

from lib.signals.base_strategy import BaseTradingStrategy
from lib.signals.signals_BB import BB_TradingStrategy
from lib.signals.signals_CCI import CCI_TradingStrategy
from lib.signals.signals_EMA import EMA_TradingStrategy
from lib.signals.signals_MACD import MACD_TradingStrategy
from lib.signals.signals_RSI import RSI_TradingStrategy
from lib.signals.signals_SMA import SMA_TradingStrategy

logger = logging.getLogger(__name__)

logger = logging.getLogger(__name__)


def add_indicators(df: pd.DataFrame, indicator_settings: dict | None = None) -> pd.DataFrame:
    """
    Add technical indicators to the DataFrame.
    
    Args:
        df: DataFrame with OHLCV data.
        
    Returns:
        DataFrame with added indicator columns.
    """
    logger.debug("Adding technical indicators")
    indicator_settings = indicator_settings or {}
    
    # ADX (Average Directional Index)
    adx_period = indicator_settings.get('adx', {}).get('period', 14)
    adx = ADXIndicator(df['High'], df['Low'], df['Close'], window=adx_period)
    df['ADX'] = adx.adx()
    
    # ATR (Average True Range)
    atr_period = indicator_settings.get('atr', {}).get('period', 14)
    atr = AverageTrueRange(df['High'], df['Low'], df['Close'], window=atr_period)
    df['ATR'] = atr.average_true_range()
    
    # OBV (On-Balance Volume)
    df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
   
    return df


def generate_signals(df: pd.DataFrame, indicator_settings: dict | None = None) -> tuple:
    """
    Generate trading signals from all strategy classes.
    
    Args:
        df: DataFrame with OHLCV data and indicators.
        
    Returns:
        Tuple of (DataFrame with signals, list of signal column headers).
    """
    logger.info("Generating trading signals")
    indicator_settings = indicator_settings or {}
    rsi_settings = indicator_settings.get('rsi', {})
    cci_settings = indicator_settings.get('cci', {})
    macd_settings = indicator_settings.get('macd', {})
    bb_settings = indicator_settings.get('bollinger', {})
    sma_settings = indicator_settings.get('sma', {})
    ema_settings = indicator_settings.get('ema', {})

    rsi_config = {
        'rsi': {'window': rsi_settings.get('period', 14)},
        'overbought_oversold': {
            'upper_threshold': rsi_settings.get('overbought', 70),
            'lower_threshold': rsi_settings.get('oversold', 30)
        }
    }
    cci_config = {
        'cci': {'window': cci_settings.get('period', 20)},
        'overbought_oversold': {
            'upper_threshold': cci_settings.get('ceiling', 100),
            'lower_threshold': cci_settings.get('floor', -100)
        }
    }
    macd_config = {
        'macd': {
            'fast_period': macd_settings.get('fast', 12),
            'slow_period': macd_settings.get('slow', 26),
            'signal_period': macd_settings.get('signal', 9)
        }
    }
    bb_config = {
        'bollinger_bands': {
            'window': bb_settings.get('window', 20),
            'window_dev': bb_settings.get('window_dev', 2)
        },
        'squeeze_strategy': {
            'squeeze_threshold': bb_settings.get('squeeze_threshold', 0.1)
        },
        'double_bottom_top_strategy': {
            'threshold': bb_settings.get('double_bottom_threshold', 0.02)
        }
    }
    sma_config = {
        'sma': {
            'short_window': sma_settings.get('short_window', 5),
            'medium_window': sma_settings.get('medium_window', 20),
            'long_window': sma_settings.get('long_window', 50),
            'trend_window': sma_settings.get('trend_window', 200)
        }
    }
    ema_config = {
        'ema': {
            'short_window': ema_settings.get('short_window', 12),
            'medium_window': ema_settings.get('medium_window', 26),
            'long_window': ema_settings.get('long_window', 50),
            'atr_window': ema_settings.get('atr_window', 14)
        }
    }
    
    strategies = [
        BB_TradingStrategy(bb_config),
        MACD_TradingStrategy(macd_config),
        RSI_TradingStrategy(rsi_config),
        CCI_TradingStrategy(cci_config),
        SMA_TradingStrategy(sma_config),
        EMA_TradingStrategy(ema_config),
    ]
    
    for strategy in strategies:
        try:
            df = strategy.generate_signals(df)
            logger.debug(f"Generated signals for {strategy.name}")
        except Exception as e:
            logger.error(f"Error generating signals for {strategy.name}: {e}")
            raise
    
    signal_headers = df.columns.tolist()
    
    return df, signal_headers

