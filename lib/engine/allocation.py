"""``CASH_ALLOCATION_RULE`` — who gets the cash when buys outrun it on one bar.

The bar data cannot say which of several same-bar buys reached the market
first, so, as with ``PRIORITY_RULE`` in :mod:`lib.orders`, the engine states a
deterministic and pessimistic rule rather than let the order of a ticker list
decide. The reasoning, the rejected alternatives and a worked example are in
[docs/portfolio-semantics.md](../../docs/portfolio-semantics.md) §4.
"""

from __future__ import annotations

import math
from typing import Callable, List, Sequence, Tuple

# One-line statement of the rule, quoted by the docs so there is one wording.
CASH_ALLOCATION_RULE = (
    "equal-share water-fill — cash is offered to competing buys in equal shares, "
    "a buy that needs less than its share releases the rest to the others, and "
    "whole-share rounding leaves the residue in cash"
)


def water_fill(
    cash: float,
    requests: Sequence[Tuple[float, float]],
    round_units: Callable[[float], float],
) -> List[float]:
    """Units each request receives, given ``(units_wanted, cost_per_unit)`` pairs.

    Each pass offers the remaining cash in equal shares to every request still
    short. A request whose share already buys everything it asked for is filled
    in full and drops out, returning the unused part of its share; the rest are
    re-offered what is left. When no request can be satisfied by its share,
    each takes its share and the cash is gone.

    Satisfaction is tested in **units**, not currency — "does my share buy the
    units I asked for" — so a request is never shorted a whole share by the
    last-bit float error in ``units * cost / cost``. With one request this is
    exactly ``min(wanted, round_units(cash / cost))``, the single-symbol
    affordability clamp.

    Nothing mutates inside a pass and the cash released by satisfied requests is
    summed with :func:`math.fsum`, so the answer does not depend on the order
    of *requests* at all — not even in the last bit.

    Args:
        cash: Cash available to the buys, after the bar's sells have settled.
        requests: ``(units_wanted, cost_per_unit)`` per competing buy, where the
            cost includes slippage and fees.
        round_units: The run's share-rounding rule.

    Returns:
        Units for each request, in the order given. A request that asked for
        nothing, or has no positive cost, receives ``0``.
    """
    granted = [0.0] * len(requests)
    active = [
        k for k, (wanted, cost) in enumerate(requests) if wanted > 0 and cost > 0
    ]
    remaining = float(cash)

    while active and remaining > 0:
        share = remaining / len(active)
        satisfied = [
            k for k in active if round_units(share / requests[k][1]) >= requests[k][0]
        ]
        if not satisfied:
            for k in active:
                wanted, cost = requests[k]
                granted[k] = min(wanted, round_units(share / cost))
            break
        for k in satisfied:
            granted[k] = requests[k][0]
        remaining = math.fsum(
            [remaining, *(-(requests[k][0] * requests[k][1]) for k in satisfied)]
        )
        done = set(satisfied)
        active = [k for k in active if k not in done]

    return [round_units(units) for units in granted]
