#!/usr/bin/env python3
"""Cheddar-Flow-style unusual options activity scanner (free, yfinance-backed)."""

from __future__ import annotations

import argparse
import json
import logging
import math
import os
import sys
import tempfile
import time
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from html import escape
from typing import Literal
from zoneinfo import ZoneInfo

import pandas as pd
import requests
import yfinance as yf
from rich.console import Console
from rich.progress_bar import ProgressBar
from rich.table import Table
from rich.text import Text

from lib.dash.flow_glossary import (
    DISCLAIMER,
    FLAG_DEFINITIONS,
    INSIGHT_CATEGORY_COLORS,
    TERM_DEFINITIONS,
    contract_signal,
    fmt_premium,
    fmt_strike,
    interpretive_insights,
    score_breakdown,
    ticker_sentiment,
)

logger = logging.getLogger(__name__)

ET = ZoneInfo("America/New_York")

FALLBACK_SYMBOLS = [
    "SPY", "QQQ", "IWM", "AAPL", "MSFT", "NVDA", "TSLA", "AMZN", "META", "GOOGL",
    "AMD", "AVGO", "JPM", "BAC", "XOM", "COIN", "PLTR", "SMCI", "ARM", "SNOW",
    "MARA", "RIOT", "NFLX", "CRM", "ORCL", "DIS", "BA", "KO", "PEP", "F",
]

YAHOO_SCREENER_URL = (
    "https://query1.finance.yahoo.com/v1/finance/screener/predefined/saved"
    "?formatted=true&lang=en-US&region=US&scrIds=most_actives"
    "&start=0&count={count}&enableSectorIndustryLabelFix=true"
    "&corsDomain=finance.yahoo.com"
)


# ---------------------------------------------------------------------------
# MODELS
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Contract:
    ticker: str
    expiry: date
    strike: float
    cp: Literal["C", "P"]
    last: float
    bid: float
    ask: float
    volume: int
    open_interest: int
    iv: float

    @property
    def premium(self) -> float:
        return self.volume * self.last * 100

    def is_unusual(self) -> bool:
        return self.volume > self.open_interest

    def is_otm(self, spot: float) -> bool:
        if self.cp == "C":
            return self.strike > spot
        return self.strike < spot

    def is_weekly(self, today: date | None = None) -> bool:
        today = today or date.today()
        return (self.expiry - today).days <= 7


@dataclass
class UnusualFlag:
    kind: Literal["unusual", "high_unusual", "block_premium", "repeat_call", "error"]
    contract: Contract | None
    message: str


@dataclass
class TickerReport:
    ticker: str
    spot: float
    prev_close: float
    day_low: float
    day_high: float
    wk52_low: float
    wk52_high: float
    contracts: list[Contract] = field(default_factory=list)
    flags: list[UnusualFlag] = field(default_factory=list)
    pc_vol_ratio: float = 0.0
    pc_oi_ratio: float = 0.0
    call_pct: float = 50.0
    put_pct: float = 50.0
    unusual_score: int = 0
    top_call_strikes: list[tuple[float, int]] = field(default_factory=list)
    top_put_strikes: list[tuple[float, int]] = field(default_factory=list)
    # Per-expiry strike ladders for inventory chart: { "YYYY-MM-DD": [row, ...] }
    strike_ladders: dict[str, list[dict]] = field(default_factory=dict)
    # Per-expiry walls / max pain: { "YYYY-MM-DD": {max_pain, call_wall, put_wall} }
    inventory_meta: dict[str, dict] = field(default_factory=dict)
    error: str | None = None


# ---------------------------------------------------------------------------
# SCANNER
# ---------------------------------------------------------------------------

def _safe_float(val, default: float = 0.0) -> float:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    try:
        return float(val)
    except (TypeError, ValueError):
        return default


def _safe_int(val, default: int = 0) -> int:
    if val is None or (isinstance(val, float) and math.isnan(val)):
        return default
    try:
        return int(val)
    except (TypeError, ValueError):
        return default


def load_watchlist(path: str) -> list[str]:
    tickers: list[str] = []
    seen: set[str] = set()
    with open(path, encoding="utf-8") as fh:
        for line in fh:
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            sym = line.upper()
            if sym not in seen:
                seen.add(sym)
                tickers.append(sym)
    return tickers


def fetch_most_active_symbols(n: int = 50) -> list[str]:
    """Best-effort most-actives list via Yahoo's private screener JSON endpoint."""
    headers = {"User-Agent": "Mozilla/5.0 (compatible; flow_scanner/1.0)"}
    try:
        resp = requests.get(YAHOO_SCREENER_URL.format(count=n), headers=headers, timeout=15)
        resp.raise_for_status()
        quotes = resp.json()["finance"]["result"][0]["quotes"]
        symbols = [q["symbol"] for q in quotes if q.get("symbol")]
        if symbols:
            return symbols[:n]
    except Exception as exc:
        logger.warning("Screener fetch failed (%s); using fallback list", exc)
    return FALLBACK_SYMBOLS[:n]


def _parse_expiry(exp_str: str) -> date:
    return datetime.strptime(exp_str, "%Y-%m-%d").date()


def _contracts_from_chain(
    ticker: str,
    expiry: date,
    df: pd.DataFrame,
    cp: Literal["C", "P"],
) -> list[Contract]:
    if df is None or df.empty:
        return []
    rows: list[Contract] = []
    for _, row in df.iterrows():
        rows.append(
            Contract(
                ticker=ticker,
                expiry=expiry,
                strike=_safe_float(row.get("strike")),
                cp=cp,
                last=_safe_float(row.get("lastPrice")),
                bid=_safe_float(row.get("bid")),
                ask=_safe_float(row.get("ask")),
                volume=_safe_int(row.get("volume")),
                open_interest=_safe_int(row.get("openInterest")),
                iv=_safe_float(row.get("impliedVolatility")),
            )
        )
    return rows


