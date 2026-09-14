"""
Regime slicing for the Dash Optimizer's combo winner.

Mirrors ``lib.regimes.runner.run_bundle_regimes`` but backtests an arbitrary
buy/sell column list through the same per-slice path as the combo walk-forward.
"""

from __future__ import annotations

from datetime import date
from typing import Any

from lib.dash.combo_walkforward import ComboSpec, _metrics_for_slice
from lib.regimes.calendar import RegimeCalendar, load_calendar
from lib.regimes.runner import build_payload, fetch_calendar_tape, today_utc


def run_combo_regimes(
    *,
    combo: ComboSpec,
    interval: str = "1d",
    initial_capital: float = 10_000.0,
    calendar: RegimeCalendar | None = None,
    today: date | None = None,
) -> dict[str, Any]:
    calendar = calendar or load_calendar()
    today = today or today_utc()
    buy = list(combo.buy_signals)
    sell = list(combo.sell_signals)
    kwargs = dict(combo.backtest_kwargs or {})

    tape = fetch_calendar_tape(
        combo.ticker,
        indicator_settings=combo.indicator_settings or {},
        interval=interval,
        calendar=calendar,
        today=today,
    )
    return build_payload(
        kind="combo",
        subject=f"combo:{','.join(buy)}|{','.join(sell)}",
        ticker=combo.ticker,
        interval=interval,
        params={"buy_signals": buy, "sell_signals": sell},
        tape=tape,
        calendar=calendar,
        score=lambda s: _metrics_for_slice(
            s,
            capital=initial_capital,
            buy=buy,
            sell=sell,
            interval=interval,
            backtest_kwargs=kwargs,
        ),
        today=today,
    )
