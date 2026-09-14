"""
Dashboard Helper Functions
Utility functions for data processing and optimization.
"""

import logging
import itertools
import math
import time
from pathlib import Path
from typing import List, Tuple, Dict, Any, Optional

import pandas as pd

from lib.dash.state import dashboard_state
from lib.strategy import run_backtest
from lib.metrics import compute_metrics, ui_row
from lib.metrics.deflated import NORMAL_KURTOSIS, deflated_sharpe_ratio, trial_sharpe_std
from lib.signals.indicators import classify_signal_columns


logger = logging.getLogger(__name__)


def format_df_for_display(df: pd.DataFrame) -> pd.DataFrame:
    """
    Format DataFrame for display in data tables.

    Args:
        df: Input DataFrame

    Returns:
        Formatted DataFrame with rounded floats
    """
    df = df.copy()
    for col in df.columns:
        if df[col].dtype == 'float64':
            df[col] = df[col].round(2)
    return df


# When each in-memory OHLCV frame was stored, by fetch_data_with_cache key.
_memory_stored_at: dict[str, float] = {}


def _memory_copy_current(cache_key: str, path: Path, interval: str) -> bool:
    """Whether the in-memory frame may be served without looking at disk.

    Only while its disk entry is fresh and no newer than the copy: past the
    soft TTL the latest bar (today's, still forming) may have moved, and a
    background revalidation may already have written a newer file. A frame
    that never reached disk (a fallback vendor's) stays usable.
    """
    from lib.dash import ohlcv_disk_cache as ohlcv_cache

    freshness = ohlcv_cache.classify_freshness(path, interval)
    if freshness == "missing":
        return True
    if freshness != "fresh":
        return False
    try:
        return path.stat().st_mtime <= _memory_stored_at.get(cache_key, 0.0)
    except OSError:
        return True


def ohlcv_newer_on_disk(ticker: str, interval: str) -> bool:
    """Whether a background revalidation has written bars newer than those in memory.

    The disk path serves a stale file at once and refreshes it in a thread, so
    the frame a session loaded (the server's startup load, typically) can be a
    session behind the file by the time a page opens. False when nothing for
    ``ticker``/``interval`` was loaded through ``fetch_data_with_cache``.
    """
    from lib.dash import ohlcv_disk_cache as ohlcv_cache
    from lib.timeframes import normalize_interval

    canon = normalize_interval(interval)
    prefix = f"{ticker}_{canon}_"
    stamps = [stamp for key, stamp in _memory_stored_at.items() if key.startswith(prefix)]
    if not stamps:
        return False
    try:
        return ohlcv_cache.cache_path(ticker, canon).stat().st_mtime > max(stamps)
    except OSError:
        return False


