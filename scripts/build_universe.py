"""Regenerate ``config/tickers_universe.csv`` — the symbol-search universe.

The output CSV is **committed to the repo**. The dashboard reads it at startup
via :mod:`lib.ticker_universe` and never hits the network, so every bit of
source fragility (rate limits, Wikipedia layout churn, dead mirrors) is
confined to this script.

Run it by hand whenever the universe should be refreshed::

    python scripts/build_universe.py                 # rebuild in place
    python scripts/build_universe.py --out /tmp/u.csv  # dry-run elsewhere

Sources, merged in priority order (first writer of a field wins, except that
the curated file always overrides):

1. NASDAQ screener API — ~7000 US-listed stocks with sector/industry/market cap.
2. nasdaqtrader symbol directory — authoritative ETF flag and listing exchange.
3. The index-membership fetchers already in :mod:`lib.data_processing`, plus a
   direct read of the S&P 500 GICS columns those fetchers drop.
4. ``config/tickers_curated.csv`` — hand-maintained ETFs, indices, FX, futures.

If every network source fails the existing CSV is left untouched and the script
exits non-zero rather than writing a truncated universe.
"""

from __future__ import annotations

import argparse
import io
import logging
import sys
from pathlib import Path
from typing import Optional

import pandas as pd
import requests

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from lib.ticker_universe import UNIVERSE_COLUMNS  # noqa: E402

logger = logging.getLogger("build_universe")

DEFAULT_OUT = REPO_ROOT / "config" / "tickers_universe.csv"
CURATED_PATH = REPO_ROOT / "config" / "tickers_curated.csv"

# The screener and the symbol directory both reject the default requests
# User-Agent. Mirrors the header trick already used for Wikipedia in
# lib/data_processing.py.
_BROWSER_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/122.0 Safari/537.36"
    ),
    "Accept": "application/json, text/plain, */*",
}

_SCREENER_URL = "https://api.nasdaq.com/api/screener/stocks"
_ETF_SCREENER_URL = "https://api.nasdaq.com/api/screener/etf"
_SCREENER_EXCHANGES = ("NASDAQ", "NYSE", "AMEX")

_NASDAQ_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/nasdaqlisted.txt"
_OTHER_LISTED_URL = "https://www.nasdaqtrader.com/dynamic/SymDir/otherlisted.txt"

_SP500_GICS_URL = (
    "https://raw.githubusercontent.com/datasets/s-and-p-500-companies/main/"
    "data/constituents.csv"
)

# otherlisted.txt uses single-letter exchange codes.
_EXCHANGE_CODES = {
    "A": "NYSE AMERICAN",
    "N": "NYSE",
    "P": "NYSE ARCA",
    "Z": "BATS",
    "V": "IEX",
}


def _blank_frame() -> pd.DataFrame:
    return pd.DataFrame(columns=UNIVERSE_COLUMNS)


def _clean_symbol(value: object) -> str:
    """Normalise a raw symbol; return '' for anything unusable.

    Yahoo Finance uses ``-`` where the listing files use ``.`` or ``/`` for
    share classes (BRK.B -> BRK-B), and test/when-issued symbols carry a ``$``
    suffix we drop entirely.
    """
    text = str(value or "").strip().upper()
    if not text or text in {"NAN", "NONE"}:
        return ""
    if "$" in text:
        return ""
    # Preserve the suffixes Yahoo uses for non-equities (=X, =F, ^, -Y.NYB).
    if text.startswith("^") or text.endswith("=X") or text.endswith("=F"):
        return text
    if "." in text and not text.endswith(".NYB"):
        text = text.replace(".", "-")
    return text.replace("/", "-")


def _clean_text(value: object) -> str:
    text = str(value or "").strip()
    if text.lower() in {"nan", "none", "n/a", "--"}:
        return ""
    return text


def _parse_market_cap(value: object) -> str:
    """Screener market caps arrive as '3054218000000' or '' — keep them as ints."""
    text = _clean_text(value).replace(",", "").replace("$", "")
    if not text:
        return ""
    try:
        return str(int(float(text)))
    except ValueError:
        return ""


