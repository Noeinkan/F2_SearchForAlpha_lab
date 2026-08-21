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

# DataFetchError / TransientFetchError live in lib.fetch_errors so that vendor
# adapters can import them without a circular import. They are re-exported here
# because several modules still import DataFetchError from this path.
from lib.fetch_errors import (
    DataFetchError,
    TransientFetchError,
    classify_fetch_error,
    retry_with_backoff,
)

# Configure module logger
logger = logging.getLogger(__name__)

# Global cache for ticker universe with TTL
_TICKER_CACHE = None
_TICKER_CACHE_TIME = None
_TICKER_CACHE_TTL_HOURS = 24


# Corporate-action columns yfinance returns when actions=True. We fetch with
# actions=False, but a cached frame written by an older build may still carry
# them, so the names stay here as the single definition.
ACTION_COLUMNS = ("Dividends", "Stock Splits", "Capital Gains")


def _yahoo_history(
    symbol: str,
    start_date: str,
    end_date: str,
    yf_int: str,
) -> pd.DataFrame:
    """Fetch raw bars from Yahoo, retrying transient failures.

    ``auto_adjust=True`` is passed explicitly: prices are split- and
    dividend-adjusted. ``actions=False`` keeps the Dividends / Stock Splits
    columns out of the pipeline -- nothing downstream consumes them and
    resampling them to 4h silently corrupts them. See docs/data-adjustment.md.
    """

    def _attempt() -> pd.DataFrame:
        try:
            ticker = yf.Ticker(symbol)
            return ticker.history(
                start=start_date,
                end=end_date,
                interval=yf_int,
                auto_adjust=True,
                actions=False,
            )
        except Exception as exc:
            raise classify_fetch_error(
                exc, f"Failed to fetch data for {symbol}: {exc}"
            ) from exc

    return retry_with_backoff(_attempt, describe=f"Yahoo fetch for {symbol}")


def fetch_data(
    symbol: str,
    start_date: str,
    end_date: str,
    validate: bool = True,
    interval: str = "1d",
) -> pd.DataFrame:
    """
    Fetch historical price data from Yahoo Finance.

    Prices are split- and dividend-adjusted (``auto_adjust=True``) and the
    corporate-action columns are excluded -- see docs/data-adjustment.md.
    Transient vendor failures (429/5xx/timeout) are retried, then raised as
    ``TransientFetchError`` so callers can distinguish them from a bad ticker.

    Args:
        symbol: Ticker symbol to fetch.
        start_date: Start date in 'YYYY-MM-DD' format.
        end_date: End date in 'YYYY-MM-DD' format.
        validate: Whether to validate the returned data.
        interval: Bar size ``1d`` / ``1h`` / ``4h`` (4h resamples from 1h).

    Returns:
        DataFrame with adjusted OHLCV data and a timezone-naive DatetimeIndex.
        ``df.attrs['source']`` names the vendor that served it.

    Raises:
        DataFetchError: If data cannot be fetched or is invalid.
    """
    from lib.timeframes import (
        IntervalError,
        clamp_window,
        normalize_interval,
        resample_ohlcv,
        yf_interval,
    )

    if not symbol or not isinstance(symbol, str):
        raise DataFetchError(f"Invalid symbol: {symbol}")

    try:
        canon = normalize_interval(interval)
    except IntervalError as exc:
        raise DataFetchError(str(exc)) from exc

    try:
        start_date, end_date = clamp_window(start_date, end_date, canon)
    except IntervalError as exc:
        raise DataFetchError(str(exc)) from exc
    yf_int = yf_interval(canon)
    logger.info(
        "Fetching data for %s from %s to %s (interval=%s, yf=%s)",
        symbol,
        start_date,
        end_date,
        canon,
        yf_int,
    )

    try:
        # Yahoo is the only wired source. _yahoo_history is the vendor seam:
        # everything below it is vendor-agnostic, so a second source only has
        # to return an OHLCV frame with a DatetimeIndex. A fallback must also
        # set df.attrs["source"], which the dashboard cache reads to avoid
        # mixing two vendors' bars in one parquet file.
        source = "yahoo"
        df = _yahoo_history(symbol, start_date, end_date, yf_int)

        if df.empty:
            raise DataFetchError(
                f"No data available for {symbol} between {start_date} and {end_date} "
                f"(interval={canon})"
            )

        df.index = pd.to_datetime(df.index)
        if getattr(df.index, "tz", None) is not None:
            df.index = df.index.tz_localize(None)

        # actions=False should already have excluded these, but strip them
        # defensively: nothing downstream reads them, resampling them to 4h
        # corrupts them, and this keeps the fetch path consistent with the
        # disk-cache read path, which strips them from older parquet files.
        present_actions = [c for c in ACTION_COLUMNS if c in df.columns]
        if present_actions:
            df = df.drop(columns=present_actions)

        # Measure NaN density before dropping, so the quality warning in
        # _validate_price_data reflects what the vendor actually sent.
        nan_pct = 0.0
        if "Close" in df.columns and len(df):
            nan_pct = df["Close"].isna().sum() / len(df) * 100

        # Drop incomplete/placeholder rows with no usable Close.
        if "Close" in df.columns:
            df = df[df["Close"].notna()]
        if df.empty:
            raise DataFetchError(
                f"No data available for {symbol} between {start_date} and {end_date} "
                f"(interval={canon})"
            )

        if canon == "4h":
            df = resample_ohlcv(df, "4h")
            if df.empty:
                raise DataFetchError(
                    f"No 4h bars after resampling for {symbol} "
                    f"between {start_date} and {end_date}"
                )

        if validate:
            _validate_price_data(df, symbol, nan_pct=nan_pct)

        df.attrs["source"] = source
        logger.info(
            "Successfully fetched %s rows for %s (interval=%s, source=%s)",
            len(df),
            symbol,
            canon,
            source,
        )
        return df

    except DataFetchError:
        raise
    except Exception as e:
        logger.error(f"Error fetching data for {symbol}: {str(e)}")
        raise classify_fetch_error(
            e, f"Failed to fetch data for {symbol}: {str(e)}"
        ) from e


