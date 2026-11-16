# Option strategy payoff & Greeks — design

Status: ROADMAP 6.6, revised 2026-11-15. The calculator first shipped as a separate `/options` page while the Flow option chain had its own browser-side strategy builder: two payoff implementations (Python and JavaScript), two charts, and a page that knew nothing of the chain's quotes. Both were merged into one panel inside Flow.

## Decisions

- **One place:** the *Strategy · payoff & Greeks* panel in the Flow page, above *Paper options & replay*. There is no OPTIONS header button and no `/options` route.
- **One pricing path:** `lib/options/pricing.py` (in-house Black–Scholes–Merton on top of `lib/options/greeks.py`; no `optlib` or other pricing dependency). The panel, `sfa options price` and the tests all call it. The browser does no payoff maths for strategies.
- **One leg editor:** the panel's table. A leg arrives three ways — **Add to strategy** in a chain quote's popup, a template (long call, long put, bull call spread, iron condor around spot), or **Add leg**. Every cell is editable for what-ifs.
- **Chain legs stay tied to their quote.** A leg added from the chain keeps its `key` (`expiry|C/P|strike`), bid and ask. Making its quantity negative re-prices it at the bid (buy at ask, sell at bid). Changing its strike or call/put turns it into a hypothetical leg. Only a table made entirely of chain legs can be sent to paper trading.
- **Chain rules:** all chain legs share one expiry and one observation (current quotes, or one historical date), at most four. A leg from another ticker, or a table with no chain leg left, starts a new strategy.
- **Inputs follow the chain.** Spot comes from the Flow report (or the historical close for a historical chain), days to expiry from the expiry and the observation date, IV from the chain. When a quote carries no IV (historical EOD), it is solved from the premium and marked `*`.
- The quote popup keeps its one-contract cost / break-even card: that is the quick look before adding a leg, not a second strategy tool.

## Where the code lives

| Piece | File |
| --- | --- |
| Pricing, payoff, implied vol | `lib/options/pricing.py` |
| Leg rules, edits, analysis, paper hand-off (pure, tested) | `lib/dash/flow_strategy.py` |
| Panel layout | `lib/dash/flow_strategy_view.py`, mounted in `lib/dash/layout/overlays.py` |
| Callbacks | `lib/dash/callbacks/flow_strategy.py` |
| Quote → panel hand-off | `lib/dash/assets/52-flow-strategy.js` writes `flow-strategy-add` |
| Paper trading | the panel writes `flow-paper-strategy-selection`, read by the paper panel as before |

## Pricing semantics

Premiums are entered per share; each leg carries its contract multiplier `m` (100 for standard US equity options, the chain's value for adjusted contracts). For a signed leg quantity `n`, expiry P/L at underlying `x` is `m × n × (intrinsic(x) − premium)`. Positive `n` is long, negative is short. Strategy Greeks are sums of per-share Greeks multiplied by `m × n`. Theta is displayed per calendar day; vega and rho per one percentage-point change. The chart samples spot outcomes but break-evens and finite extrema must be solved from the exact piecewise-linear payoff, including `x = 0`, every strike and the slope beyond the highest strike. Unbounded profit/loss is labelled explicitly.

Black–Scholes–Merton prices European exercise. US equity options may be American, and early exercise around dividends can make the estimate differ from a tradable quote. Show that limitation beside the results.

## Source boundary (ROADMAP 6.9)

`lib/options/chain_source.py::fetch_option_chain` currently returns `ChainSnapshot` with `Quote`, `ExpiryChain` frames and `failed_expiries`. A second provider should implement that contract, preserve partial-expiry failures, classify throttling as `TransientFetchError`, and be selected through explicit configuration. Existing Yahoo behaviour stays the default. Do not wire a provider or advertise fallback until account credentials and request limits are available. Tradier sandbox requires an account; FlashAlpha's small daily allowance is not suitable as an automatic fallback. Keep credentials out of source, logs and JSON output.

## Acceptance

- The panel opens from **Add to strategy** in the Flow chain, follows the Flow ticker's spot, and works with typed legs and no network.
- Canonical call at S=K=100, T=1 year, r=5%, q=0, IV=20% is about $10.4506; finite-difference checks agree with analytical Greeks.
- The four-leg short iron butterfly (sell 5 × 50 put at 2.55 and 50 call at 2.40, buy 5 × 55 call at 0.80 and 45 put at 0.85) collects $1,650, breaks even at $46.70 and $53.30, and loses at most $850.
- CLI `--json` and the panel produce the same theoretical value for the same inputs.
