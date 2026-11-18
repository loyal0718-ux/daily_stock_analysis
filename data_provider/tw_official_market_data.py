# -*- coding: utf-8 -*-
"""Official Taiwan daily trading volume overlay.

TWSE STOCK_DAY is historical/monthly; TPEx OpenAPI daily close quotes is a
latest-day snapshot. Only volume is overlaid onto Yahoo rows. Yahoo adjusted
OHLC and its estimated amount are never relabelled as official. Missing official
rows remain NaN and carry source metadata rather than being zero-filled.
"""
from __future__ import annotations

import logging
from datetime import date
from typing import Optional

import pandas as pd
import requests

logger = logging.getLogger(__name__)
_TWSE_URL = "https://www.twse.com.tw/rwd/zh/afterTrading/STOCK_DAY"
_TPEX_URL = "https://www.tpex.org.tw/openapi/v1/tpex_mainboard_daily_close_quotes"
_HEADERS = {
    "User-Agent": "Mozilla/5.0 (compatible; DailyStockAnalysis/1.0)",
    "Accept": "application/json, text/plain, */*",
    "Accept-Language": "zh-TW,zh;q=0.9,en;q=0.8",
    "Referer": "https://www.twse.com.tw/",
}
_TIMEOUT = 12


def _ad_date(value: object) -> Optional[str]:
    text = str(value or "").strip().replace("/", "").replace("-", "")
    if len(text) == 7 and text.isdigit():
        return f"{int(text[:3]) + 1911}{text[3:]}"
    if len(text) == 8 and text.isdigit():
        return text
    return None


def _int_cell(value: object) -> Optional[int]:
    text = str(value or "").replace(",", "").strip()
    if not text or text in {"-", "--", "—"}:
        return None
    try:
        result = int(text)
        return result if result >= 0 else None
    except (TypeError, ValueError):
        return None


def fetch_twse_volume(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch TWSE official historical volume (shares), month by month."""
    code = str(stock_code).strip().upper().removesuffix(".TW")
    if not (code.isdigit() and 4 <= len(code) <= 6):
        return pd.DataFrame(columns=["date", "volume"])
    start = pd.Timestamp(start_date).date().replace(day=1)
    end = pd.Timestamp(end_date).date().replace(day=1)
    rows = []
    cursor = start
    while cursor <= end:
        params = {"response": "json", "date": cursor.strftime("%Y%m%d"), "stockNo": code}
        try:
            response = requests.get(_TWSE_URL, params=params, headers=_HEADERS, timeout=_TIMEOUT)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict) or payload.get("stat") != "OK":
                cursor = (cursor.replace(day=28) + pd.Timedelta(days=4)).replace(day=1)
                continue
            fields = payload.get("fields") or []
            date_idx = next((i for i, x in enumerate(fields) if "日期" in str(x)), None)
            volume_idx = next((i for i, x in enumerate(fields) if "成交股數" in str(x)), None)
            if date_idx is None or volume_idx is None:
                logger.warning("TWSE STOCK_DAY schema changed; official volume unavailable")
            else:
                for row in payload.get("data") or []:
                    if max(date_idx, volume_idx) >= len(row):
                        continue
                    day = _ad_date(row[date_idx])
                    volume = _int_cell(row[volume_idx])
                    if day and volume is not None:
                        rows.append({"date": pd.to_datetime(day), "volume": volume})
        except Exception as exc:
            logger.warning("TWSE official volume fetch failed for %s/%s: %s", code, cursor, exc)
        cursor = (cursor.replace(day=28) + pd.Timedelta(days=4)).replace(day=1)
    result = pd.DataFrame(rows, columns=["date", "volume"])
    if not result.empty:
        result = result.drop_duplicates("date", keep="last").sort_values("date")
    return result


def fetch_tpex_latest_volume(stock_code: str) -> pd.DataFrame:
    """Fetch TPEx official volume snapshot; this endpoint is latest-day only."""
    code = str(stock_code).strip().upper().removesuffix(".TWO")
    if not (code.isdigit() and 4 <= len(code) <= 6):
        return pd.DataFrame(columns=["date", "volume"])
    try:
        response = requests.get(_TPEX_URL, headers={**_HEADERS, "Referer": "https://www.tpex.org.tw/openapi/"}, timeout=_TIMEOUT)
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return pd.DataFrame(columns=["date", "volume"])
        for row in payload:
            if not isinstance(row, dict) or str(row.get("SecuritiesCompanyCode", "")).strip() != code:
                continue
            day = _ad_date(row.get("Date"))
            volume = _int_cell(row.get("TradingShares"))
            if day and volume is not None:
                return pd.DataFrame([{"date": pd.to_datetime(day), "volume": volume}])
    except Exception as exc:
        logger.warning("TPEx official latest volume fetch failed for %s: %s", code, exc)
    return pd.DataFrame(columns=["date", "volume"])


def overlay_official_tw_volume(frame: pd.DataFrame, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Overlay only verified official volume; never substitute Yahoo when missing."""
    if frame is None or frame.empty:
        return frame
    code = str(stock_code).strip().upper()
    if code.endswith(".TW"):
        official = fetch_twse_volume(code, start_date, end_date)
        source = "TWSE_STOCK_DAY"
    elif code.endswith(".TWO"):
        official = fetch_tpex_latest_volume(code)
        source = "TPEX_LATEST_SNAPSHOT"
    else:
        return frame
    out = frame.copy()
    out["date"] = pd.to_datetime(out["date"], errors="coerce").dt.tz_localize(None)
    out["volume_yahoo"] = pd.to_numeric(out["volume"], errors="coerce")
    out["volume_official"] = pd.NA
    out["volume_source"] = "yahoo_unverified"
    if official is not None and not official.empty:
        official = official.copy()
        official["date"] = pd.to_datetime(official["date"], errors="coerce").dt.tz_localize(None)
        lookup = official.dropna(subset=["date"]).set_index("date")["volume"]
        matched = out["date"].map(lookup)
        mask = matched.notna()
        out.loc[mask, "volume"] = matched.loc[mask].astype("int64")
        out.loc[mask, "volume_official"] = matched.loc[mask].astype("int64")
        out.loc[mask, "volume_source"] = source
    # Explicit metadata lets downstream consumers distinguish official coverage.
    out.attrs["taiwan_volume_policy"] = "official_overlay_only; unmatched_rows_remain_yahoo_unverified"
    out.attrs["taiwan_official_volume_source"] = source
    return out