def _spot_from_ticker(tk: yf.Ticker) -> tuple[float, float, float, float, float, float]:
    info = {}
    try:
        info = tk.info or {}
    except Exception:
        info = {}

    spot = _safe_float(
        info.get("currentPrice") or info.get("regularMarketPrice"),
    )
    prev = _safe_float(info.get("previousClose"))
    day_low = _safe_float(info.get("dayLow"))
    day_high = _safe_float(info.get("dayHigh"))
    wk52_low = _safe_float(info.get("fiftyTwoWeekLow"))
    wk52_high = _safe_float(info.get("fiftyTwoWeekHigh"))

    if spot <= 0:
        try:
            fi = tk.fast_info
            spot = _safe_float(getattr(fi, "last_price", None) or getattr(fi, "lastPrice", None))
            prev = prev or _safe_float(getattr(fi, "previous_close", None))
            day_low = day_low or _safe_float(getattr(fi, "day_low", None))
            day_high = day_high or _safe_float(getattr(fi, "day_high", None))
            wk52_low = wk52_low or _safe_float(getattr(fi, "year_low", None))
            wk52_high = wk52_high or _safe_float(getattr(fi, "year_high", None))
        except Exception:
            pass

    return spot, prev, day_low, day_high, wk52_low, wk52_high


def detect_flags(
    report: TickerReport,
    min_premium: float,
    min_size: int,
    today: date | None = None,
) -> list[UnusualFlag]:
    today = today or date.today()
    flags: list[UnusualFlag] = []
    unusual_by_expiry: dict[date, list[Contract]] = defaultdict(list)

    for c in report.contracts:
        if c.is_unusual():
            flags.append(
                UnusualFlag(
                    kind="unusual",
                    contract=c,
                    message=f"{c.cp} {c.strike} vol>{c.open_interest}",
                )
            )
            if c.cp == "C":
                unusual_by_expiry[c.expiry].append(c)

        if c.volume > min_size and c.is_otm(report.spot) and c.is_weekly(today):
            flags.append(
                UnusualFlag(
                    kind="high_unusual",
                    contract=c,
                    message=f"OTM weekly size {c.volume}",
                )
            )

        if c.premium > min_premium:
            flags.append(
                UnusualFlag(
                    kind="block_premium",
                    contract=c,
                    message=f"premium ${c.premium:,.0f}",
                )
            )

    for expiry, calls in unusual_by_expiry.items():
        strikes = {c.strike for c in calls}
        if len(strikes) >= 3:
            flags.append(
                UnusualFlag(
                    kind="repeat_call",
                    contract=None,
                    message=f"{len(strikes)} unusual call strikes @ {expiry}",
                )
            )

    return flags


def aggregate_strike_ladder(contracts: list[Contract]) -> list[dict]:
    """Aggregate call/put OI and volume by strike for one expiry's contracts."""
    by_strike: dict[float, dict[str, int | float]] = {}
    for c in contracts:
        row = by_strike.setdefault(
            c.strike,
            {"strike": c.strike, "call_oi": 0, "put_oi": 0, "call_vol": 0, "put_vol": 0},
        )
        if c.cp == "C":
            row["call_oi"] = int(row["call_oi"]) + int(c.open_interest or 0)
            row["call_vol"] = int(row["call_vol"]) + int(c.volume or 0)
        else:
            row["put_oi"] = int(row["put_oi"]) + int(c.open_interest or 0)
            row["put_vol"] = int(row["put_vol"]) + int(c.volume or 0)
    return sorted(
        (
            {
                "strike": float(r["strike"]),
                "call_oi": int(r["call_oi"]),
                "put_oi": int(r["put_oi"]),
                "call_vol": int(r["call_vol"]),
                "put_vol": int(r["put_vol"]),
            }
            for r in by_strike.values()
        ),
        key=lambda r: r["strike"],
    )


def max_pain_strike(ladder: list[dict]) -> float | None:
    """Strike that minimises total intrinsic value of open calls + puts (max pain)."""
    if not ladder:
        return None
    strikes = [float(r["strike"]) for r in ladder]
    call_oi = {float(r["strike"]): int(r.get("call_oi") or 0) for r in ladder}
    put_oi = {float(r["strike"]): int(r.get("put_oi") or 0) for r in ladder}

    best_strike: float | None = None
    best_loss = float("inf")
    for settlement in strikes:
        total_loss = 0.0
        for s in strikes:
            coi = call_oi.get(s, 0)
            poi = put_oi.get(s, 0)
            if s > settlement:
                total_loss += (s - settlement) * coi
            elif s < settlement:
                total_loss += (settlement - s) * poi
        if total_loss < best_loss:
            best_loss = total_loss
            best_strike = settlement
    return best_strike


def call_put_walls(ladder: list[dict]) -> tuple[float | None, float | None]:
    """Return (call_wall, put_wall) — strikes with max call OI and max put OI."""
    if not ladder:
        return None, None
    call_wall = max(ladder, key=lambda r: int(r.get("call_oi") or 0))
    put_wall = max(ladder, key=lambda r: int(r.get("put_oi") or 0))
    cw = float(call_wall["strike"]) if int(call_wall.get("call_oi") or 0) > 0 else None
    pw = float(put_wall["strike"]) if int(put_wall.get("put_oi") or 0) > 0 else None
    return cw, pw


