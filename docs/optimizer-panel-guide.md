# The Optimizer — A Plain-English Guide

*How to use the full-screen **Optimizer** workspace (`/optimize/<ticker>`), why it exists,
and what you get out of it.*

> **What is the Optimizer?** The Backtest tab tests **one** idea you picked by hand. The
> Optimizer tests **hundreds of ideas for you** and ranks them, so instead of guessing
> "which signals should I combine?", you let the app try the combinations and hand you a
> leaderboard of the best ones.
>
> Educational/research use only. A high rank on past data is *not* a guarantee of future
> results — see the honesty note in §7.

---

## 1. Why you should use it

| If you… | The Optimizer lets you… |
|---|---|
| Don't know which signals to pick | Try many combinations automatically and see what worked |
| Have a favourite signal but no exit rule | Discover which sell signals pair best with it |
| Want the *best* Sharpe, not just the best return | Rank by the metric you actually care about |
| Are drowning in indicator choices | Get a short, ranked shortlist in seconds |
| Found a winner | Push it straight into the Backtest tab with one click |

The core benefit: **it turns "which of these thousands of combos is good?" into a ranked
top-10 list.** It's a search engine for trading ideas.

---

## 2. The one rule before you start

**Load data first.** Like the Backtest tab, the Optimizer works on *whatever chart is
currently loaded*. No data → it says *"Please load market data first"*.

On the **left sidebar** (Market Data): set **Symbol** — it loads full available history on
its own. Then open the Optimizer via:

- **OPEN OPTIMIZER** on the Backtest tab, or
- command palette → **Open optimizer**, or
- URL `/optimize/<TICKER>`

On the Optimizer page you can edit **capital**, **test window**, **signal universe**,
and (optionally) **realistic ranking** friction without returning to Backtest. Those
controls stay in sync with the Backtest panel (same session values).

> The price chart is the same singleton as the terminal — relocated into the Optimizer
> main pane while you are on `/optimize`. Interval lives on the chart toolbar.

---

## 3. Tour of the full-screen workspace

Layout: **left config rail** + **main pane** (chart on top, progress/leaderboard below),
with Run/Stop in the top bar.

### A — Signal Preview
*"What am I working with?"* Live counters that update as you load data and move the
sliders:

- **BUY** / **SELL** — how many signals are in the current search universe.
- **COMBOS** — combinations that will actually be tested (capped by Max Combinations).
- **EST** — rough runtime estimate.
- A one-line **conditions** summary (interval · capital · window · signal names).

### B — Capital & Window
Editable test-window presets / dates and initial capital. Changes sync to the Backtest
panel SoT controls.

### C — Signal Universe
Multi-select buy/sell lists. Empty = search **all** signal columns on the loaded frame.
Narrow the list to focus the search (bundles-lite).

### D — Search & Constraints
- **Max Signals per Side** (1–5, default `2`) — how many signals may stack per side.
- **Max Combinations** (10–1000, default `100`) — hard cap for speed.
- **Min Trades** (default `10`) — low-sample floor for ranking.
- **Sort Results By** — SCORE / RET / SHARPE / CALMAR / DD / TRADES (re-rank after a run).
- Optional **Max |DD| %** and **Min Sharpe** — discard combos before ranking.

### E — Realistic Ranking
Off by default (fast idealized engine defaults). Turn on to rank each combo with your
synced **mode / min hold / trailing stop / FX / slippage / commission**.

### The button — SEARCH SIGNAL COMBOS / STOP COMBOS
Press **SEARCH SIGNAL COMBOS** (header or left rail under Grid Search & Constraints)
to start. While running the button becomes **STOP COMBOS** (click to cancel and keep
partial results). Close restores the chart to the terminal and returns to `/ticker/<sym>`.

**Tune this bundle** (sidebar): outline actions **TUNE BUNDLE** (Bayesian) and
**SCAN PARAM GRID** are step-2 param tools for one named strategy — not the combo search.

---

## 4. What happens during and after a run

**While running:**
- A **progress bar** shows *"Testing 120/500 combinations…"*.
- A running count of *"valid strategies found so far"*.
- Once at least 5 valid results exist, a live **"Top strategies so far"** mini-table previews the current leaders.

**When it finishes:**
- A green *"✓ Completed! Tested N combinations"* message, followed by a one-line honesty
  caption reminding you that testing many combos makes the top result more likely to be luck.
- A **Best Strategy highlight** card and **top-10 table**.
- An **Apply Best Strategy** button appears.
- A **Return vs Sharpe** scatter chart plots every valid combo; the current
  winner is starred.
- **Run history** (persisted in the browser) lists recent combinatorial searches
  for this ticker — timestamp, combo count, top return/Sharpe, truncated signals.
- **VALIDATE OOS** runs a 5-window rolling walk-forward on the sorted winner and
  shows IS/OOS Sharpe means, degradation, and a robust yes/no verdict.

### Apply Best Strategy
Click it and the Optimizer will:
1. Copy the winning **buy** and **sell** signals into the Backtest tab's Signals section,
2. Close the full-screen workspace and return to the terminal, and
3. Switch you to the **Backtest** tab (and auto-run the honest scorecard).

From there you see a **full** backtest on the winner — with your real Trade Setup
knobs and Transaction Costs applied (see §7 for why that second step matters).

