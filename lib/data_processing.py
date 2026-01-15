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


def _get_default_tickers() -> pd.DataFrame:
    """Return a default list of popular tickers as fallback."""
    tickers = [
        # Major Tech
        ('AAPL', 'Apple Inc.', 'S&P 500'),
        ('MSFT', 'Microsoft Corporation', 'S&P 500'),
        ('GOOGL', 'Alphabet Inc. Class A', 'S&P 500'),
        ('AMZN', 'Amazon.com Inc.', 'S&P 500'),
        ('NVDA', 'NVIDIA Corporation', 'S&P 500'),
        ('META', 'Meta Platforms Inc.', 'S&P 500'),
        ('TSLA', 'Tesla Inc.', 'S&P 500'),
        ('AMD', 'Advanced Micro Devices Inc.', 'S&P 500'),
        ('INTC', 'Intel Corporation', 'S&P 500'),
        ('CRM', 'Salesforce Inc.', 'S&P 500'),
        ('ORCL', 'Oracle Corporation', 'S&P 500'),
        ('ADBE', 'Adobe Inc.', 'S&P 500'),
        ('NFLX', 'Netflix Inc.', 'S&P 500'),
        # Finance
        ('JPM', 'JPMorgan Chase & Co.', 'S&P 500'),
        ('BAC', 'Bank of America Corp.', 'S&P 500'),
        ('WFC', 'Wells Fargo & Company', 'S&P 500'),
        ('GS', 'Goldman Sachs Group Inc.', 'S&P 500'),
        ('MS', 'Morgan Stanley', 'S&P 500'),
        ('V', 'Visa Inc.', 'S&P 500'),
        ('MA', 'Mastercard Inc.', 'S&P 500'),
        # Healthcare
        ('JNJ', 'Johnson & Johnson', 'S&P 500'),
        ('UNH', 'UnitedHealth Group Inc.', 'S&P 500'),
        ('PFE', 'Pfizer Inc.', 'S&P 500'),
        ('MRK', 'Merck & Co. Inc.', 'S&P 500'),
        ('ABBV', 'AbbVie Inc.', 'S&P 500'),
        ('LLY', 'Eli Lilly and Company', 'S&P 500'),
        # Consumer
        ('WMT', 'Walmart Inc.', 'S&P 500'),
        ('PG', 'Procter & Gamble Co.', 'S&P 500'),
        ('KO', 'Coca-Cola Company', 'S&P 500'),
        ('PEP', 'PepsiCo Inc.', 'S&P 500'),
        ('COST', 'Costco Wholesale Corp.', 'S&P 500'),
        ('MCD', 'McDonalds Corp.', 'S&P 500'),
        ('HD', 'Home Depot Inc.', 'S&P 500'),
        ('NKE', 'Nike Inc.', 'S&P 500'),
        # Industrial
        ('CAT', 'Caterpillar Inc.', 'S&P 500'),
        ('BA', 'Boeing Company', 'S&P 500'),
        ('GE', 'General Electric Company', 'S&P 500'),
        ('MMM', '3M Company', 'S&P 500'),
        ('HON', 'Honeywell International Inc.', 'S&P 500'),
        ('UPS', 'United Parcel Service Inc.', 'S&P 500'),
        # Energy
        ('XOM', 'Exxon Mobil Corporation', 'S&P 500'),
        ('CVX', 'Chevron Corporation', 'S&P 500'),
        ('COP', 'ConocoPhillips', 'S&P 500'),
        # Telecom
        ('T', 'AT&T Inc.', 'S&P 500'),
        ('VZ', 'Verizon Communications Inc.', 'S&P 500'),
        ('TMUS', 'T-Mobile US Inc.', 'S&P 500'),
        # Index ETFs
        ('SPY', 'SPDR S&P 500 ETF', 'Index ETF'),
        ('QQQ', 'Invesco QQQ Trust', 'Index ETF'),
        ('DIA', 'SPDR Dow Jones Industrial Average ETF', 'Index ETF'),
        ('IWM', 'iShares Russell 2000 ETF', 'Index ETF'),
        ('VTI', 'Vanguard Total Stock Market ETF', 'Index ETF'),
        ('VOO', 'Vanguard S&P 500 ETF', 'Index ETF'),
        ('VGT', 'Vanguard Information Technology ETF', 'Sector ETF'),
        ('XLF', 'Financial Select Sector SPDR Fund', 'Sector ETF'),
        ('XLE', 'Energy Select Sector SPDR Fund', 'Sector ETF'),
        ('XLK', 'Technology Select Sector SPDR Fund', 'Sector ETF'),
    ]
    return pd.DataFrame(tickers, columns=['Symbol', 'Security', 'Index'])


