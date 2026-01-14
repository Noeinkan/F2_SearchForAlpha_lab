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


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """
    Add technical indicators to the DataFrame.
    
    Args:
        df: DataFrame with OHLCV data.
        
    Returns:
        DataFrame with added indicator columns.
    """
    logger.debug("Adding technical indicators")
    
    # ADX (Average Directional Index)
    adx = ADXIndicator(df['High'], df['Low'], df['Close'])
    df['ADX'] = adx.adx()
    
    # ATR (Average True Range)
    atr = AverageTrueRange(df['High'], df['Low'], df['Close'])
    df['ATR'] = atr.average_true_range()
    
    # OBV (On-Balance Volume)
    df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
   
    return df


def generate_signals(df: pd.DataFrame) -> tuple:
    """
    Generate trading signals from all strategy classes.
    
    Args:
        df: DataFrame with OHLCV data and indicators.
        
    Returns:
        Tuple of (DataFrame with signals, list of signal column headers).
    """
    logger.info("Generating trading signals")
    
    strategies = [
        BB_TradingStrategy(),
        MACD_TradingStrategy(),
        RSI_TradingStrategy(),
        CCI_TradingStrategy(),
        SMA_TradingStrategy(),
        EMA_TradingStrategy(),
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

