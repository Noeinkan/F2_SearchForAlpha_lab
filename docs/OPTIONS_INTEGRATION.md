# Options pricing workspace — current integration plan

Status: implementation plan for ROADMAP 6.6, refreshed 2026-11-15 against the current dashboard. The old optlib/tab-switcher plan was deleted because its entry points no longer exist.

## Scope and decisions

- Add an **Options pricing** workspace for manual European equity-option estimates, expiry payoff and Greeks. Educational estimates, not executable quotes.
- Use in-house Black–Scholes–Merton pricing built on `lib/options/greeks.py`. No `optlib` submodule, `greeks-package`, or new pricing dependency.
- Support long call, long put, bull call spread, and iron condor presets, with editable legs (signed quantity, call/put, strike, premium and volatility), spot, rate, dividend yield and days to expiry.
- `sfa options price ... --json` uses the same pure pricing module as Dash. Invalid inputs produce the CLI's JSON error shape and a nonzero exit.
- Keep the calculator independent of Yahoo. The Flow Scanner's chain remains a separate data product; quoted bid/ask can be integrated later without making network access necessary for pricing.

## Current architecture and insertion points

The dashboard has URL workspaces, not a tab switcher. `lib/dash/layout/header.py` renders CHART/FUNDAMENTALS/FLOW navigation. `lib/dash/layout/shell.py` mounts terminal and overlay workspaces. `lib/dash/callbacks/routing.py` owns navigation and hides the terminal for alternate routes. `lib/dash/routes.py` parses routes. `lib/dash/callbacks/__init__.py` registers callbacks. Do not edit `integrated_dashboard.py` for controls or callback imports.

1. Add `/options/<ticker>` to `dash_config.py` and `routes.py`, preserving the selected symbol through `sync_dropdown_to_url`.
2. Add an OPTIONS header button and a mounted options workspace in `layout/shell.py` via `layout/options_pricing.py`. Extend the route layout callback to hide the terminal on this route. Keep one callback writer per output.
3. Put validation, European theoretical price, theta/vega/rho, leg payoff and portfolio break-evens in `lib/options/pricing.py`. Reuse `bs_delta` and `bs_gamma` from `greeks.py`; keep all rate and IV inputs as fractions internally. Handle expiry with intrinsic value and explicitly mark Greeks as undefined there.
4. `lib/dash/callbacks/options_pricing.py` reads the mounted manual inputs, applies a preset to legs, computes through the pure module, and renders a Plotly payoff figure, per-leg Greeks and aggregate Greeks. Plotly is suitable here because the payoff is a small standalone plot; it does not touch the terminal's Lightweight Charts payload.
5. Register `lib/cli/commands/options_cmd.py` in `lib/cli/app.py`. The command prices one option using spot, strike, days to expiry, IV, rate, yield and call/put. Share model validation and units with Dash.
6. Add focused numerical and payoff tests, CLI contract tests, and dashboard routing/callback smoke tests. Restart the local dashboard after code changes as required by `CLAUDE.md`.

## Pricing semantics

Premiums are entered per share; a standard displayed contract uses a 100-share multiplier. For a signed leg quantity `n`, expiry P/L at underlying `x` is `100 × n × (intrinsic(x) − premium)`. Positive `n` is long, negative is short. Portfolio Greeks are sums of per-share Greeks multiplied by `100 × n`. Theta is displayed per calendar day; vega and rho per one percentage-point change. The chart samples spot outcomes but break-evens and finite extrema must be solved from the exact piecewise-linear payoff, including `x = 0`, every strike and the slope beyond the highest strike. Unbounded profit/loss is labelled explicitly.

Black–Scholes–Merton prices European exercise. US equity options may be American, and early exercise around dividends can make the estimate differ from a tradable quote. Show that limitation beside the results.

## Source boundary (ROADMAP 6.9)

`lib/options/chain_source.py::fetch_option_chain` currently returns `ChainSnapshot` with `Quote`, `ExpiryChain` frames and `failed_expiries`. A second provider should implement that contract, preserve partial-expiry failures, classify throttling as `TransientFetchError`, and be selected through explicit configuration. Existing Yahoo behaviour stays the default. Do not wire a provider or advertise fallback until account credentials and request limits are available. Tradier sandbox requires an account; FlashAlpha's small daily allowance is not suitable as an automatic fallback. Keep credentials out of source, logs and JSON output.

## Acceptance

- The OPTIONS workspace opens from the header, works with no network and follows ticker changes.
- Canonical call at S=K=100, T=1 year, r=5%, q=0, IV=20% is about $10.4506; finite-difference checks agree with analytical Greeks.
- Preset payoff, break-even and bounded/unbounded labels match known examples; a short leg reverses both payoff and Greeks.
- CLI `--json` and the dashboard produce the same theoretical value for the same inputs.
- Existing terminal, fundamentals and flow navigation still work; no duplicate Dash outputs.
