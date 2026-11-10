# -*- coding: utf-8 -*-
"""Volume analysis regression tests for completed daily bars vs intraday bars."""
import pandas as pd

from src.stock_analyzer import StockTrendAnalyzer, VolumeStatus


def _bars(volumes, realtime=False):
    dates = pd.date_range("2026-10-01", periods=len(volumes), freq="B")
    data = {
        "date": dates,
        "open": [100.0] * len(volumes),
        "high": [101.0] * len(volumes),
        "low": [99.0] * len(volumes),
        "close": [100.0 + i for i in range(len(volumes))],
        "volume": volumes,
    }
    if realtime:
        data["data_source"] = ["history"] * (len(volumes)-1) + ["realtime:fugle"]
    return pd.DataFrame(data)


def test_intraday_cumulative_volume_is_not_compared_to_full_day_average():
    analyzer = StockTrendAnalyzer()
    result = analyzer.analyze(_bars([100000] * 24 + [5000], realtime=True), "2330")
    assert result.volume_status == VolumeStatus.INTRADAY_UNCONFIRMED
    assert result.volume_ratio_5d is None
    assert "盤中" in result.volume_trend


def test_completed_daily_volume_still_uses_previous_five_day_average():
    analyzer = StockTrendAnalyzer()
    result = analyzer.analyze(_bars([100000] * 24 + [50000]), "2330")
    assert result.volume_ratio_5d == 0.5
    assert result.volume_status == VolumeStatus.SHRINK_VOLUME_UP


def test_missing_volume_is_not_reported_as_zero_or_shrink():
    analyzer = StockTrendAnalyzer()
    df = _bars([100000] * 24 + [None])
    result = analyzer.analyze(df, "2330")
    assert result.volume_status == VolumeStatus.UNAVAILABLE
    assert result.volume_ratio_5d is None
