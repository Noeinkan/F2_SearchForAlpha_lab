"""Local archive of end-of-day option history, downloaded in bulk from ThetaData.

Layout, one folder per underlying under ``state/option-history/``::

    AAPL/2026-03.parquet     every contract quoted on every trading day of March
    AAPL/underlying.parquet  the unadjusted daily close of AAPL itself

One month per file because ThetaData recommends EOD requests of at most a month
(larger ones may be refused with HTTP 570, in which case the month is fetched in
two halves). A month that ended before the download is final and is never asked
for again unless ``refresh`` is set; the current month is refetched each run.

The dashboard's historical chain and replay read from here first and fall back
to a live ThetaData call only for what the archive does not hold.
"""

from __future__ import annotations

import logging
from calendar import monthrange
from dataclasses import dataclass, field
from datetime import date, timedelta
from pathlib import Path
from typing import Callable, Iterable
from urllib.parse import quote

import pandas as pd

from lib.fetch_errors import DataFetchError
from lib.options import theta_history

logger = logging.getLogger(__name__)

REPO_ROOT = Path(__file__).resolve().parents[2]
ARCHIVE_DIR = REPO_ROOT / "state" / "option-history"
COLUMNS = ["date", "observed_at", "expiry", "cp", "strike", "bid", "ask", "close", "volume"]
UNIVERSES = ("sp500", "nasdaq100")


def theta_symbol(symbol: str) -> str:
    """Yahoo writes share classes with a dash (BRK-B); OPRA and ThetaData use a dot (BRK.B)."""
    return str(symbol).strip().upper().replace("-", ".")


def _folder(symbol: str) -> Path:
    return ARCHIVE_DIR / quote(theta_symbol(symbol), safe="")


def month_path(symbol: str, month: str) -> Path:
    return _folder(symbol) / f"{month}.parquet"


def month_ranges(start: date, end: date) -> list[tuple[str, date, date]]:
    """``(YYYY-MM, first day, last day)`` for each calendar month touching ``[start, end]``."""
    out = []
    cursor = date(start.year, start.month, 1)
    while cursor <= end:
        last = date(cursor.year, cursor.month, monthrange(cursor.year, cursor.month)[1])
        out.append((cursor.strftime("%Y-%m"), max(cursor, start), min(last, end)))
        cursor = last + timedelta(days=1)
    return out


def universe(names: Iterable[str]) -> list[str]:
    """Symbols of the named index universes, deduplicated, in ThetaData spelling."""
    symbols: list[str] = []
    for name in names:
        name = name.strip().lower()
        if name == "sp500":
            table = pd.read_csv(REPO_ROOT / "config" / "tickers_universe.csv", usecols=["Symbol", "Index"])
            symbols += table.loc[table["Index"] == "S&P 500", "Symbol"].tolist()
        elif name == "nasdaq100":
            from lib.data_processing import _fetch_nasdaq100_from_wikipedia

            table = _fetch_nasdaq100_from_wikipedia()
            if table is None:
                raise DataFetchError("Could not read the Nasdaq-100 constituents from Wikipedia; try again or pass --tickers")
            symbols += table["Symbol"].tolist()
        else:
            raise ValueError(f"Unknown universe {name!r}; choose from {', '.join(UNIVERSES)}")
    seen: dict[str, None] = {}
    for symbol in symbols:
        seen.setdefault(theta_symbol(symbol), None)
    return list(seen)


def _frame(rows: list[dict]) -> pd.DataFrame:
    frame = pd.DataFrame(rows, columns=COLUMNS)
    return frame.astype({"strike": "float64", "bid": "float64", "ask": "float64",
                         "close": "float64", "volume": "float64"})


def _write(path: Path, frame: pd.DataFrame) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    frame.to_parquet(temporary, index=False)
    temporary.replace(path)


def _fetch_range(symbol: str, first: date, last: date, fetch: Callable[..., list[dict]]) -> list[dict]:
    try:
        return fetch(symbol, first, last, expiration="*")
    except theta_history.ThetaTooLarge:
        if first == last:
            raise
        middle = first + (last - first) // 2
        return (_fetch_range(symbol, first, middle, fetch)
                + _fetch_range(symbol, middle + timedelta(days=1), last, fetch))


@dataclass
class TickerResult:
    symbol: str
    months_fetched: int = 0
    months_skipped: int = 0
    rows: int = 0
    error: str | None = None


