# Public demo

**Live:** <https://alpha.demos.noeinsolutions.com/> — no sign-up, nothing to install.

The demo is the research terminal running on a **frozen snapshot**: charts,
indicators, all three backtest modes, the signal-combination optimiser, grid
search, the Bayesian sweep, walk-forward validation and the fundamentals
workspace all work. What it cannot do is reach the outside world or place an
order.

## What is different from the workspace

| | Workspace (`python main.py`) | Public demo (`python -m demo.server`) |
|---|---|---|
| Prices | Yahoo Finance, live | `demo/fixtures/ohlcv/`, frozen at the **11 Sep 2026** close |
| Fundamentals | SEC EDGAR + Yahoo, live | `demo/fixtures/fundamentals/`, frozen at the same close |
| Tickers | ~13k in the symbol search | 12: TSLA, AAPL, MSFT, NVDA, AMZN, GOOGL, META, JPM, KO, XOM, SPY, QQQ |
| History | everything Yahoo serves | daily bars from 2006 (or listing), hourly bars for the last two years |
| Broker / paper trading / live mode | `sfa run` against an IB Gateway | **absent**: `ib_async` not installed, `lib/live/` deleted from the image, importing it refused |
| Flow Scanner | live options chains | off (it needs a live chain) |
| Presets, watchlists | saved to `config/` | kept in the visitor's browser only |
| State | one user, one process | one in-memory state per visitor, dropped after 30 idle minutes |

The page says so itself: the header's status label reads
`DEMO · DATA 11 SEP 2026`, and a dismissible banner states what is frozen and
what is switched off.

## Limits

Every limit is an environment variable; the defaults live in
`demo/settings.py` and the running values in `.deploy/compose.yml`.

| Variable | Default | What it caps |
|---|---|---|
| `DEMO_MAX_COMBOS` | 150 | combinations per signal-combination search |
| `DEMO_MAX_SIGNALS_PER_SIDE` | 2 | signals stacked per side in that search |
| `DEMO_MAX_GRID_COMBOS` | 250 | combinations per parameter grid search (the workspace default; narrow the parameters when a bundle's grid is larger) |
| `DEMO_MAX_BAYES_TRIALS` | 30 | trials per Bayesian sweep |
| `DEMO_OPTIMIZER_WORKERS` | 2 | threads the combination search shares, all visitors together |
| `DEMO_MAX_CONCURRENT_JOBS` | 2 | optimiser runs in flight at once, all visitors together |
| `DEMO_JOB_TIMEOUT_SECONDS` | 120 | a run still going after this is stopped (the combination search ranks what finished) |
| `DEMO_ACTIONS_PER_IP_PER_MINUTE` | 30 | backtests, data loads and fundamentals loads per IP |
| `DEMO_JOBS_PER_IP_PER_HOUR` | 20 | optimiser runs started per IP |
| `DEMO_MAX_SESSIONS` | 60 | visitor states held in memory (oldest evicted) |
| `DEMO_SESSION_IDLE_MINUTES` | 30 | idle visitor state is dropped after this |

Under those, the container is capped at **2 CPUs and 1.5 GB** (`cpus` and
`mem_limit` in `.deploy/compose.yml`), so the demo can never take more than a
quarter of the server whatever visitors do. Grid search, the Bayesian sweep and
walk-forward validation are one-at-a-time in the dashboard; in the demo only
the visitor who started one can poll or stop it.

A limit that refuses a request shows a notice under the header — what ran out,
when it resets — and changes nothing else. The date range is capped by the
snapshot itself.

## Run it locally

```bash
# PowerShell: $env:DEMO_MODE = "true"; python -m demo.server
DEMO_MODE=true python -m demo.server        # http://127.0.0.1:8050/ticker/TSLA
```

It needs only the packages in `demo/requirements.txt` (a subset of `uv.lock`
without `ib_async`, plus `waitress`). No network, no secrets.

## Kill switch

`DEMO_MODE` defaults off. Unset or `false`, `demo.server` answers **404 on
every page** (and `200 {"demo": false}` on `/healthz`, so the container stays
healthy) and never imports the dashboard. It does not fall back to the live,
unguarded workspace.

To take the public demo down: set `DEMO_MODE: "false"` in `.deploy/compose.yml`,
commit, push, `bash deploy-demo.sh`. To remove the site entirely:
`bash C:/Personal_utilities/hetzner-site/bin/site-remove.sh alpha`.

## How it is put together

Everything lives in `demo/`; the workspace carries no demo branches. The one
change to `lib/` is `create_app()` in `lib/dash/integrated_dashboard.py`, which
builds the app without serving it so a WSGI server can.

| Module | Job |
|---|---|
| `demo/server.py` | entry point; seals, patches, builds, wraps, serves with waitress |
| `demo/sealing.py` | refuses outbound sockets, `yfinance`, and imports of `lib.live` / IB clients |
| `demo/patches.py` | swaps the data seams (`_yahoo_history`, `fetch_fundamentals`, quotes, universe, disk cache, preset/watchlist writes, Flow Scanner) for the snapshot |
| `demo/sessions.py` | replaces the process-wide `dashboard_state` with a per-visitor proxy (session cookie) |
| `demo/limits.py` | per-IP sliding-window limits and the optimiser-run gate |
| `demo/guards.py` | wraps the callbacks that start CPU work: caps, limits, gate, notices |
| `demo/banner.py` | header badge, banner, the refusal notice, input `max` values |
| `demo/snapshot.py` | reads `demo/fixtures/` |
| `demo/freeze_demo_data.py` | writes `demo/fixtures/` (the only part that uses the network) |

Tests: `python -m pytest lib/tests/test_demo_mode.py` — the kill switch, both
seals, the snapshot, the limiter and gate, per-visitor isolation, and an
end-to-end run of the demo in a subprocess (a backtest on the snapshot, a
rate-limit notice, a clamped optimiser run, a second visitor refused, a shared
job its owner alone can stop, the broker import refused).

## The snapshot

- **Snapshot:** 11 Sep 2026 close. **Captured:** 14 Sep 2026.
- **Bars:** Yahoo Finance via `yfinance`, split- and dividend-adjusted, exactly
  as `lib.data_processing._yahoo_history` returns them. 4,076–5,205 daily bars
  and 3,466 hourly bars per ticker.
- **Fundamentals:** the payload `lib.fundamentals.fetch_fundamentals` returns —
  SEC EDGAR XBRL for statements (XOM fell back to Yahoo statements), Yahoo for
  analyst estimates — with *now* pinned to the snapshot close and the quote
  fields rewritten from the frozen daily bars, so the fundamentals price
  matches the chart. SPY and QQQ have none (ETFs file no 10-K).
- **Size:** about 2.4 MB, committed.

### Refresh it

```bash
python -m demo.freeze_demo_data --snapshot YYYY-MM-DD   # a completed session
python -m pytest lib/tests/test_demo_mode.py
DEMO_MODE=true python -m demo.server                    # look at the numbers on screen
```

Then update the dates in this file, `demo/demo.json` and the landing card's
note, commit `demo/fixtures/`, push and `bash deploy-demo.sh`. Retake the
landing captures with
`node C:/Personal_utilities/screenshot-kit/shotkit.mjs --config demo/shotkit.demo.config.mjs`.