def inventory_meta_for_ladder(ladder: list[dict]) -> dict:
    """Build max_pain / call_wall / put_wall for one expiry ladder."""
    cw, pw = call_put_walls(ladder)
    mp = max_pain_strike(ladder)
    return {
        "max_pain": mp,
        "call_wall": cw,
        "put_wall": pw,
    }


def build_strike_ladders(
    contracts: list[Contract],
) -> tuple[dict[str, list[dict]], dict[str, dict]]:
    """Group contracts by expiry → strike ladders + inventory meta."""
    by_expiry: dict[date, list[Contract]] = defaultdict(list)
    for c in contracts:
        by_expiry[c.expiry].append(c)

    ladders: dict[str, list[dict]] = {}
    meta: dict[str, dict] = {}
    for expiry in sorted(by_expiry):
        key = expiry.isoformat()
        ladder = aggregate_strike_ladder(by_expiry[expiry])
        ladders[key] = ladder
        meta[key] = inventory_meta_for_ladder(ladder)
    return ladders, meta


def compute_metrics(report: TickerReport) -> None:
    calls = [c for c in report.contracts if c.cp == "C"]
    puts = [c for c in report.contracts if c.cp == "P"]
    call_vol = sum(c.volume for c in calls)
    put_vol = sum(c.volume for c in puts)
    call_oi = sum(c.open_interest for c in calls)
    put_oi = sum(c.open_interest for c in puts)

    report.pc_vol_ratio = put_vol / max(call_vol, 1)
    report.pc_oi_ratio = put_oi / max(call_oi, 1)
    total_vol = call_vol + put_vol
    if total_vol > 0:
        report.call_pct = call_vol / total_vol * 100
        report.put_pct = put_vol / total_vol * 100

    report.top_call_strikes = sorted(
        ((c.strike, c.volume) for c in calls),
        key=lambda x: x[1],
        reverse=True,
    )[:10]
    report.top_put_strikes = sorted(
        ((c.strike, c.volume) for c in puts),
        key=lambda x: x[1],
        reverse=True,
    )[:10]

    report.strike_ladders, report.inventory_meta = build_strike_ladders(report.contracts)

    hu = sum(1 for f in report.flags if f.kind == "high_unusual")
    bp = sum(1 for f in report.flags if f.kind == "block_premium")
    u = sum(1 for f in report.flags if f.kind == "unusual")
    rc = sum(1 for f in report.flags if f.kind == "repeat_call")
    # unusual_score = 5*HU + 3*BP + 2*U + 10*RC
    report.unusual_score = 5 * hu + 3 * bp + 2 * u + 10 * rc


def fetch_ticker_report(
    ticker: str,
    expirations: int = 3,
    min_premium: float = 1_000_000,
    min_size: int = 5000,
) -> TickerReport:
    ticker = ticker.upper()
    try:
        tk = yf.Ticker(ticker)
        spot, prev, day_low, day_high, wk52_low, wk52_high = _spot_from_ticker(tk)

        contracts: list[Contract] = []
        try:
            expiries = list(tk.options or [])[:expirations]
        except Exception:
            expiries = []

        for exp_str in expiries:
            expiry = _parse_expiry(exp_str)
            chain = tk.option_chain(exp_str)
            contracts.extend(_contracts_from_chain(ticker, expiry, chain.calls, "C"))
            contracts.extend(_contracts_from_chain(ticker, expiry, chain.puts, "P"))

        report = TickerReport(
            ticker=ticker,
            spot=spot,
            prev_close=prev,
            day_low=day_low,
            day_high=day_high,
            wk52_low=wk52_low,
            wk52_high=wk52_high,
            contracts=contracts,
        )
        report.flags = detect_flags(report, min_premium, min_size)
        compute_metrics(report)
        return report

    except Exception as exc:
        logger.error("Failed to fetch %s: %s", ticker, exc)
        report = TickerReport(
            ticker=ticker,
            spot=0,
            prev_close=0,
            day_low=0,
            day_high=0,
            wk52_low=0,
            wk52_high=0,
            error=str(exc),
        )
        report.flags = [
            UnusualFlag(kind="error", contract=None, message=str(exc)),
        ]
        return report


def scan_tickers(
    tickers: list[str],
    expirations: int = 3,
    min_premium: float = 1_000_000,
    min_size: int = 5000,
    polite_delay: float = 0.25,
) -> list[TickerReport]:
    reports: list[TickerReport] = []
    for i, ticker in enumerate(tickers):
        reports.append(
            fetch_ticker_report(ticker, expirations, min_premium, min_size)
        )
        if polite_delay and i < len(tickers) - 1:
            time.sleep(polite_delay)
    return reports


# ---------------------------------------------------------------------------
# REPORTER
# ---------------------------------------------------------------------------

def _flag_badges(flags: list[UnusualFlag], contract: Contract | None) -> str:
    if contract is None:
        kinds = {f.kind for f in flags if f.contract is None and f.kind == "repeat_call"}
        return "RC" if "repeat_call" in kinds else ""
    badges = []
    for f in flags:
        if f.contract != contract:
            continue
        if f.kind == "unusual":
            badges.append("U")
        elif f.kind == "high_unusual":
            badges.append("HU")
        elif f.kind == "block_premium":
            badges.append("B")
    return " ".join(badges)


def _contract_flags(report: TickerReport, contract: Contract) -> list[UnusualFlag]:
    return [f for f in report.flags if f.contract == contract]


def _header_style(pc_ratio: float) -> str:
    if pc_ratio < 0.7:
        return "bold green"
    if pc_ratio <= 1.0:
        return "bold yellow"
    return "bold red"


