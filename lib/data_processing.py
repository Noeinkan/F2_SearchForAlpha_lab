# Data processing module
"""
Data fetching, preprocessing, and metric calculations for trading strategies.
"""

import logging
import numpy as np
import pandas as pd
import yfinance as yf
from typing import List, Dict, Optional
from pathlib import Path
from datetime import datetime, timedelta
import time

# Configure module logger
logger = logging.getLogger(__name__)

# Global cache for ticker universe with TTL
_TICKER_CACHE = None
_TICKER_CACHE_TIME = None
_TICKER_CACHE_TTL_HOURS = 24


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


def _get_default_tickers() -> pd.DataFrame:
    """
    Load default ticker universe from config/tickers_universe.csv.
    
    Fallback to minimal bootstrap list if config file not found.
    """
    config_path = Path(__file__).parent.parent / "config" / "tickers_universe.csv"
    
    if config_path.exists():
        try:
            return pd.read_csv(config_path)
        except Exception as e:
            logger.warning(f"Failed to load tickers from {config_path}: {e}")
    
    # Minimal bootstrap list (always available)
    bootstrap = [
        ('SPY', 'SPDR S&P 500 ETF', 'Index ETF', 'NYSE'),
        ('QQQ', 'Invesco QQQ Trust', 'Index ETF', 'NASDAQ'),
        ('IWM', 'iShares Russell 2000 ETF', 'Index ETF', 'NYSE'),
        ('DIA', 'SPDR Dow Jones Industrial Average ETF', 'Index ETF', 'NYSE'),
        ('VTI', 'Vanguard Total Stock Market ETF', 'Index ETF', 'NYSE'),
        ('AAPL', 'Apple Inc.', 'S&P 500', 'NASDAQ'),
        ('MSFT', 'Microsoft Corporation', 'S&P 500', 'NASDAQ'),
        ('GOOGL', 'Alphabet Inc. Class A', 'S&P 500', 'NASDAQ'),
        ('AMZN', 'Amazon.com Inc.', 'S&P 500', 'NASDAQ'),
        ('NVDA', 'NVIDIA Corporation', 'S&P 500', 'NASDAQ'),
    ]
    return pd.DataFrame(bootstrap, columns=['Symbol', 'Security', 'Index', 'Exchange'])



def _fetch_sp500_from_github() -> Optional[pd.DataFrame]:
    """Fetch S&P 500 constituents from GitHub datasets repo with retry logic."""
    import requests
    url = 'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv'
    max_retries = 2
    backoff_factor = 1.0
    
    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            from io import StringIO
            df = pd.read_csv(StringIO(response.text))
            df = df.rename(columns={'Name': 'Security'})
            df['Index'] = 'S&P 500'
            df['Exchange'] = 'NYSE'
            logger.info(f"Fetched {len(df)} tickers from GitHub")
            return df[['Symbol', 'Security', 'Index', 'Exchange']]
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = backoff_factor * (2 ** attempt)
                logger.warning(f"GitHub timeout, retrying in {wait_time}s...")
                time.sleep(wait_time)
            else:
                logger.warning("GitHub fetch failed after retries")
        except Exception as e:
            logger.warning(f"Failed to fetch from GitHub: {e}")
            break
    return None


def _fetch_from_wikipedia() -> Optional[pd.DataFrame]:
    """Fetch tickers from Wikipedia with retry logic."""
    import requests
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    max_retries = 1
    backoff_factor = 1.0
    
    for attempt in range(max_retries):
        try:
            # Fetch S&P 500 tickers
            sp500_resp = requests.get(
                'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
                headers=headers, timeout=5
            )
            sp500_resp.raise_for_status()
            sp500 = pd.read_html(sp500_resp.text)[0]
            sp500['Index'] = 'S&P 500'
            sp500['Exchange'] = 'NYSE'

            all_tickers = sp500[['Symbol', 'Security', 'Index', 'Exchange']] if 'Exchange' in sp500.columns else sp500[['Symbol', 'Security', 'Index']].assign(Exchange='NYSE')
            logger.info(f"Fetched {len(all_tickers)} tickers from Wikipedia")
            return all_tickers
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = backoff_factor * (2 ** attempt)
                logger.warning(f"Wikipedia timeout, retrying in {wait_time}s...")
                time.sleep(wait_time)
        except Exception as e:
            logger.warning(f"Failed to fetch from Wikipedia: {e}")
            break
    return None


