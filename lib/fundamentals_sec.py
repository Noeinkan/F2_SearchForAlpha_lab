"""SEC EDGAR XBRL: the primary statement source for U.S. filers.

Split out of ``lib/fundamentals.py``, which keeps the Yahoo side, the
orchestration and the calculation layer. Everything here reads one file per
company -- the XBRL company-facts JSON -- and turns it into statement frames
shaped like cleaned Yahoo statements, so the calculation layer cannot tell the
sources apart.

Annual statements come from 10-K facts, keyed by the calendar year of the
period end. Quarterly statements (ROADMAP 7.6) come from the same file:

- Balance-sheet items are instants and are read at each quarter end, from
  10-Qs and, for the fourth quarter, the 10-K.
- Income-statement items are usually filed as three-month amounts and are read
  directly.
- Cash-flow items are filed only as year-to-date totals, and no filing carries
  a fourth quarter. Any quarter not filed directly is therefore derived as the
  difference of two year-to-date totals that share a start date and end one
  quarter apart: Q2 = 6M - 3M, Q3 = 9M - 6M, Q4 = 12M - 9M. A derived Q4 EPS
  is approximate, because the share count moves during the year.

Per-share figures are filed on the share count of their day, while Yahoo's
prices are split-adjusted. Given the split history, every EPS is divided by the
splits that took effect after it was filed, so Apple's 2017 EPS of 9.21 reads
2.30 after the 2020 four-for-one split, the basis the later filings and the
price use.

Quarters are keyed by the calendar quarter of the period end, less a week:
52/53-week filers close a quarter a few days either side of the calendar
quarter end (Apple's September quarter has ended on the 24th through the 30th),
and the shift keeps those in the quarter they belong to.
"""

from __future__ import annotations

import json
import logging
import time
import urllib.request
from collections import defaultdict
from collections.abc import Callable
from functools import partial
from itertools import pairwise
from typing import Any, Literal

import numpy as np
import pandas as pd

from lib import fundamentals_cache as cache

logger = logging.getLogger(__name__)

# EDGAR requires a descriptive User-Agent identifying the application and a
# contact address.  See https://www.sec.gov/os/accessing-edgar-data
_SEC_UA = "SearchForAlpha/research contact@searchforalpha.local"
_SEC_HEADERS = {"User-Agent": _SEC_UA, "Accept": "application/json"}

# In-process copy of the ticker -> CIK map, with the time it was loaded.
_CIK_CACHE: dict[str, str] = {}
_CIK_LOADED_AT: list[float] = []

# XBRL concept maps: (display_label, [concepts_in_priority_order], negate)
# Labels match exactly what _series_from_statement() looks up so the
# downstream calculation layer needs no changes.
_INCOME_CONCEPTS: list[tuple[str, list[str], bool]] = [
    ("Total Revenue", ["Revenues", "RevenueFromContractWithCustomerExcludingAssessedTax",
                       "SalesRevenueNet", "SalesRevenueGoodsNet",
                       "RevenueFromContractWithCustomerIncludingAssessedTax"], False),
    ("Operating Income", ["OperatingIncomeLoss"], False),
    ("Pretax Income", ["IncomeLossFromContinuingOperationsBeforeIncomeTaxesExtraordinaryItemsNoncontrollingInterest",
                       "IncomeLossFromContinuingOperationsBeforeIncomeTaxesMinorityInterestAndIncomeLossFromEquityMethodInvestments"], False),
    ("Tax Provision", ["IncomeTaxExpenseBenefit"], False),
    ("Net Income", ["NetIncomeLoss", "ProfitLoss",
                    "NetIncomeLossAvailableToCommonStockholdersBasic"], False),
    ("Diluted EPS", ["EarningsPerShareDiluted"], False),
    ("Basic EPS", ["EarningsPerShareBasic"], False),
]
_BALANCE_CONCEPTS: list[tuple[str, list[str], bool]] = [
    ("Stockholders Equity", ["StockholdersEquity",
                              "StockholdersEquityIncludingPortionAttributableToNoncontrollingInterest"], False),
    ("Current Debt", ["LongTermDebtCurrent", "ShortTermBorrowings", "DebtCurrent"], False),
    ("Long Term Debt", ["LongTermDebtNoncurrent", "LongTermDebt"], False),
    ("Total Debt", ["DebtAndCapitalLeaseObligations", "LongTermDebtAndCapitalLeaseObligations"], False),
    ("Cash And Cash Equivalents", ["CashAndCashEquivalentsAtCarryingValue",
                                    "CashCashEquivalentsAndShortTermInvestments"], False),
]
# Capital Expenditure: SEC reports positive payments; negate to match yfinance
# sign convention (negative = cash outflow) so FCF = OCF + CAPEX works correctly.
# ProductiveAssets is the tag many filers (e.g. NVDA) use instead of PPE.
_CASHFLOW_CONCEPTS: list[tuple[str, list[str], bool]] = [
    ("Operating Cash Flow", ["NetCashProvidedByUsedInOperatingActivities"], False),
    ("Capital Expenditure", [
        "PaymentsToAcquirePropertyPlantAndEquipment",
        "PaymentsToAcquireProductiveAssets",
        "PaymentsForCapitalImprovements",
    ], True),
]

