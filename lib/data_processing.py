# Data processing module
"""
Data fetching, preprocessing, and metric calculations for trading strategies.
"""

import logging
import numpy as np
import pandas as pd
import yfinance as yf
from typing import List, Dict, Optional

# Configure module logger
logger = logging.getLogger(__name__)


class DataFetchError(Exception):
    """Custom exception for data fetching errors."""
    pass


def fetch_data(
    symbol: str,
    start_date: str,
    end_date: str,
    validate: bool = True
) -> pd.DataFrame:
    """
    Fetch historical price data from Yahoo Finance.
    
    Args:
        symbol: Ticker symbol to fetch.
        start_date: Start date in 'YYYY-MM-DD' format.
        end_date: End date in 'YYYY-MM-DD' format.
        validate: Whether to validate the returned data.
        
    Returns:
        DataFrame with OHLCV data.
        
    Raises:
        DataFetchError: If data cannot be fetched or is invalid.
    """
    if not symbol or not isinstance(symbol, str):
        raise DataFetchError(f"Invalid symbol: {symbol}")
    
    logger.info(f"Fetching data for {symbol} from {start_date} to {end_date}")
    
    try:
        ticker = yf.Ticker(symbol)
        df = ticker.history(start=start_date, end=end_date)
        
        if df.empty:
            raise DataFetchError(
                f"No data available for {symbol} between {start_date} and {end_date}"
            )
        
        df.index = pd.to_datetime(df.index).date
        
        if validate:
            _validate_price_data(df, symbol)
        
        logger.info(f"Successfully fetched {len(df)} rows for {symbol}")
        return df
        
    except DataFetchError:
        raise
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {str(e)}")
        raise DataFetchError(f"Failed to fetch data for {symbol}: {str(e)}") from e


def _validate_price_data(df: pd.DataFrame, symbol: str) -> None:
    """
    Validate price data quality.
    
    Args:
        df: DataFrame with price data.
        symbol: Symbol name for error messages.
        
    Raises:
        DataFetchError: If data fails validation.
    """
    required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise DataFetchError(f"Missing required columns for {symbol}: {missing}")
    
    # Check for excessive NaN values
    nan_pct = df['Close'].isna().sum() / len(df) * 100
    if nan_pct > 10:
        logger.warning(f"{symbol} has {nan_pct:.1f}% NaN values in Close column")


def get_all_tickers() -> pd.DataFrame:
    """
    Get list of S&P 500, NASDAQ-100 tickers and popular ETFs.
    
    Returns:
        DataFrame with Symbol, Security name, and Index columns.
        
    Raises:
        DataFetchError: If ticker list cannot be fetched.
    """
    logger.info("Fetching ticker list from Wikipedia")
    
    try:
        # Fetch S&P 500 tickers
        sp500 = pd.read_html('https://en.wikipedia.org/wiki/List_of_S%26P_500_companies')[0]
        sp500['Index'] = 'S&P 500'
        
        # Fetch NASDAQ-100 tickers
        nasdaq100 = pd.read_html('https://en.wikipedia.org/wiki/Nasdaq-100')[4]
        nasdaq100['Index'] = 'NASDAQ-100'
        nasdaq100 = nasdaq100.rename(columns={'Ticker': 'Symbol'})

        # Combine the dataframes
        all_tickers = pd.concat([
            sp500[['Symbol', 'Security', 'Index']], 
            nasdaq100[['Symbol', 'Company', 'Index']].rename(columns={'Company': 'Security'})
        ], ignore_index=True)

        # Add popular index ETFs
        index_etfs = pd.DataFrame({
            'Symbol': ['SPY', 'QQQ', 'DIA', 'IWM', 'VTI'],
            'Security': [
                'SPDR S&P 500 ETF', 
                'Invesco QQQ Trust', 
                'SPDR Dow Jones Industrial Average ETF', 
                'iShares Russell 2000 ETF', 
                'Vanguard Total Stock Market ETF'
            ],
            'Index': ['Index ETF'] * 5
        })

        all_tickers = pd.concat([all_tickers, index_etfs], ignore_index=True)
        all_tickers = all_tickers.drop_duplicates(subset='Symbol')

        logger.info(f"Fetched {len(all_tickers)} tickers")
        return all_tickers
        
    except Exception as e:
        logger.error(f"Error fetching ticker list: {str(e)}")
        raise DataFetchError(f"Failed to fetch ticker list: {str(e)}") from e