def fetch_data_with_cache(
    ticker: str,
    start_date: str,
    end_date: str,
    interval: str = "1d",
    force: bool = False,
) -> pd.DataFrame:
    """
    Fetch data with caching support via shared ``fetch_data``.

    Lookup order: in-memory LRU → disk parquet (``state/ohlcv_cache``) → Yahoo.
    Disk keys are ``{ticker}_{interval}``. Soft-fresh files return immediately;
    soft-expired / hard-OK files return stale and schedule a background
    incremental Yahoo append (SWR). Past hard TTL blocks on an incremental
    (or full) fetch. ``force=True`` does a blocking full-window refetch.

    Args:
        ticker: Stock ticker symbol
        start_date: Start date string
        end_date: End date string
        interval: Bar size ``1d`` / ``1h`` / ``4h``
        force: Skip cache reads and overwrite entries (header refresh).

    Returns:
        DataFrame with OHLCV data

    Raises:
        TransientFetchError: If the vendor failed retryably (429/5xx/timeout)
            and no cached frame exists to serve instead.
        ValueError: If no data available for ticker
    """
    from lib.data_processing import DataFetchError, TransientFetchError, fetch_data
    from lib.dash import ohlcv_disk_cache as ohlcv_cache
    from lib.timeframes import normalize_interval

    canon = normalize_interval(interval)
    cache_key = f"{ticker}_{canon}_{start_date}_{end_date}"
    path = ohlcv_cache.cache_path(ticker, canon)
    cached = None if force else dashboard_state.get_cached_data(cache_key)

    if cached is not None and _memory_copy_current(cache_key, path, canon):
        logger.debug(f"Cache hit for {cache_key}")
        return cached

    def _yahoo(start: str, end: str) -> pd.DataFrame:
        logger.info(f"Fetching data for {ticker} (interval={canon})")
        frame = fetch_data(ticker, start, end, interval=canon)
        if isinstance(frame.columns, pd.MultiIndex):
            frame.columns = frame.columns.get_level_values(0)
        return frame

    def _persist(df: pd.DataFrame) -> None:
        """Write to the parquet cache -- but only bars from the primary vendor.

        The cache key is ``{ticker}_{interval}`` with no vendor dimension, so
        writing a fallback frame would interleave two vendors' bars in one
        file. Fallbacks are a transient-outage path, so skipping the write
        costs little.
        """
        source = df.attrs.get("source", "yahoo")
        if source != "yahoo":
            logger.info(
                "Not caching %s bars for %s (fallback source)", source, ticker
            )
            return
        ohlcv_cache.write_frame(ticker, canon, df)

    def _store(df: pd.DataFrame, version: float | None = None) -> pd.DataFrame:
        """Keep ``df`` in memory, stamped with the disk version it matches.

        A copy read from disk carries that file's mtime, not the time it was
        stored: a background revalidation may write a newer file before this
        call returns, and the stamp must not hide it.
        """
        windowed = ohlcv_cache.slice_window(df, start_date, end_date)
        if windowed is None or windowed.empty:
            raise ValueError(f"No data available for {ticker}")
        dashboard_state.set_cached_data(cache_key, windowed)
        _memory_stored_at[cache_key] = time.time() if version is None else version
        return windowed

    try:
        # Read before the frame, so a write in between makes the stamp older, never newer.
        disk_version = None if force else path.stat().st_mtime
    except OSError:
        disk_version = None
    disk_frame = None if force else ohlcv_cache.load_frame(ticker, canon)
    freshness = (
        "missing"
        if force
        else ohlcv_cache.classify_freshness(path, canon)
    )

    if not force and disk_frame is not None and freshness == "fresh":
        return _store(disk_frame, disk_version)

    if not force and disk_frame is not None and freshness == "stale":
        ohlcv_cache.schedule_revalidate(
            ticker,
            canon,
            end_date,
            lambda start, end: _yahoo(start, end),
        )
        return _store(disk_frame, disk_version)

    # force, missing, or expired → blocking fetch
    try:
        if force or disk_frame is None:
            df = _yahoo(start_date, end_date)
            _persist(df)
            return _store(df)

        # expired but file exists → incremental
        start = ohlcv_cache.incremental_start(disk_frame)
        try:
            tail = _yahoo(start, end_date)
            merged = ohlcv_cache.merge_ohlcv(disk_frame, tail)
            # merge_ohlcv builds a new frame, so carry the tail's provenance
            # across: a fallback-vendor tail must not enter the Yahoo cache.
            merged.attrs["source"] = tail.attrs.get("source", "yahoo")
            df = merged
        except DataFetchError:
            # Tail fetch failed — fall back to full window once.
            df = _yahoo(start_date, end_date)
        _persist(df)
        return _store(df)
    except (DataFetchError, ValueError) as exc:
        if disk_frame is not None and not disk_frame.empty:
            logger.warning(
                "Yahoo fetch failed for %s; serving stale disk cache: %s",
                ticker,
                exc,
            )
            return _store(disk_frame, disk_version)
        # Transient failures keep their type so the UI can offer a retry
        # instead of showing a dead end. Only genuine not-found is flattened.
        if isinstance(exc, TransientFetchError):
            raise
        if isinstance(exc, DataFetchError):
            raise ValueError(str(exc)) from exc
        raise


def extract_signals(df: pd.DataFrame) -> Tuple[List[str], List[str]]:
    """
    Extract buy and sell signal column names from DataFrame.

    Args:
        df: DataFrame with signal columns

    Returns:
        Tuple of (buy_signals, sell_signals) lists
    """
    classified = classify_signal_columns(df.columns.tolist())
    buy_signals = classified['buy']
    sell_signals = classified['sell']
    return buy_signals, sell_signals