def print_terminal_summary(reports: list[TickerReport], console: Console, scan_mode: bool = False) -> None:
    if scan_mode:
        reports = sorted(reports, key=lambda r: r.unusual_score, reverse=True)

    for report in reports:
        if report.error:
            console.print(f"[red]{report.ticker}[/red] ERROR: {report.error}")
            continue

        header = (
            f"{report.ticker}  ${report.spot:,.2f}  "
            f"(prev ${report.prev_close:,.2f}, day {report.day_low:,.2f}-{report.day_high:,.2f}, "
            f"52w {report.wk52_low:,.2f}-{report.wk52_high:,.2f})"
        )
        console.print(Text.from_markup(f"[{_header_style(report.pc_vol_ratio)}]{header}[/]"))
        console.print(
            f"  P/C vol {report.pc_vol_ratio:.2f}  P/C OI {report.pc_oi_ratio:.2f}  "
            f"score {report.unusual_score}"
        )

        bar = ProgressBar(total=100, completed=report.call_pct, width=30)
        console.print(f"  Call {report.call_pct:.1f}% ", end="")
        console.print(bar, end=" ")
        console.print(f" Put {report.put_pct:.1f}%")

        repeat = any(f.kind == "repeat_call" for f in report.flags)
        if repeat:
            console.print("[bold yellow]REPEAT CALL ACTIVITY[/bold yellow]")

        table = Table(show_header=True, header_style="bold")
        for col in ("Strike", "Type", "Last", "Bid", "Ask", "Vol", "OI", "IV%", "Premium", "Flags"):
            table.add_column(col, justify="right" if col != "Type" else "center")

        flagged = [c for c in report.contracts if _contract_flags(report, c)]
        flagged.sort(key=lambda c: c.volume, reverse=True)
        show = flagged[:20] if flagged else sorted(report.contracts, key=lambda c: c.volume, reverse=True)[:10]

        for c in show:
            badges = _flag_badges(report.flags, c)
            flag_style = ""
            if "HU" in badges:
                flag_style = "[bold blue]"
            elif "B" in badges:
                flag_style = "[bold orange3]"
            elif "U" in badges:
                flag_style = "[bold magenta]"
            flag_text = f"{flag_style}{badges}[/]" if flag_style else badges

            table.add_row(
                f"{c.strike:.2f}",
                c.cp,
                f"{c.last:.2f}",
                f"{c.bid:.2f}",
                f"{c.ask:.2f}",
                str(c.volume),
                str(c.open_interest),
                f"{c.iv * 100:.1f}",
                f"${c.premium:,.0f}",
                flag_text,
            )
        console.print(table)
        console.print()


def _html_flag_badges(flags: list[UnusualFlag], contract: Contract | None) -> str:
    parts = []
    for f in flags:
        if f.contract != contract:
            continue
        cls = {"unusual": "badge-u", "high_unusual": "badge-hu", "block_premium": "badge-b"}.get(f.kind)
        if cls:
            label = {"unusual": "U", "high_unusual": "HU", "block_premium": "B"}[f.kind]
            tip = escape(f.message)
            parts.append(f'<span class="badge {cls}" title="{tip}">{label}</span>')
    for f in flags:
        if f.kind == "repeat_call" and contract is None:
            tip = escape(f.message)
            parts.append(f'<span class="badge badge-rc" title="{tip}">RC</span>')
    return " ".join(parts)


def _contract_sort_key(report: TickerReport, contract: Contract) -> tuple:
    cflags = _contract_flags(report, contract)
    hu = sum(1 for f in cflags if f.kind == "high_unusual")
    bp = sum(1 for f in cflags if f.kind == "block_premium")
    u = sum(1 for f in cflags if f.kind == "unusual")
    return (hu, bp, u, contract.volume)


def _html_insights_block(report_dict: dict) -> str:
    insights = interpretive_insights(report_dict)
    if not insights:
        return ""
    items = []
    for category, message in insights:
        color = INSIGHT_CATEGORY_COLORS.get(category, "#8b949e")
        items.append(
            f'<li><span class="insight-chip" style="background:{color}33;color:{color}">'
            f'{escape(category.upper())}</span> {escape(message)}</li>'
        )
    return f'<ul class="insights">{"".join(items)}</ul>'


def _premium_cell_class(premium: float) -> str:
    if premium >= 5_000_000:
        return "heat-premium-xl"
    if premium >= 1_000_000:
        return "heat-premium-lg"
    if premium >= 250_000:
        return "heat-premium-md"
    return ""


def _iv_cell_class(iv: float) -> str:
    if iv >= 1.5:
        return "heat-iv-high"
    if iv >= 0.8:
        return "heat-iv-mid"
    return ""


def _html_signal_cell_from_dict(contract_dict: dict) -> str:
    label, color = contract_signal(contract_dict, contract_dict.get("flags"))
    tip = escape(TERM_DEFINITIONS["signal"])
    return (
        f'<span class="signal-chip" style="color:{color};font-weight:600" '
        f'title="{tip}">{escape(label)}</span>'
    )


def _html_th(label: str, term_key: str) -> str:
    tip = escape(TERM_DEFINITIONS.get(term_key, label))
    return f'<th title="{tip}">{escape(label)}</th>'


def _html_glossary_block() -> str:
    terms = "".join(
        f"<dt>{escape(k.title())}</dt><dd>{escape(v)}</dd>"
        for k, v in TERM_DEFINITIONS.items()
    )
    flags = "".join(
        f'<dt><span class="badge badge-{fd["label"].lower()}">{escape(fd["label"])}</span> '
        f'{escape(fd["short"])}</dt><dd>{escape(fd["long"])}</dd>'
        for fd in FLAG_DEFINITIONS.values()
    )
    return (
        f'<details class="glossary"><summary>What do these terms mean?</summary>'
        f"<dl class='glossary-terms'>{terms}</dl>"
        f"<h3>Activity flags</h3><dl class='glossary-flags'>{flags}</dl></details>"
    )