def fetch_screener() -> Optional[pd.DataFrame]:
    """Fetch US-listed stocks with sector/industry from the NASDAQ screener."""
    frames: list[pd.DataFrame] = []
    for exchange in _SCREENER_EXCHANGES:
        try:
            # `download=true` is the only variant that returns sector,
            # industry and country; `tableonly=true` omits them entirely.
            response = requests.get(
                _SCREENER_URL,
                params={"download": "true", "limit": "25000", "exchange": exchange},
                headers=_BROWSER_HEADERS,
                timeout=30,
            )
            response.raise_for_status()
            payload = (response.json() or {}).get("data") or {}
            rows = payload.get("rows") or (payload.get("table") or {}).get("rows")
        except Exception as exc:
            logger.warning("Screener fetch failed for %s: %s", exchange, exc)
            continue

        if not rows:
            logger.warning("Screener returned no rows for %s", exchange)
            continue

        frame = pd.DataFrame(rows)
        frame["Exchange"] = exchange
        frames.append(frame)
        logger.info("Screener: %s rows from %s", len(frame), exchange)

    if not frames:
        return None

    raw = pd.concat(frames, ignore_index=True)
    out = _blank_frame()
    out["Symbol"] = raw.get("symbol", "").map(_clean_symbol)
    out["Security"] = raw.get("name", "").map(_clean_text)
    out["AssetClass"] = "Stock"
    out["Exchange"] = raw["Exchange"]
    out["Sector"] = raw.get("sector", "").map(_clean_text)
    out["Industry"] = raw.get("industry", "").map(_clean_text)
    out["Index"] = ""
    out["Country"] = raw.get("country", "").map(_clean_text)
    out["MarketCap"] = raw.get("marketCap", "").map(_parse_market_cap)
    return out[out["Symbol"] != ""]


def fetch_etf_screener() -> Optional[pd.DataFrame]:
    """Fetch every US-listed ETF from the NASDAQ ETF screener.

    This is the primary ETF source. The nasdaqtrader symbol directory carries
    the same flag but sits behind a bot filter that blocks repeat runs, so it
    is only a supplement (see :func:`fetch_symbol_directory`).
    """
    try:
        response = requests.get(
            _ETF_SCREENER_URL,
            params={"download": "true", "limit": "10000"},
            headers=_BROWSER_HEADERS,
            timeout=60,
        )
        response.raise_for_status()
        payload = (response.json() or {}).get("data") or {}
        rows = payload.get("rows") or (payload.get("data") or {}).get("rows")
    except Exception as exc:
        logger.warning("ETF screener fetch failed: %s", exc)
        return None

    if not rows:
        logger.warning("ETF screener returned no rows")
        return None

    raw = pd.DataFrame(rows)
    out = _blank_frame()
    out["Symbol"] = raw.get("symbol", "").map(_clean_symbol)
    out["Security"] = raw.get("companyName", "").map(_clean_text)
    out["AssetClass"] = "ETF"
    # The ETF screener does not report a listing venue; leave it blank so the
    # curated rows (which do) win during the merge.
    out["Exchange"] = ""
    out["Sector"] = ""
    out["Industry"] = ""
    out["Index"] = ""
    out["Country"] = "United States"
    out["MarketCap"] = ""
    logger.info("ETF screener: %s rows", len(out))
    return out[out["Symbol"] != ""]


def _fetch_pipe_file(url: str, required: set[str]) -> Optional[pd.DataFrame]:
    """Fetch and parse one pipe-delimited symbol-directory file.

    nasdaqtrader intermittently answers with an HTML error page instead of the
    file. That still parses as a single-column CSV, so validate the expected
    columns are present rather than letting a KeyError kill the whole build.
    """
    try:
        response = requests.get(url, headers=_BROWSER_HEADERS, timeout=30)
        response.raise_for_status()
    except Exception as exc:
        logger.warning("Symbol directory fetch failed (%s): %s", url, exc)
        return None

    try:
        frame = pd.read_csv(io.StringIO(response.text), sep="|", dtype=str)
    except Exception as exc:
        logger.warning("Symbol directory parse failed (%s): %s", url, exc)
        return None

    missing = required - set(frame.columns)
    if missing:
        logger.warning(
            "Symbol directory %s missing columns %s — skipping (got %s)",
            url,
            sorted(missing),
            list(frame.columns)[:6],
        )
        return None

    # Both files end with a "File Creation Time" trailer row that has no
    # delimiters beyond the first — drop any row whose first field says so.
    first_col = frame.columns[0]
    return frame[~frame[first_col].astype(str).str.startswith("File Creation Time")]