def generate_signal_combinations(
    buy_signals: List[str],
    sell_signals: List[str],
    max_signals: int = 3
) -> List[Tuple[Tuple[str, ...], Tuple[str, ...]]]:
    """
    Generate combinations of buy and sell signals.

    Args:
        buy_signals: List of buy signal column names
        sell_signals: List of sell signal column names
        max_signals: Maximum number of signals per side

    Returns:
        List of (buy_combo, sell_combo) tuples
    """
    all_combinations = []
    for i in range(1, min(max_signals + 1, len(buy_signals) + 1)):
        for j in range(1, min(max_signals + 1, len(sell_signals) + 1)):
            buy_combos = list(itertools.combinations(buy_signals, i))
            sell_combos = list(itertools.combinations(sell_signals, j))
            all_combinations.extend(itertools.product(buy_combos, sell_combos))
    return all_combinations


def filter_signal_universe(
    all_buy: List[str],
    all_sell: List[str],
    selected_buy: Optional[List[str]] = None,
    selected_sell: Optional[List[str]] = None,
) -> Tuple[List[str], List[str]]:
    """Restrict buy/sell lists to a user-selected universe (empty = all)."""
    buy = list(all_buy)
    sell = list(all_sell)
    if selected_buy:
        allow = set(selected_buy)
        buy = [s for s in buy if s in allow]
    if selected_sell:
        allow = set(selected_sell)
        sell = [s for s in sell if s in allow]
    return buy, sell


def apply_optimizer_constraints(
    results_df: pd.DataFrame,
    max_dd_pct: Optional[float] = None,
    min_sharpe: Optional[float] = None,
) -> pd.DataFrame:
    """Drop combos that fail optional DD / Sharpe floors before ranking.

    ``Max_Drawdown_%`` uses the negative convention from ``evaluate_signal_combination``.
    ``max_dd_pct`` is a positive magnitude (e.g. 25 means discard if DD worse than -25%).
    """
    if results_df is None or results_df.empty:
        return results_df
    out = results_df
    if max_dd_pct is not None:
        try:
            floor = -abs(float(max_dd_pct))
            if 'Max_Drawdown_%' in out.columns:
                out = out[out['Max_Drawdown_%'] >= floor]
        except (TypeError, ValueError):
            pass
    if min_sharpe is not None:
        try:
            floor = float(min_sharpe)
            if 'Sharpe_Ratio' in out.columns:
                out = out[out['Sharpe_Ratio'] >= floor]
        except (TypeError, ValueError):
            pass
    return out


def evaluate_signal_combination(
    df: pd.DataFrame,
    initial_capital: float,
    buy_combo: Tuple[str, ...],
    sell_combo: Tuple[str, ...],
    interval: str = "1d",
    **backtest_kwargs: Any,
) -> Dict[str, Any]:
    """
    Evaluate a single combination of buy and sell signals.

    Args:
        df: DataFrame with price data and signals
        initial_capital: Starting capital
        buy_combo: Tuple of buy signal column names
        sell_combo: Tuple of sell signal column names
        interval: Bar interval of ``df``. Annualises Sharpe / Sortino / Calmar.
            A named parameter rather than part of ``backtest_kwargs`` because
            that dict is forwarded to ``run_backtest``, which would reject it.
        **backtest_kwargs: Optional ``run_backtest`` kwargs (costs, stops, mode).
            Omitted keys keep engine defaults (idealized / legacy optimizer path).

    Returns:
        Dict keyed by the registry's UI names — see :mod:`lib.metrics.names`.
    """
    try:
        result_df = run_backtest(
            df=df,
            initial_capital=initial_capital,
            buy_indicators=list(buy_combo),
            sell_indicators=list(sell_combo),
            **backtest_kwargs,
        )

        m = compute_metrics(
            result_df,
            initial_capital,
            interval=interval,
            context='evaluate_signal_combination',
        )

        # ui_row applies the registry's unit conventions once: percents for the
        # rate metrics, the conventional minus sign on drawdown. Buy-and-hold,
        # excess return and Jensen's alpha ride along inside it — the metrics
        # engine measures them against the benchmark series on the result
        # frame, so this path no longer recomputes any of the three by hand.
        return {
            'Buy_Signals': ', '.join(buy_combo),
            'Sell_Signals': ', '.join(sell_combo),
            'Final_Value': result_df['Portfolio_Value'].iloc[-1],
            **ui_row(m),
        }
    except Exception as e:
        logger.warning(f"Error testing combination {buy_combo}/{sell_combo}: {e}")
        return {
            'Buy_Signals': ', '.join(buy_combo),
            'Sell_Signals': ', '.join(sell_combo),
            'Error': str(e)
        }


