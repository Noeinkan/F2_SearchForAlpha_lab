"""
Fetch a tape spanning the regime calendar and score an agent bundle on it.

The combo variant (buy/sell columns from the optimizer leaderboard) lives in
``lib/dash/combo_regimes.py`` and reuses :func:`fetch_calendar_tape` and
:func:`build_payload` from here.
"""

from __future__ import annotations

import json
from datetime import UTC, date, datetime, timedelta
from typing import Any

import pandas as pd
import typer

from lib.agent_strategy import StrategyNotFoundError, load_bundle, params_to_indicator_settings
from lib.cli.contracts import CliError
from lib.data_processing import fetch_data
from lib.regimes.calendar import RegimeCalendar, RegimeCalendarError, load_calendar
from lib.regimes.slicer import ScoreFn, score_regimes
from lib.seeds import set_global_seed
from lib.signals.indicators import add_indicators, generate_signals, longest_lookback

# longest_lookback() counts bars; a daily bar is ~1.45 calendar days once
# weekends and holidays are in, so pad the fetch generously.
_CALENDAR_DAYS_PER_BAR = 1.5
_WARMUP_PAD_DAYS = 10


def today_utc() -> date:
    return datetime.now(UTC).date()


def fetch_calendar_tape(
    ticker: str,
    *,
    indicator_settings: dict[str, Any],
    interval: str,
    calendar: RegimeCalendar,
    today: date,
) -> pd.DataFrame:
    """OHLCV from before the first regime (plus indicator warmup) to today,
    with indicators and signal columns computed over the whole span."""
    warmup = int(longest_lookback(indicator_settings) * _CALENDAR_DAYS_PER_BAR) + _WARMUP_PAD_DAYS
    start = calendar.earliest_start - timedelta(days=warmup)
    raw = fetch_data(ticker, start.isoformat(), today.isoformat(), interval=interval)
    if raw.empty:
        return raw
    return generate_signals(add_indicators(raw.copy(), indicator_settings), indicator_settings)[0]


def build_payload(
    *,
    kind: str,
    subject: str,
    ticker: str,
    interval: str,
    params: dict[str, Any],
    tape: pd.DataFrame,
    calendar: RegimeCalendar,
    score: ScoreFn,
    today: date,
) -> dict[str, Any]:
    scored = score_regimes(tape, calendar=calendar, score=score, today=today)
    now = datetime.now(UTC)
    return {
        "kind": kind,
        "subject": subject,
        "ticker": ticker.upper(),
        "interval": interval,
        "params": params,
        "data": {
            "from": pd.Timestamp(tape.index[0]).date().isoformat() if not tape.empty else None,
            "to": pd.Timestamp(tape.index[-1]).date().isoformat() if not tape.empty else None,
        },
        **scored,
        "regimes_id": f"regimes_{now.strftime('%Y%m%d_%H%M%S_%f')}",
        "recorded_at": now.isoformat(),
    }


def run_bundle_regimes(
    *,
    strategy_name: str,
    params: dict[str, Any] | None = None,
    ticker: str | None = None,
    interval: str = "1d",
    initial_capital: float = 10_000.0,
    seed: int = 42,
    calendar: RegimeCalendar | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    """Score an agent bundle in every calendar regime.

    ``params`` defaults to the bundle's ``live_params``; ``ticker`` to the
    bundle's own symbol.
    """
    # Same per-slice backtest as walk-forward, so the two reports agree on
    # position sizing and execution params.
    from lib.walkforward.runner import _backtest_metrics

    bundle = load_bundle(strategy_name)
    calendar = calendar or load_calendar()
    today = today or today_utc()
    effective = dict(params if params is not None else bundle.live_params)
    symbol = ticker or bundle.ticker
    if not symbol:
        raise ValueError(f"Strategy {strategy_name} has no ticker configured")
    set_global_seed(seed)

    tape = fetch_calendar_tape(
        symbol,
        indicator_settings=params_to_indicator_settings(effective),
        interval=interval,
        calendar=calendar,
        today=today,
    )
    return build_payload(
        kind="bundle",
        subject=strategy_name,
        ticker=symbol,
        interval=interval,
        params=effective,
        tape=tape,
        calendar=calendar,
        score=lambda s: _backtest_metrics(s, bundle, initial_capital, effective, interval=interval),
        today=today,
    )


def run_regimes_cli(
    *,
    name: str,
    params_arg: str | None,
    ticker: str | None,
    interval: str,
    initial_capital: float,
    seed: int,
    json_output: bool,
) -> None:
    from lib.timeframes import IntervalError, normalize_interval
    from lib.walkforward.runner import _resolve_params

    try:
        canon = normalize_interval(interval)
    except IntervalError as exc:
        typer.echo(json.dumps(CliError("invalid_interval", str(exc)).as_dict()))
        raise typer.Exit(code=2) from exc

    params: dict[str, Any] | None = None
    if params_arg:
        try:
            params = _resolve_params(params_arg)
        except (ValueError, json.JSONDecodeError) as exc:
            typer.echo(json.dumps(CliError("invalid_params", str(exc)).as_dict()))
            raise typer.Exit(code=2) from exc

    try:
        calendar = load_calendar()
    except (OSError, RegimeCalendarError) as exc:
        typer.echo(json.dumps(CliError("invalid_regime_calendar", str(exc)).as_dict()))
        raise typer.Exit(code=2) from exc

    try:
        payload = run_bundle_regimes(
            strategy_name=name,
            params=params,
            ticker=ticker,
            interval=canon,
            initial_capital=initial_capital,
            seed=seed,
            calendar=calendar,
        )
    except StrategyNotFoundError as exc:
        typer.echo(json.dumps(CliError("unknown_strategy", f"No agent strategy named {name!r}.").as_dict()))
        raise typer.Exit(code=2) from exc
    except Exception as exc:
        typer.echo(json.dumps(CliError("regimes_failed", str(exc)).as_dict()))
        raise typer.Exit(code=3) from exc

    if json_output:
        typer.echo(json.dumps(payload, indent=2, default=str))
        return

    metric = payload["rule"]["metric"]
    typer.echo(f"{payload['subject']}  {payload['ticker']}  [{payload['interval']}]  {payload['regimes_id']}")
    for row in payload["regimes"]:
        m = row["metrics"] or {}
        mark = {True: "PASS", False: "fail", None: "  - "}[row["passed"]]
        value = f"{float(m[metric]):+.3f}" if m else "   n/a"
        ret = f"{float(m['total_return']):+.4f}" if m else "    n/a"
        bh = f"{float(m['benchmark_return']):+.4f}" if m else "    n/a"
        typer.echo(
            f"  {mark}  {row['label']:<16s} {row['from']} -> {row['to']}  "
            f"{metric} {value}  return {ret}  buy&hold {bh}  "
            f"trades {int(m.get('num_trades', 0)) if m else 0:>3d}  [{row['coverage']}]"
        )
    verdict = payload["verdict"]
    typer.echo(f"  verdict  {verdict['status'].upper()}  ({verdict['reason']})")