def _html_strike_cell(report: TickerReport, contract: Contract, today: date) -> str:
    strike = fmt_strike(contract.strike)
    otm = contract.is_otm(report.spot)
    chip_cls = "chip-otm" if otm else "chip-itm"
    chip_label = "OTM" if otm else "ITM"
    chip_tip = escape(TERM_DEFINITIONS["otm" if otm else "itm"])
    chip = f' <span class="chip {chip_cls}" title="{chip_tip}">{chip_label}</span>'
    return f"{strike}{chip}"


def _html_expiry_cell(contract: Contract, today: date) -> str:
    expiry = contract.expiry.isoformat()
    if contract.is_weekly(today):
        tip = escape(TERM_DEFINITIONS["weekly"])
        return f'{expiry} <span class="chip chip-weekly" title="{tip}">weekly</span>'
    return expiry


def _html_type_cell(cp: str) -> str:
    color = "#3fb950" if cp == "C" else "#f85149"
    tip = escape(TERM_DEFINITIONS["type"])
    return f'<span style="color:{color};font-weight:600" title="{tip}">{cp}</span>'


def _report_to_dict(report: TickerReport, today: date | None = None) -> dict:
    today = today or date.today()
    flagged = [c for c in report.contracts if _contract_flags(report, c)]
    flagged.sort(key=lambda c: _contract_sort_key(report, c), reverse=True)
    flagged_contracts = []
    for c in flagged:
        cflags = _contract_flags(report, c)
        flagged_contracts.append({
            "strike": c.strike,
            "cp": c.cp,
            "last": c.last,
            "bid": c.bid,
            "ask": c.ask,
            "volume": c.volume,
            "open_interest": c.open_interest,
            "iv": c.iv,
            "premium": c.premium,
            "expiry": c.expiry.isoformat(),
            "is_weekly": c.is_weekly(today),
            "is_otm": c.is_otm(report.spot),
            "flags": [{"kind": f.kind, "message": f.message} for f in cflags],
        })

    return {
        "ticker": report.ticker,
        "spot": report.spot,
        "prev_close": report.prev_close,
        "day_low": report.day_low,
        "day_high": report.day_high,
        "wk52_low": report.wk52_low,
        "wk52_high": report.wk52_high,
        "pc_vol_ratio": report.pc_vol_ratio,
        "pc_oi_ratio": report.pc_oi_ratio,
        "call_pct": report.call_pct,
        "put_pct": report.put_pct,
        "unusual_score": report.unusual_score,
        "error": report.error,
        "top_call_strikes": report.top_call_strikes,
        "top_put_strikes": report.top_put_strikes,
        "strike_ladders": report.strike_ladders,
        "inventory_meta": report.inventory_meta,
        "flags": [{"kind": f.kind, "message": f.message} for f in report.flags],
        "contracts": flagged_contracts,
    }


def write_html_report(reports: list[TickerReport], output_path: str) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    today = date.today()
    total_unusual = sum(1 for r in reports for f in r.flags if f.kind == "unusual")
    total_premium = sum(
        f.contract.premium for r in reports for f in r.flags
        if f.kind == "block_premium" and f.contract
    )
    repeat_tickers = [r.ticker for r in reports if any(f.kind == "repeat_call" for f in r.flags)]
    glossary = _html_glossary_block()

    cards = []
    for report in sorted(reports, key=lambda r: r.unusual_score, reverse=True):
        if report.error:
            cards.append(
                f'<div class="card"><h2>{escape(report.ticker)}</h2>'
                f'<p class="err">{escape(report.error)}</p></div>'
            )
            continue

        repeat = any(f.kind == "repeat_call" for f in report.flags)
        rc_badge = '<span class="badge badge-rc">REPEAT CALLS</span>' if repeat else ""
        report_dict = _report_to_dict(report, today)
        score_tip = escape(score_breakdown(report_dict))
        insights_html = _html_insights_block(report_dict)
        sent_label, sent_color, sent_reason = ticker_sentiment(report_dict)
        sentiment_badge = (
            f'<span class="sentiment-badge" style="background:{sent_color}33;color:{sent_color}" '
            f'title="{escape(sent_reason)}">{escape(sent_label.upper())}</span>'
        )

        rows = []
        flagged = [c for c in report.contracts if _contract_flags(report, c)]
        flagged.sort(key=lambda c: _contract_sort_key(report, c), reverse=True)
        for c in flagged[:50]:
            cflags = _contract_flags(report, c)
            badges = _html_flag_badges(cflags, c)
            contract_dict = {
                "cp": c.cp,
                "is_otm": c.is_otm(report.spot),
                "is_weekly": c.is_weekly(today),
                "flags": [{"kind": f.kind, "message": f.message} for f in cflags],
            }
            row_cls = "row-unusual" if c.volume > c.open_interest else ""
            prem_cls = _premium_cell_class(c.premium)
            iv_cls = _iv_cell_class(c.iv)
            rows.append(
                f'<tr class="{row_cls}">'
                f"<td>{_html_strike_cell(report, c, today)}</td>"
                f"<td>{_html_type_cell(c.cp)}</td>"
                f"<td>{c.last:.2f}</td><td>{c.bid:.2f}</td><td>{c.ask:.2f}</td>"
                f"<td>{c.volume:,}</td><td>{c.open_interest:,}</td>"
                f'<td class="{iv_cls}">{c.iv * 100:.1f}%</td>'
                f'<td class="{prem_cls}">{fmt_premium(c.premium)}</td>'
                f"<td>{_html_expiry_cell(c, today)}</td>"
                f"<td>{badges}</td>"
                f"<td>{_html_signal_cell_from_dict(contract_dict)}</td></tr>"
            )

        table_body = "\n".join(rows) if rows else '<tr><td colspan="12">No flagged contracts</td></tr>'

        top_calls = ", ".join(f"${s:.0f} ({v:,})" for s, v in report.top_call_strikes[:5]) or "—"
        top_puts = ", ".join(f"${s:.0f} ({v:,})" for s, v in report.top_put_strikes[:5]) or "—"

        th_row = "".join([
            _html_th("Strike", "strike"),
            _html_th("Type", "type"),
            _html_th("Last", "last"),
            _html_th("Bid", "bid"),
            _html_th("Ask", "ask"),
            _html_th("Vol", "vol"),
            _html_th("OI", "oi"),
            _html_th("IV", "iv"),
            _html_th("Premium", "premium"),
            _html_th("Expiry", "expiry"),
            _html_th("Flags", "flags"),
            _html_th("Signal", "signal"),
        ])

        cards.append(
            f"""<div class="card" data-ticker="{escape(report.ticker)}">
  <div class="card-header">
    <h2>{escape(report.ticker)} ${report.spot:,.2f} {sentiment_badge} {rc_badge}</h2>
    <a class="flow-link" href="/fundamentals?ticker={escape(report.ticker)}">Open Fundamentals</a>
  </div>
  <div class="kpis">
    <span title="Previous session close">Prev ${report.prev_close:,.2f}</span>
    <span title="Today's trading range">Day {report.day_low:,.2f}–{report.day_high:,.2f}</span>
    <span title="52-week high and low">52-week {report.wk52_low:,.2f}–{report.wk52_high:,.2f}</span>
    <span title="{escape(TERM_DEFINITIONS['pc_vol'])}">Put/Call vol {report.pc_vol_ratio:.2f}</span>
    <span title="{score_tip}">Score {report.unusual_score}</span>
  </div>
  <div class="sentiment">
    <span>Calls {report.call_pct:.1f}%</span>
    <div class="bar"><div class="bar-call" style="width:{report.call_pct:.1f}%"></div></div>
    <span>Puts {report.put_pct:.1f}%</span>
  </div>
  <p class="top-strikes">Top calls: {escape(top_calls)} | Top puts: {escape(top_puts)}</p>
  {insights_html}
  <div class="table-wrap">
  <table class="sortable">
    <thead><tr>{th_row}</tr></thead>
    <tbody>{table_body}</tbody>
  </table>
  </div>
</div>"""
        )

    html = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Flow Scanner Report — {escape(ts)}</title>
