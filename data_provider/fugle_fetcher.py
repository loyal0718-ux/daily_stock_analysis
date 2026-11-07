# -*- coding: utf-8 -*-
"""Fugle Taiwan stock intraday quote provider."""

import logging
from datetime import datetime, timezone
from typing import Optional

import pandas as pd
import requests

from .base import BaseFetcher, DataFetchError, STANDARD_COLUMNS
from .realtime_types import RealtimeSource, UnifiedRealtimeQuote

logger = logging.getLogger(__name__)
_FUGLE_QUOTE_URL = "https://api.fugle.tw/marketdata/v1.0/stock/intraday/quote/"

 
class FugleFetcher(BaseFetcher):
    """Fugle REST quote adapter; realtime quotes only (no daily candles)."""

    name = "FugleFetcher"
    priority = 0

    def __init__(self, api_key: Optional[str] = None, timeout: float = 12.0):
        from src.config import get_config

        config = get_config()
        self.api_key = (api_key or getattr(config, "fugle_api_key", None) or "").strip()
        self.timeout = timeout

    def is_available_for_request(self, capability: str = "") -> bool:
        return bool(self.api_key) and capability == "realtime_quote"

    def _fetch_raw_data(self, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
        raise DataFetchError("FugleFetcher provides intraday quotes only; daily candles are unsupported")

    def _normalize_data(self, df: pd.DataFrame, stock_code: str) -> pd.DataFrame:
        if df is None or df.empty:
            return pd.DataFrame(columns=["code", *STANDARD_COLUMNS])
        return df.copy()

    @staticmethod
    def _number(value):
        if value in (None, ""):
            return None
        try:
            result = float(value)
            return result if pd.notna(result) else None
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _timestamp(value) -> Optional[str]:
        """Convert Fugle Unix timestamps (microseconds) to UTC ISO-8601."""
        if value in (None, "", 0, "0"):
            return None
        try:
            stamp = float(value)
            # Fugle quote timestamps are microseconds since Unix epoch.
            if stamp > 10_000_000_000_000:
                stamp /= 1_000_000
            elif stamp > 10_000_000_000:
                stamp /= 1_000
            return datetime.fromtimestamp(stamp, tz=timezone.utc).isoformat()
        except (TypeError, ValueError, OverflowError, OSError):
            return None

    @staticmethod
    def _symbol(stock_code: str) -> Optional[str]:
        code = (stock_code or "").strip().upper()
        if code.endswith(".TWO"):
            code = code[:-4]
        elif code.endswith(".TW"):
            code = code[:-3]
        return code if code.isdigit() and 4 <= len(code) <= 6 else None

    def get_realtime_quote(self, stock_code: str) -> Optional[UnifiedRealtimeQuote]:
        symbol = self._symbol(stock_code)
        if not self.api_key or not symbol:
            return None

        try:
            response = requests.get(
                f"{_FUGLE_QUOTE_URL}{symbol}",
                headers={"X-API-KEY": self.api_key},
                timeout=self.timeout,
            )
            response.raise_for_status()
            data = response.json()
        except Exception as exc:
            logger.warning("[Fugle] realtime quote failed for %s: %s", symbol, exc)
            return None

        if not isinstance(data, dict):
            return None

        total = data.get("total") or {}
        last_trade = data.get("lastTrade") or {}
        price = self._number(data.get("lastPrice"))
        if price is None:
            price = self._number(data.get("closePrice"))
        if price is None or price <= 0:
            return None

        timestamp = (
            data.get("lastUpdated")
            or last_trade.get("time")
            or data.get("closeTime")
        )
        volume = self._number(total.get("tradeVolume"))
        amount = self._number(total.get("tradeValue"))

        return UnifiedRealtimeQuote(
            code=stock_code,
            name=str(data.get("name") or ""),
            source=RealtimeSource.FUGLE,
            provider_timestamp=self._timestamp(timestamp),
            market="tw",
            currency="TWD",
            data_quality="ok",
            price=price,
            change_pct=self._number(data.get("changePercent")),
            change_amount=self._number(data.get("change")),
            volume=int(volume) if volume is not None else None,
            amount=amount,
            amplitude=self._number(data.get("amplitude")),
            open_price=self._number(data.get("openPrice")),
            high=self._number(data.get("highPrice")),
            low=self._number(data.get("lowPrice")),
            pre_close=self._number(data.get("previousClose")),
        )
