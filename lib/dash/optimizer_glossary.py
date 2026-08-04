"""
Copy and structure for the Optimizer LEARN explainer.

Pure data — no Dash, no theme, no engine imports — so it can be unit-tested and
diffed on its own. Mirrors ``lib/dash/flow_glossary.py``.
"""

from __future__ import annotations

DISCLAIMER = (
    "Educational/research use only. A high rank on past data is not a guarantee "
    "of future results — not financial advice."
)

# Numbered path shown in the empty state and at the top of LEARN.
QUICK_START_STEPS: tuple[str, ...] = (
    "Load a symbol so the chart has prices (left sidebar).",
    "Set Capital & Window on the left rail (same values sync to Backtest).",
    "Leave Max Signals = 2 and Max Combinations = 100 for a first pass.",
    "Click RUN OPTIMIZER — that is the signal-combo grid search.",
    "Read the leaderboard, then Apply Best Strategy (or Validate OOS first).",
)

# What each analysis does — used in the LEARN comparison table + section blurbs.
ANALYSIS_SPECS: dict[str, dict[str, str]] = {
    "combinatorial": {
        "name": "Signal combo search",
        "aka": "Grid search",
        "button": "RUN OPTIMIZER",
        "one_liner": (
            "Tries many buy/sell signal stacks on the loaded window and ranks "
            "them. Start here if you do not know which signals to pick."
        ),
        "when": "You need a shortlist of signal combinations.",
        "output": "Leaderboard of combos + Apply / Validate OOS.",
    },
    "bayesian": {
        "name": "Bayesian Sweep",
        "aka": "Param tuning",
        "button": "RUN BAYESIAN",
        "one_liner": (
            "Tunes numeric parameters of one named agent strategy bundle "
            "(Optuna TPE). Needs a bundle with a search_space in config."
        ),
        "when": "You already chose a strategy and want better params.",
        "output": "Best params + Apply Params / Validate OOS (bundle).",
    },
    "param_grid": {
        "name": "Param Grid Search",
        "aka": "Cartesian grid",
        "button": "RUN GRID",
        "one_liner": (
            "Enumerates a capped floor→ceiling grid of indicator and optional "
            "execution params for one bundle. Use when the space is small; "
            "otherwise prefer Bayesian."
        ),
        "when": "You want an exhaustive scan of a few parameters (≤ max-combos).",
        "output": "Best combo + estimate/range visuals + Apply Params.",
    },
    "oos": {
        "name": "Validate OOS",
        "aka": "Walk-forward",
        "button": "VALIDATE OOS",
        "one_liner": (
            "Re-tests the current winner across five rolling train/test windows "
            "to see if the edge survives out of sample."
        ),
        "when": "After a combo or Bayesian run looks too good to be true.",
        "output": "IS vs OOS Sharpe, degradation, robust yes/no.",
    },
    "realistic": {
        "name": "Realistic Ranking",
        "aka": "Costs & stops",
        "button": "Checklist on rail",
        "one_liner": (
            "When on, each combo is ranked with your synced execution mode, "
            "stops, and transaction costs instead of idealized defaults."
        ),
        "when": "You want the shortlist closer to a real Backtest scorecard.",
        "output": "Same leaderboard, scored under friction.",
    },
}

ANALYSIS_ORDER: tuple[str, ...] = (
    "combinatorial",
    "bayesian",
    "param_grid",
    "oos",
    "realistic",
)

# Accordion / control blurbs shown inline on the rail (short).
SECTION_BLURBS: dict[str, str] = {
    "capital": (
        "Same capital and test window as Backtest — edit here or there; they stay in sync."
    ),
    "universe": (
        "Optional filter. Empty means search every buy/sell column on the loaded frame."
    ),
    "search": (
        "Grid search knobs: how wide the combo space is, how many to test, and how to rank."
    ),
    "realistic": (
        "Off = fast idealized screen. On = rank with costs, stops, and execution mode."
    ),
    "bayesian": (
        "Different tool: tune parameters of one strategy bundle, not signal combinations."
    ),
    "param_grid": (
        "Exhaustive capped grid over selected params (and optional execution space). "
        "Collapsible visuals show combo count and floor→ceiling ranges before you run."
    ),
}

CONTROL_HINTS: dict[str, str] = {
    "signal_preview": (
        "BUY / SELL = signals in the search universe. COMBOS = how many stacks will "
        "actually be tested (already capped). EST ≈ runtime. Check this before you run."
    ),
    "max_signals": (
        "How many signals may stack on each side. 1 = singles only (fast). "
        "2 = pairs (good default). 3–5 explode the search space and overfit more easily."
    ),
    "max_combos": (
        "Hard cap on combinations tested. 50–100 for a quick scan; 300–1000 for a "
        "thorough sweep (slower)."
    ),
    "min_trades": (
        "Combos with fewer trades than this are flagged 'low sample' and ranked below "
        "credible ones — a great ratio on a handful of trades is usually noise."
    ),
    "sort_metric": (
        "Metric that ranks the leaderboard. SCORE blends risk-adjusted return and "
        "penalises too-few trades. You can change this after a run without retesting."
    ),
    "max_dd": (
        "Optional filter: drop combos whose max drawdown is worse than this percent "
        "before ranking."
    ),
    "min_sharpe": (
        "Optional filter: drop combos with Sharpe below this threshold before ranking."
    ),
}

LEARN_SECTIONS: list[dict[str, str]] = [
    {
        "title": "What RUN OPTIMIZER actually does (grid search)",
        "body": (
            "It is a capped combinatorial / grid search over buy and sell signal "
            "stacks. The app builds combinations up to Max Signals per Side, stops "
            "after Max Combinations, backtests each on your Test Window, and sorts "
            "the survivors. You are not tuning RSI length here — you are asking "
            "\"which of these signal recipes worked on this history?\""
        ),
    },
    {
        "title": "Beginner defaults that work",
        "body": (
            "Max Signals per Side = 2, Max Combinations = 100, Sort by SCORE or RET, "
            "Realistic Ranking off for the first pass. Watch COMBOS and EST before "
            "you click Run. After the leaderboard appears, flip Sort Results By "
            "(SCORE / SHARPE / DD) — the table reorders instantly so you can "
            "cross-check without another search."
        ),
    },
    {
        "title": "Apply Best Strategy vs Validate OOS",
        "body": (
            "Apply copies the winning buy/sell signals into Backtest, closes the "
            "workspace, and runs an honest scorecard with your Trade Setup and costs. "
            "Validate OOS keeps you here and stress-tests the winner on five rolling "
            "windows (walk-forward). Prefer Validate when the #1 row looks suspiciously "
            "perfect; always Apply before trusting any number for real decisions."
        ),
    },
    {
        "title": "Bayesian Sweep is a different job",
        "body": (
            "Use it only when you already have a named agent strategy bundle with a "
            "search_space. Trials = how many Optuna attempts; Held-out months = a "
            "tail of the window reserved from the search; Objective = what Optuna "
            "maximises (Sortino / Sharpe / Calmar / Composite). Apply Params writes "
            "the best numbers into indicator settings and the bundle's signals."
        ),
    },
    {
        "title": "Honesty note (read once)",
        "body": (
            "Without Realistic Ranking, the combo search uses simplified defaults — "
            "treat it as a fast screen, then confirm on Backtest with costs and stops. "
            "The more combinations you test, the more likely the top row overfit noise. "
            "Prefer simpler stacks, enough trades, cross-metric ranking, and OOS when "
            "in doubt."
        ),
    },
]