@dataclass
class DownloadSummary:
    start: str
    end: str
    tickers: list[TickerResult] = field(default_factory=list)
    stopped: str | None = None

    def as_dict(self) -> dict:
        return {"start": self.start, "end": self.end, "stopped": self.stopped,
                "tickers": [vars(t) for t in self.tickers],
                "rows": sum(t.rows for t in self.tickers),
                "failed": [t.symbol for t in self.tickers if t.error]}


def download_ticker(symbol: str, start: date, end: date, *, refresh: bool = False,
                    today: date | None = None,
                    fetch: Callable[..., list[dict]] | None = None,
                    fetch_stock: Callable[..., dict[str, float]] | None = None) -> TickerResult:
    """Fill the archive for one underlying; months already final are skipped."""
    fetch = fetch or theta_history.option_eod
    fetch_stock = fetch_stock or theta_history.stock_eod
    symbol = theta_symbol(symbol)
    today = today or date.today()
    result = TickerResult(symbol)
    for month, first, last in month_ranges(start, end):
        path = month_path(symbol, month)
        month_end = date(first.year, first.month, monthrange(first.year, first.month)[1])
        final = month_end < today - timedelta(days=1)
        if path.exists() and final and not refresh:
            result.months_skipped += 1
            continue
        rows = _fetch_range(symbol, first, last, fetch)
        _write(path, _frame([{k: r.get(k) for k in COLUMNS} for r in rows]))
        result.months_fetched += 1
        result.rows += len(rows)
    closes = fetch_stock(symbol, start, end)
    if closes:
        old = underlying(symbol)
        merged = {**old, **closes}
        _write(_folder(symbol) / "underlying.parquet",
               pd.DataFrame({"date": list(merged), "close": list(merged.values())}).sort_values("date"))
    return result


def download(symbols: list[str], start: date, end: date, *, refresh: bool = False,
             progress: Callable[[int, int, TickerResult], None] | None = None,
             **kwargs) -> DownloadSummary:
    """Download many underlyings, one at a time; a terminal outage stops the run, a bad symbol does not."""
    summary = DownloadSummary(start.isoformat(), end.isoformat())
    for position, symbol in enumerate(symbols, 1):
        try:
            result = download_ticker(symbol, start, end, refresh=refresh, **kwargs)
        except theta_history.ThetaUnavailable as exc:
            summary.stopped = str(exc)
            break
        except DataFetchError as exc:
            result = TickerResult(theta_symbol(symbol), error=str(exc))
            logger.warning("Option history for %s failed: %s", symbol, exc)
        summary.tickers.append(result)
        if progress:
            progress(position, len(symbols), result)
    return summary


# --- readers ---------------------------------------------------------------

def _read(path: Path) -> pd.DataFrame | None:
    try:
        return pd.read_parquet(path)
    except (OSError, ValueError):
        return None


def _records(frame: pd.DataFrame) -> list[dict]:
    rows = frame.astype(object).where(frame.notna(), None).to_dict("records")
    for row in rows:
        row["multiplier"] = theta_history.STANDARD_MULTIPLIER
    return rows


def chain_on(symbol: str, day: date) -> list[dict] | None:
    """Every archived contract quoted on ``day``, or None when that month is not archived."""
    frame = _read(month_path(symbol, day.strftime("%Y-%m")))
    if frame is None:
        return None
    return _records(frame[frame["date"] == day.isoformat()])


def contract_history(symbol: str, expiry: str, cp: str, strike: float,
                     start: date, end: date) -> list[dict] | None:
    """Daily rows of one contract, or None unless every month of the range is archived."""
    frames = []
    for month, _, _ in month_ranges(start, end):
        frame = _read(month_path(symbol, month))
        if frame is None:
            return None
        frames.append(frame[(frame["expiry"] == expiry) & (frame["cp"] == cp)
                            & ((frame["strike"] - strike).abs() < 1e-6)
                            & (frame["date"] >= start.isoformat()) & (frame["date"] <= end.isoformat())])
    return _records(pd.concat(frames)) if frames else []


def underlying(symbol: str) -> dict[str, float]:
    frame = _read(_folder(symbol) / "underlying.parquet")
    if frame is None:
        return {}
    return {str(d): float(c) for d, c in zip(frame["date"], frame["close"])}


def status() -> list[dict]:
    """One row per archived underlying: months held and the date range covered."""
    out = []
    if not ARCHIVE_DIR.exists():
        return out
    for folder in sorted(p for p in ARCHIVE_DIR.iterdir() if p.is_dir()):
        months = sorted(p.stem for p in folder.glob("????-??.parquet"))
        if months:
            out.append({"symbol": folder.name, "months": len(months), "first": months[0], "last": months[-1]})
    return out