def _validate_price_data(
    df: pd.DataFrame,
    symbol: str,
    *,
    nan_pct: float | None = None,
) -> None:
    """
    Validate price data quality.

    Args:
        df: DataFrame with price data.
        symbol: Symbol name for error messages.
        nan_pct: Percentage of NaN Closes measured *before* they were dropped.
            Callers must pass this; measuring it here would always read 0
            because fetch_data drops NaN Closes first.

    Raises:
        DataFetchError: If data fails validation.
    """
    required_columns = ['Open', 'High', 'Low', 'Close', 'Volume']
    missing = [col for col in required_columns if col not in df.columns]
    if missing:
        raise DataFetchError(f"Missing required columns for {symbol}: {missing}")

    if nan_pct is None:
        nan_pct = df['Close'].isna().sum() / len(df) * 100 if len(df) else 0.0

    # Check for excessive NaN values
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


_WIKIPEDIA_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
}


def _find_wikipedia_table(
    html: str,
    required_columns: set[str],
) -> Optional[pd.DataFrame]:
    """Return the first Wikipedia HTML table containing all required columns."""
    from io import StringIO

    for table in pd.read_html(StringIO(html)):
        columns = {str(col).strip() for col in table.columns}
        if required_columns.issubset(columns):
            return table
    return None