def calculate_max_drawdown(df: pd.DataFrame) -> float:
    """
    Calculate maximum drawdown from cumulative returns.
    
    Args:
        df: DataFrame with 'Cumulative_Returns' column.
        
    Returns:
        Maximum drawdown as a decimal (negative value).
    """
    if 'Cumulative_Returns' not in df.columns:
        logger.warning("Cumulative_Returns column not found, returning 0")
        return 0.0
    cumulative_returns = df['Cumulative_Returns']
    peak = cumulative_returns.expanding(min_periods=1).max()
    drawdown = (cumulative_returns - peak) / peak
    return drawdown.min()


def calculate_sharpe_ratio(
    returns: pd.Series,
    risk_free_rate: float = 0.02,
    periods_per_year: int = 252
) -> float:
    """
    Calculate annualized Sharpe ratio.
    
    Args:
        returns: Series of periodic returns.
        risk_free_rate: Annual risk-free rate.
        periods_per_year: Number of trading periods per year.
        
    Returns:
        Annualized Sharpe ratio.
    """
    if returns.std() == 0:
        return 0.0
    excess_returns = returns - risk_free_rate / periods_per_year
    return np.sqrt(periods_per_year) * excess_returns.mean() / excess_returns.std()


def calculate_win_rate(df: pd.DataFrame) -> float:
    """
    Calculate the win rate of trading strategy.
    
    Args:
        df: DataFrame with 'Strategy_Returns' column.
        
    Returns:
        Win rate as a decimal.
    """
    if 'Strategy_Returns' not in df.columns:
        return 0.0
    profitable_trades = (df['Strategy_Returns'] > 0).sum()
    total_trades = len(df['Strategy_Returns'])
    return profitable_trades / total_trades if total_trades > 0 else 0.0


def calculate_profit_factor(df: pd.DataFrame) -> float:
    """
    Calculate the profit factor (gross profits / gross losses).
    
    Args:
        df: DataFrame with 'Strategy_Returns' column.
        
    Returns:
        Profit factor (inf if no losses).
    """
    if 'Strategy_Returns' not in df.columns:
        return 0.0
    gross_profits = df['Strategy_Returns'][df['Strategy_Returns'] > 0].sum()
    gross_losses = abs(df['Strategy_Returns'][df['Strategy_Returns'] < 0].sum())
    return gross_profits / gross_losses if gross_losses != 0 else np.inf

def calculate_max_consecutive(series: pd.Series) -> int:
    """
    Calculate maximum consecutive occurrences in a boolean series.
    
    Args:
        series: Boolean series.
        
    Returns:
        Maximum consecutive count.
    """
    if series.empty:
        return 0
    groups = (series != series.shift()).cumsum()
    return max((series.groupby(groups).cumcount() + 1).max(), 0)


def calculate_average_trade_duration(df: pd.DataFrame) -> float:
    """
    Calculate average trade duration in days.
    
    Args:
        df: DataFrame with 'Units' column.
        
    Returns:
        Average trade duration in days.
    """
    if 'Units' not in df.columns:
        return 0.0
        
    try:
        trade_starts = df.index[df['Units'] != df['Units'].shift(1)]
        trade_ends = df.index[df['Units'] != df['Units'].shift(-1)]
        
        if len(trade_starts) > 0 and len(trade_ends) > 0:
            trade_durations = [
                (end - start).days 
                for start, end in zip(trade_starts, trade_ends) 
                if end > start
            ]
            return sum(trade_durations) / len(trade_durations) if trade_durations else 0.0
    except Exception as e:
        logger.warning(f"Error calculating trade duration: {e}")
    return 0.0

# Data processing module

def create_backtest_results(
    df: pd.DataFrame,
    ticker: str,
    initial_capital: float,
    buy_strategy: List[str],
    sell_strategy: List[str]
) -> Dict:
    """
    Create a dictionary of backtest results and metrics.
    
    Args:
        df: DataFrame with backtest results.
        ticker: Ticker symbol.
        initial_capital: Initial capital used.
        buy_strategy: List of buy indicator names.
        sell_strategy: List of sell indicator names.
        
    Returns:
        Dictionary with backtest metrics.
    """
    try:
        return {
            'ticker': ticker,
            'start_date': df.index[0].strftime('%Y-%m-%d') if hasattr(df.index[0], 'strftime') else str(df.index[0]),
            'end_date': df.index[-1].strftime('%Y-%m-%d') if hasattr(df.index[-1], 'strftime') else str(df.index[-1]),
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
    except Exception as e:
        logger.error(f"Error creating backtest results: {e}")
        raise