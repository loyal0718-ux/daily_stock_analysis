# -*- coding: utf-8 -*-
"""Regression test for legacy Tushare realtime quote volume units."""
import sys
from types import SimpleNamespace

import pandas as pd

from data_provider.tushare_fetcher import TushareFetcher


class _ProClient:
    def quotation(self, **kwargs):
        raise RuntimeError("force legacy fallback")


def test_legacy_tushare_realtime_volume_remains_in_shares(monkeypatch):
    fake_sdk = SimpleNamespace(
        get_realtime_quotes=lambda symbol: pd.DataFrame([{
            "name": "示例股票",
            "price": "10.00",
            "pre_close": "9.90",
            "volume": "1234500",
            "amount": "12345000",
            "high": "10.10",
            "low": "9.80",
            "open": "9.90",
        }])
    )
    monkeypatch.setitem(sys.modules, "tushare", fake_sdk)

    fetcher = TushareFetcher.__new__(TushareFetcher)
    fetcher._api = _ProClient()
    fetcher._minute_start = None
    fetcher._call_count = 0
    fetcher.rate_limit_per_minute = 80

    quote = fetcher.get_realtime_quote("600519")

    assert quote is not None
    # Tushare legacy get_realtime_quotes documents volume as shares;
    # volume / 100 is only needed when converting to lots.
    assert quote.volume == 1_234_500



def test_pro_quotation_does_not_publish_unverified_volume_or_amount():
    class _ProQuoteClient:
        def quotation(self, **kwargs):
            return pd.DataFrame([{
                "name": "示例股票",
                "price": 10.0,
                "pre_close": 9.9,
                "pct_chg": 1.01,
                "change": 0.1,
                "vol": 12345,
                "amount": 123456.0,
                "high": 10.1,
                "low": 9.8,
                "open": 9.9,
                "turnover_ratio": 0.5,
                "pe": 10.0,
                "pb": 1.0,
                "total_mv": 1000000.0,
            }])

    fetcher = TushareFetcher.__new__(TushareFetcher)
    fetcher._api = _ProQuoteClient()
    fetcher._check_rate_limit = lambda: None
    fetcher._convert_stock_code = lambda _code: "600519.SH"

    quote = fetcher.get_realtime_quote("600519")

    assert quote is not None
    assert quote.price == 10.0
    # No public unit contract was verified for quotation.vol / quotation.amount.
    assert quote.volume is None
    assert quote.amount is None
