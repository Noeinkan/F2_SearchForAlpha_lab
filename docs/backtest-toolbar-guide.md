# The Backtest Toolbar — A Plain-English Guide

*How to use the panel on the right side of the dashboard, why it exists, and what you get out of it.*

> **What is a backtest?** It's a "time machine" for trading ideas. You pick a set of
> rules ("buy when the RSI is low, sell when it's high"), then the app replays real
> historical prices and pretends it traded for you. At the end it tells you whether you
> would have made or lost money — **without risking a single real dollar.**
>
> Educational/research use only. A backtest shows what *would have* happened, not what
> *will* happen. Past performance is not a promise.

---

## 1. Why you should use it

| If you… | The Backtest toolbar lets you… |
|---|---|
| Have a trading hunch | Test it on years of real data in seconds |
| Wonder "is this actually any good?" | Get hard numbers: return, risk, win rate |
| Want to avoid expensive mistakes | Fail *on paper* instead of with real money |
| Are comparing two ideas | Run both and put the scorecards side by side |
| Forget that trading has fees | See exactly how much fees + slippage eat your profit |

The core benefit: **it turns a vague opinion into evidence.** Instead of "I think buying
dips works," you get "this rule returned +34% with a 58% win rate and a worst-case loss
of 12% over the last 3 years."

---

## 2. The one rule before you start

**Load data first.** The Backtest panel tests *whatever chart is currently loaded*. If no
price data is loaded, the panel will tell you *"Please load market data first."*

On the **left sidebar** (Market Data section):
1. **Symbol** — type a ticker or company name (e.g. `AAPL`, `Tesla`).
2. **Start Date / End Date** — the historical window to test over.
3. **Initial Capital** — your pretend starting cash (e.g. `10000`).
4. Press **REFRESH** (or `Ctrl+Enter`). Changing the symbol loads automatically.

Now the chart shows prices, and the Backtest panel on the right is ready.

---

## 3. Tour of the toolbar (top to bottom)

The panel has three tabs at the top — **Backtest**, **Optimizer**, **Data**. This guide
is about the **Backtest** tab (the default). It's made of four collapsible sections plus
the big orange **RUN BACKTEST** button.

> 💡 See a small **`?`** next to a label? Hover it for a plain-language tooltip. Every
> control in the panel has one.

### Section A — Execution Type
*"How should the app spend and cash out my money?"*

This is the single most important choice. Pick one of three styles:

| Mode | Plain meaning | Best for |
|---|---|---|
| **Trading — Full Buy/Sell** | Go all-in on a buy signal, then fully cash out on a sell signal. | Classic in-and-out trading. |
| **Accumulation — DCA** | Put a **fixed dollar amount** in on every buy signal and keep building a position (dollar-cost averaging). No selling required. | Long-term "keep buying the dip" investing. |
| **Rebalancing — Partial** | Trade only a **percentage** of your portfolio per signal, scaling in and out gradually. | Smoother, less all-or-nothing exposure. |

Your choice here changes which options appear in the next section.

### Section B — Trade Setup
*"The fine-tuning knobs."* Only the knobs relevant to your Execution Type appear:

**Shown in Trading mode:**
- **Strategy Preset** — quick starting points: `Swing`, `Position`, `Trend` (or `Custom`). Sets sensible holding periods and stops for you.
- **Min Holding Period (bars)** — force the trade to stay open at least N bars before it's allowed to sell. Stops jittery in-and-out churn.
- **Trailing Stop (%)** — auto-sell if price falls this % from its peak. Your safety net.
- **Take Profit (%)** — auto-sell once you're up this %. Locks in gains. (`0` = off.)
- **Position Scaling (%)** — add this % more to your position on repeated buy signals.
- **Kelly Criterion (Win Rate + Win/Loss Ratio)** — an advanced bet-sizing formula. Leave at defaults (0.50 / 1.50) unless you know it.

**Shown in Accumulation mode:**
- **Amount Per Buy ($)** — how many dollars to invest on each buy signal (e.g. `1000`).

**Shown in Rebalancing mode:**
- **Position Size (%)** — what slice of the portfolio to trade per signal (e.g. `25`).
- Plus Min Holding Period, Trailing Stop, and Take Profit.

**Always shown — Consecutive Signals:** controls what happens when the same signal fires
over and over on consecutive bars:
- **Scale-in** (default) — act every time. *(Repeated buys stack up.)*
- **Edge trigger (0→1 only)** — act only the moment a signal first turns on. Avoids piling in.
- **Cooldown** — after acting, wait N **bars** (the *Cooldown bars* box) before acting again.
- **Reset + Cooldown** — stricter: the signal must switch fully off *and* the cooldown must pass.

### Section C — Signals
*"What actually triggers a buy or a sell?"* This is your strategy's brain.

- **Search / Category filters** — narrow the long list of available indicators (RSI, MACD, Bollinger, etc.).
- **The signal list** — tick the indicators you want as **buy** triggers and **sell** triggers.
- **OR / AND toggle:**
  - **OR** — fire if *any* selected signal triggers (more trades, looser).
  - **AND** — fire only when *all* selected signals agree (fewer trades, stricter/higher-conviction).
- **AND Window (slider)** — when using AND, how close together (in bars) the signals must occur to still "count as agreeing." `0` means same bar.

> ⚠️ **You must select at least one buy signal.** In **Trading** mode you also need at
> least one sell signal (otherwise the app never knows when to cash out).

