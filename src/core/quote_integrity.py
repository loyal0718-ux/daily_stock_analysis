# -*- coding: utf-8 -*-
"""Deterministic integrity checks for unified realtime quotes."""
from __future__ import annotations
import math
from typing import Any


def _get(value: Any, key: str):
    if isinstance(value, dict):
        return value.get(key)
    return getattr(value, key, None)


def _number(value: Any):
    try:
        if value is None or value == "":
            return None
        result = float(value)
        return result if math.isfinite(result) else None
    except (TypeError, ValueError):
        return None


def validate_realtime_quote(quote: Any, reference_close: Any = None) -> dict:
    """Check quote arithmetic and OHLC consistency without rewriting provider data."""
    price = _number(_get(quote, "price"))
    provider_previous_close = _number(_get(quote, "pre_close"))
    daily_reference_close = _number(reference_close)
    if (
        provider_previous_close is not None
        and daily_reference_close is not None
        and abs(provider_previous_close - daily_reference_close) > 0.06
    ):
        # The provider's previous close should agree with the last completed daily candle.
        # Preserve the provider value for arithmetic, but surface the discrepancy.
        previous_close_mismatch = True
    else:
        previous_close_mismatch = False
    previous_close = provider_previous_close
    if previous_close is None:
        previous_close = daily_reference_close

    reported_change = _number(_get(quote, "change_amount"))
    reported_pct = _number(_get(quote, "change_pct"))
    open_price = _number(_get(quote, "open_price"))
    high = _number(_get(quote, "high"))
    low = _number(_get(quote, "low"))
    volume = _number(_get(quote, "volume"))
    amount = _number(_get(quote, "amount"))

    issues = []
    if previous_close_mismatch:
        issues.append("previous_close_mismatch")
    calculated_change = None
    calculated_pct = None

    if price is None or price <= 0:
        issues.append("missing_or_invalid_price")
    if previous_close is not None and previous_close <= 0:
        issues.append("invalid_previous_close")
        previous_close = None

    if price is not None and previous_close is not None and previous_close > 0:
        calculated_change = price - previous_close
        calculated_pct = calculated_change / previous_close * 100
        if reported_change is not None and abs(reported_change - calculated_change) > 0.06:
            issues.append("change_amount_mismatch")
        if reported_pct is not None and abs(reported_pct - calculated_pct) > 0.15:
            issues.append("change_pct_mismatch")

    if high is not None and low is not None and high < low:
        issues.append("high_below_low")
    if open_price is not None and high is not None and open_price > high + 0.06:
        issues.append("open_above_high")
    if open_price is not None and low is not None and open_price < low - 0.06:
        issues.append("open_below_low")
    if price is not None and high is not None and price > high + 0.06:
        issues.append("price_above_high")
    if price is not None and low is not None and price < low - 0.06:
        issues.append("price_below_low")
    if volume is not None and volume < 0:
        issues.append("negative_volume")
    if amount is not None and amount < 0:
        issues.append("negative_amount")

    stale = _get(quote, "is_stale")
    freshness = "stale" if stale is True else "fresh" if stale is False else "unknown"
    if stale is True:
        issues.append("provider_quote_flagged_stale")

    status = "warning" if issues else (
        "pass" if price is not None and previous_close is not None else "unknown"
    )
    return {
        "status": status,
        "freshness": freshness,
        "reference_close": previous_close,
        "calculated_change": calculated_change,
        "calculated_pct": calculated_pct,
        "reported_change": reported_change,
        "reported_pct": reported_pct,
        "provider_timestamp": _get(quote, "provider_timestamp"),
        "fetched_at": _get(quote, "fetched_at"),
        "stale_seconds": _get(quote, "stale_seconds"),
        "issues": issues,
    }
