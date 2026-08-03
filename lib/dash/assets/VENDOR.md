# Vendored front-end assets

Dash auto-serves everything in this directory and injects `.css` / `.js` into the
page in sorted filename order. The numeric prefixes on the chart files exist to
pin that order — the library must evaluate before the glue that uses it.

| File | Version | Source | License |
|---|---|---|---|
| `00-lightweight-charts.standalone.production.js` | 5.2.0 | [unpkg](https://unpkg.com/lightweight-charts@5.2.0/dist/lightweight-charts.standalone.production.js) | Apache-2.0 |
| `bootstrap.min.css` | 5.x | Bootstrap | MIT |

Both are served locally rather than from a CDN — see the comment in
`lib/dash/integrated_dashboard.py` about Edge Tracking Prevention noise.

## TradingView Lightweight Charts™ — NOTICE

    TradingView Lightweight Charts™
    Copyright (c) 2026 TradingView, Inc. https://www.tradingview.com/

Licensed under the Apache License, Version 2.0. You may obtain a copy of the
License at http://www.apache.org/licenses/LICENSE-2.0.

The license requires attribution. The chart is configured with
`layout.attributionLogo: true` (see `10-sfa-chart.js`), which renders the
TradingView logo linking to https://www.tradingview.com/ in the chart corner and
satisfies that requirement. **Do not disable it.**

## Upgrading

Replace the file with the same-named build at the new version, update the table
above, and re-run `lib/tests/test_chart_assets.py` — it pins the expected version
string and the API symbols the glue depends on, so a breaking upgrade fails
loudly instead of blanking the chart at runtime.