# Every concept the statements read. The cache keeps only these, and an entry
# written for a different set is refetched rather than served short.
SEC_CONCEPTS: tuple[str, ...] = tuple(sorted({
    concept
    for concepts in (_INCOME_CONCEPTS, _BALANCE_CONCEPTS, _CASHFLOW_CONCEPTS)
    for _label, names, _negate in concepts
    for concept in names
}))

_UNITS = ("USD", "USD/shares", "shares")
_QUARTERLY_FORMS = frozenset({"10-Q", "10-Q/A", "10-K", "10-K/A"})
# A 13-week quarter is 91 days and a 14-week one 98.
_QUARTER_MIN_DAYS, _QUARTER_MAX_DAYS = 80, 100
_QUARTER_END_SHIFT = pd.Timedelta(days=7)

SecPeriod = Literal["annual", "quarterly"]
QuarterKey = tuple[int, int]
# (effective date, ratio) per stock split, oldest first: 4.0 for 4-for-1, 0.1 for 1-for-10.
Splits = tuple[tuple[pd.Timestamp, float], ...]


# ---------------------------------------------------------------------------
# Network, through the cache
# ---------------------------------------------------------------------------

def _download_ticker_map() -> dict[str, str] | None:
    url = "https://www.sec.gov/files/company_tickers.json"
    try:
        req = urllib.request.Request(url, headers=_SEC_HEADERS)
        with urllib.request.urlopen(req, timeout=15) as resp:
            data: dict = json.loads(resp.read())
    except Exception as exc:
        logger.warning("SEC ticker→CIK mapping unavailable: %s", exc)
        return None
    return {entry["ticker"].upper(): str(entry["cik_str"]).zfill(10) for entry in data.values()}


def _sec_cik(ticker: str, *, use_cache: bool = False) -> str | None:
    """Resolve a ticker symbol to a zero-padded 10-digit CIK string.

    The map is held in-process and, with ``use_cache``, on disk for the
    ``symbols`` tier; a listing newer than the cached map falls back to Yahoo
    until the map is refetched.
    """
    expired = bool(_CIK_LOADED_AT) and time.time() - _CIK_LOADED_AT[0] >= cache.SYMBOLS.ttl_seconds
    if not _CIK_CACHE or expired:
        read = cache.read_through(
            "sec-tickers", "company_tickers", cache.SYMBOLS, _download_ticker_map, enabled=use_cache,
        )
        if read.value:
            _CIK_CACHE.clear()
            _CIK_CACHE.update(read.value)
            _CIK_LOADED_AT[:] = [time.time()]
        elif not _CIK_CACHE:
            return None
    return _CIK_CACHE.get(ticker)


def _sec_company_facts(cik: str) -> dict[str, Any] | None:
    """Fetch the full XBRL company-facts JSON for the given CIK."""
    url = f"https://data.sec.gov/api/xbrl/companyfacts/CIK{cik}.json"
    try:
        req = urllib.request.Request(url, headers=_SEC_HEADERS)
        with urllib.request.urlopen(req, timeout=30) as resp:
            return json.loads(resp.read())
    except Exception as exc:
        logger.warning("SEC company facts unavailable for CIK %s: %s", cik, exc)
        return None