### Section D — Transaction Costs
*"Make the simulation honest."* Real trading isn't free. These get charged on every trade:

- **FX Fee (%)** — currency-conversion fee (default `0.15`).
- **Slippage (%)** — the small price you lose between deciding and actually filling (default `0.05`).
- **Commission (%)** — broker fee per trade (default `0.00`).

The hint *"Trading 212 UK: 0% commission, 0.15% FX fee"* is a real-broker preset you can copy.

> Leaving costs in gives you the **truth**. Setting them all to `0` gives you the
> **fantasy** best case. The results panel shows you *both*, so you can see the gap.

### The button — RUN BACKTEST
Press it. The results appear right below.

---

## 4. Reading your results

After a run you get a green *"Backtest completed successfully!"* banner, a one-line
portfolio strip, and a grid of six **scorecards**:

| Scorecard | What it means | Good sign |
|---|---|---|
| **Total Return** | Overall % gain/loss. Also shows *"NO COSTS"* — what you'd have made with zero fees. | Positive, and close to the no-costs number. |
| **Sharpe** | Return adjusted for how bumpy the ride was. | ≥ 1 (labelled **ROBUST**). |
| **Max DD** (drawdown) | The worst peak-to-valley drop along the way — your stomach test. | Milder than −20% (**CONTROLLED**). |
| **Trade Count** | How many trades happened. | Enough to be meaningful (not 2, not 2000). |
| **Win Rate** | % of trades that made money. | Above 50%. |
| **Profit Factor** | Total profits ÷ total losses. | Above 1.00 — you make more than you lose. |

The portfolio strip also shows **COST DRAG** — exactly how much money fees + slippage
cost you, in both % and dollars. This is the honesty check: a strategy that only wins
*before* costs isn't a real strategy.

> **Reading tip:** a high return with a *terrible* Max DD or a win rate under 40% is a
> warning, not a win — it may have gotten lucky on one or two trades. Look at all six
> cards together.

---

## 5. Example workflows

### Workflow 1 — "Does buying oversold RSI dips work on Apple?" (beginner)
1. Left sidebar: Symbol `AAPL`, dates last 3 years, capital `10000`, **REFRESH**.
2. Execution Type → **Trading**.
3. Signals → tick an **RSI oversold** signal for **buy**, an **RSI overbought** signal for **sell**. Logic = **OR**.
4. Transaction Costs → leave defaults (honest).
5. **RUN BACKTEST**. Read Total Return, Win Rate, Max DD.
6. Compare **Total Return** vs its **NO COSTS** figure — how much did fees hurt?

### Workflow 2 — "I want fewer, higher-conviction trades" (intermediate)
1. Same setup, but pick **two** buy signals (e.g. RSI oversold **AND** MACD bullish).
2. Signals logic → **AND**, AND Window → `2` (they must agree within 2 bars).
3. Trade Setup → set a **Trailing Stop** of `8%` and **Min Holding Period** of `5` bars.
4. Run it. You'll see **Trade Count** drop and (ideally) **Win Rate** rise.

### Workflow 3 — "Set-and-forget dollar-cost averaging" (long-term)
1. Execution Type → **Accumulation**.
2. Trade Setup → **Amount Per Buy** = `500`.
3. Signals → one broad buy signal (no sell signal needed in this mode).
4. Run it to see how steady drip-buying would have grown your capital.

### Workflow 4 — "Fees reality check"
1. Run any strategy with **all costs = 0**. Note the Total Return.
2. Restore realistic costs (FX `0.15`, Slippage `0.05`) and run again.
3. The difference is your **COST DRAG** — proof of whether the edge survives real-world friction.

### Workflow 5 — "I don't know which signals to pick" → use the Optimizer
Switch to the **Optimizer** tab (next to Backtest). Instead of guessing, it **tries many
signal combinations for you** and ranks them by the metric you choose (Return, Sharpe,
Drawdown, or Trades). Then click **Apply Best Strategy** to drop the winner straight into
the Backtest panel — and re-run it there to inspect the full scorecard.

---

## 6. Save what works

Found a setup you like? Use the **Saved Configurations** section in the left sidebar:
type a **Name**, click **Save**, and your whole toolbar setup is stored. Reload it any
time from the **Preset** dropdown — no need to re-tick everything.

---

## 7. Quick troubleshooting

| You see… | It means… | Fix |
|---|---|---|
| *"Please load market data first"* | No prices loaded. | Set a symbol + dates on the left, press REFRESH. |
| *"Select at least one buy signal"* | No buy trigger chosen. | Tick a buy signal in the Signals section. |
| *"Trading mode requires at least one sell signal"* | Trading mode needs an exit rule. | Tick a sell signal, or switch to Accumulation mode. |
| Zero or very few trades | Your AND rules are too strict. | Loosen to **OR**, or widen the **AND Window**. |
| Amazing return, scary Max DD | Possibly one lucky trade. | Check Trade Count + Win Rate before trusting it. |

---

## 8. The 30-second mental model

1. **Load data** (left) → 2. **Pick a style** (Execution Type) → 3. **Tune the knobs**
(Trade Setup) → 4. **Choose triggers** (Signals) → 5. **Keep it honest** (Costs) →
6. **RUN** → 7. **Read the six cards** → 8. **Save** if it's good, or tweak and repeat.

That loop — *idea → test → measure → refine* — is the entire point of the toolbar. It
lets you be wrong cheaply and often, so the ideas that survive are the ones worth real
attention.

*Not financial advice. For research and learning only.*
