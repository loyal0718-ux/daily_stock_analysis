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