def _trim_facts(facts: dict[str, Any] | None) -> dict[str, Any] | None:
    """Keep the entity name and the concepts the statements read."""
    if not facts:
        return None
    usgaap = facts.get("facts", {}).get("us-gaap", {}) or {}
    return {
        "entityName": facts.get("entityName"),
        "concepts": list(SEC_CONCEPTS),
        "facts": {"us-gaap": {name: usgaap[name] for name in SEC_CONCEPTS if name in usgaap}},
    }


def _decode_facts(raw: Any) -> dict[str, Any] | None:
    if not isinstance(raw, dict) or raw.get("concepts") != list(SEC_CONCEPTS):
        return None
    return raw


def load_company_facts(
    ticker: str, *, force: bool = False, use_cache: bool = True,
) -> cache.CacheRead[dict[str, Any] | None]:
    """The trimmed company-facts file for ``ticker``, or a ``miss`` for a non-SEC symbol."""
    cik = _sec_cik(ticker, use_cache=use_cache)
    if not cik:
        return cache.CacheRead(None, "miss", None, cache.FILINGS)
    return cache.read_through(
        "sec-facts",
        f"CIK{cik}",
        cache.FILINGS,
        lambda: _trim_facts(_sec_company_facts(cik)),
        force=force,
        enabled=use_cache,
        decode=_decode_facts,
    )


# ---------------------------------------------------------------------------
# Statements
# ---------------------------------------------------------------------------

def sec_statements(
    facts: dict[str, Any] | None,
    ticker: str,
    *,
    period: SecPeriod = "annual",
    splits: Splits = (),
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Income, balance and cash-flow frames plus entity metadata; all empty when there is nothing.

    ``splits`` puts per-share figures on today's share basis; see
    ``_split_factor``.
    """
    usgaap = (facts or {}).get("facts", {}).get("us-gaap", {})
    if not usgaap:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}
    income = _build_sec_statement(_INCOME_CONCEPTS, usgaap, period=period, splits=splits)
    balance = _build_sec_statement(_BALANCE_CONCEPTS, usgaap, period=period, splits=splits)
    cashflow = _build_sec_statement(_CASHFLOW_CONCEPTS, usgaap, period=period, splits=splits)
    sec_info: dict[str, Any] = {
        "longName": (facts or {}).get("entityName") or ticker,
        "financialCurrency": "USD",
    }
    return income, balance, cashflow, sec_info


def _fetch_sec_fundamentals(
    ticker: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Fetch annual income, balance, and cashflow statements from SEC EDGAR XBRL, uncached.

    Returns empty DataFrames and an empty dict if the ticker cannot be resolved
    or EDGAR is unreachable, so the caller can transparently fall back.
    """
    cik = _sec_cik(ticker)
    if not cik:
        return pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}
    return sec_statements(_sec_company_facts(cik), ticker, period="annual")


def _build_sec_statement(
    concepts: list[tuple[str, list[str], bool]],
    usgaap: dict[str, Any],
    *,
    period: SecPeriod = "annual",
    splits: Splits = (),
) -> pd.DataFrame:
    """Build a statement DataFrame from SEC XBRL concept definitions.

    Returns a DataFrame with row labels matching the names that
    _series_from_statement() already looks up, and integer year columns
    (annual) or ``(year, quarter)`` columns (quarterly) -- the shape of a
    cleaned yfinance statement.  Period-end dates are stored on
    ``df.attrs['period_ends']`` so incomplete periods can be filtered before
    they become table columns.
    """
    parser = _sec_quarterly_series_and_ends if period == "quarterly" else _sec_annual_series_and_ends
    series_fn = partial(parser, splits=splits)
    rows: dict[str, dict[Any, float]] = {}
    period_ends: dict[Any, pd.Timestamp] = {}
    for label, concept_names, negate in concepts:
        series, ends = _best_sec_series(usgaap, concept_names, series_fn)
        if series:
            rows[label] = {key: -val if negate else val for key, val in series.items()}
            for key, end in ends.items():
                prev = period_ends.get(key)
                if prev is None or end > prev:
                    period_ends[key] = end

    if not rows:
        return pd.DataFrame()

    all_keys = sorted({key for s in rows.values() for key in s})
    df = pd.DataFrame(
        [[series.get(key, np.nan) for key in all_keys] for series in rows.values()],
        index=list(rows),
        # Flat, so _clean_statement does not mistake (year, quarter) for two levels.
        columns=pd.Index(all_keys, tupleize_cols=False),
        dtype="float64",
    )
    df.attrs["period_ends"] = {key: period_ends[key] for key in all_keys if key in period_ends}
    return df


