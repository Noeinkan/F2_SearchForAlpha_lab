"""Estimate ETF creations and redemptions from State Street's daily NAV files."""

from concurrent.futures import ThreadPoolExecutor
from datetime import date, timedelta
from io import BytesIO
from threading import Lock
from time import monotonic
from urllib.request import urlopen
from zipfile import BadZipFile

import pandas as pd
from openpyxl.utils.exceptions import InvalidFileException

SECTOR_ETFS = {
    "XLK": "Technology",
    "XLE": "Energy",
    "XLI": "Industrials",
    "XLU": "Utilities",
    "XSD": "Semiconductors",
    "XAR": "Aerospace & defense",
}
SOURCE_URL = "https://www.ssga.com/library-content/products/fund-data/etfs/us/navhist-us-en-{ticker}.xlsx"
_CACHE_SECONDS = 3600
_cache: dict[str, tuple[float, pd.DataFrame]] = {}
_cache_lock = Lock()


def read_nav_history(workbook: bytes) -> pd.DataFrame:
    """Normalize the issuer's observations into ascending trading-date order."""
    frame = pd.read_excel(BytesIO(workbook), sheet_name="navhist", header=3)
    history = frame[["Date", "NAV", "Shares Outstanding"]].rename(
        columns={"Date": "date", "NAV": "nav", "Shares Outstanding": "shares"}
    )
    history["date"] = pd.to_datetime(history["date"], format="mixed", errors="coerce")
    for field in ("nav", "shares"):
        history[field] = pd.to_numeric(history[field], errors="coerce")
    return (
        history.dropna()
        .loc[lambda rows: (rows["nav"] > 0) & (rows["shares"] > 0)]
        .drop_duplicates("date")
        .set_index("date")
        .sort_index()
    )


def load_nav_history(ticker: str) -> pd.DataFrame:
    """Cache recent successful downloads without caching empty responses."""
    with _cache_lock:
        cached = _cache.get(ticker)
        if cached and monotonic() - cached[0] < _CACHE_SECONDS:
            return cached[1]
    with urlopen(SOURCE_URL.format(ticker=ticker.lower()), timeout=12) as response:
        history = read_nav_history(response.read())
    if history.empty:
        raise ValueError(f"No NAV history for {ticker}")
    with _cache_lock:
        _cache[ticker] = monotonic(), history
    return history


def _load_ticker(ticker: str) -> tuple[str, pd.DataFrame]:
    try:
        return ticker, load_nav_history(ticker)
    except (OSError, ValueError, KeyError, BadZipFile, InvalidFileException):
        return ticker, pd.DataFrame()


def load_sector_histories() -> dict[str, pd.DataFrame]:
    with ThreadPoolExecutor(max_workers=len(SECTOR_ETFS)) as pool:
        return dict(pool.map(_load_ticker, SECTOR_ETFS))


def _daily_flows(history: pd.DataFrame) -> pd.DataFrame:
    previous_shares = history["shares"].shift()
    previous_nav = history["nav"].shift()
    share_ratio = history["shares"] / previous_shares
    nav_ratio = history["nav"] / previous_nav
    # Treat a matching, large inverse move as a split and exclude its change
    # in units from creations/redemptions. Allow for ordinary daily NAV moves.
    for factor in (0.1, 0.2, 0.25, 1 / 3, 0.5, 2, 3, 4, 5, 10):
        split = ((share_ratio / factor - 1).abs() < 0.08) & ((nav_ratio * factor - 1).abs() < 0.08)
        previous_shares.loc[split] *= factor
    return pd.DataFrame({
        "flow": (history["shares"] - previous_shares) * history["nav"],
        "prior_assets": history["shares"].shift() * previous_nav,
    })


def compare_weeks(histories: dict[str, pd.DataFrame], today: date) -> tuple[date | None, list[dict]]:
    """Compare two aligned weeks. A missing trading observation stays missing."""
    dates = pd.DatetimeIndex(sorted({
        day for history in histories.values() for day in history.index if day.date() <= today
    }))
    if dates.empty:
        return None, []

    # The issuer may publish Friday's observations after the weekend. A later
    # published session also confirms the preceding week closed on a holiday.
    latest_observation = dates[-1].date()
    friday = latest_observation - timedelta(days=(latest_observation.weekday() - 4) % 7)
    if friday >= today:
        friday -= timedelta(days=7)

    ends = [friday - timedelta(days=7), friday]
    sessions = [dates[(dates > pd.Timestamp(end - timedelta(days=7))) & (dates <= pd.Timestamp(end))]
                for end in ends]
    rows = []
    for ticker, label in SECTOR_ETFS.items():
        history = histories.get(ticker)
        values = [None, None]
        if history is not None and not history.empty:
            # Align before calculating differences so a multi-session share
            # change cannot be counted as a single day's flow across a gap.
            daily = _daily_flows(history.reindex(dates).tail(20))
            for index, trading_days in enumerate(sessions):
                period = daily.reindex(trading_days)
                if not period.empty and period.notna().all().all():
                    net = period["flow"].sum()
                    values[index] = float(net), float(net / period["prior_assets"].iloc[0])
        rows.append({"ticker": ticker, "label": label, "prior": values[0], "latest": values[1]})
    return friday, rows