def compute_robustness_scores(results_df: pd.DataFrame, min_trades: int) -> pd.DataFrame:
    """
    Add a robustness-weighted score and a low-sample flag to optimization results.

    The score rewards risk-adjusted performance (Sharpe, with Calmar as a mild
    bonus) and penalises combinations that traded too few times to be credible,
    via a confidence factor that ramps from 0 to 1 as trade count approaches
    ``min_trades``. Raw return is folded in only as a small tiebreaker.

    Best practice: a strong ratio on a handful of trades is noise, not edge.
    """
    df = results_df.copy()
    if df.empty:
        return df

    min_trades = max(1, int(min_trades or 1))
    trades = df.get('Trades', pd.Series(0, index=df.index)).fillna(0).clip(lower=0)
    confidence = (trades / min_trades).clip(upper=1.0)

    sharpe = df.get('Sharpe_Ratio', pd.Series(0.0, index=df.index)).fillna(0.0)
    calmar = df.get('Calmar', pd.Series(0.0, index=df.index)).fillna(0.0)
    total_return = df.get('Total_Return_%', pd.Series(0.0, index=df.index)).fillna(0.0)

    df['Low_Sample'] = trades < min_trades
    df['Robustness_Score'] = (
        (sharpe + 0.25 * calmar) * confidence + 0.001 * total_return
    )
    return df


def apply_deflated_sharpe(results_df: pd.DataFrame, *, num_trials: int | None = None) -> pd.DataFrame:
    """Re-deflate every leaderboard row against the size of the search.

    ``evaluate_signal_combination`` computes each row on its own and cannot see
    the sweep it belongs to, so its ``DSR_%`` is a single-trial figure. Only
    here, with the whole leaderboard in hand, are the two missing inputs known:
    how many configurations were tried, and how widely their Sharpe ratios
    scattered. Both come from Bailey & López de Prado's expected maximum — a
    wide search over a noisy space sets a high bar for the winner.

    Args:
        results_df: Leaderboard rows in UI units, as ``ui_row`` produces them.
        num_trials: Configurations tested. Defaults to the row count, which
            undercounts when some combinations errored out — pass the real
            total when it is known.

    Returns a copy with ``DSR_%`` and ``Trials`` rewritten. Rows missing the
    sample columns keep a 0.0 DSR: no sample, no confidence.
    """
    df = results_df.copy()
    if df.empty or 'Sharpe_Ratio' not in df.columns:
        return df

    sharpes = pd.to_numeric(df['Sharpe_Ratio'], errors='coerce').fillna(0.0)
    trials = max(1, int(num_trials if num_trials is not None else len(df)))
    sharpe_std = trial_sharpe_std(sharpes.to_numpy())

    def _num(row: pd.Series, key: str, fallback: float) -> float:
        """A finite number off a leaderboard row, or *fallback*.

        A row that predates these columns, or one an older persisted run wrote,
        carries NaN here — and NaN would sail through ``int()`` as an exception
        and through the formula as a silent zero.
        """
        try:
            value = float(row.get(key))
        except (TypeError, ValueError):
            return fallback
        return value if math.isfinite(value) else fallback

    def _row_dsr(row: pd.Series) -> float:
        return deflated_sharpe_ratio(
            _num(row, 'Sharpe_Ratio', 0.0),
            n_obs=int(_num(row, 'Bars', 0.0)),
            skew=_num(row, 'Skew', 0.0),
            kurtosis=_num(row, 'Kurtosis', NORMAL_KURTOSIS),
            num_trials=trials,
            sharpe_std=sharpe_std,
            periods_per_year=int(_num(row, 'Periods_Per_Year', 252.0)),
        )

    # DSR_% is in UI units — a percent, like every other 'fraction' column.
    df['DSR_%'] = df.apply(_row_dsr, axis=1).astype(float) * 100.0
    df['Trials'] = trials
    return df