def _best_sec_series(
    usgaap: dict[str, Any],
    concept_names: list[str],
    series_fn: Callable[[dict[str, Any], str], tuple[dict[Any, float], dict[Any, pd.Timestamp]]] | None = None,
) -> tuple[dict[Any, float], dict[Any, pd.Timestamp]]:
    """Pick the alternate XBRL concept with the best recent coverage.

    Filers rename tags over time (PPE vs ProductiveAssets).  The first
    non-empty concept is not enough — a single ancient year would mask a
    complete modern series.
    """
    series_fn = series_fn or _sec_annual_series_and_ends
    best: dict[Any, float] = {}
    best_ends: dict[Any, pd.Timestamp] = {}
    best_score: tuple[Any, int] | None = None  # (latest period, count)
    for concept in concept_names:
        series, ends = series_fn(usgaap, concept)
        if not series:
            continue
        score = (max(series), len(series))
        if best_score is None or score > best_score:
            best_score = score
            best = series
            best_ends = ends
    return best, best_ends


# ---------------------------------------------------------------------------
# Annual facts
# ---------------------------------------------------------------------------

def _sec_period_year(entry: dict[str, Any]) -> int | None:
    """Calendar year of the fact's period end (fallback: filing fiscal year).

    10-Ks embed up to three annual columns that share the same filing ``fy``.
    Keying by period end avoids comparative years overwriting the current year.
    """
    end = entry.get("end")
    if isinstance(end, str) and len(end) >= 4:
        try:
            year = int(end[:4])
            if 1900 <= year <= 2100:
                return year
        except ValueError:
            pass
    fy = entry.get("fy")
    return fy if isinstance(fy, int) else None


def _sec_is_annual_fact(entry: dict[str, Any]) -> bool:
    """True when the XBRL fact looks like a full-year 10-K amount."""
    if entry.get("form") not in ("10-K", "10-K/A"):
        return False
    fp = entry.get("fp")
    if fp is not None and fp != "FY":
        return False
    start, end = entry.get("start"), entry.get("end")
    if isinstance(start, str) and isinstance(end, str):
        try:
            days = (pd.Timestamp(end) - pd.Timestamp(start)).days
        except (TypeError, ValueError):
            return True
        # Reject YTD / stub periods that occasionally appear on 10-K forms.
        if days < 300:
            return False
    return True


def _sec_annual_series(usgaap: dict[str, Any], concept: str) -> dict[int, float]:
    """Return a period-year→value dict from SEC XBRL for one concept."""
    values, _ends = _sec_annual_series_and_ends(usgaap, concept)
    return values


def _split_factor(unit: str, filed: str, splits: Splits) -> float:
    """What to divide a filed value by to put it on today's share basis.

    A filing already reflects every split effective on or before its filing
    date (ASC 260 restates for a split between period end and issuance), so
    only later splits apply. Per-share amounts divide by the split ratio;
    anything not per share is left alone.
    """
    if unit != "USD/shares" or not splits or not filed:
        return 1.0
    try:
        filed_on = pd.Timestamp(filed)
    except (TypeError, ValueError):
        return 1.0
    factor = 1.0
    for effective, ratio in splits:
        if effective > filed_on:
            factor *= ratio
    return factor


def _sec_annual_series_and_ends(
    usgaap: dict[str, Any], concept: str, *, splits: Splits = (),
) -> tuple[dict[int, float], dict[int, pd.Timestamp]]:
    """Return values and period-end timestamps for one SEC XBRL concept.

    Only annual 10-K / 10-K/A facts are included.  Facts are keyed by the
    calendar year of ``end`` (not filing ``fy``), so comparative columns in a
    single 10-K do not clobber each other.  When the same period appears in
    multiple filings, the latest-filed value wins.
    """
    concept_data = usgaap.get(concept)
    if not concept_data:
        return {}, {}
    for unit in _UNITS:
        entries = concept_data.get("units", {}).get(unit)
        if not entries:
            continue
        # period_year → (filed_date, val, period_end)
        best: dict[int, tuple[str, float, pd.Timestamp]] = {}
        for entry in entries:
            if not _sec_is_annual_fact(entry):
                continue
            period_year = _sec_period_year(entry)
            if period_year is None:
                continue
            val = entry.get("val")
            if val is None:
                continue
            filed = entry.get("filed", "")
            fallback_end = pd.Timestamp(year=period_year, month=12, day=31)
            end_raw = entry.get("end")
            try:
                end_ts = pd.Timestamp(end_raw) if end_raw else fallback_end
            except (TypeError, ValueError):
                end_ts = fallback_end
            if period_year not in best or filed > best[period_year][0]:
                best[period_year] = (filed, float(val) / _split_factor(unit, filed, splits), end_ts)
        if best:
            values = {year: val for year, (_, val, _) in best.items()}
            ends = {year: end for year, (_, _, end) in best.items()}
            return values, ends
    return {}, {}


