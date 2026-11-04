# Commercial audit

## Description
SearchForAlpha Lab is an algorithmic trading research platform: it fetches market data, computes indicator signals, backtests and optimises strategies, validates them with walk-forward analysis and can run them on an Interactive Brokers paper account. A Dash research terminal adds charts, an optimiser, fundamentals valuation and an options Flow Scanner.

## Problem and buyers
Problem: ad-hoc trading research is non-reproducible and has no consistent path from idea to a validated, executable strategy; overfitting goes unchecked (product.md, "Problem it Solves").
Who might pay: Hypothesis to validate: independent systematic traders and researchers who use Python for repeated backtests, especially Interactive Brokers paper users seeking a reproducible path from idea to out-of-sample validation. Small quantitative research teams are a secondary segment. Market research identifies comparable paid offerings, but no SearchForAlpha buyer interviews, purchase requests or customers are documented (reports/Mercato SearchForAlpha Lab.md).

## Stage
production

## Customer demos
unknown — a public demo with a free 7-day trial behind email verification is live at alpha.demos.noeinsolutions.com, and a hosted workspace serves "the owner and the people they invite"; no record of who has used either (docs/DEMO.md, docs/HOSTED.md)

## Commercial evidence
level: 1
- Pain point described (product.md)
- Public 7-day trial with email sign-up exists, so interest could be measured; no sign-ups or invited users recorded in the docs (docs/DEMO.md, docs/HOSTED.md)
- Positioned as "educational and research use only, not financial advice" (USE_CASES.md)

## Technical value
Full research loop in one CLI with JSON contracts for agents: Optuna Bayesian search, rolling walk-forward with a robustness verdict, a promotion gate before live parameters change, and guarded IB paper execution.

## Sources
- product.md, USE_CASES.md, docs/DEMO.md, docs/HOSTED.md, README.md, reports/Mercato SearchForAlpha Lab.md
