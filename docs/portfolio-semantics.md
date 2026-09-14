# Portfolio semantics — what a multi-asset backtest means

Decided 2026-08-22, closing roadmap **3.8.1**. Everything from 3.8.2 to 3.8.9 reads
from this page: the panel alignment, the per-symbol engine state, the contention
rule, the result contract and the portfolio metrics all follow from the choices
below rather than being re-argued in each.

When this page was written the engine was scalar top to bottom — one `units`,
one `cash`, 1-D price arrays, one ticker per bundle. It decided what the
generalised version had to mean, in the same spirit as `PRIORITY_RULE` in
[lib/orders.py](../lib/orders.py): where the bar data cannot say what happened,
state a deterministic and pessimistic rule out loud rather than let an
implementation detail decide it.

**Implemented 2026-09-14 (3.8.3, 3.8.4)** in [lib/engine/](../lib/engine/), with
[lib/portfolio.py](../lib/portfolio.py) as the entry point. §1–§4, §6 and §8 are
live; §7's benchmark is computed on the provisional result; the `max_weight` cap
in §1 is not built. Where the implementation had to decide something this page
had not, the decision is recorded under the section it belongs to, marked
*Implementation note*.

## The decisions, in one table

| Question | Decision |
|---|---|
| Shared cash or per-sleeve? | **One cash account.** Per-sleeve is expressed as an optional per-symbol exposure cap, not as separate books |
| Sizing base | **Total** portfolio value — cash plus every symbol's mark, from the *previous* bar |
| Two symbols buy, cash is short | **Equal-share water-fill** (`CASH_ALLOCATION_RULE`), order-independent, no partial fills invented |
| Fills per symbol per bar | **Still one.** The portfolio allows N of them, one per symbol |
| Same-bar sell to buy funding | **Allowed.** Credits settle before debits within the bar (T+0) |
| Rebalance cadence | **Signal-driven only.** No calendar rebalance in 3.8 |
| A symbol with no bar | **Valued, not traded** — last close carries the mark, execution is skipped |
| Portfolio benchmark | **Equal-weight buy-and-hold of the same basket**, bought once at the first tradable bar |
| Currency | **Single-currency basket.** `fx_fee_pct` keeps its present flat-rate meaning |
| Strategy config | **One config for the whole basket** in v1; signals stay per-symbol because each symbol's frame carries its own indicator columns |

---

## 1. One cash account, not N sleeves

**Decision: a single `cash` balance funds every symbol.**

Per-sleeve accounting — split the capital N ways at t0 and let each symbol run
against its own purse — is already available today without touching the engine:
run N single-symbol backtests and sum the equity curves. Building the engine for
that would be building nothing. The only thing a real portfolio engine adds is
**cash contention**: the fact that a buy in one name can starve a buy in another,
and that a stop-out in a third can fund both. That is the question 3.8 exists to
answer, so the accounting has to be single-pool.

Per-sleeve behaviour survives as a *sizing policy* on top of the single pool: an
optional per-symbol exposure cap (`max_weight`, a fraction of total portfolio
value) that clamps a symbol's position the way `affordable_units` clamps it to
cash. Set every cap to `1/N` and the sleeves stop competing, which is the
per-sleeve model as a special case — the same way the single-symbol engine is
about to become the one-symbol case of the portfolio engine.

**Rejected:** separate books per symbol. It reduces to N runs and a spreadsheet.

## 2. Sizing reads the *total* portfolio value, from the previous bar

**Decision: `prev_portfolio_value` is computed once per bar, before any symbol
trades, as `cash + sum(units_i * close_i)` at bar `i-1`.**

Two properties matter, and both are load-bearing:

* **Total, not per-sleeve.** `percentage_of_portfolio(2%)` means 2% of the whole
  portfolio, not 2% of a notional slice. Every sizer in `get_position_sizer`
  inherits this unchanged.
* **Previous bar, and the same number for everyone.** Sizing off a running
  balance that phase-2 sells have already topped up would make each symbol's
  size depend on which symbols traded before it — the exact order-dependence
  this page exists to remove. The single-symbol engine already sizes off
  `portfolio_value[i - 1]`; the portfolio engine keeps that line and only
  widens what it sums.

This finally makes `strategy_mode='rebalancing'` mean what its name always
claimed. `position_size_pct` becomes a per-symbol **target weight against total
portfolio value**. Weights are **not normalised** — a basket of five symbols each
asking for 100% is not silently rescaled to 20%; the allocation rule below and
the affordability clamp handle the overflow, exactly as `size_buy` already caps
an over-weight request at available cash today. Normalising would quietly change
what the user asked for. The equal-weight default for an N-symbol basket is
`position_size_pct = 100 / N`, and that is a default, not a constraint.

