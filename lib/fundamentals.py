"""
Fundamental analysis helpers for the dashboard.

The fetch layer is intentionally thin around yfinance; the calculation layer is
kept pure so valuation and growth formulas can be tested with fixed fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import logging
import math
from typing import Any

import numpy as np
import pandas as pd
import yfinance as yf

logger = logging.getLogger(__name__)


DEFAULT_MARR = 0.15
DEFAULT_MARGIN_OF_SAFETY = 0.50
DEFAULT_FUNDAMENTAL_YEARS = 11


@dataclass(frozen=True)
class FundamentalResult:
    ticker: str
    company_name: str
    currency: str
    years: list[int]
    financials: list[dict[str, Any]]
    big_five: list[dict[str, Any]]
    big_five_note: str
    valuation: list[dict[str, Any]]
    chart_series: dict[str, list[float | None]]
    quality_notes: list[str]
    as_of: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "ticker": self.ticker,
            "company_name": self.company_name,
            "currency": self.currency,
            "years": self.years,
            "financials": self.financials,
            "big_five": self.big_five,
            "big_five_note": self.big_five_note,
            "valuation": self.valuation,
            "chart_series": self.chart_series,
            "quality_notes": self.quality_notes,
            "as_of": self.as_of,
        }


def fetch_fundamentals(ticker: str, years: int = DEFAULT_FUNDAMENTAL_YEARS) -> dict[str, Any]:
    """Fetch annual fundamentals from yfinance and return dashboard-ready data."""
    symbol = (ticker or "").strip().upper()
    if not symbol:
        raise ValueError("Ticker is required")

    ticker_obj = yf.Ticker(symbol)
    info = _safe_info(ticker_obj)
    income = _safe_statement(ticker_obj, ("income_stmt", "financials"))
    balance = _safe_statement(ticker_obj, ("balance_sheet", "balancesheet"))
    cashflow = _safe_statement(ticker_obj, ("cashflow",))

    first_year = _first_statement_year(income, balance, cashflow)
    history = _safe_history(ticker_obj, first_year)
    yearly_prices = _yearly_close_prices(history)

    return build_fundamentals_result(
        ticker=symbol,
        info=info,
        income=income,
        balance=balance,
        cashflow=cashflow,
        yearly_prices=yearly_prices,
        years=years,
    ).to_dict()


def build_fundamentals_result(
    *,
    ticker: str,
    info: dict[str, Any] | None,
    income: pd.DataFrame | None,
    balance: pd.DataFrame | None,
    cashflow: pd.DataFrame | None,
    yearly_prices: pd.Series | None = None,
    years: int = DEFAULT_FUNDAMENTAL_YEARS,
    marr: float = DEFAULT_MARR,
    margin_of_safety: float = DEFAULT_MARGIN_OF_SAFETY,
) -> FundamentalResult:
    """Build the fundamentals payload from normalized statement inputs."""
    info = info or {}
    income = _clean_statement(income)
    balance = _clean_statement(balance)
    cashflow = _clean_statement(cashflow)
    yearly_prices = _clean_yearly_prices(yearly_prices)

    statement_years = _collect_years(income, balance, cashflow)
    all_years = (statement_years or _collect_years(yearly_prices))[-years:]
    if not all_years:
        raise ValueError(f"No annual fundamentals available for {ticker}")

    financial_map = _build_financial_map(income, balance, cashflow, yearly_prices, all_years)
    big_five = _build_big_five(financial_map, all_years)
    valuation = _build_valuation(info, financial_map, all_years, marr, margin_of_safety)
    notes = _quality_notes(financial_map, all_years)

    return FundamentalResult(
        ticker=ticker,
        company_name=str(info.get("longName") or info.get("shortName") or ticker),
        currency=str(info.get("financialCurrency") or info.get("currency") or "USD"),
        years=all_years,
        financials=_rows_from_map(financial_map, all_years),
        big_five=big_five,
        big_five_note="NOTE: Big Five should be >= 10% per year over the last 10 years.",
        valuation=valuation,
        chart_series=_chart_series(financial_map, all_years),
        quality_notes=notes,
        as_of=datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
    )


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
        cleaned = _clean_statement(statement)
        years.extend(cleaned.columns.tolist())
    return min(years) if years else None


def _clean_statement(statement: pd.DataFrame | None) -> pd.DataFrame:
    if statement is None or statement.empty:
        return pd.DataFrame()

    df = statement.copy()
    if isinstance(df.columns, pd.MultiIndex):
        df.columns = df.columns.get_level_values(0)

    converted_columns = {}
    for column in df.columns:
        try:
            converted_columns[column] = pd.Timestamp(column).year
        except Exception:
            try:
                converted_columns[column] = int(column)
            except Exception:
                continue

    df = df.rename(columns=converted_columns)
    df = df[[column for column in df.columns if isinstance(column, int)]]
    if df.empty:
        return pd.DataFrame()
    df = df.T.groupby(level=0).first().T
    return df.reindex(sorted(df.columns), axis=1)


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


def _clean_yearly_prices(yearly_prices: pd.Series | None) -> pd.Series:
    if yearly_prices is None or yearly_prices.empty:
        return pd.Series(dtype="float64")
    prices = yearly_prices.copy().dropna()
    prices.index = [int(pd.Timestamp(index).year) if not isinstance(index, (int, np.integer)) else int(index) for index in prices.index]
    return prices.groupby(level=0).last().sort_index().astype(float)


def _collect_years(*sources: Any) -> list[int]:
    collected: set[int] = set()
    for source in sources:
        if isinstance(source, pd.DataFrame) and not source.empty:
            collected.update(int(year) for year in source.columns)
        elif isinstance(source, pd.Series) and not source.empty:
            collected.update(int(year) for year in source.index)
    return sorted(collected)


def _build_financial_map(
    income: pd.DataFrame,
    balance: pd.DataFrame,
    cashflow: pd.DataFrame,
    yearly_prices: pd.Series,
    years: list[int],
) -> dict[str, dict[str, Any]]:
    revenue = _series_from_statement(income, ("Total Revenue", "Operating Revenue"), years)
    equity = _series_from_statement(balance, ("Stockholders Equity", "Total Equity Gross Minority Interest", "Common Stock Equity"), years)
    eps = _series_from_statement(income, ("Diluted EPS", "Basic EPS"), years)
    operating_income = _series_from_statement(income, ("Operating Income", "EBIT"), years)
    pretax_income = _series_from_statement(income, ("Pretax Income", "Income Before Tax"), years)
    tax_provision = _series_from_statement(income, ("Tax Provision", "Income Tax Expense"), years)
    net_income = _series_from_statement(income, ("Net Income", "Net Income Common Stockholders"), years)
    current_debt = _series_from_statement(balance, ("Current Debt", "Current Debt And Capital Lease Obligation", "Short Long Term Debt"), years)
    long_debt = _series_from_statement(balance, ("Long Term Debt", "Long Term Debt And Capital Lease Obligation"), years)
    total_debt = _series_from_statement(balance, ("Total Debt",), years)
    if total_debt.isna().all():
        total_debt = current_debt.fillna(0) + long_debt.fillna(0)
    cash = _series_from_statement(balance, ("Cash And Cash Equivalents", "Cash Cash Equivalents And Short Term Investments"), years).fillna(0)
    operating_cashflow = _series_from_statement(cashflow, ("Operating Cash Flow", "Total Cash From Operating Activities"), years)
    capex = _series_from_statement(cashflow, ("Capital Expenditure", "Capital Expenditures"), years)
    free_cash_flow = _series_from_statement(cashflow, ("Free Cash Flow",), years)
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
    stock_price = pd.Series({year: yearly_prices.get(year, np.nan) for year in years}, dtype="float64")
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


def _series_from_statement(statement: pd.DataFrame, field_names: tuple[str, ...], years: list[int]) -> pd.Series:
    series = pd.Series(index=years, dtype="float64")
    if statement.empty:
        return series
    normalized = {_normalize_label(index): index for index in statement.index}
    for field_name in field_names:
        original = normalized.get(_normalize_label(field_name))
        if original is not None:
            values = pd.to_numeric(statement.loc[original], errors="coerce")
            return values.reindex(years).astype(float)
    return series


def _normalize_label(value: Any) -> str:
    return " ".join(str(value).replace("_", " ").lower().split())


def _metric(label: str, unit: str, values: pd.Series, *, scale: float = 1.0, percent: bool = False) -> dict[str, Any]:
    scaled = values.astype(float) / scale
    return {"label": label, "unit": unit, "values": scaled, "percent": percent, "kind": "level"}


def _growth_metric(label: str, values: pd.Series) -> dict[str, Any]:
    growth = values.astype(float).pct_change().replace([np.inf, -np.inf], np.nan)
    return {"label": label, "unit": "%", "values": growth, "percent": True, "kind": "growth", "source_values": values}


def _rows_from_map(financial_map: dict[str, dict[str, Any]], years: list[int]) -> list[dict[str, Any]]:
    row_keys = [
        "sales", "equity", "eps", "fcf", "nopat", "net_income", "avg_invested_capital",
        "current_debt", "long_debt", "total_debt", "stock_price", "debt_ratio", "pe_ratio",
    ]
    return [_display_row(financial_map[key], years) for key in row_keys]


def _build_big_five(financial_map: dict[str, dict[str, Any]], years: list[int]) -> list[dict[str, Any]]:
    rows = []
    for key in ("roic", "equity_gr", "eps_gr", "sales_gr", "fcf_gr", "debt_ratio", "pe_ratio"):
        metric = financial_map[key]
        row = _display_row(metric, years)
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
    years: list[int],
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
    estimated_growth = _first_positive(analysts_growth, historical_equity_growth, historical_eps_growth) or 0.0
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
        ("Current Price", _format_money(price)),
        ("Entry Price", _format_money(entry_price)),
        ("Current/Entry price ratio", _format_number(current_entry_ratio, 1)),
    ]
    return [{"metric": metric, "value": value} for metric, value in rows]


def _display_row(metric: dict[str, Any], years: list[int]) -> dict[str, Any]:
    values = metric["values"]
    row = {"metric": metric["label"], "unit": metric["unit"], "kind": metric["kind"]}
    for year in years:
        value = values.get(year, np.nan)
        row[str(year)] = _format_pct(value) if metric["percent"] else _format_metric_value(value, metric["unit"])
    return row


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


def _chart_series(financial_map: dict[str, dict[str, Any]], years: list[int]) -> dict[str, list[float | None]]:
    chart_keys = {
        "ROIC": "roic",
        "Equity": "equity",
        "Earning per share": "eps",
        "Sales": "sales",
        "Free Cash Flow": "fcf",
        "Debt": "long_debt",
    }
    return {
        label: [_json_number(financial_map[key]["values"].get(year, np.nan)) for year in years]
        for label, key in chart_keys.items()
    }


def _quality_notes(financial_map: dict[str, dict[str, Any]], years: list[int]) -> list[str]:
    notes = []
    required = ("sales", "equity", "eps", "fcf", "net_income")
    for key in required:
        missing = sum(pd.isna(financial_map[key]["values"].get(year, np.nan)) for year in years)
        if missing:
            notes.append(f"{financial_map[key]['label']}: {missing} missing annual values")
    if financial_map["stock_price"]["values"].isna().all():
        notes.append("Year-end stock prices unavailable; PE and valuation may be incomplete")
    return notes or ["All core annual fields available"]


def _growth_from_info(info: dict[str, Any]) -> float:
    for key in ("earningsGrowth", "revenueGrowth", "earningsQuarterlyGrowth"):
        value = _number(info.get(key))
        if _is_number(value):
            return value / 100 if value > 1 else value
    return np.nan


def _first_positive(*values: float) -> float:
    for value in values:
        if _is_number(value) and value > 0:
            return value
    return np.nan


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