def fetch_symbol_directory() -> Optional[pd.DataFrame]:
    """Fetch the nasdaqtrader directory — the authoritative ETF flag."""
    parts: list[pd.DataFrame] = []

    nasdaq = _fetch_pipe_file(_NASDAQ_LISTED_URL, {"Symbol", "Security Name"})
    if nasdaq is not None:
        out = _blank_frame()
        out["Symbol"] = nasdaq["Symbol"].map(_clean_symbol)
        out["Security"] = nasdaq["Security Name"].map(_clean_text)
        out["AssetClass"] = nasdaq.get("ETF", "N").map(
            lambda flag: "ETF" if str(flag).strip().upper() == "Y" else "Stock"
        )
        out["Exchange"] = "NASDAQ"
        parts.append(out)
        logger.info("Symbol directory: %s NASDAQ rows", len(out))

    other = _fetch_pipe_file(_OTHER_LISTED_URL, {"Security Name"})
    if other is not None and not {"ACT Symbol", "NASDAQ Symbol"}.isdisjoint(other.columns):
        out = _blank_frame()
        # ACT Symbol is the Yahoo-compatible identifier; NASDAQ Symbol is not.
        symbol_col = "ACT Symbol" if "ACT Symbol" in other.columns else "NASDAQ Symbol"
        out["Symbol"] = other[symbol_col].map(_clean_symbol)
        out["Security"] = other["Security Name"].map(_clean_text)
        out["AssetClass"] = other.get("ETF", "N").map(
            lambda flag: "ETF" if str(flag).strip().upper() == "Y" else "Stock"
        )
        out["Exchange"] = other.get("Exchange", "").map(
            lambda code: _EXCHANGE_CODES.get(str(code).strip().upper(), "NYSE")
        )
        parts.append(out)
        logger.info("Symbol directory: %s other-listed rows", len(out))

    if not parts:
        return None

    merged = pd.concat(parts, ignore_index=True).fillna("")
    merged["Index"] = ""
    merged["Sector"] = ""
    merged["Industry"] = ""
    merged["Country"] = "United States"
    merged["MarketCap"] = ""
    return merged[merged["Symbol"] != ""][UNIVERSE_COLUMNS]


def fetch_sp500_gics() -> Optional[pd.DataFrame]:
    """S&P 500 constituents *with* the GICS columns the app previously dropped."""
    try:
        response = requests.get(_SP500_GICS_URL, timeout=30)
        response.raise_for_status()
        raw = pd.read_csv(io.StringIO(response.text))
    except Exception as exc:
        logger.warning("S&P 500 GICS fetch failed: %s", exc)
        return None

    out = _blank_frame()
    out["Symbol"] = raw["Symbol"].map(_clean_symbol)
    out["Security"] = raw.get("Security", raw.get("Name", "")).map(_clean_text)
    out["AssetClass"] = "Stock"
    out["Exchange"] = ""
    out["Sector"] = raw.get("GICS Sector", "").map(_clean_text)
    out["Industry"] = raw.get("GICS Sub-Industry", "").map(_clean_text)
    out["Index"] = "S&P 500"
    out["Country"] = "United States"
    out["MarketCap"] = ""
    logger.info("S&P 500 GICS: %s rows", len(out))
    return out[out["Symbol"] != ""]


def fetch_index_membership() -> Optional[pd.DataFrame]:
    """NASDAQ-100 and Russell 2000 membership via the existing fetchers."""
    from lib.data_processing import (
        _fetch_nasdaq100_from_wikipedia,
        _fetch_russell2000_from_wikipedia,
    )

    parts: list[pd.DataFrame] = []
    for fetcher in (_fetch_nasdaq100_from_wikipedia, _fetch_russell2000_from_wikipedia):
        try:
            fetched = fetcher()
        except Exception as exc:
            logger.warning("%s failed: %s", fetcher.__name__, exc)
            continue
        if fetched is None or fetched.empty:
            continue

        out = _blank_frame()
        out["Symbol"] = fetched["Symbol"].map(_clean_symbol)
        out["Security"] = fetched["Security"].map(_clean_text)
        out["AssetClass"] = "Stock"
        out["Exchange"] = fetched["Exchange"].map(_clean_text)
        out["Sector"] = ""
        out["Industry"] = ""
        out["Index"] = fetched["Index"]
        out["Country"] = "United States"
        out["MarketCap"] = ""
        parts.append(out[out["Symbol"] != ""])
        logger.info("Index membership: %s rows from %s", len(out), fetcher.__name__)

    if not parts:
        return None
    return pd.concat(parts, ignore_index=True)