## 3. The per-bar sequence is phase-major, not symbol-major

**Decision: each phase runs across every symbol before the next phase starts.**

The single-symbol loop is a strict cascade — work the book, else check exits,
else process signals, and *a fill consumes the bar*. The portfolio version keeps
that cascade **per symbol** and reorders it across symbols so that everything
which releases cash happens before anything that spends it:

1. **Expire and arm** every symbol's order book.
2. **Credits.** Every symbol's cash-releasing fill: resting sells, bracket stops
   and targets, the trailing stop, take profit, signal sells. A sell is always
   affordable, so there is no contention here and no ordering to decide.
3. **Debits.** Collect every symbol's would-be buy — resting buy fills first,
   then signal buys, which is the existing "placed earlier wins" rule — and
   settle them against the one cash balance with the rule in §4.
4. **Sync exit orders** per symbol, writing the levels the *next* bar is tested
   against.
5. **Snapshot** per-symbol state, then the portfolio totals.

A symbol resolves in phase 2 or phase 3, never both, so **the
one-fill-per-symbol-per-bar rule is unchanged**. What changes is only that N
symbols may each take their one fill on the same bar.

Phase 2 running before phase 3 means **cash from a same-bar sell funds a same-bar
buy**. That is T+0 and it is generous against a real broker's settlement cycle;
it is stated here rather than discovered, and a `settle_bars` parameter is the
obvious escape hatch if the optimism ever needs measuring. It is also the only
choice consistent with the single-symbol engine, where the cash from any exit is
available on the very next bar with no settlement delay.

*Implementation note — reading and moving cash.* No fill writes the balance
directly. Fills queue their credit or debit, and the queue is folded in once at
the end of phase 2 and once at the end of phase 3 with an exactly-rounded sum
(`math.fsum`). A plain running `cash += x` over the symbols would make the last
bits of every balance depend on list order — which in turn can tip a
whole-share rounding. Everything read during phase 2 (the accumulation cap, the
clamp on a newly placed limit order) therefore sees the cash the bar opened
with, the same number for every symbol.

*Implementation note — a resting buy and a same-bar sale.* The single-symbol
book walk cancels a resting buy that cannot afford one unit and moves on to the
next touched order, which may be a sell. To keep that walk intact the test is
made in phase 2 against the bar-opening cash: a resting buy that cannot buy one
unit with it is cancelled `unaffordable`, as before; one that can becomes a
phase-3 request and may be topped up by other symbols' same-bar sales. A same-bar
sale can therefore enlarge a fundable resting buy but cannot rescue one that was
unfundable when the bar opened. Market buys on a signal have no such test and
take the full T+0 benefit. A phase-3 buy that the allocation rule leaves at zero
units is cancelled `unaffordable` if it was resting, and otherwise takes the
unaffordable-buy path described in §4.

## 4. `CASH_ALLOCATION_RULE` — equal-share water-fill

When several symbols want to buy on one bar and the cash will not cover them all,
the bar data cannot say who traded first. The rule, implemented as `water_fill`
in [lib/engine/allocation.py](../lib/engine/allocation.py):

> **Cash is offered to competing buys in equal shares. A symbol that needs less
> than its share takes only what it needs and the remainder is re-split, equally,
> among those still short — repeatedly, until the cash is gone or every request
> is met. Whole-share rounding leaves the residue in cash.**

Formally, with cash `C` after phase 2 and requests `r_i` (each symbol's
`size_buy` quantity at its own fill level, times its own fee- and
slippage-inclusive cost per unit):

```
remaining = C
budget    = {i: 0}
active    = {i : r_i > 0}

while remaining > EPS and active:
    share     = remaining / len(active)
    satisfied = {i in active : r_i - budget_i <= share}
    if satisfied:
        for i in satisfied:
            remaining -= r_i - budget_i
            budget_i   = r_i
        active -= satisfied
    else:
        for i in active:
            budget_i += share
        remaining = 0

units_i = round_units(budget_i / cost_per_unit_i)
```

It terminates in at most `len(active)` iterations, mutates nothing inside a pass,
and therefore gives the same answer for any ordering of the symbols.

*Implementation note.* The code tests satisfaction in units rather than
currency — `round_units(share / cost_per_unit_i) >= units_wanted_i` — which is
the same condition without the float trap of dividing `units * cost` back by
`cost` and landing a hair under a whole share. With one request it is exactly
`min(units_wanted, round_units(cash / cost_per_unit))`, the single-symbol
affordability clamp.

