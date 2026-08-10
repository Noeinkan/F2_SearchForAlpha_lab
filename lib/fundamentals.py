"""
Fundamental analysis helpers for the dashboard.

Fetch strategy:
  1. SEC EDGAR XBRL (free, no API key, long annual history) — primary for U.S. stocks.
  2. yfinance — fallback for non-U.S. / tickers not found in EDGAR, and supplemental
     source for analyst estimates (forwardPE, earningsGrowth) not available in filings.
  3. yfinance quarterly statements — quarterly financials + charts only (no SEC
     quarterly XBRL in this release). Valuation and Big Five remain annual.

The calculation layer (build_fundamentals_result) stays pure so it can be tested
with fixed fixtures independent of any remote source.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import json
import logging
import math
from typing import Any, Literal

PeriodKey = int | tuple[int, int]
PeriodMode = Literal["annual", "quarterly"]
import urllib.error
import urllib.request

import numpy as np
import pandas as pd
import yfinance as yf

from lib.config_loader import get_config
from lib.dcf import DcfAssumptions, build_dcf, dcf_rows

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# SEC EDGAR configuration
# ---------------------------------------------------------------------------
# EDGAR requires a descriptive User-Agent identifying the application and a
# contact address.  See https://www.sec.gov/os/accessing-edgar-data
_SEC_UA = "SearchForAlpha/research contact@searchforalpha.local"
_SEC_HEADERS = {"User-Agent": _SEC_UA, "Accept": "application/json"}

# In-process cache: populated once per process from company_tickers.json
_CIK_CACHE: dict[str, str] = {}

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
_CASHFLOW_CONCEPTS: list[tuple[str, list[str], bool]] = [
    ("Operating Cash Flow", ["NetCashProvidedByUsedInOperatingActivities"], False),
    ("Capital Expenditure", ["PaymentsToAcquirePropertyPlantAndEquipment",
                              "PaymentsForCapitalImprovements"], True),
]

DEFAULT_MARR = 0.15
DEFAULT_MARGIN_OF_SAFETY = 0.50
DEFAULT_FUNDAMENTAL_YEARS = 11
DEFAULT_FUNDAMENTAL_QUARTERS = 40
# Rule #1: use the most conservative positive growth estimate; cap compounding rate.
MAX_ESTIMATED_GROWTH = 0.50


@dataclass(frozen=True)
class FundamentalResult:
    ticker: str
    company_name: str
    currency: str
    years: list[int] | list[str]
    period: PeriodMode
    financials: list[dict[str, Any]]
    big_five: list[dict[str, Any]]
    big_five_note: str
    valuation: list[dict[str, Any]]
    dcf: list[dict[str, Any]]
    dcf_sensitivity: list[dict[str, Any]]
    chart_series: dict[str, list[float | None]]
    quality_notes: list[str]
    as_of: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "currency": self.currency,
            "years": self.years,
            "period": self.period,
            "financials": self.financials,
            "big_five": self.big_five,
            "big_five_note": self.big_five_note,
            "valuation": self.valuation,
            "dcf": self.dcf,
            "dcf_sensitivity": self.dcf_sensitivity,
            "chart_series": self.chart_series,
            "quality_notes": self.quality_notes,
            "as_of": self.as_of,
        }


def _dcf_assumptions_from_config() -> DcfAssumptions:
    """Load DCF assumptions from strategy_config.yaml; unknown keys ignored."""
    raw = get_config().get("dcf", {}) or {}
    if not isinstance(raw, dict):
        return DcfAssumptions()
    allowed = {
        "risk_free",
        "equity_risk_premium",
        "terminal_growth",
        "beta",
        "beta_floor",
        "beta_cap",
        "stage1_years",
        "max_stage1_growth",
        "fade_to_terminal",
    }
    kwargs = {key: raw[key] for key in allowed if key in raw}
    return DcfAssumptions(**kwargs)


def fetch_fundamentals(ticker: str, years: int = DEFAULT_FUNDAMENTAL_YEARS) -> dict[str, Any]:
    """Fetch annual and quarterly fundamentals and return dashboard-ready data.

    Primary source: SEC EDGAR XBRL (free, long annual history for U.S. stocks).
    Fallback: yfinance statements (used when the ticker is not found in EDGAR).
    yfinance is always queried for supplemental analyst estimates (forwardPE,
    earningsGrowth, trailingEps) which are not available in SEC filings.
    Quarterly financials are sourced from yfinance only.
    Price history for period-end closes is always sourced from yfinance.
    """
    symbol = (ticker or "").strip().upper()
    if not symbol:
        raise ValueError("Ticker is required")

    # --- primary: SEC EDGAR ---------------------------------------------------
    sec_income, sec_balance, sec_cashflow, sec_info = _fetch_sec_fundamentals(symbol)
    sec_available = not sec_income.empty

    # --- supplemental: yfinance (info + prices) --------------------------------
    ticker_obj = yf.Ticker(symbol)
    yf_info = _safe_info(ticker_obj)

    if sec_available:
        income = sec_income
        balance = sec_balance
        cashflow = sec_cashflow
        # yfinance supplies analyst estimates; SEC supplies entity name / currency.
        # Merge order: yfinance base, SEC overrides metadata keys.
        info = {**yf_info, **sec_info}
        data_source = "SEC EDGAR"
        logger.info("Using SEC EDGAR data for %s", symbol)
    else:
        logger.info("SEC data unavailable for %s — falling back to yfinance statements", symbol)
        income = _safe_statement(ticker_obj, ("income_stmt", "financials"))
        balance = _safe_statement(ticker_obj, ("balance_sheet", "balancesheet"))
        cashflow = _safe_statement(ticker_obj, ("cashflow",))
        info = yf_info
        data_source = "yfinance (fallback)"

    q_income, q_balance, q_cashflow = _fetch_yfinance_quarterly(ticker_obj)

    first_year = _first_statement_year(income, balance, cashflow)
    history = _safe_history(ticker_obj, first_year)
    yearly_prices = _yearly_close_prices(history)
    quarterly_prices = _quarterly_close_prices(history)

    # Live quote snapshot read once from info so both the payload header and
    # the Stock Price row agree on the same source of truth.
    live_snapshot = _live_price_snapshot(info)
    dcf_assumptions = _dcf_assumptions_from_config()

    annual_result = build_fundamentals_result(
        ticker=symbol,
        info=info,
        income=income,
        balance=balance,
        cashflow=cashflow,
        period_prices=yearly_prices,
        periods=years,
        period="annual",
        live_price=live_snapshot["last_price"],
        dcf_assumptions=dcf_assumptions,
    ).to_dict()

    try:
        quarterly_result = build_fundamentals_result(
            ticker=symbol,
            info=info,
            income=q_income,
            balance=q_balance,
            cashflow=q_cashflow,
            period_prices=quarterly_prices,
            periods=DEFAULT_FUNDAMENTAL_QUARTERS,
            period="quarterly",
            live_price=live_snapshot["last_price"],
        ).to_dict()
    except ValueError as exc:
        logger.warning("Quarterly fundamentals unavailable for %s: %s", symbol, exc)
        quarterly_result = {
            "ticker": symbol,
            "company_name": annual_result["company_name"],
            "currency": annual_result["currency"],
            "years": [],
            "period": "quarterly",
            "financials": [],
            "big_five": [],
            "big_five_note": "",
            "valuation": [],
            "dcf": [],
            "dcf_sensitivity": [],
            "chart_series": {},
            "quality_notes": [str(exc)],
            "as_of": annual_result["as_of"],
        }

    payload: dict[str, Any] = {
        "ticker": annual_result["ticker"],
        "company_name": annual_result["company_name"],
        "currency": annual_result["currency"],
        "as_of": annual_result["as_of"],
        "annual": annual_result,
        "quarterly": quarterly_result,
        # Back-compat aliases for callers still reading top-level annual keys.
        "years": annual_result["years"],
        "period": "annual",
        "financials": annual_result["financials"],
        "big_five": annual_result["big_five"],
        "big_five_note": annual_result["big_five_note"],
        "valuation": annual_result["valuation"],
        "dcf": annual_result["dcf"],
        "dcf_sensitivity": annual_result["dcf_sensitivity"],
        "chart_series": annual_result["chart_series"],
        "quality_notes": [f"Data source: {data_source}"] + annual_result["quality_notes"],
    }
    payload.update(_live_price_snapshot(info, currency=payload.get("currency")))
    return payload


def _live_price_snapshot(info: dict[str, Any], *, currency: str | None = None) -> dict[str, Any]:
    """Extract last-price fields from a yfinance info dict.

    Returns None when unavailable so the UI can render a placeholder instead
    of fabricating a value.
    """
    last_price = _number(info.get("currentPrice"))
    if not _is_number(last_price):
        last_price = _number(info.get("regularMarketPrice"))
    previous_close = _number(info.get("previousClose"))
    if not _is_number(previous_close):
        previous_close = _number(info.get("regularMarketPreviousClose"))
    change = _number(info.get("regularMarketChange"))
    change_pct = _number(info.get("regularMarketChangePercent"))
    if not _is_number(change) and _is_number(last_price) and _is_number(previous_close):
        change = last_price - previous_close
    if not _is_number(change_pct) and _is_number(change) and _is_number(previous_close) and previous_close:
        change_pct = change / previous_close
    raw_state = info.get("marketState")
    market_state = str(raw_state).strip().upper() if raw_state else None
    price_currency = info.get("currency") or info.get("financialCurrency") or currency or "USD"
    return {
        "last_price": _json_number(last_price),
        "previous_close": _json_number(previous_close),
        "last_change": _json_number(change),
        "last_change_pct": _json_number(change_pct),
        "market_state": market_state or None,
        "price_currency": str(price_currency),
    }


def build_fundamentals_result(
    *,
    ticker: str,
    info: dict[str, Any] | None,
    income: pd.DataFrame | None,
    balance: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    period_prices: pd.Series | None = None,
    yearly_prices: pd.Series | None = None,
    periods: int | None = None,
    years: int = DEFAULT_FUNDAMENTAL_YEARS,
    period: PeriodMode = "annual",
    marr: float = DEFAULT_MARR,
    margin_of_safety: float = DEFAULT_MARGIN_OF_SAFETY,
    live_price: float | None = None,
    dcf_assumptions: DcfAssumptions | None = None,
) -> FundamentalResult:
    """Build the fundamentals payload from normalized statement inputs."""
    if period_prices is None:
        period_prices = yearly_prices
    window = periods if periods is not None else years

    info = info or {}
    income = _clean_statement(income, period=period)
    balance = _clean_statement(balance, period=period)
    cashflow = _clean_statement(cashflow, period=period)
    period_prices = _clean_period_prices(period_prices, period=period)

    statement_periods = _collect_periods(income, balance, cashflow, period=period)
    all_periods = (statement_periods or _collect_periods(period_prices, period=period))[-window:]
    if not all_periods:
        label = "quarterly" if period == "quarterly" else "annual"
        raise ValueError(f"No {label} fundamentals available for {ticker}")

    period_labels = [_period_column_key(value) for value in all_periods]
    financial_map = _build_financial_map(income, balance, cashflow, period_prices, all_periods)
    notes_extra: list[str] = []
    if period == "quarterly":
        big_five: list[dict[str, Any]] = []
        big_five_note = ""
        valuation: list[dict[str, Any]] = []
        dcf: list[dict[str, Any]] = []
        dcf_sensitivity: list[dict[str, Any]] = []
    else:
        big_five = _build_big_five(financial_map, all_periods)
        valuation = _build_valuation(info, financial_map, all_periods, marr, margin_of_safety)
        big_five_note = "NOTE: Big Five should be >= 10% per year over the last 10 years."
        try:
            dcf_result = build_dcf(info, financial_map, dcf_assumptions or DcfAssumptions())
            dcf, dcf_sensitivity = dcf_rows(dcf_result), dcf_result.sensitivity
            notes_extra = list(dcf_result.notes)
        except ValueError as exc:
            dcf, dcf_sensitivity, notes_extra = [], [], [f"DCF unavailable: {exc}"]
    notes = _quality_notes(financial_map, all_periods, period=period) + notes_extra
    financials = _attach_live_price(
        _rows_from_map(financial_map, all_periods), live_price
    )

    return FundamentalResult(
        ticker=ticker,
        company_name=str(info.get("longName") or info.get("shortName") or ticker),
        currency=str(info.get("financialCurrency") or info.get("currency") or "USD"),
        years=period_labels,
        period=period,
        financials=financials,
        big_five=big_five,
        big_five_note=big_five_note,
        valuation=valuation,
        dcf=dcf,
        dcf_sensitivity=dcf_sensitivity,
        chart_series=_chart_series(financial_map, all_periods),
        quality_notes=notes,
        as_of=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


# ---------------------------------------------------------------------------
# SEC EDGAR fetch helpers
# ---------------------------------------------------------------------------

def _sec_cik(ticker: str) -> str | None:
    """Resolve a ticker symbol to a zero-padded 10-digit CIK string.

    On the first call the full ticker→CIK mapping is fetched from EDGAR and
    cached in-process.  Subsequent calls are local dictionary lookups.
    """
    if not _CIK_CACHE:
        url = "https://www.sec.gov/files/company_tickers.json"
        try:
            req = urllib.request.Request(url, headers=_SEC_HEADERS)
            with urllib.request.urlopen(req, timeout=15) as resp:
                data: dict = json.loads(resp.read())
            _CIK_CACHE.update(
                {entry["ticker"].upper(): str(entry["cik_str"]).zfill(10)
                 for entry in data.values()}
            )
        except Exception as exc:
            logger.warning("SEC ticker\u2192CIK mapping unavailable: %s", exc)
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


def _sec_annual_series(usgaap: dict[str, Any], concept: str) -> dict[int, float]:
    """Return a fiscal-year\u2192value dict from SEC XBRL for one concept.

    Only 10-K and 10-K/A filings are included.  When a fiscal year has
    multiple entries (e.g. original + amendment) the latest-filed value wins.
    """
    concept_data = usgaap.get(concept)
    if not concept_data:
        return {}
    for unit in ("USD", "USD/shares", "shares"):
        entries = concept_data.get("units", {}).get(unit)
        if not entries:
            continue
        best: dict[int, tuple[str, float]] = {}  # fy \u2192 (filed_date, val)
        for entry in entries:
            if entry.get("form") not in ("10-K", "10-K/A"):
                continue
            fy = entry.get("fy")
            if not isinstance(fy, int):
                continue
            val = entry.get("val")
            if val is None:
                continue
            filed = entry.get("filed", "")
            if fy not in best or filed > best[fy][0]:
                best[fy] = (filed, float(val))
        if best:
            return {fy: val for fy, (_, val) in best.items()}
    return {}


def _build_sec_statement(
    concepts: list[tuple[str, list[str], bool]],
    usgaap: dict[str, Any],
) -> pd.DataFrame:
    """Build a statement DataFrame from SEC XBRL concept definitions.

    Returns a DataFrame with row labels matching the names that
    _series_from_statement() already looks up and integer year columns,
    identical in shape to a cleaned yfinance statement.
    """
    rows: dict[str, dict[int, float]] = {}
    for label, concept_names, negate in concepts:
        series: dict[int, float] = {}
        for concept in concept_names:
            series = _sec_annual_series(usgaap, concept)
            if series:
                break
        if series:
            rows[label] = {fy: -val if negate else val for fy, val in series.items()}

    if not rows:
        return pd.DataFrame()

    all_years = sorted({fy for s in rows.values() for fy in s})
    df = pd.DataFrame(
        {label: [series.get(yr, np.nan) for yr in all_years]
         for label, series in rows.items()},
        index=all_years,
    ).T
    df.columns = pd.Index(all_years)
    return df


def _fetch_sec_fundamentals(
    ticker: str,
) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]]:
    """Fetch annual income, balance, and cashflow statements from SEC EDGAR XBRL.

    Returns empty DataFrames and an empty dict if the ticker cannot be resolved
    or EDGAR is unreachable, so the caller can transparently fall back.
    """
    _empty: tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame, dict[str, Any]] = (
        pd.DataFrame(), pd.DataFrame(), pd.DataFrame(), {}
    )

    cik = _sec_cik(ticker)
    if not cik:
        return _empty

    facts = _sec_company_facts(cik)
    if not facts:
        return _empty

    usgaap = facts.get("facts", {}).get("us-gaap", {})
    if not usgaap:
        return _empty

    income = _build_sec_statement(_INCOME_CONCEPTS, usgaap)
    balance = _build_sec_statement(_BALANCE_CONCEPTS, usgaap)
    cashflow = _build_sec_statement(_CASHFLOW_CONCEPTS, usgaap)

    sec_info: dict[str, Any] = {
        "longName": facts.get("entityName", ticker),
        "financialCurrency": "USD",
    }
    return income, balance, cashflow, sec_info


def _fetch_yfinance_quarterly(ticker_obj: Any) -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    """Fetch quarterly statements from yfinance (no SEC quarterly XBRL in this release)."""
    income = _safe_statement(
        ticker_obj,
        ("quarterly_income_stmt", "quarterly_financials", "quarterly_incomestmt"),
    )
    balance = _safe_statement(
        ticker_obj,
        ("quarterly_balance_sheet", "quarterly_balancesheet"),
    )
    cashflow = _safe_statement(
        ticker_obj,
        ("quarterly_cashflow", "quarterly_cash_flow"),
    )
    return income, balance, cashflow


def _period_column_key(period: PeriodKey) -> int | str:
    if isinstance(period, tuple):
        return f"{period[0]}-Q{period[1]}"
    return int(period)


def _period_sort_key(period: PeriodKey) -> tuple[int, int]:
    if isinstance(period, tuple):
        return int(period[0]), int(period[1])
    return int(period), 0


# ---------------------------------------------------------------------------
# yfinance fetch helpers
# ---------------------------------------------------------------------------

def _safe_info(ticker_obj: Any) -> dict[str, Any]:
    try:
        return dict(ticker_obj.info or {})
    except Exception as exc:
        logger.warning("Could not fetch ticker info: %s", exc)
        return {}


def _safe_statement(ticker_obj: Any, attrs: tuple[str, ...]) -> pd.DataFrame:
    for attr in attrs:
        try:
            statement = getattr(ticker_obj, attr)
        except Exception as exc:
            logger.debug("Could not read %s: %s", attr, exc)
            continue
        if isinstance(statement, pd.DataFrame) and not statement.empty:
            return statement
    return pd.DataFrame()


def _safe_history(ticker_obj: Any, first_year: int | None) -> pd.DataFrame:
    try:
        if first_year:
            return ticker_obj.history(start=f"{first_year}-01-01", auto_adjust=False)
        return ticker_obj.history(period="15y", auto_adjust=False)
    except Exception as exc:
        logger.warning("Could not fetch price history: %s", exc)
        return pd.DataFrame()


def _first_statement_year(*statements: pd.DataFrame) -> int | None:
    years = []
    for statement in statements:
        cleaned = _clean_statement(statement, period="annual")
        years.extend(cleaned.columns.tolist())
    return min(years) if years else None


def _clean_statement(statement: pd.DataFrame | None, *, period: PeriodMode = "annual") -> pd.DataFrame:
    if statement is None or statement.empty:
        return pd.DataFrame()

    df = statement.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    converted_columns: dict[Any, PeriodKey] = {}
    for column in df.columns:
        if isinstance(column, tuple) and len(column) == 2:
            converted_columns[column] = (int(column[0]), int(column[1]))
            continue
        if isinstance(column, (int, np.integer)):
            if period == "quarterly":
                continue
            converted_columns[column] = int(column)
            continue
        try:
            timestamp = pd.Timestamp(column)
            if period == "quarterly":
                converted_columns[column] = (timestamp.year, timestamp.quarter)
            else:
                converted_columns[column] = timestamp.year
        except Exception:
            try:
                if period == "quarterly":
                    continue
                converted_columns[column] = int(column)
            except Exception:
                continue

    df = df.rename(columns=converted_columns)
    if period == "quarterly":
        df = df[[column for column in df.columns if isinstance(column, tuple)]]
    else:
        df = df[[column for column in df.columns if isinstance(column, (int, np.integer))]]
    if df.empty:
        return pd.DataFrame()
    df = df.T.groupby(level=0).first().T
    ordered = sorted(df.columns, key=_period_sort_key)
    return df.reindex(ordered, axis=1)


def _yearly_close_prices(history: pd.DataFrame) -> pd.Series:
    if history is None or history.empty or "Close" not in history:
        return pd.Series(dtype="float64")
    prices = history["Close"].dropna().copy()
    if prices.empty:
        return pd.Series(dtype="float64")
    prices.index = pd.to_datetime(prices.index)
    yearly = prices.groupby(prices.index.year).last()
    yearly.index = yearly.index.astype(int)
    return yearly.astype(float)


def _quarterly_close_prices(history: pd.DataFrame) -> pd.Series:
    if history is None or history.empty or "Close" not in history:
        return pd.Series(dtype="float64")
    prices = history["Close"].dropna().copy()
    if prices.empty:
        return pd.Series(dtype="float64")
    prices.index = pd.to_datetime(prices.index)
    quarterly = prices.groupby([prices.index.year, prices.index.quarter]).last()
    quarterly.index = pd.Index(
        [(int(year), int(quarter)) for year, quarter in quarterly.index],
        dtype="object",
    )
    return quarterly.astype(float)


def _clean_period_prices(period_prices: pd.Series | None, *, period: PeriodMode = "annual") -> pd.Series:
    if period_prices is None or period_prices.empty:
        return pd.Series(dtype="float64")
    prices = period_prices.copy().dropna()
    if period == "quarterly":
        normalized: list[PeriodKey] = []
        for index in prices.index:
            if isinstance(index, tuple) and len(index) == 2:
                normalized.append((int(index[0]), int(index[1])))
            else:
                timestamp = pd.Timestamp(index)
                normalized.append((timestamp.year, timestamp.quarter))
        prices.index = pd.Index(normalized, dtype="object")
        if prices.index.duplicated().any():
            prices = prices.groupby(prices.index).last()
    else:
        prices.index = [
            int(pd.Timestamp(index).year) if not isinstance(index, (int, np.integer)) else int(index)
            for index in prices.index
        ]
        prices = prices.groupby(level=0).last()
    ordered = sorted(prices.index, key=_period_sort_key)
    return prices.reindex(ordered).astype(float)


def _clean_yearly_prices(yearly_prices: pd.Series | None) -> pd.Series:
    return _clean_period_prices(yearly_prices, period="annual")


def _collect_periods(*sources: Any, period: PeriodMode = "annual") -> list[PeriodKey]:
    collected: set[PeriodKey] = set()
    for source in sources:
        if isinstance(source, pd.DataFrame) and not source.empty:
            for column in source.columns:
                if period == "quarterly" and isinstance(column, tuple):
                    collected.add((int(column[0]), int(column[1])))
                elif period == "annual" and isinstance(column, (int, np.integer)):
                    collected.add(int(column))
        elif isinstance(source, pd.Series) and not source.empty:
            for index in source.index:
                if period == "quarterly" and isinstance(index, tuple):
                    collected.add((int(index[0]), int(index[1])))
                elif period == "annual" and isinstance(index, (int, np.integer)):
                    collected.add(int(index))
    return sorted(collected, key=_period_sort_key)


def _collect_years(*sources: Any) -> list[int]:
    return [int(value) for value in _collect_periods(*sources, period="annual")]


def _build_financial_map(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cashflow: pd.DataFrame,
    period_prices: pd.Series,
    periods: list[PeriodKey],
) -> dict[str, dict[str, Any]]:
    revenue = _series_from_statement(income, ("Total Revenue", "Operating Revenue"), periods)
    equity = _series_from_statement(balance, ("Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"), periods)
    eps = _series_from_statement(income, ("Diluted EPS", "Basic EPS"), periods)
    operating_income = _series_from_statement(income, ("Operating Income", "EBIT"), periods)
    pretax_income = _series_from_statement(income, ("Pretax Income", "Income Before Tax"), periods)
    tax_provision = _series_from_statement(income, ("Tax Provision", "Income Tax Expense"), periods)
    net_income = _series_from_statement(income, ("Net Income", "Net Income Common Stockholders"), periods)
    current_debt = _series_from_statement(balance, ("Current Debt", "Current Debt And Capital Lease Obligation", "Short Long Term Debt"), periods)
    long_debt = _series_from_statement(balance, ("Long Term Debt", "Long Term Debt And Capital Lease Obligation"), periods)
    total_debt = _series_from_statement(balance, ("Total Debt",), periods)
    if total_debt.isna().all():
        total_debt = current_debt.fillna(0) + long_debt.fillna(0)
    cash = _series_from_statement(balance, ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"), periods).fillna(0)
    operating_cashflow = _series_from_statement(cashflow, ("Operating Cash Flow", "Total Cash From Operating Activities"), periods)
    capex = _series_from_statement(cashflow, ("Capital Expenditure", "Capital Expenditures"), periods)
    free_cash_flow = _series_from_statement(cashflow, ("Free Cash Flow",), periods)
    if free_cash_flow.isna().all():
        free_cash_flow = operating_cashflow + capex.fillna(0)

    tax_rate = (tax_provision / pretax_income).replace([np.inf, -np.inf], np.nan).clip(lower=0, upper=0.50)
    tax_rate = tax_rate.fillna(0.21)
    nopat = operating_income * (1 - tax_rate)
    invested_capital = equity + total_debt.fillna(0) - cash
    avg_invested_capital = (invested_capital + invested_capital.shift(1)) / 2
    avg_invested_capital = avg_invested_capital.fillna(invested_capital)
    roic = nopat / avg_invested_capital
    debt_ratio = long_debt / free_cash_flow.replace(0, np.nan)
    stock_price = pd.Series({period: period_prices.get(period, np.nan) for period in periods}, dtype="float64")
    pe_ratio = stock_price / eps.replace(0, np.nan)

    return {
        "sales": _metric("Sales (Rev)", "$mil", revenue, scale=1_000_000),
        "equity": _metric("Equity", "$mil", equity, scale=1_000_000),
        "eps": _metric("EPS", "$", eps),
        "fcf": _metric("FCF", "$mil", free_cash_flow, scale=1_000_000),
        "nopat": _metric("NOPAT", "$mil", nopat, scale=1_000_000),
        "net_income": _metric("Net Income (Profit)", "$mil", net_income, scale=1_000_000),
        "avg_invested_capital": _metric("Avg. Invested Capital", "$mil", avg_invested_capital, scale=1_000_000),
        "current_debt": _metric("Current Debt (Liab)", "$mil", current_debt, scale=1_000_000),
        "long_debt": _metric("Long-term debt (Liab)", "$mil", long_debt, scale=1_000_000),
        "total_debt": _metric("Total Debt (Liab)", "$mil", total_debt, scale=1_000_000),
        "stock_price": _metric("Stock Price (31/12)", "$", stock_price),
        "roic": _metric("ROIC", "%", roic, percent=True),
        "equity_gr": _growth_metric("Equity-GR", equity),
        "eps_gr": _growth_metric("EPS-GR", eps),
        "sales_gr": _growth_metric("Sales-GR", revenue),
        "fcf_gr": _growth_metric("FCF-GR", free_cash_flow),
        "debt_ratio": _metric("Debt Ratio", "y", debt_ratio),
        "pe_ratio": _metric("PE Ratio", "x", pe_ratio),
    }


def _series_from_statement(statement: pd.DataFrame, field_names: tuple[str, ...], periods: list[PeriodKey]) -> pd.Series:
    series = pd.Series(index=periods, dtype="float64")
    if statement.empty:
        return series
    normalized = {_normalize_label(index): index for index in statement.index}
    for field_name in field_names:
        original = normalized.get(_normalize_label(field_name))
        if original is not None:
            values = pd.to_numeric(statement.loc[original], errors="coerce")
            return values.reindex(periods).astype(float)
    return series


def _normalize_label(value: Any) -> str:
    return " ".join(str(value).replace("_", " ").lower().split())


def _metric(label: str, unit: str, values: pd.Series, *, scale: float = 1.0, percent: bool = False) -> dict[str, Any]:
    scaled = values.astype(float) / scale
    return {"label": label, "unit": unit, "values": scaled, "percent": percent, "kind": "level"}


def _growth_metric(label: str, values: pd.Series) -> dict[str, Any]:
    growth = values.astype(float).pct_change().replace([np.inf, -np.inf], np.nan)
    return {"label": label, "unit": "%", "values": growth, "percent": True, "kind": "growth", "source_values": values}


def _rows_from_map(financial_map: dict[str, dict[str, Any]], periods: list[PeriodKey]) -> list[dict[str, Any]]:
    # Stock price sits at the top so the live quote column below it lands
    # directly under the latest annual price and is easy to compare visually.
    row_keys = [
        "stock_price",
        "sales", "equity", "eps", "fcf", "nopat", "net_income", "avg_invested_capital",
        "current_debt", "long_debt", "total_debt", "debt_ratio", "pe_ratio",
    ]
    return [_display_row(financial_map[key], periods) for key in row_keys]


def _build_big_five(financial_map: dict[str, dict[str, Any]], periods: list[PeriodKey]) -> list[dict[str, Any]]:
    rows = []
    for key in ("roic", "equity_gr", "eps_gr", "sales_gr", "fcf_gr", "debt_ratio", "pe_ratio"):
        metric = financial_map[key]
        row = _display_row(metric, periods)
        source = metric.get("source_values", metric["values"])
        if key == "roic":
            summary = _summary_average_values(metric["values"])
            row.update(_format_summary_values(summary, percent=True))
            row.update(_big_five_statuses(summary, threshold=0.10))
        elif metric["kind"] == "growth":
            summary = _summary_cagr_values(source)
            row.update(_format_summary_values(summary, percent=True))
            row.update(_big_five_statuses(summary, threshold=0.10))
        else:
            summary = _summary_average_values(metric["values"])
            row.update(_format_summary_values(summary, percent=False))
            row.update(_big_five_statuses(summary, threshold=None))
        rows.append(row)
    return rows


def _build_valuation(
    info: dict[str, Any],
    financial_map: dict[str, dict[str, Any]],
    periods: list[PeriodKey],
    marr: float,
    margin_of_safety: float,
) -> list[dict[str, Any]]:
    eps = financial_map["eps"]["values"].dropna()
    equity = financial_map["equity"]["values"].dropna()
    pe = financial_map["pe_ratio"]["values"].dropna()
    price = _latest(financial_map["stock_price"]["values"])
    current_eps = _number(info.get("trailingEps")) or _latest(eps)
    historical_equity_growth = _cagr(equity, min(10, max(len(equity) - 1, 1)))
    historical_eps_growth = _cagr(eps, min(10, max(len(eps) - 1, 1)))
    analysts_growth = _growth_from_info(info)
    estimated_growth = _estimated_growth_rate(
        analysts_growth, historical_equity_growth, historical_eps_growth
    )
    estimated_eps_10y = current_eps * ((1 + estimated_growth) ** 10) if _is_number(current_eps) else np.nan
    rule1_price_earn = max(0.0, estimated_growth * 200)
    forward_pe = _number(info.get("forwardPE"))
    historical_pe = pe.tail(10).mean() if not pe.empty else np.nan
    rule1_pe_candidates = [value for value in (rule1_price_earn, forward_pe, historical_pe) if _is_number(value) and value > 0]
    rule1_pe = min(rule1_pe_candidates) if rule1_pe_candidates else np.nan
    peg = (rule1_pe / (estimated_growth * 100)) if estimated_growth > 0 and _is_number(rule1_pe) else np.nan
    future_market_price = estimated_eps_10y * rule1_pe if _is_number(estimated_eps_10y) and _is_number(rule1_pe) else np.nan
    sticker_price = future_market_price / ((1 + marr) ** 10) if _is_number(future_market_price) else np.nan
    entry_price = sticker_price * margin_of_safety if _is_number(sticker_price) else np.nan
    current_entry_ratio = price / entry_price if _is_number(price) and _is_number(entry_price) and entry_price else np.nan

    rows = [
        ("Analysts' GR", _format_pct(analysts_growth)),
        ("Historical Equity GR", _format_pct(historical_equity_growth)),
        ("Estimated EPS GR", _format_pct(estimated_growth)),
        ("Current EPS", _format_money(current_eps)),
        ("Estimated EPS 10y", _format_money(estimated_eps_10y)),
        ("PEG", _format_number(peg, 1)),
        ("Rule #1st Price/Earn Ratio", _format_number(rule1_price_earn, 1)),
        ("Forward Price/Earn Ratio", _format_number(forward_pe, 1)),
        ("Historical PE", _format_number(historical_pe, 1)),
        ("Rule #1 PE", _format_number(rule1_pe, 1)),
        ("MARR", _format_pct(marr)),
        ("MOS", _format_pct(margin_of_safety)),
        ("Fut. Market Price (10 Y)", _format_money(future_market_price)),
        ("Sticker Price", _format_money(sticker_price)),
        ("Year-end Close", _format_money(price)),
        ("Entry Price", _format_money(entry_price)),
        ("Close/Entry price ratio", _format_number(current_entry_ratio, 1)),
    ]
    return [{"metric": metric, "value": value} for metric, value in rows]


def _display_row(metric: dict[str, Any], periods: list[PeriodKey], *, live_value: float | None = None) -> dict[str, Any]:
    values = metric["values"]
    row = {"metric": metric["label"], "unit": metric["unit"], "kind": metric["kind"]}
    for period in periods:
        value = values.get(period, np.nan)
        row[_period_column_key(period)] = _format_pct(value) if metric["percent"] else _format_metric_value(value, metric["unit"])
    if live_value is not None:
        row["live_value"] = live_value
    return row


def _attach_live_price(financials: list[dict[str, Any]], live_price: float | None) -> list[dict[str, Any]]:
    """Stamp the live price onto the Stock Price (31/12) row so the UI can
    surface it without re-walking the payload."""
    if live_price is None:
        return financials
    enriched: list[dict[str, Any]] = []
    for row in financials:
        if row.get("metric") == "Stock Price (31/12)":
            new_row = dict(row)
            new_row["live_value"] = float(live_price)
            enriched.append(new_row)
        else:
            enriched.append(row)
    return enriched


def _summary_averages(values: pd.Series, *, percent: bool) -> dict[str, str]:
    return _format_summary_values(_summary_average_values(values), percent=percent)


def _summary_cagrs(values: pd.Series) -> dict[str, str]:
    return _format_summary_values(_summary_cagr_values(values), percent=True)


def _summary_average_values(values: pd.Series) -> dict[str, float]:
    clean = values.dropna()
    return {
        "10Y": clean.tail(10).mean() if not clean.empty else np.nan,
        "5Y": clean.tail(5).mean() if not clean.empty else np.nan,
        "1Y": _latest(clean),
    }


def _summary_cagr_values(values: pd.Series) -> dict[str, float]:
    clean = values.dropna()
    return {
        "10Y": _cagr(clean, 10),
        "5Y": _cagr(clean, 5),
        "1Y": clean.pct_change().iloc[-1] if len(clean) >= 2 else np.nan,
    }


def _format_summary_values(summary: dict[str, float], *, percent: bool) -> dict[str, str]:
    formatter = _format_pct if percent else _format_number
    return {label: formatter(value) for label, value in summary.items()}


def _big_five_statuses(summary: dict[str, float], *, threshold: float | None) -> dict[str, str]:
    return {f"status_{label}": _status_for_value(value, threshold) for label, value in summary.items()}


def _status_for_value(value: float, threshold: float | None) -> str:
    if not _is_number(value):
        return "na"
    number = float(value)
    if threshold is None:
        return "neutral"
    if number >= threshold:
        return "good"
    if number > 0:
        return "warn"
    return "bad"


def _cagr(values: pd.Series, periods: int) -> float:
    clean = values.dropna()
    if len(clean) < 2:
        return np.nan
    periods = min(periods, len(clean) - 1)
    start = clean.iloc[-periods - 1]
    end = clean.iloc[-1]
    if start <= 0 or not _is_number(start) or not _is_number(end):
        return np.nan
    return (end / start) ** (1 / periods) - 1


def _chart_series(financial_map: dict[str, dict[str, Any]], periods: list[PeriodKey]) -> dict[str, list[float | None]]:
    chart_keys = {
        "ROIC": "roic",
        "Equity": "equity",
        "Earning per share": "eps",
        "Sales": "sales",
        "Free Cash Flow": "fcf",
        "Debt": "long_debt",
    }
    return {
        label: [_json_number(financial_map[key]["values"].get(period, np.nan)) for period in periods]
        for label, key in chart_keys.items()
    }


def _quality_notes(
    financial_map: dict[str, dict[str, Any]],
    periods: list[PeriodKey],
    *,
    period: PeriodMode = "annual",
) -> list[str]:
    notes = []
    required = ("sales", "equity", "eps", "fcf", "net_income")
    for key in required:
        missing = sum(pd.isna(financial_map[key]["values"].get(value, np.nan)) for value in periods)
        if missing:
            label = "quarterly" if period == "quarterly" else "annual"
            notes.append(f"{financial_map[key]['label']}: {missing} missing {label} values")
    if financial_map["stock_price"]["values"].isna().all():
        notes.append("Period-end stock prices unavailable; PE and valuation may be incomplete")
    return notes or [f"All core {'quarterly' if period == 'quarterly' else 'annual'} fields available"]


def _growth_from_info(info: dict[str, Any]) -> float:
    for key in ("earningsGrowth", "revenueGrowth", "earningsQuarterlyGrowth"):
        value = _number(info.get(key))
        if _is_number(value):
            return value / 100 if value > 1 else value
    return np.nan


def _minimum_positive(*values: float) -> float:
    positives = [float(value) for value in values if _is_number(value) and value > 0]
    return min(positives) if positives else np.nan


def _estimated_growth_rate(
    analysts_growth: float,
    historical_equity_growth: float,
    historical_eps_growth: float,
) -> float:
    """Rule #1 growth: minimum of positive analyst / equity / EPS estimates, capped."""
    conservative = _minimum_positive(
        analysts_growth, historical_equity_growth, historical_eps_growth
    )
    if not _is_number(conservative):
        return 0.0
    return min(float(conservative), MAX_ESTIMATED_GROWTH)


