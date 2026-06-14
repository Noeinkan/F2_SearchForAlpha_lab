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
            parts.append(f'<span class="badge {cls}">{label}</span>')
    for f in flags:
        if f.kind == "repeat_call" and contract is None:
            parts.append('<span class="badge badge-rc">RC</span>')
    return " ".join(parts)


def write_html_report(reports: list[TickerReport], output_path: str) -> None:
    ts = datetime.now().isoformat(timespec="seconds")
    total_unusual = sum(1 for r in reports for f in r.flags if f.kind == "unusual")
    total_premium = sum(
        f.contract.premium for r in reports for f in r.flags
        if f.kind == "block_premium" and f.contract
    )
    repeat_tickers = [r.ticker for r in reports if any(f.kind == "repeat_call" for f in r.flags)]

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

        rows = []
        flagged = [c for c in report.contracts if _contract_flags(report, c)]
        flagged.sort(key=lambda c: c.volume, reverse=True)
        for c in flagged[:50]:
            badges = _html_flag_badges(_contract_flags(report, c), c)
            rows.append(
                "<tr>"
                f"<td>{c.strike:.2f}</td><td>{c.cp}</td>"
                f"<td>{c.last:.2f}</td><td>{c.bid:.2f}</td><td>{c.ask:.2f}</td>"
                f"<td>{c.volume}</td><td>{c.open_interest}</td>"
                f"<td>{c.iv * 100:.1f}%</td><td>${c.premium:,.0f}</td>"
                f"<td>{badges}</td></tr>"
            )

        table_body = "\n".join(rows) if rows else '<tr><td colspan="10">No flagged contracts</td></tr>'

        top_calls = ", ".join(f"${s:.0f} ({v:,})" for s, v in report.top_call_strikes[:5]) or "—"
        top_puts = ", ".join(f"${s:.0f} ({v:,})" for s, v in report.top_put_strikes[:5]) or "—"

        cards.append(
            f"""<div class="card" data-ticker="{escape(report.ticker)}">
  <div class="card-header">
    <h2>{escape(report.ticker)} ${report.spot:,.2f} {rc_badge}</h2>
    <a class="flow-link" href="/fundamentals?ticker={escape(report.ticker)}">Open Fundamentals</a>
  </div>
  <div class="kpis">
    <span>Prev ${report.prev_close:,.2f}</span>
    <span>Day {report.day_low:,.2f}–{report.day_high:,.2f}</span>
    <span>52w {report.wk52_low:,.2f}–{report.wk52_high:,.2f}</span>
    <span>P/C vol {report.pc_vol_ratio:.2f}</span>
    <span>Score {report.unusual_score}</span>
  </div>
  <div class="sentiment">
    <span>Calls {report.call_pct:.1f}%</span>
    <div class="bar"><div class="bar-call" style="width:{report.call_pct:.1f}%"></div></div>
    <span>Puts {report.put_pct:.1f}%</span>
  </div>
  <p class="top-strikes">Top calls: {escape(top_calls)} | Top puts: {escape(top_puts)}</p>
  <table class="sortable">
    <thead><tr>
      <th>Strike</th><th>Type</th><th>Last</th><th>Bid</th><th>Ask</th>
      <th>Vol</th><th>OI</th><th>IV</th><th>Premium</th><th>Flags</th>
    </tr></thead>
    <tbody>{table_body}</tbody>
  </table>
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
.summary {{ display:flex; gap:16px; flex-wrap:wrap; margin-bottom:20px; }}
.summary span {{ background:#161b22; padding:8px 14px; border-radius:6px; border:1px solid #30363d; }}
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
table {{ width:100%; border-collapse:collapse; font-size:0.82rem; margin-top:8px; }}
th, td {{ padding:6px 8px; text-align:right; border-bottom:1px solid #21262d; }}
th {{ cursor:pointer; color:#8b949e; user-select:none; }}
th:hover {{ color:#c9d1d9; }}
td:nth-child(2) {{ text-align:center; }}
.badge {{ display:inline-block; padding:1px 6px; border-radius:4px; font-size:0.75rem; font-weight:600; margin-right:4px; }}
.badge-u {{ background:#a371f733; color:#a371f7; }}
.badge-hu {{ background:#58a6ff33; color:#58a6ff; }}
.badge-b {{ background:#f0883e33; color:#f0883e; }}
.badge-rc {{ background:#f0c67433; color:#f0c674; }}
.err {{ color:#f85149; }}
</style>
</head>
<body>
<h1>Flow Scanner Report — {escape(ts)}</h1>
<div class="summary">
  <span>Tickers: {len(reports)}</span>
  <span>Unusual contracts: {total_unusual}</span>
  <span>Block premium flagged: ${total_premium:,.0f}</span>
  <span>Repeat-call tickers: {", ".join(repeat_tickers) or "—"}</span>
</div>
{"".join(cards)}
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
      table.querySelectorAll('th').forEach(h => delete h.dataset.sort);
      th.dataset.sort = asc ? 'asc' : 'desc';
      rows.sort((a, b) => {{
        let av = a.children[idx].textContent.replace(/[$,%]/g, '');
        let bv = b.children[idx].textContent.replace(/[$,%]/g, '');
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


def reports_to_json(reports: list[TickerReport]) -> str:
    payload = []
    for r in reports:
        payload.append({
            "ticker": r.ticker,
            "spot": r.spot,
            "pc_vol_ratio": r.pc_vol_ratio,
            "pc_oi_ratio": r.pc_oi_ratio,
            "call_pct": r.call_pct,
            "put_pct": r.put_pct,
            "unusual_score": r.unusual_score,
            "error": r.error,
            "flags": [{"kind": f.kind, "message": f.message} for f in r.flags],
        })
    return json.dumps(payload, indent=2)


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

    if args.json:
        print(reports_to_json(reports))

    if not args.quiet:
        print_terminal_summary(reports, console, scan_mode=args.scan)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
