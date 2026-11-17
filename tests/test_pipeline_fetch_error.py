# -*- coding: utf-8 -*-
"""Regression tests for pipeline data-fetch error handling."""

from datetime import date, datetime, timezone
import unittest
from unittest.mock import MagicMock, patch

from src.core.pipeline import StockAnalysisPipeline


class PipelineFetchErrorTestCase(unittest.TestCase):
    """`fetch_and_save_stock_data` should preserve the original exception."""

    def test_fetch_and_save_handles_stock_name_lookup_failure(self):
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        pipeline.db = MagicMock()
        pipeline.fetcher_manager.get_stock_name.side_effect = RuntimeError("name lookup failed")

        success, error = StockAnalysisPipeline.fetch_and_save_stock_data(pipeline, "600519")

        self.assertFalse(success)
        self.assertIn("name lookup failed", error or "")

    @patch.object(
        StockAnalysisPipeline,
        "_resolve_resume_target_date",
        return_value=date(2026, 3, 27),
    )
    def test_fetch_and_save_uses_effective_trading_date_for_resume_check(self, _mock_target):
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        pipeline.db = MagicMock()
        pipeline.fetcher_manager.get_stock_name.return_value = "贵州茅台"
        pipeline.db.has_today_data.return_value = True
        pipeline.db.get_data_range.return_value = [
            SimpleNamespace(to_dict=lambda: {"price_adjustment_basis": "auto_adjusted"})
        ]
        current_time = datetime(2026, 3, 28, 1, 0, tzinfo=timezone.utc)

        success, error = StockAnalysisPipeline.fetch_and_save_stock_data(
            pipeline,
            "600519",
            current_time=current_time,
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        _mock_target.assert_called_once_with(
            "600519", current_time=current_time, analysis_target=None
        )
        pipeline.db.has_today_data.assert_called_once_with("600519", date(2026, 3, 27))
        pipeline.db.get_data_range.assert_called_once_with(
            "600519", date(2025, 12, 28), date(2026, 3, 27)
        )
        pipeline.fetcher_manager.get_daily_data.assert_not_called()

    @patch.object(
        StockAnalysisPipeline,
        "_resolve_resume_target_date",
        return_value=date(2026, 3, 27),
    )
    def test_fetch_and_save_refreshes_full_price_basis_lookback(self, _mock_target):
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        pipeline.db = MagicMock()
        pipeline.fetcher_manager.get_stock_name.return_value = "台積電"
        pipeline.db.has_today_data.return_value = False
        daily_frame = MagicMock()
        daily_frame.empty = False
        pipeline.fetcher_manager.get_daily_data.return_value = (daily_frame, "Yahoo")

        success, error = StockAnalysisPipeline.fetch_and_save_stock_data(
            pipeline,
            "2330.TW",
            force_refresh=True,
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        pipeline.fetcher_manager.get_daily_data.assert_called_once_with("2330.TW", days=120)
        pipeline.db.save_daily_data.assert_called_once_with(daily_frame, "2330.TW", "Yahoo")

    @patch.object(
        StockAnalysisPipeline,
        "_resolve_resume_target_date",
        return_value=date(2026, 3, 27),
    )
    def test_fetch_and_save_refreshes_when_existing_history_has_unknown_basis(self, _mock_target):
        pipeline = StockAnalysisPipeline.__new__(StockAnalysisPipeline)
        pipeline.fetcher_manager = MagicMock()
        pipeline.db = MagicMock()
        pipeline.fetcher_manager.get_stock_name.return_value = "台積電"
        pipeline.db.has_today_data.return_value = True
        pipeline.db.get_data_range.return_value = [
            SimpleNamespace(to_dict=lambda: {"price_adjustment_basis": None})
        ]
        daily_frame = MagicMock()
        daily_frame.empty = False
        pipeline.fetcher_manager.get_daily_data.return_value = (daily_frame, "Yahoo")

        success, error = StockAnalysisPipeline.fetch_and_save_stock_data(
            pipeline, "2330.TW"
        )

        self.assertTrue(success)
        self.assertIsNone(error)
        pipeline.db.get_data_range.assert_called_once_with(
            "2330.TW", date(2025, 12, 28), date(2026, 3, 27)
        )
        pipeline.fetcher_manager.get_daily_data.assert_called_once_with(
            "2330.TW", days=120
        )
        pipeline.db.save_daily_data.assert_called_once_with(
            daily_frame, "2330.TW", "Yahoo"
        )

    def test_resolve_resume_target_date_normalizes_supported_a_share_formats(self):
        with patch("src.core.pipeline.get_market_for_stock", return_value="cn") as mock_market, patch(
            "src.core.pipeline.get_effective_trading_date",
            return_value=date(2026, 3, 27),
        ) as mock_target:
            for code in ("SH600519", "000001.SZ", "BJ920748"):
                result = StockAnalysisPipeline._resolve_resume_target_date(code)
                self.assertEqual(result, date(2026, 3, 27))

        self.assertEqual(
            [args.args[0] for args in mock_market.call_args_list],
            ["600519", "000001", "920748"],
        )
        self.assertEqual(mock_target.call_count, 3)


if __name__ == "__main__":
    unittest.main()