def _fetch_from_wikipedia() -> Optional[pd.DataFrame]:
    """Fetch S&P 500 tickers from Wikipedia with retry logic."""
    import requests
    max_retries = 1
    backoff_factor = 1.0

    for attempt in range(max_retries):
        try:
            sp500_resp = requests.get(
                'https://en.wikipedia.org/wiki/List_of_S%26P_500_companies',
                headers=_WIKIPEDIA_HEADERS, timeout=5
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


def _fetch_nasdaq100_from_wikipedia() -> Optional[pd.DataFrame]:
    """Fetch NASDAQ-100 constituents from Wikipedia."""
    import requests

    try:
        response = requests.get(
            'https://en.wikipedia.org/wiki/Nasdaq-100',
            headers=_WIKIPEDIA_HEADERS,
            timeout=5,
        )
        response.raise_for_status()
        table = _find_wikipedia_table(response.text, {'Ticker', 'Company'})
        if table is None:
            logger.warning("NASDAQ-100 constituents table not found on Wikipedia")
            return None

        df = table.rename(columns={'Ticker': 'Symbol', 'Company': 'Security'})
        df['Index'] = 'NASDAQ-100'
        df['Exchange'] = 'NASDAQ'
        logger.info(f"Fetched {len(df)} tickers from Wikipedia (NASDAQ-100)")
        return df[['Symbol', 'Security', 'Index', 'Exchange']]
    except Exception as e:
        logger.warning(f"Failed to fetch NASDAQ-100 from Wikipedia: {e}")
        return None


def _fetch_russell2000_from_github() -> Optional[pd.DataFrame]:
    """Fetch Russell 2000 constituents from a community GitHub CSV."""
    import requests
    from io import StringIO

    url = (
        'https://raw.githubusercontent.com/ikoniaris/Russell2000/master/'
        'russell_2000_components.csv'
    )
    max_retries = 2
    backoff_factor = 1.0

    for attempt in range(max_retries):
        try:
            response = requests.get(url, timeout=5)
            response.raise_for_status()
            df = pd.read_csv(StringIO(response.text))
            df = df.rename(columns={'Ticker': 'Symbol', 'Name': 'Security'})
            df['Index'] = 'Russell 2000'
            df['Exchange'] = 'NYSE'
            logger.info(f"Fetched {len(df)} tickers from GitHub (Russell 2000)")
            return df[['Symbol', 'Security', 'Index', 'Exchange']]
        except requests.exceptions.Timeout:
            if attempt < max_retries - 1:
                wait_time = backoff_factor * (2 ** attempt)
                logger.warning(
                    f"Russell 2000 GitHub timeout, retrying in {wait_time}s..."
                )
                time.sleep(wait_time)
            else:
                logger.warning("Russell 2000 GitHub fetch failed after retries")
        except Exception as e:
            logger.warning(f"Failed to fetch Russell 2000 from GitHub: {e}")
            break
    return None


def _fetch_russell2000_from_wikipedia() -> Optional[pd.DataFrame]:
    """Fetch Russell 2000 constituents (GitHub primary, Wikipedia secondary)."""
    russell_df = _fetch_russell2000_from_github()
    if russell_df is not None:
        return russell_df

    import requests

    try:
        response = requests.get(
            'https://en.wikipedia.org/wiki/Russell_2000_Index',
            headers=_WIKIPEDIA_HEADERS,
            timeout=5,
        )
        response.raise_for_status()
        table = _find_wikipedia_table(response.text, {'Ticker', 'Company'})
        if table is None:
            table = _find_wikipedia_table(response.text, {'Symbol', 'Security'})
        if table is None:
            logger.warning("Russell 2000 constituents table not found on Wikipedia")
            return None

        if 'Ticker' in table.columns:
            df = table.rename(columns={'Ticker': 'Symbol', 'Company': 'Security'})
        else:
            df = table.copy()
        df['Index'] = 'Russell 2000'
        df['Exchange'] = 'Unknown'
        logger.info(f"Fetched {len(df)} tickers from Wikipedia (Russell 2000)")
        return df[['Symbol', 'Security', 'Index', 'Exchange']]
    except Exception as e:
        logger.warning(f"Failed to fetch Russell 2000 from Wikipedia: {e}")
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
    Get S&P 500, NASDAQ-100, and Russell 2000 tickers plus curated extras.

    Uses caching with TTL to minimize network calls. Fallback strategy:
    1. Return cached data if still valid (< 24 hours old)
    2. Try GitHub datasets repo for S&P 500 (most reliable)
    3. Try Wikipedia for S&P 500 backup
    4. Merge NASDAQ-100 (Wikipedia) and Russell 2000 (GitHub, Wikipedia backup)
    5. Fall back to local config file
    6. Use minimal bootstrap list as last resort

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

    extra_sources: List[pd.DataFrame] = []
    for fetcher in (_fetch_nasdaq100_from_wikipedia, _fetch_russell2000_from_wikipedia):
        fetched = fetcher()
        if fetched is not None:
            extra_sources.append(fetched)

    if tickers_df is None and extra_sources:
        tickers_df = pd.concat(extra_sources, ignore_index=True)
    elif extra_sources:
        tickers_df = pd.concat([tickers_df, *extra_sources], ignore_index=True)
    
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
    Calculate average trade duration in days (fractional for intraday holds).

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
            trade_durations = []
            for start, end in zip(trade_starts, trade_ends):
                if end <= start:
                    continue
                delta = pd.Timestamp(end) - pd.Timestamp(start)
                trade_durations.append(delta.total_seconds() / 86400.0)
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