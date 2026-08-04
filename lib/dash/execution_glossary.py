"""
Copy and structure for the Execution Type explainer.

Pure data — no Dash, no theme, no engine imports — so it can be unit-tested and
diffed on its own. Mirrors ``lib/dash/flow_glossary.py``.

Every claim here is either (a) a structural fact pinned by a test in
``lib/tests/test_strategy_engine.py``, or (b) a number, in which case it does not
live here at all: numbers come from :mod:`lib.dash.execution_sim` at render time.
Keep it that way. The captions this replaces went stale precisely because they
stated arithmetic the engine no longer performed.
"""

from __future__ import annotations

MODE_ORDER: tuple[str, ...] = ('trading', 'accumulation', 'rebalancing')

# ``accent_key`` indexes lib/dash/dash_config.py THEMES so colours stay themed.
MODE_SPECS: dict[str, dict[str, str]] = {
    'trading': {
        'name': 'Trading',
        'suffix': 'Signal In/Out',
        'accent_key': 'text_primary',
        'caption': 'Kelly-sized entries, exit on signal or stop',
        'one_liner': (
            "Each buy signal opens or adds a Kelly-sized slice; each sell signal, "
            "trailing stop or take-profit closes it. The mode with every risk "
            "control switched on."
        ),
    },
    'accumulation': {
        'name': 'Accumulation',
        'suffix': 'DCA',
        'accent_key': 'accent_green',
        'caption': 'Fixed $ per buy · never sells · no stop',
        'one_liner': (
            "Buy a fixed dollar amount on every buy signal until the cash runs "
            "out. Sell signals, stops and take-profits are all inactive — this "
            "mode only ever accumulates."
        ),
    },
    'rebalancing': {
        'name': 'Rebalancing',
        'suffix': 'Target Weight',
        'accent_key': 'accent_blue',
        'caption': 'Trade a fixed % of portfolio value per signal',
        'one_liner': (
            "Every signal trades the same percentage of portfolio value — in on "
            "a buy, out on a sell — so position changes stay equal-weight rather "
            "than shrinking as cash is spent."
        ),
    },
}

# The mechanics matrix. Each row is one question a user actually has, answered
# for all three modes. This table is the highest-value element in the explainer:
# it makes "Accumulation never sells" and "only Accumulation has no stop"
# visible at a glance instead of buried in prose.
MECHANICS_ROWS: tuple[dict[str, str], ...] = (
    {
        'label': 'On a BUY signal',
        'trading': 'Buys Kelly size × scale-in %',
        'accumulation': 'Buys a fixed $ amount',
        'rebalancing': 'Buys % of portfolio value',
    },
    {
        'label': 'On a SELL signal',
        'trading': 'Sells down the position',
        'accumulation': 'Ignored entirely',
        'rebalancing': 'Sells % of portfolio value',
    },
    {
        'label': 'Trailing stop',
        'trading': 'Active',
        'accumulation': 'Never — no stop, ever',
        'rebalancing': 'Active (exits 100%)',
    },
    {
        'label': 'Take profit',
        'trading': 'Active',
        'accumulation': 'Never',
        'rebalancing': 'Active (exits 100%)',
    },
    {
        'label': 'Min holding period',
        'trading': 'Blocks signal sells + TP',
        'accumulation': 'No effect',
        'rebalancing': 'Blocks signal sells + TP',
    },
    {
        'label': 'Repeat buy signals',
        'trading': 'Stack, ramping in size',
        'accumulation': 'Stack, same $ each time',
        'rebalancing': 'Stack, equal weight each time',
    },
    {
        'label': 'Runs out of cash?',
        'trading': 'Order clamps to cash left',
        'accumulation': 'Yes — then it stops buying',
        'rebalancing': 'Order clamps to cash left',
    },
    {
        'label': 'Needs sell signals?',
        'trading': 'Yes — required',
        'accumulation': 'No',
        'rebalancing': 'Optional but recommended',
    },
    {
        'label': 'Win rate / profit factor',
        'trading': 'Meaningful',
        'accumulation': 'Not meaningful',
        'rebalancing': 'Meaningful',
    },
)

# Cells worth flagging visually: (row label, mode) -> tone.
# 'off' = the mechanic is inactive in that mode, 'warn' = active but surprising.
CELL_TONES: dict[tuple[str, str], str] = {
    ('On a SELL signal', 'accumulation'): 'off',
    ('Trailing stop', 'accumulation'): 'off',
    ('Take profit', 'accumulation'): 'off',
    ('Min holding period', 'accumulation'): 'off',
    ('Win rate / profit factor', 'accumulation'): 'off',
    ('Runs out of cash?', 'accumulation'): 'warn',
    ('Repeat buy signals', 'trading'): 'warn',
    ('Trailing stop', 'rebalancing'): 'warn',
    ('Take profit', 'rebalancing'): 'warn',
}

