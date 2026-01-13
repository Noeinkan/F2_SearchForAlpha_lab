# indicators module

import numpy as np
import pandas as pd
import yfinance as yf

from ta.trend import ADXIndicator
from ta.volatility import AverageTrueRange


from lib.data_processing import *
from lib.visualization import *
from lib.utils import *
from lib.strategy import *
from SearchForAlpha_lab.lib.signal_combo_optimisation import *
# from SS.dash_visualization import *


from lib.signals.signals_BB import *
from lib.signals.signals_CCI import *
from lib.signals.signals_EMA import *
from lib.signals.signals_MACD import *
from lib.signals.signals_RSI import *
from lib.signals.signals_SMA import *

def add_indicators(df):
    
    # ADX (Average Directional Index)
    adx = ADXIndicator(df['High'], df['Low'], df['Close'])
    df['ADX'] = adx.adx()
    
    # ATR (Average True Range)
    atr = AverageTrueRange(df['High'], df['Low'], df['Close'])
    df['ATR'] = atr.average_true_range()
    
    # OBV (On-Balance Volume)
    df['OBV'] = (np.sign(df['Close'].diff()) * df['Volume']).fillna(0).cumsum()
   
    return df

def generate_signals(df: pd.DataFrame) -> pd.DataFrame:
    bb_strategy = BB_TradingStrategy()
    macd_strategy = MACD_TradingStrategy()
    rsi_strategy = RSI_TradingStrategy()
    cci_strategy = CCI_TradingStrategy()
    sma_strategy = SMA_TradingStrategy() 
    ema_strategy = EMA_TradingStrategy()


    df = bb_strategy.BB_generate_signals(df)
    df = macd_strategy.MACD_generate_signals(df)
    df = rsi_strategy.RSI_generate_signals(df)
    df = cci_strategy.CCI_generate_signals(df)
    df = sma_strategy.SMA_generate_signals(df)  # Aggiungi questa linea
    df = ema_strategy.EMA_generate_signals(df)
    
    signal_headers = df.columns.tolist()
    
    
    return df, signal_headers