def _fetch_sp500_from_github() -> Optional[pd.DataFrame]:
    """Fetch S&P 500 constituents from GitHub datasets repo."""
    import requests
    url = 'https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/data/constituents.csv'
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
        from io import StringIO
        df = pd.read_csv(StringIO(response.text))
        df = df.rename(columns={'Name': 'Security'})
        df['Index'] = 'S&P 500'
        return df[['Symbol', 'Security', 'Index']]
    except Exception as e:
        logger.warning(f"Failed to fetch from GitHub: {e}")
        return None


def _fetch_from_wikipedia() -> Optional[pd.DataFrame]:
    """Fetch tickers from Wikipedia with proper headers."""
    import requests
    headers = {
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
    }
    try:
        # Fetch S&P 500 tickers
        sp500_resp = requests.get(
            'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
            headers=headers, timeout=10
        )
        sp500_resp.raise_for_status()
        sp500 = pd.read_html(sp500_resp.text)[0]
        sp500['Index'] = 'S&P 500'

        # Fetch NASDAQ-100 tickers
        nasdaq_resp = requests.get(
            'https://en.wikipedia.org/wiki/Nasdaq-100',
            headers=headers, timeout=10
        )
        nasdaq_resp.raise_for_status()
        nasdaq100 = pd.read_html(nasdaq_resp.text)[4]
        nasdaq100['Index'] = 'NASDAQ-100'
        nasdaq100 = nasdaq100.rename(columns={'Ticker': 'Symbol'})

        all_tickers = pd.concat([
            sp500[['Symbol', 'Security', 'Index']],
            nasdaq100[['Symbol', 'Company', 'Index']].rename(columns={'Company': 'Security'})
        ], ignore_index=True)

        return all_tickers
    except Exception as e:
        logger.warning(f"Failed to fetch from Wikipedia: {e}")
        return None


def get_all_tickers() -> pd.DataFrame:
    """
    Get list of S&P 500, NASDAQ-100 tickers and popular ETFs.

    Uses multiple sources with fallback:
    1. GitHub datasets repo (most reliable)
    2. Wikipedia (comprehensive but may block)
    3. Built-in default list (always works)

    Returns:
        DataFrame with Symbol, Security name, and Index columns.
    """
    logger.info("Fetching ticker list")

    # Try GitHub first (most reliable)
    tickers_df = _fetch_sp500_from_github()

    # Try Wikipedia as backup
    if tickers_df is None:
        logger.info("Trying Wikipedia as fallback")
        tickers_df = _fetch_from_wikipedia()

    # Use default list as final fallback
    if tickers_df is None:
        logger.info("Using default ticker list")
        tickers_df = _get_default_tickers()
    else:
        # Add popular ETFs to fetched data
        index_etfs = pd.DataFrame({
            'Symbol': ['SPY', 'QQQ', 'DIA', 'IWM', 'VTI', 'VOO'],
            'Security': [
                'SPDR S&P 500 ETF',
                'Invesco QQQ Trust',
                'SPDR Dow Jones Industrial Average ETF',
                'iShares Russell 2000 ETF',
                'Vanguard Total Stock Market ETF',
                'Vanguard S&P 500 ETF'
            ],
            'Index': ['Index ETF'] * 6
        })
        tickers_df = pd.concat([tickers_df, index_etfs], ignore_index=True)

    tickers_df = tickers_df.drop_duplicates(subset='Symbol')
    logger.info(f"Loaded {len(tickers_df)} tickers")
    return tickers_df


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