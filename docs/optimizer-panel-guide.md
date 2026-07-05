# The Optimizer Panel — A Plain-English Guide

*How to use the **Optimizer** tab on the right-hand panel, why it exists, and what you get out of it.*

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

On the **left sidebar** (Market Data): set **Symbol**, **Start / End Date**, **Initial
Capital**, then press **REFRESH**. Once prices are loaded, switch to the **Optimizer** tab
at the top of the right-hand panel.

---

## 3. Tour of the panel (top to bottom)

### A — Signal Preview
*"What am I working with?"* Three live counters that update as you load data and move the
sliders:

- **BUY** — how many buy signals are available on the loaded data.
- **SELL** — how many sell signals are available.
- **COMBOS** — the estimated number of combinations that will actually be tested (already capped by your Max Combinations setting).

Use this as a sanity check *before* running: if COMBOS says `500`, that's how much work
you're about to ask for.

### B — Max Signals per Side
*Slider, 1–5, default `2`.*

How many signals may be **stacked together** on each side (buy and sell).

- `1` = test single signals only (fast, simple).
- `2` = allow pairs like "RSI oversold **+** MACD bullish" (the sweet spot).
- `3`–`5` = richer combinations, but the number of possibilities explodes quickly.

> Higher = more thorough but slower, and more prone to **overfitting** (see §7). Start at `2`.

### C — Max Combinations
*Number box, 10–1000, default `100`.*

A hard **cap** on how many combinations to actually test, for speed. Even if Max Signals
per Side would theoretically produce thousands of combos, the Optimizer stops after this
many.

- Quick scan: `50–100`.
- Thorough sweep: `300–1000` (slower).

### C2 — Min Trades
*Number box, default `10`.*

The reliability floor. Any combination that traded **fewer** times than this is tagged
**"low sample"** and pushed *below* the credible ones in the ranking — it isn't deleted,
just deprioritised. A great-looking Sharpe or profit factor built on 3 trades is luck, not
edge, so this stops flukes from topping the board.

### D — Sort Results By
*Segmented buttons.* Which metric ranks the leaderboard:

| Button | Ranks by | You want… |
|---|---|---|
| **SCORE** | Robustness Score (default) | The best all-round pick — risk-adjusted return with a penalty for too-few trades |
| **RET** | Total Return % | Biggest raw gain |
| **SHARPE** | Sharpe Ratio | Best *risk-adjusted* return (smoothest ride) |
| **CALMAR** | Calmar Ratio | Best return relative to worst-case drawdown |
| **DD** | Max Drawdown % | Smallest worst-case loss (sorted so least-bad is on top) |
| **TRADES** | Number of trades | Most (or fewest) trades |

> 💡 You can change this **after** a run — the table re-ranks instantly without re-testing
> anything. So run once, then flip between SCORE / RET / SHARPE / CALMAR / DD to see the
> picture from different angles. Low-sample combos always stay grouped below credible ones.

### The button — RUN OPTIMIZER
Press it. A progress bar appears and the search begins.

---

## 4. What happens during and after a run

**While running:**
- A **progress bar** shows *"Testing 120/500 combinations…"*.
- A running count of *"valid strategies found so far"*.
- Once at least 5 valid results exist, a live **"Top strategies so far"** mini-table previews the current leaders.
- The RUN OPTIMIZER button is disabled until it finishes (the search runs in the background in small batches, so the app stays responsive).

**When it finishes:**
- A green *"✓ Completed! Tested N combinations"* message, followed by a one-line honesty
  caption reminding you that testing many combos makes the top result more likely to be luck.
- A **Best Strategy highlight** card — the winner by your chosen metric. It shows Total
  Return, Sharpe, Max Drawdown, **Sortino, Calmar, Win Rate, Profit Factor**, trade count,
  and a **"vs Buy & Hold" alpha** line so you can instantly see whether the strategy actually
  beat simply holding the stock. A **"LOW SAMPLE"** chip appears if the winner traded too few times.
- A **top-10 table** with the same metrics (plus Alpha %). Low-sample rows are greyed out.
- An **Apply Best Strategy** button appears at the bottom.

### Apply Best Strategy
Click it and the Optimizer will:
1. Copy the winning **buy** and **sell** signals into the Backtest tab's Signals section, and
2. Switch you over to the **Backtest** tab automatically.

From there you can run a **full** backtest on the winner — with your real Trade Setup
knobs and Transaction Costs applied (see §7 for why that second step matters).

---

## 5. Example workflows

### Workflow 1 — "I have no idea where to start" (beginner)
1. Load a symbol and dates on the left, **REFRESH**.
2. Optimizer tab → leave **Max Signals per Side** = `2`, **Max Combinations** = `100`.
3. Sort by **RET**. Click **RUN OPTIMIZER**.
4. Read the Best Strategy card and top-10 table.
5. Click **Apply Best Strategy**, then **RUN BACKTEST** on the Backtest tab for the full scorecard.

### Workflow 2 — "I care about a smooth ride, not just raw return" (risk-aware)
1. Run the Optimizer as above.
2. When it finishes, switch **Sort Results By** to **SHARPE** — the table re-ranks instantly.
3. Then flip to **DD** to see which combos had the gentlest worst-case loss.
4. Pick a strategy that scores well across *all three* views, not just one.

### Workflow 3 — "Thorough overnight sweep" (advanced)
1. Set **Max Signals per Side** = `3`, **Max Combinations** = `1000`.
2. Watch the COMBOS counter to confirm the workload before running.
3. **RUN OPTIMIZER** and let it grind through.
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
Combinations) → 3. **Pick a ranking metric** (Sort Results By) → 4. **RUN OPTIMIZER** →
5. **Read the leaderboard**, re-sorting to cross-check → 6. **Apply Best Strategy** →
7. **Re-run it on the Backtest tab** with real costs → 8. **Save** the survivors.

The Optimizer's job is to *narrow the field*; the Backtest tab's job is to *confirm the
winner honestly*. Use them together.

*Not financial advice. For research and learning only.*