<style>
body {{ background:#0d1117; color:#c9d1d9; font-family:Segoe UI,system-ui,sans-serif; margin:0; padding:16px; }}
h1 {{ font-size:1.4rem; margin:0 0 12px; }}
.summary {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:12px; }}
.summary span {{ background:#161b22; padding:8px 14px; border-radius:6px; border:1px solid #30363d; }}
.glossary {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:10px 14px; margin-bottom:20px; }}
.glossary summary {{ cursor:pointer; font-weight:600; color:#e6edf3; }}
.glossary dl {{ margin:8px 0 0; font-size:0.85rem; }}
.glossary dt {{ color:#e6edf3; margin-top:6px; }}
.glossary dd {{ margin:2px 0 0 1rem; color:#8b949e; }}
.glossary h3 {{ font-size:0.9rem; margin:12px 0 4px; color:#c9d1d9; }}
.card {{ background:#161b22; border:1px solid #30363d; border-radius:8px; padding:14px; margin-bottom:16px; }}
.card-header {{ display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:8px; }}
.card h2 {{ margin:0; color:#e6edf3; font-size:1.1rem; }}
.flow-link {{ color:#58a6ff; text-decoration:none; font-size:0.85rem; }}
.flow-link:hover {{ text-decoration:underline; }}
.kpis {{ display:flex; flex-wrap:wrap; gap:12px; font-size:0.85rem; color:#8b949e; margin:8px 0; }}
.sentiment {{ display:flex; align-items:center; gap:8px; margin:8px 0; font-size:0.85rem; }}
.bar {{ flex:1; height:10px; background:#21262d; border-radius:4px; overflow:hidden; max-width:300px; }}
.bar-call {{ height:100%; background:#3fb950; }}
.top-strikes {{ font-size:0.8rem; color:#8b949e; }}
.interp {{ font-size:0.85rem; color:#58a6ff; margin:8px 0; line-height:1.4; }}
.insights {{ list-style:none; margin:8px 0; padding:0; font-size:0.85rem; }}
.insights li {{ margin-bottom:4px; line-height:1.4; color:#8b949e; }}
.insight-chip {{ display:inline-block; padding:1px 6px; border-radius:4px; font-weight:600; font-size:0.75rem; margin-right:6px; }}
.sentiment-badge {{ display:inline-block; padding:2px 8px; border-radius:4px; font-size:0.75rem; font-weight:600; margin-left:6px; cursor:help; }}
.signal-chip {{ font-size:0.82rem; }}
.row-unusual td {{ background:#21262d; }}
.heat-premium-xl {{ background:#f0883e44; color:#f0883e; font-weight:600; }}
.heat-premium-lg {{ background:#f0883e22; color:#f0883e; font-weight:600; }}
.heat-premium-md {{ background:#d2992218; color:#d29922; }}
.heat-iv-high {{ background:#f8514922; color:#f85149; }}
.heat-iv-mid {{ background:#d2992218; color:#d29922; }}
.table-wrap {{ overflow-x:auto; margin-top:8px; }}
table {{ width:100%; border-collapse:collapse; font-size:0.82rem; }}
th, td {{ padding:6px 8px; text-align:right; border-bottom:1px solid #21262d; white-space:nowrap; }}
th {{ cursor:pointer; color:#8b949e; user-select:none; position:sticky; top:0; background:#161b22; z-index:1; }}
th:hover {{ color:#c9d1d9; }}
th .sort-glyph {{ margin-left:4px; font-size:0.7rem; }}
td:nth-child(2) {{ text-align:center; }}
.chip {{ display:inline-block; padding:0 4px; border-radius:3px; font-size:0.65rem; font-weight:600; margin-left:4px; vertical-align:middle; }}
.chip-otm {{ background:#58a6ff22; color:#58a6ff; }}
.chip-itm {{ background:#3fb95022; color:#3fb950; }}
.chip-weekly {{ background:#f0c67422; color:#f0c674; }}
.badge {{ display:inline-block; padding:1px 6px; border-radius:4px; font-size:0.75rem; font-weight:600; margin-right:4px; }}
.badge-u {{ background:#a371f733; color:#a371f7; }}
.badge-hu {{ background:#58a6ff33; color:#58a6ff; }}
.badge-b {{ background:#f0883e33; color:#f0883e; }}
.badge-rc {{ background:#f0c67433; color:#f0c674; }}
.err {{ color:#f85149; }}
footer {{ margin-top:24px; font-size:0.75rem; color:#8b949e; text-align:center; }}
</style>
</head>
<body>
<h1>Flow Scanner Report — {escape(ts)}</h1>
<div class="summary">
  <span>Tickers: {len(reports)}</span>
  <span>Unusual contracts: {total_unusual}</span>
  <span>Block premium flagged: {fmt_premium(total_premium)}</span>
  <span>Repeat-call tickers: {", ".join(repeat_tickers) or "—"}</span>
</div>
{glossary}
{"".join(cards)}
<footer>{escape(DISCLAIMER)}</footer>
<script>
document.querySelectorAll('.flow-link').forEach(link => {{
  link.addEventListener('click', function(e) {{
    if (window.parent !== window) {{
      e.preventDefault();
      window.parent.location.href = this.getAttribute('href');
    }}
  }});
}});
document.querySelectorAll('table.sortable').forEach(table => {{
  table.querySelectorAll('th').forEach((th, idx) => {{
    th.addEventListener('click', () => {{
      const tbody = table.querySelector('tbody');
      const rows = Array.from(tbody.querySelectorAll('tr'));
      const asc = th.dataset.sort !== 'asc';
      table.querySelectorAll('th').forEach(h => {{
        delete h.dataset.sort;
        const g = h.querySelector('.sort-glyph');
        if (g) g.remove();
      }});
      th.dataset.sort = asc ? 'asc' : 'desc';
      const glyph = document.createElement('span');
      glyph.className = 'sort-glyph';
      glyph.textContent = asc ? '▲' : '▼';
      th.appendChild(glyph);
      rows.sort((a, b) => {{
        let av = a.children[idx].textContent.replace(/[$,%KM]/g, '');
        let bv = b.children[idx].textContent.replace(/[$,%KM]/g, '');
        let an = parseFloat(av), bn = parseFloat(bv);
        if (!isNaN(an) && !isNaN(bn)) return asc ? an - bn : bn - an;
        return asc ? av.localeCompare(bv) : bv.localeCompare(av);
      }});
      rows.forEach(r => tbody.appendChild(r));
    }});
  }});
}});
</script>
</body>
</html>"""

    directory = os.path.dirname(os.path.abspath(output_path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".html", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(html)
        os.replace(tmp, output_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


def reports_to_json(reports: list[TickerReport], *, today: date | None = None) -> str:
    today = today or date.today()
    payload = {
        "generated_at": datetime.now().isoformat(timespec="seconds"),
        "reports": [_report_to_dict(r, today) for r in reports],
    }
    return json.dumps(payload, indent=2)


def write_json_report(reports: list[TickerReport], output_path: str) -> None:
    directory = os.path.dirname(os.path.abspath(output_path)) or "."
    os.makedirs(directory, exist_ok=True)
    fd, tmp = tempfile.mkstemp(suffix=".json", dir=directory)
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            fh.write(reports_to_json(reports))
        os.replace(tmp, output_path)
    except Exception:
        if os.path.exists(tmp):
            os.unlink(tmp)
        raise


# ---------------------------------------------------------------------------
# WATCH
# ---------------------------------------------------------------------------

def is_market_hours(now: datetime | None = None) -> bool:
    now = now or datetime.now(ET)
    if now.weekday() >= 5:
        return False
    open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
    close_t = now.replace(hour=16, minute=0, second=0, microsecond=0)
    return open_t <= now <= close_t


def seconds_until_market_open(now: datetime | None = None) -> float:
    now = now or datetime.now(ET)
    open_t = now.replace(hour=9, minute=30, second=0, microsecond=0)
    if now.weekday() >= 5:
        days = 7 - now.weekday()
        open_t = (now + timedelta(days=days)).replace(hour=9, minute=30, second=0, microsecond=0)
    elif now.time() >= open_t.time() and now.weekday() < 5:
        if now.time() <= datetime.strptime("16:00", "%H:%M").time():
            return 0
        open_t = (now + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
        if open_t.weekday() >= 5:
            open_t += timedelta(days=7 - open_t.weekday())
    elif now.time() < open_t.time():
        pass
    else:
        open_t = (now + timedelta(days=1)).replace(hour=9, minute=30, second=0, microsecond=0)
        if open_t.weekday() >= 5:
            open_t += timedelta(days=7 - open_t.weekday())
    return max(0, (open_t - now).total_seconds())


def _contract_key(c: Contract) -> tuple:
    return (c.ticker, c.expiry.isoformat(), c.strike, c.cp)


def _snapshot_flags(reports: list[TickerReport]) -> set[tuple]:
    keys: set[tuple] = set()
    for r in reports:
        for f in r.flags:
            if f.contract:
                keys.add((_contract_key(f.contract), f.kind))
            elif f.kind == "repeat_call":
                keys.add((r.ticker, "repeat_call"))
    return keys


def _print_diff(prev: set[tuple], curr: set[tuple], reports: list[TickerReport], console: Console) -> None:
    new_keys = curr - prev
    if not new_keys:
        return
    for key in new_keys:
        if len(key) == 2 and key[1] == "repeat_call":
            console.print(f"[bold yellow]NEW repeat-call activity: {key[0]}[/bold yellow]")
            continue
        (ckey, kind) = key
        ticker, expiry, strike, cp = ckey
        style = {
            "unusual": "bold magenta",
            "high_unusual": "bold blue",
            "block_premium": "bold orange3",
        }.get(kind, "bold")
        console.print(f"[{style}]NEW {kind}: {ticker} {cp} ${strike} exp {expiry}[/{style}]")


def watch_loop(
    tickers: list[str],
    interval: int,
    output_path: str,
    expirations: int,
    min_premium: float,
    min_size: int,
    console: Console,
) -> None:
    prev_snapshot: set[tuple] = set()
    slept_outside = False

    try:
        while True:
            now = datetime.now(ET)
            if not is_market_hours(now):
                wait = seconds_until_market_open(now)
                if not slept_outside:
                    console.print(
                        f"[yellow]Outside market hours. Sleeping until next open "
                        f"({wait / 3600:.1f}h)...[/yellow]"
                    )
                    slept_outside = True
                time.sleep(min(wait, interval))
                continue

            slept_outside = False
            reports = scan_tickers(tickers, expirations, min_premium, min_size)
            snap = _snapshot_flags(reports)
            _print_diff(prev_snapshot, snap, reports, console)
            prev_snapshot = snap

            if output_path:
                write_html_report(reports, output_path)

            time.sleep(interval)
    except KeyboardInterrupt:
        console.print("[dim]Watch loop stopped.[/dim]")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------

def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        description="Unusual options flow scanner (Cheddar Flow-style, free yfinance data)",
    )
    p.add_argument("tickers", nargs="*", help="Ticker symbols to scan")
    p.add_argument(
        "--watchlist",
        nargs="?",
        const="watchlist.txt",
        default=None,
        metavar="PATH",
        help="Load tickers from file (default: ./watchlist.txt)",
    )
    p.add_argument("--scan", action="store_true", help="Scan top 50 most active US tickers")
    p.add_argument(
        "--watch",
        action="store_true",
        help="Re-run every --interval seconds during market hours (9:30-16:00 ET)",
    )
    p.add_argument("--interval", type=int, default=60, help="Watch poll interval seconds (default 60)")
    p.add_argument("--expirations", type=int, default=3, help="Option expirations per ticker (default 3)")
    p.add_argument("--output", default="flow_report.html", help="HTML report path")
    p.add_argument("--json-out", default=None, metavar="PATH", help="JSON report path for Dash dashboard")
    p.add_argument("--min-premium", type=float, default=1_000_000, help="Block premium threshold")
    p.add_argument("--min-size", type=int, default=5000, help="High-unusual size threshold")
    p.add_argument("--no-html", action="store_true", help="Skip HTML report")
    p.add_argument("--json", action="store_true", help="Print JSON summary to stdout")
    p.add_argument("-q", "--quiet", action="store_true", help="Suppress terminal tables")
    return p


def resolve_tickers(args: argparse.Namespace) -> list[str]:
    tickers: list[str] = []
    if args.scan:
        tickers = fetch_most_active_symbols(50)
    elif args.watchlist:
        path = args.watchlist
        if not os.path.isfile(path):
            sys.exit(f"Watchlist not found: {path}")
        tickers = load_watchlist(path)
    if args.tickers:
        seen = set(tickers)
        for t in args.tickers:
            sym = t.upper()
            if sym not in seen:
                seen.add(sym)
                tickers.append(sym)
    if not tickers:
        raise SystemExit("Provide tickers, --watchlist, or --scan")
    return tickers


def main(argv: list[str] | None = None) -> int:
    logging.basicConfig(level=logging.WARNING, format="%(levelname)s: %(message)s")
    parser = build_parser()
    args = parser.parse_args(argv)

    if args.watch and args.scan:
        parser.error("--watch and --scan are mutually exclusive (use --watch with tickers or --watchlist)")

    try:
        tickers = resolve_tickers(args)
    except SystemExit as exc:
        parser.error(str(exc))

    console = Console(force_terminal=True)

    if args.watch:
        watch_loop(
            tickers,
            args.interval,
            "" if args.no_html else args.output,
            args.expirations,
            args.min_premium,
            args.min_size,
            console,
        )
        return 0

    reports = scan_tickers(
        tickers,
        args.expirations,
        args.min_premium,
        args.min_size,
    )

    if args.scan:
        reports.sort(key=lambda r: r.unusual_score, reverse=True)

    if not args.no_html:
        write_html_report(reports, args.output)
        if not args.quiet:
            console.print(f"[dim]HTML report: {args.output}[/dim]")

    if args.json_out:
        write_json_report(reports, args.json_out)
        if not args.quiet:
            console.print(f"[dim]JSON report: {args.json_out}[/dim]")

    if args.json:
        print(reports_to_json(reports))

    if not args.quiet:
        print_terminal_summary(reports, console, scan_mode=args.scan)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