def _latest(values: pd.Series) -> float:
    clean = values.dropna() if isinstance(values, pd.Series) else pd.Series(dtype="float64")
    return float(clean.iloc[-1]) if not clean.empty else np.nan


def _number(value: Any) -> float:
    try:
        if value is None:
            return np.nan
        number = float(value)
    except (TypeError, ValueError):
        return np.nan
    return number if math.isfinite(number) else np.nan


def _is_number(value: Any) -> bool:
    try:
        return value is not None and math.isfinite(float(value))
    except (TypeError, ValueError):
        return False


def _json_number(value: Any) -> float | None:
    number = _number(value)
    return float(number) if _is_number(number) else None


def _format_metric_value(value: Any, unit: str) -> str:
    if not _is_number(value):
        return "--"
    value = float(value)
    if unit == "$mil":
        return f"${value:,.0f}"
    if unit == "$":
        return f"${value:,.2f}"
    if unit == "x":
        return f"{value:,.2f}"
    if unit == "y":
        return f"{value:,.2f}"
    return f"{value:,.2f}"


def _format_money(value: Any) -> str:
    return f"${float(value):,.2f}" if _is_number(value) else "--"


def _format_number(value: Any, places: int = 2) -> str:
    return f"{float(value):,.{places}f}" if _is_number(value) else "--"


def _format_pct(value: Any) -> str:
    return f"{float(value) * 100:.2f}%" if _is_number(value) else "--"