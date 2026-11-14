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

## Persisted historical price-basis metadata

The historical OHLC pipeline now attaches an explicit basis after normalization, cleaning, and indicator calculation:
- AkShare daily history: `qfq` (the inspected A-share, ETF and HK endpoints explicitly request `adjust="qfq"`).
- Yahoo Finance daily history: `auto_adjusted` (`yf.download(auto_adjust=True)`).
- Tushare daily / fund_daily history: `raw` (the inspected endpoints return the daily price fields without applying `adj_factor`).

`StockDaily.price_adjustment_basis` is nullable. The additive SQLite migration leaves all pre-existing rows NULL because their basis cannot safely be reconstructed. New writes persist DataFrame metadata; updates without basis metadata preserve an existing non-NULL basis. ORM `to_dict()` includes the basis so analysis reads it back from persisted rows.

Realtime overlay now requires all persisted rows in the frame to agree on a known raw/unadjusted basis. Adjusted, mixed, or unknown history is rejected rather than comparing a raw realtime quote against incompatible historical prices. This is deliberately conservative; Taiwan daily history currently routes through Yahoo Finance and is tagged `auto_adjusted`, so Fugle raw intraday prices will not be merged into those daily bars until a verified adjustment-factor conversion is implemented.

The schema migration and preservation behavior, YFinance basis tagging, and adjusted/unknown realtime rejection have regression tests. The latest complete CI run before these changes still failed in backend shard 1 on four unrelated tests (one missing Chat session table in a test DB and three AkShare HTTP-boundary tests); two other backend shards and Docker build passed. The new storage/basis tests are awaiting the latest CI run.

### Official provider documentation cross-check (2026-11-10)

- Fugle's official [Intraday Quote API](https://developer.fugle.tw/docs/data/http-api/intraday/quote/) sample for 2330 reports `total.tradeVolume=54,538`, `avgPrice=568.77`, and `total.tradeValue=31,019,803,000`. The value is consistent with 54,538 lots × 1,000 shares × approximately NT$568.77. The adapter's lot-to-share conversion is therefore supported by the published sample; the official response field itself is labelled cumulative volume but does not explicitly state the unit. The conversion remains covered by a regression test.
- Fugle's [usage statement](https://developer.fugle.tw/docs/data/intro/) also says intraday cumulative volume/value covers regular board-lot trades only; odd-lot and after-hours transactions are excluded. This limitation must be shown in the report and must not be compared blindly to a full-day all-session historical volume.
- Tushare's [A-share daily API](https://tushare.pro/document/1?doc_id=27) explicitly documents `daily` as unadjusted, volume in lots, and amount in thousand yuan. The current historical normalizer scales those values to shares and yuan.
- Tushare's [rt_k real-time daily API](https://tushare.pro/document/1?doc_id=372) documents volume in shares and amount in yuan. The current code does not call `rt_k`; it calls `quotation`, whose exact response contract still requires separate verification. Do not infer `quotation` units from `rt_k`.


## CI follow-up (2026-11-14)

- PR head `bc47d43b62cd6e603a056f4681fde52e8fc97518` completed GitHub Actions run #55 successfully: all three backend test shards passed, Docker build passed, AI governance passed, change detection passed, and backend-gate passed. The three backend shards together reported 2,805 passed, 49 warnings, and 361 subtests passed.
- Removed a Shenzhen-specific AkShare capital-flow test because Shenzhen/A-share coverage is outside this Taiwan dashboard's acceptance scope. Updated the remaining AkShare contract test to the current endpoint name; this is not evidence that live Taiwan institutional data has been verified.
- Production `main` remains unchanged. PR #1 remains draft and unmerged.
- Remaining pre-merge checks are operational/data-source checks, not a reason to weaken CI: verify current TWSE T86 and TPEx OpenAPI live payloads, confirm the exact AkShare 1.20.45 endpoint signature/columns if that adapter remains in scope, and confirm the user-facing report displays the Taiwan institutional source date and unit (shares). The TWSE/TPEx institutional fetcher is Taiwan-only and is the intended source for Taiwan three-institution figures; AkShare capital-flow compatibility is separate and must not be presented as Taiwan institutional data.


## Product acceptance scope update (2026-11-14)

The user has explicitly removed intraday real-time quotes from the required dashboard workflow. The intended report is post-market and must use completed daily bars; no intraday quote, partial-day volume, or realtime-price overlay is required for acceptance. Fugle quote normalization and realtime overlay are retained only as optional provider/legacy capabilities, not as dependencies or acceptance gates for the Taiwan daily report.

Historical daily price-adjustment-basis metadata remains required: all candles used together for moving averages and other technical indicators must have a consistent, known basis, and missing/unknown basis must be disclosed or handled conservatively. The Taiwan institutional-flow block remains sourced from TWSE T86 / TPEx OpenAPI and must display its own source date and unit (shares). Missing or invalid figures remain unavailable, never fabricated as zero.

This update disables realtime quote collection and realtime technical-indicator overlays by default. Explicit environment overrides can still enable legacy realtime functionality; that is not part of the Taiwan dashboard's required workflow. It does not change the post-market daily report or its Telegram/Email delivery.


## Notification scope clarification (2026-11-15)

Only automatic intraday real-time quote notifications are cancelled. The scheduled intraday Fugle snapshot workflow has had its cron triggers removed; manual dispatch remains available for maintenance/testing. The post-market daily analysis report and its existing Telegram/Email delivery routes are explicitly retained and unchanged. No report-channel environment variable is overridden or disabled by this change.