### Why this one

Four properties, and the alternatives each break at least one:

* **Deterministic** — same inputs, same fills, on any platform.
* **Order-independent** — no symbol is structurally advantaged. This is the one
  that kills the obvious implementation.
* **Pessimistic under ambiguity** — nobody gets more than an equal claim on
  contested cash.
* **Invents no partial fills** — each symbol is clamped once, exactly as
  `affordable_units` clamps it today. Fill counts stay meaningful.

**Rejected — first-come by column order.** The natural implementation, and a
silent bias: whichever ticker sits leftmost in the panel gets funded first in
every backtest in the repo. Alphabetical ordering would make AAPL structurally
richer than ZM for reasons that have nothing to do with either strategy.

**Rejected — strict pro-rata** (scale every request by `C / sum(r)`). It fills
every order partially, so no order ever gets what it asked for, and under
whole-share rounding a small scaled request rounds to zero units while still
consuming a rung of the scale-in ramp. It also inflates `num_fills` against
`num_trades`.

**Rejected — rank by signal strength.** `calculate_signal_strengths` exists, but
`use_signal_strength` is off by default and strengths are not comparable across
different indicators, so the rule would be undefined for most runs.

**Rejected — single-pass equal split with no re-fill.** Simpler, and a strict
subset of the rule above: it can only ever leave *more* cash idle, never fund a
different symbol. But leaving one symbol's unused share stranded while another
sits starved looks like a bug in the equity curve, so it is not worth the
simplicity.

### What an under-funded buy looks like in the output

It takes the existing unaffordable-buy path: `buy_triggered` is set, `_hold` runs,
the cooldown is **not** armed, and the scale-in ramp has **already advanced**
inside `size_buy` — a rung is consumed by a buy that did not fill, which is
today's behaviour and stays today's behaviour.

Note the gap this exposes: `Buy_Trigger_Rejected` is set only by the
consecutive-signal gate in `process_signals`, never by affordability. So a buy
starved by contention is indistinguishable in the flags from a buy starved by an
empty account. A portfolio run makes that ambiguity common rather than rare, so
3.8.5 should add an explicit `Buy_Unfunded` column instead of overloading the
rejection flag.

### Worked example

$10,000 cash, three symbols signalling a buy on the same bar, whole shares,
5 bp slippage and 15 bp fees (so cost per unit is `price * 1.0005 * 1.0015`):

| Symbol | Price | Units wanted | Cost/unit | Requested |
|---|---:|---:|---:|---:|
| A | 50 | 20 | 50.100 | 1,002.00 |
| B | 200 | 40 | 200.400 | 8,016.00 |
| C | 350 | 30 | 350.700 | 10,521.00 |
| | | | | **19,539.00** |

Pass 1 — share is 10,000 / 3 = 3,333.33. A needs 1,002.00, less than its share,
so it is satisfied in full; 8,998.00 remains for B and C.

Pass 2 — share is 8,998.00 / 2 = 4,499.00. Neither B nor C can be satisfied, so
both take their share and the cash is gone.

| Symbol | Budget | Units filled | Spent |
|---|---:|---:|---:|
| A | 1,002.00 | 20 | 1,002.00 |
| B | 4,499.00 | 22 | 4,408.80 |
| C | 4,499.00 | 12 | 4,208.40 |
| | | | **9,619.20** |

$380.80 stays in cash — whole-share rounding, the same residue a single-symbol
run leaves today.

Under first-come-by-column-order the same bar fills A with 20, **B with its full
40**, and leaves C with **2 units** out of 30. The difference between 12 and 2 is
entirely an artefact of where B sits in the ticker list, which is the point.

## 5. Rebalance cadence: signal-driven only

**Decision: no calendar rebalance in 3.8.**

`strategy_mode='rebalancing'` is signal-driven today — it changes *how a signal is
sized*, not *when it trades* — and it stays that way. A monthly or quarterly drift
correction would emit trades with no signal behind them, which changes what
`num_trades`, win rate, profit factor and turnover mean across every existing
comparison, and it is not needed to answer whether a basket survives cash
contention.

If it is ever wanted, the shape is known: a `rebalance_every` parameter emitting
market orders on session boundaries in phase 3, with a `rebalance` exit reason so
[lib/metrics/ledger.py](../lib/metrics/ledger.py) can separate forced round trips
from signalled ones. It should not ship without that separation.

