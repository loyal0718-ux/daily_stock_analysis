# -*- coding: utf-8 -*-
"""Tests for deterministic realtime quote integrity checks."""
from src.core.quote_integrity import validate_realtime_quote


def test_valid_quote_passes_and_calculates_change():
    result = validate_realtime_quote({
        "price": 105.0, "pre_close": 100.0, "change_amount": 5.0,
        "change_pct": 5.0, "open_price": 101.0, "high": 106.0,
        "low": 100.5, "volume": 100000, "amount": 10400000,
        "is_stale": False,
    })
    assert result["status"] == "pass"
    assert result["calculated_change"] == 5.0
    assert result["calculated_pct"] == 5.0
    assert result["issues"] == []


def test_mismatched_change_fields_are_flagged_not_silently_reconciled():
    result = validate_realtime_quote({
        "price": 105.0, "pre_close": 100.0, "change_amount": 1.0,
        "change_pct": -0.5, "open_price": 101.0, "high": 106.0,
        "low": 100.5,
    })
    assert result["status"] == "warning"
    assert "change_amount_mismatch" in result["issues"]
    assert "change_pct_mismatch" in result["issues"]
    assert result["calculated_pct"] == 5.0


def test_missing_previous_close_is_unknown_not_zero():
    result = validate_realtime_quote({"price": 105.0})
    assert result["status"] == "unknown"
    assert result["reference_close"] is None
    assert result["calculated_pct"] is None


def test_stale_quote_is_explicitly_flagged():
    result = validate_realtime_quote({
        "price": 105.0, "pre_close": 100.0, "is_stale": True,
    })
    assert result["freshness"] == "stale"
    assert result["status"] == "warning"
    assert "provider_quote_flagged_stale" in result["issues"]


def test_provider_previous_close_must_match_last_daily_candle():
    result = validate_realtime_quote(
        {
            "price": 105.0,
            "pre_close": 99.0,
            "change_amount": 6.0,
            "change_pct": 6.06,
            "is_stale": False,
        },
        reference_close=100.0,
    )
    assert result["status"] == "warning"
    assert "previous_close_mismatch" in result["issues"]
