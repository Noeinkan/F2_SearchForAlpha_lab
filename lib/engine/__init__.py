"""The backtest engine's internals, one responsibility per module.

Public entry points live elsewhere and are the only things callers should
import: :func:`lib.strategy.backtest` for one symbol, and
:func:`lib.portfolio.backtest_portfolio` for a basket. Both drive the same
loop — a single-symbol run is a basket of one.

* :mod:`~lib.engine.state` — shared config, the one cash account, per-symbol state
* :mod:`~lib.engine.setup` — arguments → config and per-symbol contexts
* :mod:`~lib.engine.steps` — one symbol's exits, signal gating, sizing and fills
* :mod:`~lib.engine.resting` — one symbol's resting-order book and exit orders
* :mod:`~lib.engine.allocation` — ``CASH_ALLOCATION_RULE``, the same-bar cash split
* :mod:`~lib.engine.loop` — the phase-major bar loop over every symbol
* :mod:`~lib.engine.sizing`, :mod:`~lib.engine.signal_inputs`,
  :mod:`~lib.engine.results`, :mod:`~lib.engine.errors` — helpers re-exported
  from :mod:`lib.strategy`
"""
