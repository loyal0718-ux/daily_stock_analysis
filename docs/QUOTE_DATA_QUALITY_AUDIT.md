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
