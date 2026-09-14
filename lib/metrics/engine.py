"""``BacktestMetrics`` and the one function that produces it.

Everything that reports a backtest — the ``sfa`` CLI's JSON contract, the
Bayesian and grid optimisers, walk-forward, the Dash Backtest tab and the
combinatorial optimizer's leaderboard — goes through :func:`compute_metrics`.

Trade statistics are read from the engine's round-trip ledger
(``result_df.attrs['trades']``, see :mod:`lib.metrics.ledger`). They are *not*
reconstructed by scanning the ``Units`` column: that reconstruction could not
see partial exits, could not separate fees from price moves, and disagreed with
the ledger on any scale-in.

Benchmark-relative figures come from :mod:`lib.metrics.benchmark`, measured
against the ``Returns`` column the engine already writes — buy-and-hold on the
same bars. The confidence figures come from :mod:`lib.metrics.deflated`.

Units are documented on :class:`BacktestMetrics` and enforced by
``lib/tests/test_metrics.py``. In short: rates are fractions, ratios are
annualised at the bar interval, and ``max_drawdown`` is positive.
"""

from __future__ import annotations

import logging
from dataclasses import asdict, dataclass, replace
from typing import Any, Optional

import pandas as pd

from lib.metrics import core, deflated
from lib.metrics.benchmark import benchmark_stats

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

    Benchmark-relative
    ------------------
    All measured against buy-and-hold on the same bars — the ``Returns``
    column. See :mod:`lib.metrics.benchmark`.

    ``benchmark_return``
        Fraction. What holding the symbol over the window returned.
    ``excess_return``
        Fraction. ``total_return - benchmark_return``, an arithmetic
        difference with no risk adjustment. This is the figure the combo
        search has always shown as "Alpha".
    ``alpha``
        Fraction, annualised **Jensen's alpha** — the excess return that beta
        does *not* explain. Not the same number as ``excess_return``.
    ``beta``, ``up_capture``, ``down_capture``
        Ratios. ``down_capture`` below 1 means the strategy lost less than the
        benchmark on the benchmark's down bars.
    ``information_ratio``
        Annualised active return over tracking error.
    ``tracking_error``
        Fraction, annualised standard deviation of the active return.

    Confidence
    ----------
    See :mod:`lib.metrics.deflated`. Both are probabilities in ``[0, 1]``.

    ``psr``
        Probabilistic Sharpe: the chance the true Sharpe is above zero, given
        this sample's length, skew and kurtosis.
    ``deflated_sharpe``
        The same probability against the Sharpe the best of ``num_trials``
        would reach on noise alone. With ``num_trials == 1`` it equals ``psr``
        — a single backtest has no selection bias to deflate. The optimizer
        re-deflates its leaderboard with the real combination count; see
        :func:`with_deflated_sharpe`.
    ``num_trials``
        Trials folded into ``deflated_sharpe``. ``1`` for a lone backtest.
    ``num_bars``, ``returns_skew``, ``returns_kurtosis``, ``periods_per_year``
        The sample the two probabilities were computed from, carried along so
        a caller that later learns the trial count can redo the deflation
        without re-running the backtest. ``returns_kurtosis`` is **non-excess**
        — 3.0 is normal.
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
    benchmark_return: float = 0.0
    excess_return: float = 0.0
    alpha: float = 0.0
    beta: float = 0.0
    information_ratio: float = 0.0
    tracking_error: float = 0.0
    up_capture: float = 0.0
    down_capture: float = 0.0
    psr: float = 0.0
    deflated_sharpe: float = 0.0
    num_trials: int = 1
    num_bars: int = 0
    returns_skew: float = 0.0
    returns_kurtosis: float = deflated.NORMAL_KURTOSIS
    periods_per_year: int = 252

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
    benchmark_returns: Optional[Any] = None,
    num_trials: int = 1,
    trial_sharpe_std: Optional[float] = None,
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
        benchmark_returns: Per-bar benchmark returns. Defaults to the frame's
            ``Returns`` column — buy-and-hold on the same bars. Pass an empty
            series to skip the benchmark-relative block entirely.
        num_trials: How many configurations were searched to arrive at this
            one, folded into ``deflated_sharpe``. Leave at 1 for a single
            backtest; the optimizer passes its combination count.
        trial_sharpe_std: Dispersion of the annualised Sharpe ratios across
            those trials. Required for the deflation to bite — with one trial,
            or none supplied, ``deflated_sharpe`` equals ``psr``.
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

    sharpe = core.sharpe_ratio(returns, periods_per_year=ppy, risk_free_rate=risk_free_rate)

    # Buy-and-hold on the same bars. ``Returns`` is the market series the engine
    # already writes; a caller with its own benchmark passes it in.
    bench_source = benchmark_returns
    if bench_source is None and "Returns" in df.columns:
        bench_source = df["Returns"]
    bench = benchmark_stats(
        returns,
        bench_source,
        periods_per_year=ppy,
        strategy_total_return=total,
        risk_free_rate=risk_free_rate,
    )

    n_obs, skew, kurtosis = deflated.sample_moments(returns)
    psr = deflated.probabilistic_sharpe_ratio(
        sharpe, n_obs=n_obs, skew=skew, kurtosis=kurtosis, periods_per_year=ppy
    )
    dsr = deflated.deflated_sharpe_ratio(
        sharpe,
        n_obs=n_obs,
        skew=skew,
        kurtosis=kurtosis,
        num_trials=num_trials,
        sharpe_std=trial_sharpe_std,
        periods_per_year=ppy,
    )

    return BacktestMetrics(
        total_return=total,
        cagr=growth,
        sharpe=sharpe,
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
        benchmark_return=bench.benchmark_return,
        excess_return=bench.excess_return,
        alpha=bench.alpha,
        beta=bench.beta,
        information_ratio=bench.information_ratio,
        tracking_error=bench.tracking_error,
        up_capture=bench.up_capture,
        down_capture=bench.down_capture,
        psr=psr,
        deflated_sharpe=dsr,
        num_trials=max(1, int(num_trials or 1)),
        num_bars=n_obs,
        returns_skew=skew,
        returns_kurtosis=kurtosis,
        periods_per_year=ppy,
    )


def with_deflated_sharpe(
    metrics: BacktestMetrics, *, num_trials: int, trial_sharpe_std: Optional[float]
) -> BacktestMetrics:
    """Redo the deflation on an existing result, now that the search is sized.

    ``compute_metrics`` runs once per candidate and cannot know how many other
    candidates there were, or how widely they scored. The optimizer knows both
    only after the sweep finishes, and this folds them in without re-running a
    single backtest — every input the deflation needs is already on *metrics*.
    """
    dsr = deflated.deflated_sharpe_ratio(
        metrics.sharpe,
        n_obs=metrics.num_bars,
        skew=metrics.returns_skew,
        kurtosis=metrics.returns_kurtosis,
        num_trials=num_trials,
        sharpe_std=trial_sharpe_std,
        periods_per_year=metrics.periods_per_year,
    )
    return replace(
        metrics, deflated_sharpe=dsr, num_trials=max(1, int(num_trials or 1))
    )


__all__ = ["BacktestMetrics", "compute_metrics", "with_deflated_sharpe"]