def _is_cache_valid() -> bool:
    """Check if in-memory ticker cache is still valid."""
    global _TICKER_CACHE, _TICKER_CACHE_TIME
    if _TICKER_CACHE is None or _TICKER_CACHE_TIME is None:
        return False
    age = datetime.now() - _TICKER_CACHE_TIME
    return age < timedelta(hours=_TICKER_CACHE_TTL_HOURS)



def get_all_tickers() -> pd.DataFrame:
    """
    Get list of S&P 500, NASDAQ-100 tickers and popular ETFs.

    Uses caching with TTL to minimize network calls. Fallback strategy:
    1. Return cached data if still valid (< 24 hours old)
    2. Try GitHub datasets repo (most reliable)
    3. Try Wikipedia (comprehensive but may be slow)
    4. Fall back to local config file
    5. Use minimal bootstrap list as last resort

    Returns:
        DataFrame with Symbol, Security name, Index, and Exchange columns.
    """
    global _TICKER_CACHE, _TICKER_CACHE_TIME
    
    # Return cached data if valid
    if _is_cache_valid():
        logger.debug("Returning cached ticker list")
        return _TICKER_CACHE  # type: ignore
    
    logger.info("Ticker cache expired or empty, refreshing...")
    tickers_df = None
    
    # Try GitHub first (most reliable, no parsing fragility)
    tickers_df = _fetch_sp500_from_github()
    
    # Try Wikipedia as backup
    if tickers_df is None:
        logger.info("GitHub unavailable, trying Wikipedia...")
        tickers_df = _fetch_from_wikipedia()
    
    # Fall back to local config file
    if tickers_df is None:
        logger.info("Network sources unavailable, loading from config...")
        tickers_df = _get_default_tickers()
    else:
        # Merge with local config to ensure comprehensive coverage
        local_tickers = _get_default_tickers()
        tickers_df = pd.concat([tickers_df, local_tickers], ignore_index=True)
    
    # Ensure 'Exchange' column exists
    if 'Exchange' not in tickers_df.columns:
        tickers_df['Exchange'] = 'Unknown'
    
    # Remove duplicates, prefer data from network sources
    tickers_df = tickers_df.drop_duplicates(subset='Symbol', keep='first')
    
    # Normalize: ensure no NaN values, handle common cases
    tickers_df['Symbol'] = tickers_df['Symbol'].fillna('').str.strip()
    tickers_df = tickers_df[tickers_df['Symbol'].str.len() > 0]
    
    logger.info(f"Loaded {len(tickers_df)} tickers")
    
    # Update cache
    _TICKER_CACHE = tickers_df
    _TICKER_CACHE_TIME = datetime.now()
    
    return tickers_df


def validate_symbol(symbol: str, cache_hit: bool = True) -> bool:
    """
    Validate if a symbol exists and is tradeable.
    
    Args:
        symbol: Ticker symbol to validate.
        cache_hit: If True, check against known ticker universe; 
                   if False, attempt fetch from Yahoo Finance.
    
    Returns:
        True if symbol is valid, False otherwise.
    """
    if not symbol or not isinstance(symbol, str):
        return False
    
    symbol = symbol.strip().upper()
    
    # Quick check against ticker universe (fast)
    if cache_hit:
        known_tickers = get_all_tickers()
        return symbol in known_tickers['Symbol'].values
    
    # Slow check: try to fetch from Yahoo Finance (validates tradeable)
    try:
        ticker = yf.Ticker(symbol)
        history = ticker.history(period='1d')
        return not history.empty
    except Exception as e:
        logger.debug(f"Symbol validation failed for {symbol}: {e}")
        return False




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
            'total_return': ((df['Portfolio_Value'].iloc[-1] / initial_capital) - 1) * 100,
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