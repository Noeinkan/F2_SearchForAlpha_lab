# Ways to use SearchForAlpha Lab

Step-by-step examples across the three workspaces: the **terminal** (backtests and
the Optimizer), **Fundamentals** (a company's financials and valuation) and the
**Flow Scanner** (what options traders are doing today).

For the full reference behind each panel, see the
[Backtest toolbar guide](docs/backtest-toolbar-guide.md) and the
[Optimizer guide](docs/optimizer-panel-guide.md).

> Educational and research use only. A backtest shows what *would have* happened,
> not what will, and no screen in this app is a buy or sell recommendation.
> Not financial advice.

## Where each part runs

| Part | Public demo (<https://alpha.demos.noeinsolutions.com/>) | Local workspace (`python main.py`) |
| --- | --- | --- |
| Backtesting and the Optimizer | Yes: 12 tickers, prices frozen at the 11 Sep 2026 close | Yes: ~13k tickers, live Yahoo prices |
| Fundamentals | Yes, frozen at the same close (SPY and QQQ are funds and have none) | Yes, live from SEC filings and Yahoo |
| Flow Scanner | **No**: it needs live option chains | Yes |

## Contents

**Part 1: Backtesting and the Optimizer**

1. [Test a trading idea](#1-test-a-trading-idea)
2. [Let the Optimizer find the signals](#2-let-the-optimizer-find-the-signals)
3. [Check whether the winner holds up](#3-check-whether-the-winner-holds-up)
4. [Compare regular buying with holding](#4-compare-regular-buying-with-holding)
5. [The Golden Cross](#5-the-golden-cross)
6. [Connors RSI(2) dip buying](#6-connors-rsi2-dip-buying)
7. [Buy dips only in sideways markets](#7-buy-dips-only-in-sideways-markets)
8. [Squeeze breakout with a stop](#8-squeeze-breakout-with-a-stop)
9. [Stress-test a strategy](#9-stress-test-a-strategy)

**Part 2: Fundamentals**

10. [Is this a quality business?](#10-is-this-a-quality-business)
11. [What price would be a bargain?](#11-what-price-would-be-a-bargain)
12. [Get a second opinion on value](#12-get-a-second-opinion-on-value)
13. [Spot a recent slowdown](#13-spot-a-recent-slowdown)

**Part 3: Flow Scanner (local workspace only)**

14. [See what options traders are doing today](#14-see-what-options-traders-are-doing-today)
15. [Find the unusual trades](#15-find-the-unusual-trades)
16. [Map the price levels options traders are watching](#16-map-the-price-levels-options-traders-are-watching)
17. [Keep a watchlist scanned automatically](#17-keep-a-watchlist-scanned-automatically)

**Part 4: Putting it together**

18. [From company to trade plan](#18-from-company-to-trade-plan)

---

## Before you start

**Sign in (demo only).** Open the demo, type your email, and enter the 6-digit code
it sends you. That starts a 7-day free trial.

**Demo tickers:** TSLA, AAPL, MSFT, NVDA, AMZN, GOOGL, META, JPM, KO, XOM, SPY, QQQ.
Daily bars go back to 2006 (or the listing date); hourly bars cover the last two years.

**The header** has three buttons, one per workspace: **SFA** (the terminal),
**FUNDAMENTALS** and **FLOW**. Each opens on the symbol you have loaded.

**Three things that are hidden by default in the terminal:**

- **Indicator settings** are the ⚙ icons in the left sidebar. Changing a number
  there recalculates the signals straight away, with no reload.
- **Signal categories.** In the Backtest panel's Signals section, the SMA, EMA, ADX,
  ATR, OBV, VWAP and STOCH signals only appear after you tick their box under
  **Categories**.
- **Every result depends on the loaded chart.** If the panel says *"Please load
  market data first"*, pick a symbol on the left, or press **⟳** in the header.

---

## Part 1: Backtesting and the Optimizer

### 1. Test a trading idea

*"Does buying Apple on RSI dips make money?"* A backtest replays past prices and
trades your rules on paper, so you see the outcome without risking money.

1. **Left sidebar:** click the symbol box (or press `/`), type `AAPL` and pick it.
   The chart loads on its own.
2. **Right panel → Backtest tab → Test Window:** click **2Y** and leave Initial
   Capital at `10000`.
3. **Execution Type:** choose **Trading – Signal In/Out**.
4. **Signals:** tick `RSI_Oversold_Buy` as a buy and `RSI_Overbought_Sell` as a sell.
   Leave the logic on **OR**.
5. **Transaction Costs:** leave the defaults, so the result includes realistic fees.
6. Press **RUN BACKTEST**.
7. **Read the six scorecards:** Total Return, Sharpe, Max DD, Trade Count, Win Rate,
   Profit Factor. Compare Total Return with its **NO COSTS** figure to see how much
   fees cost you.

### 2. Let the Optimizer find the signals

The Optimizer tries many combinations of buy and sell signals and ranks them.

1. Load a symbol on the left, for example `NVDA`.
2. On the Backtest tab, click **OPEN OPTIMIZER**. The full-screen Optimizer opens.
3. **Left rail:** leave **Max Signals per Side** at `2` and set **Max Combinations**
   to `150`. Those are the demo's limits; asking for more gets capped.
4. Set **Sort Results By** to **SCORE** and click **SEARCH SIGNAL COMBOS**. A progress
   bar shows how many combinations it has tested.
5. When it finishes, re-sort the table by **SHARPE**, then by **DD**. Prefer a
   combination that ranks well in all of them.
6. Check the **DSR %** column. It estimates how likely the result is real, allowing
   for how many combinations were tried. Below 50% means it is probably luck.
7. Click **Apply Best Strategy**. You go back to the Backtest tab with the winning
   signals ticked, and it runs a full backtest that includes your costs.

*The demo allows 25 Optimizer runs per person per day.*

### 3. Check whether the winner holds up

A high rank on past data can be a fluke. These two checks catch most flukes.

1. **Chart toolbar (top right of the chart):** make sure the interval is **D** (daily).
   On 1H or 4H there are only about two years of history, so the regime check will
   almost always say INCONCLUSIVE.
2. Run the Optimizer as in example 2.
3. Click **VALIDATE OOS**, next to Apply. This is an out-of-sample test: it trains on
   12 months and tests on the next 3, five times over. It passes if at least 80% of
   the test windows score a Sharpe above 1.0 and the drop from training to testing
   stays under 0.4.
4. Click **REGIMES**. A table appears with a separate backtest for each market period
   since 2019 (COVID crash, the 2022 bear, the AI bull run, and so on). Each row also
   shows what simply holding the stock would have made.
5. **Read the verdict at the top:**
   - **PASSES:** the strategy did well in at least 3 of the 7 periods, including the
     2022 bear.
   - **FAILS:** it did not meet that rule.
   - **INCONCLUSIVE:** some periods are missing data.

### 4. Compare regular buying with holding

1. Load `SPY` on the left.
2. **Test Window:** click **5Y**.
3. **Execution Type:** choose **Accumulation – DCA**. This spends a fixed amount on
   every buy signal and never sells.
4. **Trade Setup:** set **Amount Per Buy** to `500`.
5. **Signals:** tick one buy signal, such as `RSI_Oversold_Buy`. Sell signals are
   ignored in this mode.
6. Press **RUN BACKTEST**.
7. Scroll to the **VS BUY & HOLD** cards:
   - **Excess Return:** how much more (or less) you made than just holding SPY.
   - **Alpha:** whether that difference came from skill or just from being invested
     more of the time.

   Win Rate and Profit Factor stay blank here. That is expected: nothing is ever sold.

### 5. The Golden Cross

*Follow the long-term trend and step aside in bear markets.* Moving-average
crossovers are the classic trend-following rule. The usual claim is that they give up
some return but avoid the worst crashes, and the demo's SPY history from 2006
includes 2008 to test that.

1. **Left sidebar:** load `SPY`.
2. **Sidebar → Overlays:** tick **SMA** so the averages show on the chart. Click the
   **SMA ⚙** and set Short `20`, Medium `50`, Long `200`.
3. **Backtest tab → Test Window:** click **MAX**.
4. **Execution Type:** choose **Rebalancing – Target Weight**. Under Trade Setup, set
   **Portfolio Weight** to `100`. Each buy then goes all in and each sell gets fully
   out, which makes the comparison with holding SPY fair.
5. **Signals:** under Categories, tick **SMA**. Then tick `SMA_TripleCross_Buy` as a
   buy and `SMA_TripleCross_Sell` as a sell.
   *The app's version needs the three averages stacked in order and the price above
   the short one, not just a single crossing.*
6. **Trade Setup → Consecutive Signals:** choose **Edge trigger (0→1 only)**. This
   signal stays "on" for as long as the trend lasts; without this setting it would
   buy again on every bar.
7. Press **RUN BACKTEST**.
8. **Compare** **Max DD** with the drawdown of simply holding, and check **Excess
   Return**. The usual result is a smaller worst loss and a lower return. Whether
   that trade-off is worth it is your call.

### 6. Connors RSI(2) dip buying

*Very short-term dip buying on an index.* Larry Connors popularised using a 2-day
RSI instead of the usual 14-day one to buy short, sharp dips in index funds. The app
ships a ready-made strategy for it, called `connors_rsi2`.

1. Load `SPY` and set **Test Window** to **MAX**.
2. **Sidebar → Indicators:** click the **RSI ⚙** and set Period `2`, Oversold `10`,
   Overbought `70`.
3. **Execution Type:** **Trading**. Under **Signals**, tick `RSI_Oversold_Buy` as a buy
   and `RSI_Overbought_Sell` as a sell.
4. **Consecutive Signals:** **Edge trigger (0→1 only)**, so a dip that lasts three days
   does not buy three times.
5. Press **RUN BACKTEST**. Look at **Win Rate** and **Trade Count**. Published tests
   of this rule report win rates above 70%, but gains per trade are small, so check
   **COST DRAG** too.
6. **Let the app fine-tune the numbers:**
   1. Click **OPEN OPTIMIZER** and open the **Tune this bundle · Param grid** section
      on the left.
   2. Set **Strategy bundle** to `connors_rsi2`.
   3. Under **Parameters**, tick only `rsi_window` and `rsi_oversold`. That makes 84
      combinations. With all three ticked the grid is over 2,000, far beyond the
      demo's cap of 250.
   4. Press **SCAN PARAM GRID**, then **APPLY PARAMS**. The best settings are copied
      back into the Backtest tab.
7. **Afterwards:** set RSI back to `14 / 30 / 70`. The ⚙ setting stays in place for
   your next test.

*The classic version also only buys when the price is above its 200-day average. The
closest signal here is `SMA_TrendFollow_Buy`, which also needs the averages stacked in
order, so it is stricter.*

### 7. Buy dips only in sideways markets

Buying dips works when a stock moves sideways and loses money in a strong downtrend.
ADX is an indicator that measures how strong a trend is. One published test claims
that adding an ADX filter removed most of the biggest losing trades and cost only a
few winners. Here is how to check that yourself.

1. Load `KO`, a stock that tends to move sideways. Set **Test Window** to **5Y** and
   choose **Trading**.
2. **Run A, no filter:**
   - Buy `BB_MeanReversion_Buy`, sell `BB_MeanReversion_Sell`, logic **OR**.
   - Press **RUN BACKTEST** and write down Trade Count, Win Rate, Max DD and Profit
     Factor.
3. **Run B, with the filter:**
   1. Under Categories, tick **ADX**.
   2. Also tick `ADX_RangeRegime_Buy` as a buy. It is only "on" when ADX is below 20,
      meaning no strong trend.
   3. Switch the logic to **AND** and leave **AND Window** at `0`, so both must be
      true on the same day.
   4. Run it again.
4. **Compare the two runs.** You want fewer trades, a smaller Max DD and a higher
   Profit Factor. If Trade Count drops to a handful, the filter is too strict: raise
   **Range Threshold** in the **ADX ⚙** (for example to `25`).

### 8. Squeeze breakout with a stop

*Then check how the exit is simulated.* A Bollinger "squeeze" is a quiet period when
the bands narrow, and it often comes before a big move. Breakout traders pair it with
a stop.

1. Load `TSLA`, set **Test Window** to **2Y** and choose **Trading**.
2. **Signals:** buy `BB_Squeeze_Buy`, sell `BB_Squeeze_Sell`.
3. **Trade Setup:** **Trailing Stop** `8`, **Take Profit** `25`.
4. **Run 1:** leave **Exit Handling** on **Close check (default)** and press
   **RUN BACKTEST**. Note Total Return and Max DD.
5. **Run 2:** set **Exit Handling** to **Trailing stop order** and run again. The stop
   can now be hit by a day's low, not just its close. That is closer to reality and
   usually looks worse; TSLA's volatility makes the gap obvious.
6. **Run 3:** set **Exit Handling** to **OCO bracket** and run again. The stop and the
   target now stay fixed at the entry price instead of trailing. If a single day
   touches both, the app counts it as the stop.
7. **Check the individual trades:**
   1. Open the **Data** tab, next to Backtest and Optimizer.
   2. Under Columns, keep **Portfolio** ticked.
   3. Look at `Holding_Sessions` to see which trades were held overnight.
   4. **EXPORT CSV** downloads the table (up to 5,000 rows).

### 9. Stress-test a strategy

*Other stocks, another timeframe, nudged settings.* Robustness guides agree on one
test: a real edge should still work on similar markets, on another timeframe, and
when a setting is changed slightly. A strategy that only works on one exact setup is
probably a fit to past noise.

1. Build any strategy you like, for example from example 7, and run it once on the
   stock you designed it for.
2. **Other stocks:** load `JPM`, then `XOM`, then `QQQ`, and press **RUN BACKTEST**
   after each one. Your ticked signals and settings stay in place when you switch
   symbol.
3. **Another timeframe:** in the chart toolbar (top right of the chart), click **1H**
   and run again.
   - The demo only has about two years of hourly data, so set the Test Window to
     **1Y** or **2Y** for a like-for-like comparison.
   - Click **D** afterwards to go back to daily bars.
4. **Nudged settings:** go back to the original stock and change one number by about
   10–20%, for example Bollinger **Window** from `20` to `17`, then `23`, in the
   **BB ⚙**. Run each version.
5. **Keep a small table:** one row per run, with Total Return, Sharpe, Max DD and
   Trade Count.
6. **Read the table:**
   - Similar results across rows mean the strategy is robust.
   - One great row surrounded by poor ones means you found luck, not an edge.
7. If it survives, open the Optimizer and run **VALIDATE OOS** and **REGIMES** on it
   (example 3). Then save it from the left sidebar: **Saved Configurations**, type a
   name, click **Save**.

---

## Part 2: Fundamentals

The Fundamentals workspace shows up to ten years of a company's financials and
values the business three separate ways. It opens from the **FUNDAMENTALS** button in
the header, with `G` then `F`, or at the address `/fundamentals/<TICKER>`. Click
**CLOSE** to go back to the chart.

Two habits help in every example below:

- **Hover** any row name for a one-line definition.
- **Click** any cell. The numbers it is built from light up across the tables, and a
  panel explains the formula and where each input came from. Press `Esc` to clear it.

In the local workspace, filings are cached for 24 hours and the price for 15
minutes; **REFRESH** fetches them again. In the demo everything is frozen, so REFRESH
changes nothing.

### 10. Is this a quality business?

The "Rule #1" method popularised by Phil Town starts from five growth numbers, the
**Big Five**, and wants each of them growing at 10% a year or more over ten years.
A company that manages that for a decade usually has a durable advantage.

1. Load `KO` and click **FUNDAMENTALS** in the header.
2. **Toolbar and top strip:** the company name sits in the toolbar. The strip below it
   shows **LAST PRICE**, currency, **Last FY** (the latest full fiscal year) and
   **Updated** (when the data was fetched).
3. **Quality → Big Five:** one row per measure, one column per year, then three summary
   columns: **10Y**, **5Y** and **1Y**.
   - **ROIC:** the return the company earns on the money invested in it.
   - **Equity-GR, EPS-GR, Sales-GR, FCF-GR:** growth of book value, earnings per share,
     revenue and free cash flow.
   - **Debt Ratio:** long-term debt divided by free cash flow, in years. Roughly, how
     many years of cash it would take to repay the debt. Lower is safer.
   - **PE Ratio:** price divided by earnings, shown for context, without a grade.
4. **Read the arrows in the summary columns:** **↑** 10% or more, **→** between 0 and
   10%, **↓** zero or negative. The growth rows show compound yearly growth; ROIC
   shows an average.
5. **Compare three very different companies:** repeat for `NVDA` (fast growth) and
   `XOM` (cyclical, it rises and falls with oil prices). Mostly ↑ across 10Y, 5Y and
   1Y means steady quality. A strong 10Y with a ↓ at 1Y is a business that has
   recently stalled.

### 11. What price would be a bargain?

Rule #1 turns growth into a **Sticker Price** (what the business is worth today if you
want a 15% yearly return) and then demands a 50% discount on it, the **margin of
safety**.

1. Open Fundamentals for `MSFT` and scroll to **Valuation → Rule #1**.
2. **Read the assumptions line:** `MARR 15%` is the yearly return you require; `MOS 50%`
   is the margin of safety.
3. **Follow the table from top to bottom.** Each row feeds the next:
   1. **Estimated EPS GR:** the growth rate used. It takes the lowest positive of
      **Analysts' GR**, **Historical Equity GR** and past earnings growth, so it stays
      conservative.
   2. **Estimated EPS 10y:** today's earnings per share grown for ten years at that
      rate.
   3. **Rule #1 PE:** the lowest of three price/earnings ratios (**Rule #1st
      Price/Earn Ratio**, **Forward Price/Earn Ratio**, **Historical PE**).
   4. **Fut. Market Price (10 Y):** the ten-year earnings times that ratio.
   5. **Sticker Price:** that future price brought back to today at your 15%.
   6. **Entry Price:** the Sticker Price with the 50% discount applied. This is the
      buy-below level.
4. **Compare Entry Price with LAST PRICE** in the top strip.
   - The **Close/Entry price ratio** row uses the **Year-end Close** (the price at the
     end of the last fiscal year), not today's price. Below 1 means that price was
     under the entry price.
5. **Click Sticker Price** to see every input light up, then click one of those
   inputs to see where it came from.
6. **Know its limits:** the method is built for steady, predictable businesses. On a
   fast grower such as `NVDA`, a small change in the growth rate moves the Sticker
   Price a lot. Compare it with `KO` to see the difference.

### 12. Get a second opinion on value

Rule #1 is one theory of value. The same section holds two more, and the app
deliberately does not average them.

1. Stay on the same company and scroll to **Valuation → DCF (FCFE)**. A DCF
   (discounted cash flow) values the company as the cash it will hand to shareholders
   in future, brought back to today.
2. **Read the assumptions line:**
   - `r`: the yearly return shareholders require (the discount rate).
   - `g1`: cash-flow growth over the first years.
   - `g2`: growth forever after that.
3. **Read the key rows:**
   - **DCF Fair Value:** value per share.
   - **Upside vs Price:** how far the fair value sits above (positive) or below
     (negative) the current price.
   - **Terminal Value Share:** how much of that value comes from the "forever after"
     part. A high share means the answer rests mostly on long-term guesses. The notes
     at the bottom of the page flag it above 75%.
4. **Read the sensitivity grid** (*"fair value / share — center = base case"*):
   - Rows change `r` and columns change `g₂`.
   - Green cells are more than 2% above the base case, red cells more than 2% below.
   - If a small step in either direction pushes the fair value across today's price,
     the DCF cannot settle the question.
5. **Analyst Targets:** **Recommendation**, **Analysts Covering**, **Target Low / Mean /
   Median / High** and **Upside vs Last**. These are brokers' price targets from Yahoo,
   not a model. **Open analysis ↗** opens Yahoo's live page in a new tab.
6. **Put the three side by side:** Rule #1 **Entry Price**, **DCF Fair Value** and
   analysts' **Target Mean**.
   - All three above today's price means a consistent case.
   - Wide disagreement means one assumption drives the answer; click the cells to
     find which.

If the panel says *"DCF unavailable for this symbol (needs positive FCFE and share
count)"*, the company has negative free cash flow, and a DCF cannot value it.

### 13. Spot a recent slowdown

Ten-year averages hide the last few quarters. The quarterly view shows them.

1. Open Fundamentals for `TSLA` or `AAPL`.
2. **Growth:** six charts (**ROIC**, **Equity**, **Earning per share**, **Sales**,
   **Free Cash Flow**, **Debt**), each with a trend line.
3. **Financials:** switch the toggle in the section header from **Annual** to
   **Quarterly**. The Financials table and the Growth charts switch to quarters.
   Big Five and Valuation stay on yearly numbers.
4. **Look at the last four to six quarters** of Sales and Earning per share. A line
   that flattens or turns down after years of rising is a slowdown the 10Y figures
   will not show for a while.
5. **Financials table:** the **Last** column puts today's price next to **Stock Price
   (FYE)**, the price at each period end.
6. **Scroll to the notes at the bottom.** They list missing values, for example
   *"Sales: 2 missing quarterly values"*. The more gaps, the less the charts can be
   trusted. If you see *"Quarterly financials are unavailable for this symbol."*,
   stay on Annual.

---

## Part 3: Flow Scanner (local workspace only)

The Flow Scanner reads a stock's option chain from Yahoo and flags unusual activity.
It needs live data, so it runs in the local workspace (`python main.py`) but not in
the public demo.

**What it is not:** Yahoo does not say whether a trade was a purchase or a sale, and
the gamma figures are the app's own estimates. Everything here describes positioning;
none of it forecasts price.

### 14. See what options traders are doing today

1. In the terminal, load `NVDA` and click **FLOW** in the header. The page is also at
   `/flow/NVDA`.
2. If it says *"No report for NVDA yet. Click RESCAN NOW."*, press **RESCAN NOW**.
   - It takes a few seconds. The status line then reads *"Rescanned NVDA at
     14:05:12"*.
   - If it says **RATE LIMITED**, Yahoo is throttling requests. Nothing is wrong with
     the symbol: wait a minute and rescan. An earlier good report stays on screen.
3. **Card header:** the price, a sentiment badge (**BULLISH**, **BEARISH**, **MIXED** or
   **NEUTRAL**; hover it to see why), **REPEAT CALLS** when present, and the **Score**.
4. **Insight lines** under the header say in plain words what drove the badge, tagged
   **BULLISH**, **BEARISH**, **INSTITUTIONAL**, **SPECULATIVE** or **NEUTRAL**.
5. **Key numbers row:**
   - **Prev**, **Day** and **52-week:** the previous close, today's range and the
     year's range.
   - **Put/Call vol:** put volume divided by call volume. Above 1.0 is put-heavy (read
     as hedging or bearish); below 0.7 is call-heavy.
   - **Calls % / Puts %** bar, then **Top calls** and **Top puts**: the busiest strikes
     with their volume.
6. **Score chips:** for example `2 HU × 5 + 1 B × 3 = 13`. The score is 5 per HU,
   3 per B, 2 per U and 10 per RC (the flags are explained in example 15). A higher
   score means more flagged activity, not a better stock.
7. **New to options?** Press **LEARN** for "Options 101", or **GLOSSARY** for every term.
   The **Concepts** section at the bottom of the page has *How to read this page*,
   *Theta Decay* and *Implied Volatility Surface*.

### 15. Find the unusual trades

Guides to unusual options activity agree on what deserves attention: volume above
open interest (new positions being opened), large premium, short-dated contracts far
from the current price, and the same direction repeated.

1. **In the card, Option chain:** pick an expiry in the dropdown (the nearest is
   selected) and choose **Flagged only**.
   - Calls are on the left, strikes in the centre, puts on the right.
   - The **Spot** divider marks today's price, and flagged sides are highlighted.
2. **What the flags mean:**
   - **U – Unusual:** today's volume is above open interest, so new positions are
     likely being opened.
   - **HU – High unusual:** a weekly, out-of-the-money contract with abnormally large
     volume. Often a short-term speculative bet.
   - **B – Block premium:** more than $1M changed hands on one contract. Usually
     institutional size.
   - **RC – Repeat calls:** three or more unusual call strikes on the same expiry.
3. **For a list of individual contracts,** press **OPEN IN NEW TAB**.
   - The report that opens has one row per contract: Strike, Type, Last, Bid, Ask,
     Vol, OI, IV, Premium, Expiry, Flags and **Signal**.
   - Signal labels each row **Block**, **Speculative**, **Bullish bet**, **Hedge** or
     **Flow** (nothing notable).
   - Hover any column header for its definition.
4. **Read it with care:**
   - A big put block may be insurance on shares someone owns, not a bet against the
     stock.
   - One day of activity can be anything. The same direction on several days means
     more, so rescan on the following days and compare.
   - A burst of short-dated calls often comes just before a scheduled event such as
     earnings. Check the company's calendar before reading it as news.

### 16. Map the price levels options traders are watching

Where open interest piles up, options traders and the dealers hedging them have a
stake in the price. Those strikes are often watched as ceilings and floors, especially
in the last days before an expiry.

1. **In the card, Options inventory:** choose an expiry and **Open interest**.
   - Green bars above zero are calls; red bars below zero are puts.
   - Dashed lines mark **Spot**, **Call Resistance** (the strike with the most call open
     interest), **Put Support** (the most put open interest) and **HVL** (today's
     busiest strike).
   - A dotted **Max pain** line appears when available.
2. **Switch to Volume.** If today's busiest strikes sit away from the open-interest
   walls, fresh activity is building somewhere new.
3. **Net gamma exposure:** the app's estimate of dealer gamma at each strike.
   - Green bars to the right are positive and red bars to the left are negative. The
     curves are running totals.
   - The dropdown includes **All expirations**, and the caption under the chart lists
     Call resistance, Put support, HVL and Spot in dollars.
4. **Press ⛶** on any chart to see it full screen.
5. **Write the levels down.** Then press **CLOSE** and look at the price chart: is the
   price sitting just under Call Resistance, or just above Put Support? These levels
   do not appear on the chart, so compare them by eye.
6. **Treat them as context, not barriers.** Walls weaken as open interest moves, and a
   broken level can speed a move up rather than stop it.
7. **Advanced:** the **OI Vanna Model** chart overlays expiries you tick. LEARN →
   *How to read the vanna flow chart* explains it.

### 17. Keep a watchlist scanned automatically

1. **In the project folder,** create or edit `watchlist.txt`: one ticker per line;
   lines starting with `#` are ignored.
2. **Start the dashboard** with `python main.py`. While it runs, it rescans in the
   background:
   - **Which tickers:** those in `watchlist.txt`, plus any ticker already scanned from
     the page, up to 20.
   - **When:** every 15 minutes during US market hours (9:30–16:00 New York time,
     weekdays), plus one last scan after the close. There is no holiday calendar.
3. **Open any of those tickers on the FLOW page.** The status line reads, for example,
   *"Report from 14:05 · auto-refresh every 15 min"*. A page left open picks up the
   newer report on its own within a minute.
4. **To change the interval,** set it in the same PowerShell window before starting,
   for example `$env:SFA_FLOW_REFRESH_MINUTES = "30"; python main.py`. `0` turns the
   background refresh off.
5. **A failed or throttled scan never replaces a good report.** The status line says
   so, for example *"RATE LIMITED — kept the report from 14:05"*.
6. **Without the dashboard,** the scanner runs from the command line:
   - `python scripts/flow_scanner.py NVDA TSLA` scans those symbols.
   - `--watchlist` reads `watchlist.txt`; `--scan` takes the 50 most active US tickers.
   - `--watch` repeats the scan during market hours.

   It writes its own `flow_report.html`; the FLOW page does not read that file.

---

## Part 4: Putting it together

### 18. From company to trade plan

The three workspaces answer different questions: *is the business good and fairly
priced*, *what are options traders positioned for*, and *would a rule have traded it
well*. In the demo, skip step 2.

1. **Fundamentals:** pick a company whose Big Five are mostly ↑ (example 10). Write
   down its **Entry Price** and **DCF Fair Value** (examples 11 and 12).
2. **Flow (local workspace):** click **FLOW** for the same symbol. Write down the
   sentiment badge, **Put/Call vol**, **Put Support** and **Call Resistance** for the
   nearest monthly expiry (examples 14 and 16). Each Flow card also has an
   **Open Fundamentals** link for going the other way.
3. **Backtest:** click **SFA** to return to the terminal. Test a dip-buying rule on this
   stock (example 1 or 7) over **5Y**, with costs left on.
4. **Check VS BUY & HOLD.** For a quality company, simply holding is a hard benchmark.
   A rule that trails it with a deeper drawdown adds nothing.
5. **Validate:** run **REGIMES** (example 3) and the stress test (example 9).
6. **Save** the setup under **Saved Configurations**, named after the symbol. The app
   does not store your notes, so keep the levels from steps 1 and 2 alongside it.

---

## Handy shortcuts

| Keys | What it does |
| --- | --- |
| `/` or `Ctrl + /` | Open symbol search |
| `Ctrl + K` | Open the command palette |
| `Ctrl + B` | Run the backtest |
| `Ctrl + Enter` | Reload market data |
| `G` then `F` | Open Fundamentals for the current symbol |
| `Esc` | Close the open panel or dialog, or clear a Fundamentals selection |

In the demo, saved configurations are kept in your browser only.

## Sources used for inspiration

**Strategies and robustness**

- [Golden Cross Trading Strategy (Backtest Analysis) – QuantifiedStrategies](https://www.quantifiedstrategies.com/golden-cross-trading-strategy/)
- [Trend Following vs Mean Reversion – Robot Traders](https://robottraders.io/blog/trend-following-vs-mean-reversion)
- [RSI(2) – StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2)
- [RSI 2 Strategy: Larry Connors' rules – QuantifiedStrategies](https://www.quantifiedstrategies.com/rsi-2-strategy/)
- [Bollinger Bands Strategy: Backtest Results Guide – StratBase](https://stratbase.ai/en/blog/bollinger-bands-strategy-guide)
- [Bollinger Band Squeeze Breakout with Trailing Stops – PyQuantLab](https://pyquantlab.medium.com/bollinger-band-squeeze-breakout-trading-strategy-with-trailing-stops-7aedc2f10958)
- [How to Use TradingView Strategy Tester (2026 Guide) – ChartWise Hub](https://chartwisehub.com/tradingview-strategy-tester/)
- [Robustness Testing Guide – Build Alpha](https://www.buildalpha.com/robustness-testing-guide/)
- [Trading Strategy Robustness Testing: 2026 Guide – PickMyTrade](https://blog.pickmytrade.io/trading-strategy-robustness-testing-2026-guide/)

**Fundamentals**

- [How to Invest: Margin of Safety & Sticker Price – Rule One Investing](https://www.ruleoneinvesting.com/blog/how-to-invest/how-to-invest-sticker-price-and-margin-of-safety/)
- [Rule #1 Stock Screening – AAII](https://www.aaii.com/journal/article/rule-1-stock-screening)

**Options flow**

- [Unusual Options Activity: The Complete Guide – CenterPoint Securities](https://centerpointsecurities.com/unusual-options-activity/)
- [Deciphering unusual options activity – E*TRADE](https://us.etrade.com/knowledge/library/perspectives/daily-insights/unusual-call-options-activity)
- [Call Walls & Put Walls – DayTrading.com](https://www.daytrading.com/call-put-walls)
- [Call Wall: What It Is and How SpotGamma Uses It – SpotGamma](https://support.spotgamma.com/hc/en-us/articles/15297391724179-Call-Wall-What-It-Is-and-How-SpotGamma-Uses-It)
