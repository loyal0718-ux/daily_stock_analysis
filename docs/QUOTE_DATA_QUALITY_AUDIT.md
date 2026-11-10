# Taiwan quote data-quality audit

## Scope

This change set is intentionally isolated on `king/data-quality-audit-20261110`.
It does not change the production `main` branch or the scheduled Telegram workflows.

## Confirmed data-contract issue

`UnifiedRealtimeQuote.volume` is documented in this repository as shares, consistent with historical daily bars. Fugle's intraday quote response exposes `total.tradeVolume` and `total.tradeValue`; the official example's `avgPrice`, `tradeVolume`, and `tradeValue` reconcile when the reported volume is interpreted as lots and converted to shares. The adapter now normalizes the volume at the provider boundary. Confirm this against a live Taiwan quote before production merge.

## Deterministic quote integrity

`src/core/quote_integrity.py` checks:
- price, previous close, reported change, and reported percentage arithmetic;
- OHLC range consistency;
- negative volume / turnover values;
- provider freshness metadata.

It records discrepancies instead of silently selecting or rewriting conflicting fields. Missing values remain unknown, not zero.

The pipeline attaches the result to the analysis context. The LLM prompt instructs the model to disclose unknown or warning data quality and to avoid precise entry/stop levels or strong trade calls when quote integrity is not confirmed.

## Validation status

- Regression tests added for Fugle volume normalization and quote-integrity checks.
- GitHub Actions run on the initial PR commit reported 2,883 passed, 4 failed, and 1 cancelled shard. The observed failures were in unrelated agent-session database migration and live AkShare capital-flow adapter tests. The new regression tests were added after that run and have not yet been confirmed by CI.
- Do not merge until the latest branch head has a passing targeted test run and the remaining CI failures are understood.

## Additional findings: intraday volume and Tushare legacy adapter

- The trend analyzer previously compared a partial intraday cumulative volume with five completed daily bars. It now marks this volume as `INTRADAY_UNCONFIRMED`, leaves the ratio as `None`, and does not call it shrink/heavy volume. Missing volume is also `UNAVAILABLE`, not zero.
- The previous `縮量回調 = 主力洗盤` wording was too strong: volume/price alone cannot identify institutional intent. The wording now describes only lower trading activity.
- Tushare's legacy `get_realtime_quotes` documents `volume` as shares (the documentation says divide by 100 only to express lots). The adapter incorrectly divided by 100 even though the unified quote contract is shares; this has been corrected and a regression test added.
- Tushare Pro's documented `rt_k` endpoint reports volume in shares, but the current adapter calls `quotation`, which is not the documented `rt_k` method. Its exact payload contract must be verified before treating that branch as trusted. We do not switch to the documented paid real-time endpoint as part of this free-first patch.

## Adjustment-basis safety

Historical daily data is not guaranteed to share one price-adjustment basis: AkShare requests `adjust="qfq"` and yfinance uses `auto_adjust=True`, while realtime provider quotes are raw market prices. Comparing raw `pre_close` to an adjusted daily close can create false mismatches on ex-dividend / corporate-action dates; mixing a raw intraday price into an adjusted historical series can also distort moving averages.

The integrity validator therefore compares a historical reference close only when the caller explicitly guarantees it is unadjusted. The intraday K-line overlay now requires `df.attrs["price_adjustment_basis"]` to be explicitly `raw`, `none`, or `unadjusted`; otherwise it skips the overlay. The current DB-loaded frame does not yet consistently expose this metadata, so intraday MA overlay may be skipped until the history ingestion/storage layer records adjustment basis. This is intentionally conservative.

## CI follow-up (2026-11-10)

The first complete CI run after introducing the raw-price-basis guard completed syntax, lint, deterministic checks, AI governance, and Docker build successfully. Backend shards 1 and 2 failed on a mix of existing unrelated failures and integration tests that still encoded the pre-guard realtime-overlay behavior; shard 3 passed.

The integration failures exposed two real contract details:
- When the historical frame already contains today's partial bar, the correct comparison close is the prior completed candle (`df.iloc[-2]`), not today's partial close.
- Realtime-augmented rows must be marked `data_source=realtime:<provider>` and `is_partial_bar=true`; otherwise downstream volume analysis can mistake a partial cumulative volume for a completed daily bar.

Both are now corrected. Test fixtures now explicitly declare raw/unadjusted history and internally consistent provider previous-close / change / percent / freshness metadata. These follow-up commits have not yet been covered by a new completed CI run.

The realtime overlay intentionally remains disabled for production history frames until the ingestion layer supplies verified `price_adjustment_basis` metadata. This prevents accidental mixing of qfq/auto-adjusted history with raw provider quotes.

## Taiwan institutional-flow audit

The repository already contains a Taiwan-only TWSE T86 / TPEx OpenAPI fetcher. It returns raw net figures in **shares**, preserves negative values as net sells, and distinguishes dealer-excluded foreign investors from dealers. TWSE and TPEx fixtures both reconcile the official three-institution total to foreign + trust + dealer.

A new fail-open guard now rejects a row if the official total differs from the three component net figures, rather than allowing contradictory numbers into the prompt. Regression tests cover a one-share discrepancy for both TWSE and TPEx. The raw figures are supplied to the Taiwan analysis prompt as context; they do not directly create a numeric score. The current prompt's directional descriptions are heuristic context only, not a deterministic buy/sell signal.

The institutional fetcher only accepts explicit `.TW` / `.TWO` suffixes and checks the TPEx served date against an explicitly requested date. Missing fields, malformed values, date mismatch, and fetch errors fail open as unavailable rather than fabricated zero. This is the correct direction; remaining work is to confirm the live official response and ensure every report displays its source date and unit.