# ---------------------------------------------------------------------------
# Quarterly facts
# ---------------------------------------------------------------------------

def _sec_quarter_key(end: pd.Timestamp) -> QuarterKey:
    shifted = end - _QUARTER_END_SHIFT
    return int(shifted.year), int(shifted.quarter)


def _is_quarter_span(start: pd.Timestamp, end: pd.Timestamp) -> bool:
    return _QUARTER_MIN_DAYS <= (end - start).days <= _QUARTER_MAX_DAYS


def _latest_filed_facts(
    entries: list[dict[str, Any]], unit: str = "USD", splits: Splits = (),
) -> dict[tuple[pd.Timestamp | None, pd.Timestamp], float]:
    """10-K/10-Q facts keyed by ``(start, end)``; ``start`` is ``None`` for an instant.

    The same period recurs as a comparative in later filings; the latest-filed
    value wins, so a restatement replaces the original. Values are put on
    today's share basis here, before any quarter is derived: a year-to-date
    total filed before a split must not be subtracted from one filed after it.
    """
    best: dict[tuple[pd.Timestamp | None, pd.Timestamp], tuple[str, float]] = {}
    for entry in entries:
        if entry.get("form") not in _QUARTERLY_FORMS or entry.get("val") is None:
            continue
        try:
            end = pd.Timestamp(entry["end"])
            start = pd.Timestamp(entry["start"]) if entry.get("start") else None
        except (KeyError, TypeError, ValueError):
            continue
        filed = str(entry.get("filed", ""))
        key = (start, end)
        if key not in best or filed > best[key][0]:
            best[key] = (filed, float(entry["val"]) / _split_factor(unit, filed, splits))
    return {key: val for key, (_, val) in best.items()}


def _quarter_amounts(
    facts: dict[tuple[pd.Timestamp | None, pd.Timestamp], float],
) -> dict[pd.Timestamp, float]:
    """Three-month amounts by period end: filed directly, else derived from year-to-date totals."""
    spans = [(start, end, val) for (start, end), val in facts.items() if start is not None]
    quarters = {end: val for start, end, val in spans if _is_quarter_span(start, end)}
    by_start: dict[pd.Timestamp, list[tuple[pd.Timestamp, float]]] = defaultdict(list)
    for start, end, val in spans:
        by_start[start].append((end, val))
    for totals in by_start.values():
        totals.sort()
        for (prev_end, prev_val), (end, val) in pairwise(totals):
            if end not in quarters and _is_quarter_span(prev_end, end):
                quarters[end] = val - prev_val
    return quarters


def _sec_quarterly_series_and_ends(
    usgaap: dict[str, Any], concept: str, *, splits: Splits = (),
) -> tuple[dict[QuarterKey, float], dict[QuarterKey, pd.Timestamp]]:
    """Quarterly values and period ends for one concept -- flows as three-month amounts, stocks as instants."""
    concept_data = usgaap.get(concept)
    if not concept_data:
        return {}, {}
    for unit in _UNITS:
        entries = concept_data.get("units", {}).get(unit)
        if not entries:
            continue
        facts = _latest_filed_facts(entries, unit, splits)
        by_end = _quarter_amounts(facts) or {
            end: val for (start, end), val in facts.items() if start is None
        }
        if not by_end:
            continue
        values: dict[QuarterKey, float] = {}
        ends: dict[QuarterKey, pd.Timestamp] = {}
        # Ascending, so when a change of fiscal year end puts two period ends
        # in one quarter, the later one wins.
        for end in sorted(by_end):
            key = _sec_quarter_key(end)
            values[key] = by_end[end]
            ends[key] = end
        return values, ends
    return {}, {}
