# Ten ways to use SearchForAlpha Lab

Step-by-step examples, from a first backtest to stress-testing a strategy.
They are written for the public demo at <https://alpha.demos.noeinsolutions.com/>;
the local workspace (`python main.py`) works the same way, with ~13k tickers and
live prices instead of 12 tickers frozen at the 11 Sep 2026 close.

For the full reference behind each panel, see the
[Backtest toolbar guide](docs/backtest-toolbar-guide.md) and the
[Optimizer guide](docs/optimizer-panel-guide.md).

> Educational and research use only. A backtest shows what *would have* happened,
> not what will. Not financial advice.

## Contents

**Getting started**

1. [Test a trading idea](#1-test-a-trading-idea-does-buying-apple-on-rsi-dips-make-money)
2. [Let the Optimizer find the signals](#2-let-the-optimizer-find-the-signals-for-you)
3. [Check whether the winner holds up](#3-check-whether-the-winning-strategy-holds-up)
4. [Regular buying vs simply holding](#4-compare-regular-buying-with-simply-holding)
5. [Look at a company's financials](#5-look-at-a-companys-financials-before-you-trade-it)

**Classic strategies and robustness checks**

6. [The Golden Cross](#6-the-golden-cross-follow-the-long-term-trend-and-step-aside-in-bear-markets)
7. [Connors RSI(2)](#7-connors-rsi2-very-short-term-dip-buying-on-an-index)
8. [Buy dips only in sideways markets](#8-buy-dips-only-when-the-market-is-going-sideways)
9. [Squeeze breakout with a stop](#9-squeeze-breakout-with-a-stop-then-check-how-the-exit-is-simulated)
10. [Stress-test one strategy](#10-stress-test-one-strategy-other-stocks-another-timeframe-nudged-settings)

---

## Before you start

**Sign in (demo only).** Open the demo, type your email, and enter the 6-digit code
it sends you. That starts a 7-day free trial.

**Demo tickers:** TSLA, AAPL, MSFT, NVDA, AMZN, GOOGL, META, JPM, KO, XOM, SPY, QQQ.
Daily bars go back to 2006 (or the listing date); hourly bars cover the last two years.

**Three things that are hidden by default:**

- **Indicator settings** are the ⚙ icons in the left sidebar. Changing a number
  there recalculates the signals straight away, with no reload.
- **Signal categories.** In the Backtest panel's Signals section, the SMA, EMA, ADX,
  ATR, OBV, VWAP and STOCH signals only appear after you tick their box under
  **Categories**.
- **Every result depends on the loaded chart.** If the panel says *"Please load
  market data first"*, pick a symbol on the left, or press **⟳** in the header.

---

## Getting started

### 1. Test a trading idea: "Does buying Apple on RSI dips make money?"

A backtest replays past prices and trades your rules on paper, so you see the
outcome without risking money.

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

### 2. Let the Optimizer find the signals for you

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

### 3. Check whether the winning strategy holds up

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

### 4. Compare regular buying with simply holding

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

### 5. Look at a company's financials before you trade it

1. Load a company, for example `MSFT` or `KO`. SPY and QQQ are funds and have no
   financials.
2. In the header, click **FUNDAMENTALS** (or press `G` then `F`). The workspace opens
   over the chart.
3. **Quality → Big Five:** ten years of growth and return-on-capital figures. You
   want steady, positive numbers.
4. **Growth:** charts of revenue, earnings and cash flow over time.
5. **Financials:** switch between **Annual** and **Quarterly** at the top of the
   section.
6. **Valuation:**
   - **Rule #1** shows a *Sticker Price* (an estimate of fair value) and a *Margin of
     Safety* price (a discounted buy price). Click any cell to see the formula and
     where each number came from.
   - **DCF** is a second, independent estimate of value.
7. Click **CLOSE** to go back to the chart.

---

## Classic strategies and robustness checks

### 6. The "Golden Cross": follow the long-term trend and step aside in bear markets

Moving-average crossovers are the classic trend-following rule. The usual claim is
that they give up some return but avoid the worst crashes, and the demo's SPY history
from 2006 includes 2008 to test that.

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

### 7. Connors RSI(2): very short-term dip buying on an index

Larry Connors popularised using a 2-day RSI instead of the usual 14-day one to buy
short, sharp dips in index funds. The app ships a ready-made strategy for it, called
`connors_rsi2`.

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

### 8. Buy dips only when the market is going sideways

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

### 9. Squeeze breakout with a stop, then check how the exit is simulated

A Bollinger "squeeze" is a quiet period when the bands narrow, and it often comes
before a big move. Breakout traders pair it with a stop.

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

### 10. Stress-test one strategy: other stocks, another timeframe, nudged settings

Robustness guides agree on one test: a real edge should still work on similar markets,
on another timeframe, and when a setting is changed slightly. A strategy that only
works on one exact setup is probably a fit to past noise.

1. Build any strategy you like, for example from example 8, and run it once on the
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

## Handy shortcuts

| Keys | What it does |
| --- | --- |
| `/` or `Ctrl + /` | Open symbol search |
| `Ctrl + K` | Open the command palette |
| `Ctrl + B` | Run the backtest |
| `Ctrl + Enter` | Reload market data |
| `G` then `F` | Open Fundamentals for the current symbol |
| `Esc` | Close the open panel or dialog |

In the demo, saved configurations are kept in your browser only.

## Sources used for inspiration

- [Golden Cross Trading Strategy (Backtest Analysis) – QuantifiedStrategies](https://www.quantifiedstrategies.com/golden-cross-trading-strategy/)
- [Trend Following vs Mean Reversion – Robot Traders](https://robottraders.io/blog/trend-following-vs-mean-reversion)
- [RSI(2) – StockCharts ChartSchool](https://chartschool.stockcharts.com/table-of-contents/trading-strategies-and-models/trading-strategies/rsi-2)
- [RSI 2 Strategy: Larry Connors' rules – QuantifiedStrategies](https://www.quantifiedstrategies.com/rsi-2-strategy/)
- [Bollinger Bands Strategy: Backtest Results Guide – StratBase](https://stratbase.ai/en/blog/bollinger-bands-strategy-guide)
- [Bollinger Band Squeeze Breakout with Trailing Stops – PyQuantLab](https://pyquantlab.medium.com/bollinger-band-squeeze-breakout-trading-strategy-with-trailing-stops-7aedc2f10958)
- [How to Use TradingView Strategy Tester (2026 Guide) – ChartWise Hub](https://chartwisehub.com/tradingview-strategy-tester/)
- [Robustness Testing Guide – Build Alpha](https://www.buildalpha.com/robustness-testing-guide/)
- [Trading Strategy Robustness Testing: 2026 Guide – PickMyTrade](https://blog.pickmytrade.io/trading-strategy-robustness-testing-2026-guide/)
