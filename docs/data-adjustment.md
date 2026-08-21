# Corporate actions and price adjustment

How SearchForAlpha treats splits and dividends on the OHLCV fetch path.
Audited 2026-08-21.

## What the code does

`fetch_data()` in [lib/data_processing.py](../lib/data_processing.py) requests
bars through `_yahoo_history()` with both adjustment flags stated explicitly:

```python
ticker.history(start=..., end=..., interval=..., auto_adjust=True, actions=False)
```

- **`auto_adjust=True`** — every OHLC value is back-adjusted for splits *and*
  dividends. `Close` is the adjusted close; there is no separate `Adj Close`.
- **`actions=False`** — the `Dividends` and `Stock Splits` columns are not
  returned. `fetch_data` also drops them defensively if a vendor sends them
  anyway, and the parquet cache strips them on read.

Before this audit neither flag was passed. The code inherited yfinance's
defaults — which happen to be `auto_adjust=True, actions=True` — so the
behaviour was the same but undocumented, and the two action columns flowed
unnoticed into `add_indicators`, the parquet cache and the data table.

## Why the action columns are dropped

1. **Nothing reads them.** No module in `lib/` references either name.
2. **Resampling corrupted them.** `resample_ohlcv` aggregated every non-OHLCV
   column with `"last"`, so a dividend on the first 1h bar of a 4h bucket was
   overwritten by the final bar's `0.0`. Fixed in
   [lib/timeframes.py](../lib/timeframes.py): `_OHLCV_AGG` now sums them, and a
   regression test covers it. The columns are excluded upstream regardless, but
   `resample_ohlcv` is public and may be handed a vendor frame that has them.
3. **They are not price data.** Carrying them in an OHLCV frame invites them
   into indicator maths by accident.

## How much the adjustment moves prices

Measured over 2024-01-01 → 2025-06-30 (373 bars), comparing
`auto_adjust=False` against what `fetch_data` returns. The gap is the
downward shift applied to historical prices to account for dividends since
paid, largest at the start of the window and shrinking toward the present:

| Ticker | Dividends paid | Splits | Gap, first bar | Gap, last bar |
|---|---|---|---|---|
| KO   | $2.96 | none | +6.99% | +2.75% |
| AAPL | $1.50 | none | +1.20% | +0.48% |
| T    | $1.67 | none | +13.00% | +5.45% |

**This is material.** For a high-yield name like T, raw and adjusted history
differ by 13% at the far end of an 18-month window. Any backtest, indicator
threshold or optimizer result is computed on the adjusted series.

## Consequences to keep in mind

- **Adjusted history is not what you could have traded.** A price level from
  2024 in an adjusted series is not the price that printed that day. Absolute
  price levels in old bars are not tradeable prices.
- **History is not stable.** Every new dividend or split back-adjusts the
  entire series, so a backtest re-run months later reads slightly different
  input. Trials record a seed, wall time and git commit
  ([lib/seeds.py](../lib/seeds.py)), but not a data snapshot hash — two runs of
  the same commit can differ if a dividend landed in between.
- **The cache is self-healing but not versioned.** Parquet files written by an
  older build still hold the action columns; `_normalize_frame` in
  [lib/dash/ohlcv_disk_cache.py](../lib/dash/ohlcv_disk_cache.py) drops them on
  read. The cached *prices* are whatever the adjustment was at write time.
- **A second vendor must match this.** Any fallback source has to return
  split- and dividend-adjusted bars, or its frames will not be comparable to
  the cached Yahoo ones. See [data-vendors.md](data-vendors.md).

## Not covered

- No verification against an independent vendor — see
  [data-vendors.md](data-vendors.md) for why no free second source was
  available to cross-check against.
- Return-of-capital, spin-offs and the `Capital Gains` column that yfinance
  emits for funds are not separately validated.
