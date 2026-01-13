# data processing module

import numpy as np
import pandas as pd
import yfinance as yf

from typing import List, Dict

def fetch_data(symbol, start_date, end_date):

    ticker = yf.Ticker(symbol)
    df = ticker.history(start=start_date, end=end_date)
    #df.reset_index(inplace=True)
    #df['Date'] = pd.to_datetime(df['Date']).dt.date
    
    df.index = pd.to_datetime(df.index).date
    
    return df


def get_all_tickers():
    # Existing code to get S&P 500 and NASDAQ-100 stocks
    sp500 = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]
    sp500['Index'] = 'S&P 500'
    nasdaq100 = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')[4]
    nasdaq100['Index'] = 'NASDAQ-100'
    nasdaq100 = nasdaq100.rename(columns={'Ticker': 'Symbol'})

    # Combine the dataframes
    all_tickers = pd.concat([sp500[['Symbol', 'Security', 'Index']], 
                             nasdaq100[['Symbol', 'Company', 'Index']].rename(columns={'Company': 'Security'})], 
                            ignore_index=True)

    # Add popular index ETFs
    index_etfs = pd.DataFrame({
        'Symbol': ['SPY', 'QQQ', 'DIA', 'IWM', 'VTI'],
        'Security': ['SPDR S&P 500 ETF', 'Invesco QQQ Trust', 'SPDR Dow Jones Industrial Average ETF', 'iShares Russell 2000 ETF', 'Vanguard Total Stock Market ETF'],
        'Index': ['Index ETF'] * 5
    })

    # Append index ETFs to the main DataFrame
    all_tickers = pd.concat([all_tickers, index_etfs], ignore_index=True)

    # Remove duplicates
    all_tickers = all_tickers.drop_duplicates(subset='Symbol')

    return all_tickers


def calculate_max_drawdown(df):
    cumulative_returns = df['Cumulative_Returns']
    peak = cumulative_returns.expanding(min_periods=1).max()
    drawdown = (cumulative_returns - peak) / peak
    return drawdown.min()

def calculate_sharpe_ratio(returns, risk_free_rate=0.02):
    excess_returns = returns - risk_free_rate / 252  # Assuming daily returns
    return np.sqrt(252) * excess_returns.mean() / excess_returns.std()

def calculate_win_rate(df):
    profitable_trades = (df['Strategy_Returns'] > 0).sum()
    total_trades = len(df['Strategy_Returns'])
    return profitable_trades / total_trades if total_trades > 0 else 0

def calculate_profit_factor(df):
    gross_profits = df['Strategy_Returns'][df['Strategy_Returns'] > 0].sum()
    gross_losses = abs(df['Strategy_Returns'][df['Strategy_Returns'] < 0].sum())
    return gross_profits / gross_losses if gross_losses != 0 else np.inf

def calculate_max_consecutive(series):
    return max((series.groupby((series != series.shift()).cumsum()).cumcount() + 1).max(), 0)

def calculate_average_trade_duration(df):
    trade_starts = df.index[df['Units'] != df['Units'].shift(1)]
    trade_ends = df.index[df['Units'] != df['Units'].shift(-1)]
    if len(trade_starts) > 0 and len(trade_ends) > 0:
        trade_durations = [(end - start).days for start, end in zip(trade_starts, trade_ends) if end > start]
        return sum(trade_durations) / len(trade_durations) if trade_durations else 0
    return 0

# data processing module

def create_backtest_results(df: pd.DataFrame, ticker: str, initial_capital: float, buy_strategy: List[str], sell_strategy: List[str]) -> Dict:
    return {
        'ticker': ticker,
        'start_date': df.index[0].strftime('%Y-%m-%d'),
        'end_date': df.index[-1].strftime('%Y-%m-%d'),
        'initial_capital': initial_capital,
        'final_portfolio_value': df['Portfolio_Value'].iloc[-1],
        'total_return': (df['Cumulative_Returns'].iloc[-1] - 1) * 100,
        'market_return': ((df['Close'].iloc[-1] / df['Close'].iloc[0]) - 1) * 100,
        'buy_strategy': buy_strategy,
        'sell_strategy': sell_strategy,
        'max_drawdown': calculate_max_drawdown(df),
        'sharpe_ratio': calculate_sharpe_ratio(df['Strategy_Returns']),
        'win_rate': calculate_win_rate(df),
        'profit_factor': calculate_profit_factor(df),
        'avg_trade_duration': calculate_average_trade_duration(df)
    }