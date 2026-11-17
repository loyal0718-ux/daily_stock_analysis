# -*- coding: utf-8 -*-
"""Regression tests for Fugle intraday quote volume normalization."""

from data_provider.fugle_fetcher import FugleFetcher


class _FakeResponse:
    def raise_for_status(self):
        return None

    def json(self):
        # Official Fugle quote example: 54,538 volume units and
        # NT$31,019,803,000 turnover at a price around NT$568.
        return {
            "name": "台積電",
            "lastPrice": 568,
            "change": 2,
            "changePercent": 0.35,
            "previousClose": 566,
            "lastUpdated": 1685338200000000,
            "total": {
                "tradeValue": 31019803000,
                "tradeVolume": 54538,
            },
        }


def test_fugle_trade_volume_is_normalized_from_lots_to_shares(monkeypatch):
    monkeypatch.setattr(
        "data_provider.fugle_fetcher.requests.get",
        lambda *args, **kwargs: _FakeResponse(),
    )

    quote = FugleFetcher(api_key="test-key").get_realtime_quote("2330.TW")

    assert quote is not None
    assert quote.volume == 54_538_000
    assert quote.amount == 31_019_803_000
