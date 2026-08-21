# Market data vendors — what the free tiers actually offer

Survey run 2026-08-21, while looking for (a) a second source behind
`fetch_data` and (b) intraday history deeper than Yahoo's 728-day cap.

**Outcome: neither gap has a free solution today.** Yahoo via `yfinance`
remains the only wired source. This page records what was checked so the
question does not have to be re-opened from scratch.

## The two gaps

1. **A second daily source.** Needed as a fallback when Yahoo rate-limits, and
   as a cross-check for the price-adjustment audit
   ([data-adjustment.md](data-adjustment.md)).
2. **Intraday beyond 728 days.** `MAX_LOOKBACK_DAYS` in
   [lib/timeframes.py](../lib/timeframes.py) clamps 1h/4h requests to Yahoo's
   limit. Deeper 1h bars would need a vendor that keeps them.

## What was checked

| Vendor | Free tier | Daily fallback? | Deep intraday? |
|---|---|---|---|
| **Stooq** | keyless, no signup | ❌ blocked, see below | ❌ no intraday product |
| **Alpha Vantage** | 25 req/day | ⚠️ viable but tiny quota | ❌ premium-gated |
| **Twelve Data** | 800 credits/day | ⚠️ viable, needs key | ❌ ~2 years, no gain |
| **Tiingo** | 1000 req/day, 500 symbols/mo | ⚠️ viable, needs key | ❌ IEX-only volume |
| **Polygon.io** | 5 req/min | ⚠️ EOD-oriented | ❌ not on free tier |

### Stooq — keyless, but behind a JS challenge

Stooq was the preferred option precisely because it needs no key and no
signup, so it would work on a fresh clone. Its CSV endpoint
(`https://stooq.com/q/d/l/?s=aapl.us&i=d`) **no longer serves data to
non-browser clients**. It answers HTTP 200 with an HTML interstitial reading
*"This site requires JavaScript to verify your browser"*.

Verified 2026-08-21 — none of these got CSV back:

- no custom headers → HTTP 404 stub page
- a browser `User-Agent` → HTTP 200, JS challenge page
- `User-Agent` + `Accept` + `Accept-Language` → same challenge
- a session that loads the homepage first → same challenge, and **no cookie is
  set at all**, so there is no token to carry forward

Clearing it needs real JavaScript execution, i.e. a headless browser. That is
far too heavy and too brittle for a fallback data source, so the adapter was
removed rather than shipped dead.

### Alpha Vantage — deep intraday exists, but is paid

`TIME_SERIES_INTRADAY` does support a `month=YYYY-MM` parameter covering *"any
month in the last 20+ years since 2000-01"*, at 1/5/15/30/60-minute
resolution. This is exactly what gap 2 needs. The docs mark it:

> 💡 Tip: This is a premium endpoint. If you would like to access realtime,
> 15-minute delayed, and/or historical intraday data, please subscribe to a
> premium membership plan.

The free tier is 25 requests/day and 15-minute delayed.

### Twelve Data — no depth advantage

Free tier is 800 credits/day, but intraday history runs roughly 2 years, and
1-minute data starts 2020-02-10. No improvement over Yahoo's 728 days.

### Tiingo — deep intraday, wrong volume

The free tier is the most generous surveyed (1000 req/day, 50/hour, 500 unique
symbols/month, 30+ years of daily), and its intraday history reaches back to
2016 — genuinely deeper than Yahoo.

The blocker is *which* intraday. Tiingo's intraday is the **IEX feed**, and its
volume field is documented as *"the number of shares traded on IEX only"* — a
few percent of the consolidated tape. This repo ships **VWAP and OBV**
strategies, both of which read volume directly. Backtesting them on IEX-only
volume produces signals that are not comparable to the Yahoo bars in the same
cache, without any visible sign that the meaning changed.

Tiingo's *daily* feed is composite and would serve gap 1 fine. It needs a free
API key, so it does nothing on a fresh clone until one is configured.

## What would reopen these

- **Gap 1:** any free daily source that responds to a plain HTTP client with
  split- and dividend-adjusted bars. The seam is ready — see below.
- **Gap 2:** a free or cheap source of intraday bars with **consolidated**
  volume. Deeper bars alone are not enough; a partial-tape feed silently breaks
  the volume-based strategies.

## The seam, for whoever adds one

The vendor coupling is one function: `_yahoo_history()` in
[lib/data_processing.py](../lib/data_processing.py). Everything around it —
timezone normalisation, the NaN-Close drop, 4h resampling, validation, error
classification — is vendor-agnostic. A new source needs to:

1. Return a frame with `Open/High/Low/Close/Volume` and a `DatetimeIndex`.
2. Return **adjusted** prices, or its bars will not match the cache
   ([data-adjustment.md](data-adjustment.md)).
3. Raise via `classify_fetch_error()` from
   [lib/fetch_errors.py](../lib/fetch_errors.py) so retries and the dashboard's
   rate-limit state work the same way.
4. Set `df.attrs["source"]`. **The parquet cache key is `{ticker}_{interval}`
   with no vendor dimension**, so `_persist()` in
   [lib/dash/helpers.py](../lib/dash/helpers.py) refuses to cache any frame not
   tagged `yahoo`. Without that guard two vendors' bars interleave in one file.
5. Read its API key from an `SFA_*` env var if it needs one, following the
   convention in [lib/dash/dash_config.py](../lib/dash/dash_config.py), and add
   it to `.env.example`. Note `.env` is **not** auto-loaded — there is no
   `python-dotenv` dependency, so the value must come from the shell or the
   service wrapper.
