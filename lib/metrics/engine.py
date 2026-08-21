"""``BacktestMetrics`` and the one function that produces it.

Everything that reports a backtest — the ``sfa`` CLI's JSON contract, the
Bayesian and grid optimisers, walk-forward, the Dash Backtest tab and the
combinatorial optimizer's leaderboard — goes through :func:`compute_metrics`.

Trade statistics are read from the engine's round-trip ledger
(``result_df.attrs['trades']``, see :mod:`lib.metrics.ledger`). They are *not*
reconstructed by scanning the ``Units`` column: that reconstruction could not
see partial exits, could not separate fees from price moves, and disagreed with
the ledger on any scale-in.

Units are documented on :class:`BacktestMetrics` and enforced by
``lib/tests/test_metrics.py``. In short: rates are fractions, ratios are
annualised at the bar interval, and ``max_drawdown`` is positive.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass
from typing import Optional

import pandas as pd

from lib.metrics import core

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class BacktestMetrics:
    """The metric contract. Field order is the order the CLI prints them.

    Units
    -----
    ``total_return``, ``cagr``, ``max_drawdown``, ``win_rate``, ``exposure``
        Fractions. ``0.2`` is 20%. ``max_drawdown`` is a **positive magnitude**.
    ``sharpe``, ``sortino``, ``calmar``
        Annualised ratios, using the bar interval's periods-per-year.
    ``profit_factor``
        Ratio; :data:`lib.metrics.core.PROFIT_FACTOR_SENTINEL` when there are
        winners and no losers.
    ``num_trades``
        **Closed round trips.** Not fills — see ``num_fills``. A position still
        open on the last bar is counted in ``open_trades`` instead, so an
        accumulation-mode run reports ``num_trades == 0``.
    ``num_fills``
        Individual executions, buys plus sells.
    ``avg_win``, ``avg_loss``, ``expectancy``, ``total_fees``
        Currency, in the units of ``initial_capital``. ``avg_loss`` is negative.
    ``avg_holding_bars``
        Bars of tape held per closed round trip — never calendar time, so the
        hours a market was shut are not in it.
    ``avg_holding_sessions``
        Session boundaries crossed per closed round trip. ``0`` means trades
        opened and closed inside one session; on a daily tape it matches
        ``avg_holding_bars``.
    ``turnover``
        Gross traded notional over mean equity; unitless.
    """

    total_return: float = 0.0
    cagr: float = 0.0
    sharpe: float = 0.0
    sortino: float = 0.0
    calmar: float = 0.0
    max_drawdown: float = 0.0
    num_trades: int = 0
    num_fills: int = 0
    open_trades: int = 0
    win_rate: float = 0.0
    profit_factor: float = 0.0
    avg_win: float = 0.0
    avg_loss: float = 0.0
    expectancy: float = 0.0
    avg_holding_bars: float = 0.0
    avg_holding_sessions: float = 0.0
    total_fees: float = 0.0
    exposure: float = 0.0
    turnover: float = 0.0

    def as_dict(self) -> dict[str, float | int]:
        return asdict(self)


def _ledger_from(
    df: pd.DataFrame, trades: Optional[pd.DataFrame], context: str
) -> Optional[pd.DataFrame]:
    """Resolve the trade ledger, warning loudly when it is missing.

    ``DataFrame.attrs`` does not survive ``pd.concat``, a parquet round trip or
    a groupby. Every caller computes metrics on the frame ``backtest()`` just
    returned, so the ledger is normally right there — but if it ever goes
    missing the trade statistics silently become zero, and that is worth a line
    in the log rather than a plausible-looking wrong number.
    """
    if trades is not None:
        return trades
    ledger = df.attrs.get("trades")
    if ledger is None:
        logger.warning(
            "No trade ledger on the result frame (%s); trade statistics will be zero. "
            "DataFrame.attrs is dropped by concat/parquet — compute metrics on the "
            "frame backtest() returned, or pass trades= explicitly.",
            context,
        )
    return ledger


def compute_metrics(
    df: pd.DataFrame,
    initial_capital: Optional[float] = None,
    *,
    interval: str = "1d",
    periods_per_year: Optional[int] = None,
    trades: Optional[pd.DataFrame] = None,
    risk_free_rate: Optional[float] = None,
    context: str = "",
) -> BacktestMetrics:
    """Summarise a backtest result frame.

    Args:
        df: A frame returned by ``lib.strategy.backtest``.
        initial_capital: Starting capital. Defaults to the first bar's
            ``Portfolio_Value``, which is what the engine seeds it with.
        interval: Bar interval (``1d`` / ``1h`` / ``4h``), used to annualise.
        periods_per_year: Overrides ``interval``'s annualisation factor.
        trades: The round-trip ledger. Defaults to ``df.attrs['trades']``.
        risk_free_rate: Annual hurdle. Defaults to the configured convention.
        context: Free text naming the caller, used only in the missing-ledger
            warning.
    """
    from lib.timeframes import periods_per_year as ppy_for

    if df is None or len(df) == 0:
        return BacktestMetrics()

    ppy = int(periods_per_year) if periods_per_year is not None else ppy_for(interval)

    equity = df["Portfolio_Value"] if "Portfolio_Value" in df.columns else None
    returns = df["Strategy_Returns"] if "Strategy_Returns" in df.columns else None

    total = core.total_return(equity, initial_capital)
    growth = core.cagr(equity, periods_per_year=ppy, initial_capital=initial_capital)
    max_dd = core.max_drawdown(equity)

    stats = core.round_trip_stats(_ledger_from(df, trades, context or "unnamed caller"))

    return BacktestMetrics(
        total_return=total,
        cagr=growth,
        sharpe=core.sharpe_ratio(
            returns, periods_per_year=ppy, risk_free_rate=risk_free_rate
        ),
        sortino=core.sortino_ratio(
            returns, periods_per_year=ppy, risk_free_rate=risk_free_rate
        ),
        calmar=core.calmar_ratio(growth, max_dd),
        max_drawdown=max_dd,
        num_trades=stats.num_trades,
        num_fills=core.count_fills(df.get("Units_to_buy"), df.get("Units_to_sell")),
        open_trades=stats.open_trades,
        win_rate=stats.win_rate,
        profit_factor=stats.profit_factor,
        avg_win=stats.avg_win,
        avg_loss=stats.avg_loss,
        expectancy=stats.expectancy,
        avg_holding_bars=stats.avg_holding_bars,
        avg_holding_sessions=stats.avg_holding_sessions,
        total_fees=stats.total_fees,
        exposure=core.exposure(df.get("Units")),
        turnover=core.turnover(
            df.get("Units_to_buy"), df.get("Units_to_sell"), df.get("Close"), equity
        ),
    )


__all__ = ["BacktestMetrics", "compute_metrics"]