# Which Trade Setup controls do anything, per mode. Drives the "these knobs are
# inert" notice, so a user never tunes a slider the engine ignores.
ACTIVE_CONTROLS: dict[str, tuple[str, ...]] = {
    'trading': (
        'Strategy preset', 'Min holding period', 'Trailing stop', 'Scale-in %',
        'Take profit', 'Kelly win rate', 'Kelly win/loss ratio',
    ),
    'accumulation': ('Amount per buy',),
    'rebalancing': ('Min holding period', 'Trailing stop', 'Take profit', '% of portfolio'),
}

EXECUTION_SECTIONS: list[dict[str, str]] = [
    {
        'title': 'Execution Type is about sizing, not about signals',
        'body': (
            "Your indicators decide *when* to trade. Execution Type decides *how "
            "much* — and whether a sell signal, a stop or a profit target is even "
            "listened to. Two modes on identical signals can produce completely "
            "different equity curves, so this setting is doing more work than any "
            "single indicator you pick."
        ),
    },
    {
        'title': 'Trading — every control switched on',
        'body': (
            "Entries are sized by the Kelly criterion: at a 0.50 win rate and a "
            "1.50 win/loss ratio, Kelly asks for about 16.7% of the account, and "
            "the scale-in slider multiplies that. Scale-in is a ramp on each "
            "order, not a target to converge on — repeated buy signals keep "
            "adding, each one larger than the last, until cash or signals run "
            "out. Sell signals, the trailing stop and take-profit all apply."
        ),
    },
    {
        'title': 'Accumulation — one-way by design',
        'body': (
            "Spend the same dollar amount on every buy signal until the account "
            "is empty, then stop. This mode discards sell signals, so if you have "
            "sell indicators selected they do nothing. It also never sets a "
            "trailing stop or take-profit. Because the position is never closed, "
            "the trade ledger holds a single open trade — which is why win rate "
            "and profit factor are blank rather than bad."
        ),
    },
    {
        'title': 'Rebalancing — equal weight both ways',
        'body': (
            "Each signal trades a fixed percentage of portfolio value: buys add "
            "that weight, sells shed it. Because it sizes off total portfolio "
            "value rather than leftover cash, the third buy is the same size as "
            "the first. Stops and take-profits are active here, and when one "
            "fires it exits the whole position, not a slice."
        ),
    },
    {
        'title': 'Reading the numbers below',
        'body': (
            "Everything in the sandbox is produced by running the real backtest "
            "engine over a fixed 24-bar tape with fees switched off — the same "
            "code path a live run uses. If the engine changes, these numbers "
            "change with it. Educational/research use only; not financial advice."
        ),
    },
]

# Predict-then-reveal. ``answer_key`` names a SandboxRun attribute so the correct
# option is resolved from the engine at render time, never hardcoded here.
PREDICT_QUESTIONS: dict[str, dict] = {
    'trading': {
        'question': "You start with $10,000. How much does the first buy signal put to work?",
        'options': ('about $400', 'about $1,700', 'about $5,000', 'all $10,000'),
        'answer_key': 'first_entry_value',
        'thresholds': (800.0, 3_000.0, 7_500.0),
        'sting': (
            "Kelly caps the entry near 16.7% of the account — nowhere near the "
            "'full buy' the old label promised. Drop scale-in below 100% and it "
            "gets smaller still."
        ),
    },
    'accumulation': {
        'question': "You start with $10,000 and buy $1,000 a time. What happens on buy signal #11?",
        'options': ('buys $1,000', 'buys what is left', 'nothing — out of cash', 'sells to rebuy'),
        'answer_key': 'buy_count',
        'sting': (
            "Cash runs out and buying simply stops. There is no sell side to "
            "recycle capital, because sell signals are discarded in this mode."
        ),
    },
    'rebalancing': {
        'question': "Three buy signals in a row at 25%. How big is the third one?",
        'options': ('same as the first', 'about half the first', 'about a third', 'zero'),
        'answer_key': 'first_entry_value',
        'sting': (
            "Equal weight — each buy is 25% of *portfolio value*. Sizing off "
            "leftover cash instead would have decayed it to 14% of the account."
        ),
    },
}

DISCLAIMER = "Educational/research use only. Not financial advice."