### Validate OOS (walk-forward)
After a combinatorial run finishes, click **VALIDATE OOS** next to Apply. The app
re-tests the current leaderboard winner across five rolling 12-month train / 3-month
test windows (same geometry as the CLI walk-forward runner). The strip shows mean
in-sample vs out-of-sample Sharpe, degradation, and whether the combo passes the
robustness gate (≥80% of windows with OOS Sharpe > 1.0 and mean degradation < 0.4).
This uses the same signal columns as the winner; when **Realistic ranking** was on,
costs/stops from that run are applied.

### Bayesian Sweep (agent bundles)
The **Bayesian Sweep** accordion runs Optuna TPE on a named **agent strategy**
bundle from `config/strategy_config.yaml` (search_space required). Set trials,
objective metric (sortino/sharpe/calmar/composite), and held-out months; the search
window is your test-window dates minus the held-out tail. Results show best params
and metrics when the background study completes — this can take several minutes.

While running, the button reads **STOP TUNE** (click to cancel; partial
trials are kept). Progress shows `Trial N/M`. When finished:

- **APPLY PARAMS** copies the best flat params into indicator settings and the
  bundle's buy/sell signals into Backtest (same handoff as combinatorial Apply).
- **VALIDATE OOS (BUNDLE)** runs the same 5-window walk-forward on the Bayesian
  winner; click again while running to **STOP** (result is discarded if stopped).

---

## 5. Example workflows

### Workflow 1 — "I have no idea where to start" (beginner)
1. Pick a symbol on the left so prices load.
2. Click **OPEN OPTIMIZER** → set Capital & Window on the rail if needed; leave **Max Signals** = `2`, **Max Combinations** = `100`.
3. Sort by **RET**. Click **SEARCH SIGNAL COMBOS**.
4. Read the Best Strategy card and top-10 table.
5. Click **Apply Best Strategy** for the full scorecard on the Backtest tab.

### Workflow 2 — "I care about a smooth ride, not just raw return" (risk-aware)
1. Run the Optimizer as above.
2. When it finishes, switch **Sort Results By** to **SHARPE** — the table re-ranks instantly.
3. Then flip to **DD** to see which combos had the gentlest worst-case loss.
4. Pick a strategy that scores well across *all three* views, not just one.

### Workflow 3 — "Thorough overnight sweep" (advanced)
1. Set **Max Signals per Side** = `3`, **Max Combinations** = `1000`.
2. Watch the COMBOS counter to confirm the workload before running.
3. **SEARCH SIGNAL COMBOS** and let it grind through.
4. Treat the results with healthy suspicion — the more combos you test, the more likely the "winner" got lucky (§7).

### Workflow 4 — "Optimizer → Backtest handoff" (the recommended loop)
1. Optimizer finds a promising combo → **Apply Best Strategy**.
2. On the Backtest tab, add realistic **Transaction Costs** and your **Trade Setup** (trailing stop, min holding, etc.).
3. **RUN BACKTEST**. Check whether the edge survives costs and your risk controls.
4. If it holds up, **Save** it as a preset (left sidebar → Saved Configurations).

---

## 6. Reading the leaderboard

Each row is one signal combination. The columns mirror the Backtest scorecards — Total
Return %, **Alpha %** (vs buy-and-hold), Sharpe, **Sortino, Calmar**, Max Drawdown %,
**Win Rate %, Profit Factor**, and trade count. Quick reading rules:

- **Check Alpha first.** A big Total Return means little if the stock itself doubled. **Alpha %** is the strategy's return *minus* buy-and-hold — if it's negative, you'd have done better just holding.
- **Don't just take row #1.** A tiny difference in return between #1 and #5 is noise; prefer the combo that also has a decent Sharpe/Calmar and a controlled drawdown.
- **Beware greyed-out (low-sample) rows.** A combo that "won" on 2 trades is luck, not edge — that's why the Min Trades floor pushes them down the board.
- **Cross-check metrics.** Re-sort by SHARPE, CALMAR and DD; a combo that ranks well under *all* of them is far more trustworthy than one that only tops RET. **SCORE** already blends these for you.

---

## 7. The honesty note (please read)

Two things to keep in mind so the Optimizer helps rather than misleads:

1. **The Optimizer runs a *simplified*, fast backtest.** It evaluates each combination
   with **default settings** — it does **not** apply the Trade Setup knobs (trailing stop,
   take profit, min holding, position sizing) or the Transaction Costs from the Backtest
   tab. Think of it as a **fast screen** to shortlist candidates. Always re-run the winner
   on the **Backtest** tab with realistic costs and your risk controls before trusting it.

2. **Overfitting is real.** The more combinations you test, the higher the chance that the
   top result simply fit the *noise* of this particular history and won't repeat. Guard
   against it: prefer simpler combos (fewer signals per side), demand enough trades, sanity-check across
   metrics, and — ideally — re-test the winner on a *different* date range to see if it holds.

---

## 8. The 30-second mental model

1. **Load data** (left) → 2. **Set the search size** (Max Signals per Side + Max
Combinations) → 3. **Pick a ranking metric** (Sort Results By) → 4. **SEARCH SIGNAL COMBOS** →
5. **Read the leaderboard**, re-sorting to cross-check → 6. **Apply Best Strategy** →
7. **Re-run it on the Backtest tab** with real costs → 8. **Save** the survivors.

The Optimizer's job is to *narrow the field*; the Backtest tab's job is to *confirm the
winner honestly*. Use them together.

*Not financial advice. For research and learning only.*