def load_curated(path: Path = CURATED_PATH) -> Optional[pd.DataFrame]:
    """Load the hand-maintained ETF / index / FX / futures rows."""
    if not path.exists():
        logger.warning("Curated file missing: %s", path)
        return None
    raw = pd.read_csv(path, dtype=str).fillna("")
    out = raw.reindex(columns=UNIVERSE_COLUMNS).fillna("")
    # Curated symbols are already Yahoo-shaped; only strip whitespace.
    out["Symbol"] = out["Symbol"].map(lambda v: str(v).strip().upper())
    logger.info("Curated: %s rows", len(out))
    return out[out["Symbol"] != ""]


def merge_sources(frames: list[pd.DataFrame]) -> pd.DataFrame:
    """Merge source frames by symbol.

    Earlier frames win for identity fields (``Security``, ``AssetClass``,
    ``Exchange``); every frame may contribute a value for a field an earlier
    one left blank. This is what lets the screener supply sector while the
    symbol directory supplies the ETF flag for the same row.
    """
    combined = pd.concat(frames, ignore_index=True).fillna("")
    for column in UNIVERSE_COLUMNS:
        combined[column] = combined[column].astype(str).str.strip()

    # Rank preserves source priority through the groupby.
    combined["_rank"] = range(len(combined))
    merged_rows: list[dict] = []
    for symbol, group in combined.groupby("Symbol", sort=False):
        group = group.sort_values("_rank")
        row = {"Symbol": symbol}
        for column in UNIVERSE_COLUMNS[1:]:
            values = [v for v in group[column].tolist() if v]
            row[column] = values[0] if values else ""
        # A symbol tagged ETF by the authoritative directory stays an ETF even
        # if the screener listed it as a stock first.
        classes = {v for v in group["AssetClass"].tolist() if v}
        for special in ("Future", "FX", "Index", "ETF"):
            if special in classes:
                row["AssetClass"] = special
                break
        row["AssetClass"] = row["AssetClass"] or "Stock"
        merged_rows.append(row)

    out = pd.DataFrame(merged_rows, columns=UNIVERSE_COLUMNS)
    return out.sort_values(["AssetClass", "Symbol"]).reset_index(drop=True)


def build(out_path: Path) -> int:
    frames: list[pd.DataFrame] = []

    # Priority order matters — see merge_sources().
    curated = load_curated()
    if curated is not None:
        frames.append(curated)

    screener = fetch_screener()
    if screener is not None:
        frames.append(screener)

    etfs = fetch_etf_screener()
    if etfs is not None:
        frames.append(etfs)

    gics = fetch_sp500_gics()
    if gics is not None:
        frames.append(gics)

    membership = fetch_index_membership()
    if membership is not None:
        frames.append(membership)

    directory = fetch_symbol_directory()
    if directory is not None:
        frames.append(directory)

    network_frames = [
        f for f in (screener, etfs, gics, membership, directory) if f is not None
    ]
    if not network_frames:
        logger.error(
            "Every network source failed — refusing to overwrite %s with the "
            "curated list alone.",
            out_path,
        )
        return 1

    # The stock screener is the backbone: without it the file would lose most
    # of its sector metadata, which is a silent quality regression rather than
    # an obvious failure. Refuse rather than write a degraded universe.
    if screener is None:
        logger.error(
            "Stock screener unavailable — refusing to overwrite %s and lose "
            "sector metadata. Re-run when the source is reachable.",
            out_path,
        )
        return 1

    universe = merge_sources(frames)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    universe.to_csv(out_path, index=False)

    print(f"\nWrote {len(universe)} symbols to {out_path}")
    print("\nBy asset class:")
    for asset_class, count in universe["AssetClass"].value_counts().items():
        print(f"  {asset_class:<8} {count:>6}")
    with_sector = int((universe["Sector"].astype(str).str.len() > 0).sum())
    print(f"\nWith sector metadata: {with_sector} ({with_sector / len(universe):.0%})")
    print(f"Distinct sectors:     {universe['Sector'].replace('', pd.NA).nunique()}")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT,
        help=f"Output CSV path (default: {DEFAULT_OUT})",
    )
    parser.add_argument("-v", "--verbose", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if args.verbose else logging.INFO,
        format="%(levelname)s %(name)s: %(message)s",
    )
    return build(args.out)


if __name__ == "__main__":
    raise SystemExit(main())
