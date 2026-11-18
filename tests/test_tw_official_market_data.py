import unittest
from unittest.mock import MagicMock, patch

import pandas as pd

from data_provider.tw_official_market_data import (
    _ad_date, _int_cell, fetch_twse_volume, fetch_tpex_latest_volume,
    overlay_official_tw_volume,
)


class TestTaiwanOfficialVolume(unittest.TestCase):
    def test_date_and_integer_normalizers(self):
        self.assertEqual(_ad_date("115/06/26"), "20260626")
        self.assertEqual(_ad_date("2026-06-26"), "20260626")
        self.assertIsNone(_ad_date("bad"))
        self.assertEqual(_int_cell("30,973,127"), 30973127)
        self.assertIsNone(_int_cell("--"))

    @patch("data_provider.tw_official_market_data.requests.get")
    def test_twse_monthly_official_volume(self, get):
        response = MagicMock()
        response.json.return_value = {
            "stat": "OK", "fields": ["日期", "成交股數"],
            "data": [["115/06/26", "30,973,127"]]
        }
        response.raise_for_status.return_value = None
        get.return_value = response
        result = fetch_twse_volume("2330.TW", "2026-06-01", "2026-06-30")
        self.assertEqual(int(result.iloc[0]["volume"]), 30973127)

    @patch("data_provider.tw_official_market_data.requests.get")
    def test_tpex_latest_snapshot(self, get):
        response = MagicMock()
        response.json.return_value = [{
            "Date": "1150626", "SecuritiesCompanyCode": "6488",
            "TradingShares": "1,234,567"
        }]
        response.raise_for_status.return_value = None
        get.return_value = response
        result = fetch_tpex_latest_volume("6488.TWO")
        self.assertEqual(int(result.iloc[0]["volume"]), 1234567)

    @patch("data_provider.tw_official_market_data.fetch_twse_volume")
    def test_overlay_only_replaces_matching_official_volume(self, fetch):
        fetch.return_value = pd.DataFrame({
            "date": [pd.Timestamp("2026-06-26")], "volume": [30973127]
        })
        source = pd.DataFrame({
            "date": pd.to_datetime(["2026-06-26", "2026-06-25"]),
            "volume": [28844142, 20000000],
            "Close": [100.0, 99.0],
        })
        result = overlay_official_tw_volume(
            source, "2330.TW", "2026-06-25", "2026-06-26"
        )
        self.assertEqual(int(result.iloc[0]["volume"]), 30973127)
        self.assertEqual(int(result.iloc[0]["volume_yahoo"]), 28844142)
        self.assertEqual(result.iloc[0]["volume_source"], "TWSE_STOCK_DAY")
        self.assertEqual(result.iloc[1]["volume_source"], "yahoo_unverified")
        self.assertEqual(result.iloc[1]["volume"], 20000000)


if __name__ == "__main__":
    unittest.main()