## 6. A symbol with no bar is valued, not traded

**Decision: on a timestamp where a symbol printed no bar, its last close carries
the mark and the symbol is skipped for execution.**

[lib/panel.py](../lib/panel.py) aligns the panel on a common session-aware index
(3.8.2, shipped), and holidays, halts and differing venue calendars guarantee
holes. Forward-filling for *valuation* is right — the position still exists and
still belongs in portfolio value, which the sizing base in §2 depends on.
Forward-filling for *execution* is wrong: it would trade a halted name at a stale
price and let a resting stop fill against a bar that never happened. The two
rules are the `Mark` and `Tradable` columns respectively.

A third case turned up in the implementation and belongs here: **signal columns
fill with `0`, not `NaN`.** `{INDICATOR}_{CONDITION}_Buy` is int-coded, so a
plain reindex leaves `NaN` in every hole — and `NaN` is truthy, which would fire
a buy on precisely the bars the symbol could not trade. "No bar, no signal."

*Implementation note — what a hole does in the engine.* On a bar with
`Tradable=False` the symbol's holding clock (`Holding_Period`) and its cooldown
counters still tick, since they count bars of the panel's tape, and its position
is marked at `Mark`. Nothing else runs for it: no exit, no signal, no expiry or
fill in its order book, no exit-order re-sync. Time in force therefore counts
only bars the order could actually have traded, the rule
[lib/orders.py](../lib/orders.py) already stated. A signal whose execution bar
(`signal bar + delay`) is a hole is lost, not deferred. And the first bar back
after a hole counts as a reopening for gap fills: a trailing stop the symbol
reopens through fills at the open, as it would after a weekend, even though a
halt is not a session boundary for the basket.

Session inference stays [lib/sessions.py](../lib/sessions.py)'s job and runs on
the **merged** index, so `Session_Start`, `BARS_PER_SESSION` and the annualisation
factor describe the panel the portfolio actually traded, not any one symbol's
tape. A hole in one symbol is not a session boundary for the basket.

## 7. The portfolio benchmark is the equal-weight basket

**Decision: `Returns` for a portfolio run is equal-weight buy-and-hold of the same
symbols, bought once at the first tradable bar and never rebalanced.**

Per [CLAUDE.md](../CLAUDE.md), `alpha`, `beta`, `information_ratio`,
`tracking_error`, `excess_return` and the up/down capture ratios all read the
frame's own `Returns` column, so this one choice defines six metrics. Equal-weight
buy-and-hold is the honest null hypothesis for a basket strategy: *did the signals
add anything over simply owning these names?* Never rebalancing keeps the
benchmark free of the trades §5 declined to make.

A named external benchmark — SPY, or a group from the ETF benchmark registry that
3.8.8 already plans to reuse
([lib/cli/research_utils.py](../lib/cli/research_utils.py)) — is a strictly better
comparison for some questions, and `compute_metrics` already accepts a benchmark
source rather than insisting on the column. That is a seam, not a decision to make
now.

## 8. The one-symbol case is today's engine, bit for bit

Every rule above degenerates:

* equal-share water-fill across one competitor hands it all the cash, which is
  `affordable_units`;
* total portfolio value over one symbol is `cash + units * close`;
* phase-major ordering over one symbol is the existing cascade, because the
  per-symbol consume latch is unchanged;
* the equal-weight basket benchmark over one symbol is that symbol's
  buy-and-hold, which is what `Returns` already holds.

**`test_strategy_snapshot` must not be touched by 3.8.** That is the same
commitment 3.7 made and kept, and it is the cheapest available proof that the
generalisation did not quietly reprice the single-symbol path.

## 9. Deliberately not decided here

* **Shorting.** The engine is long-only; a basket does not change that.
* **Leverage and cross-symbol margin.** Cash cannot go negative, in one name or
  across the basket.
* **Multi-currency baskets.** `fx_fee_pct` is a flat rate on notional and stays
  one. A basket quoted in mixed currencies needs an FX series, which is a data
  problem ([data-vendors.md](data-vendors.md)) before it is an engine one.
* **Per-symbol strategy configs.** One indicator set, one parameter set, one mode
  for the whole basket in v1. Signals are already per-symbol — each symbol's frame
  carries its own `{INDICATOR}_{CONDITION}_{Buy|Sell}` columns — so this is a
  configuration limit, not an engine one, and lifting it later changes no rule
  above.
* **Correlation-aware sizing.** 3.8.7 *reports* correlation and concentration; it
  does not feed them back into the sizer.

---

Educational and research use only. Not financial advice.
