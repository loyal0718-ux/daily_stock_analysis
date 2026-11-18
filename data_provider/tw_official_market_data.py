# -*- coding: utf-8 -*-
"""Official Taiwan daily trading volume overlay.

TWSE STOCK_DAY is historical/monthly; TPEx OpenAPI daily close quotes is a
latest-day snapshot. TPEx snapshots are persisted as a small, exchange-data-only
JSONL file so consecutive GitHub Actions runs can build a daily history. Yahoo
adjusted OHLC and its estimated amount are never relabelled as official.
Missing official rows remain unverified rather than being zero-filled.
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
from pathlib import Path
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
_HISTORY_COLUMNS = ["date", "volume"]


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


def _tpex_history_path() -> Path:
    """Location of the exchange-only history restored by GitHub Actions cache."""
    return Path(
        os.getenv(
            "TPEX_OFFICIAL_HISTORY_PATH",
            "data/official_market_data/tpex_daily.jsonl",
        )
    )


def _read_tpex_history_records(path: Path) -> dict[tuple[str, str], dict]:
    records: dict[tuple[str, str], dict] = {}
    if not path.exists():
        return records
    try:
        with path.open("r", encoding="utf-8") as handle:
            for line in handle:
                try:
                    row = json.loads(line)
                    code = str(row.get("code", "")).strip()
                    day = _ad_date(row.get("date"))
                    volume = _int_cell(row.get("volume"))
                    if code and day and volume is not None:
                        records[(code, day)] = {
                            "code": code,
                            "date": day,
                            "volume": volume,
                            "source": "TPEX_LATEST_SNAPSHOT",
                        }
                except (AttributeError, TypeError, ValueError, json.JSONDecodeError):
                    continue
    except OSError as exc:
        logger.warning("Could not read TPEx official history %s: %s", path, exc)
    return records


def _upsert_tpex_history(stock_code: str, official: pd.DataFrame) -> None:
    """Idempotently retain official daily TPEx volume, keyed by code + date."""
    if official is None or official.empty:
        return
    code = str(stock_code).strip().upper().removesuffix(".TWO")
    path = _tpex_history_path()
    records = _read_tpex_history_records(path)
    for row in official.to_dict("records"):
        day = pd.to_datetime(row.get("date"), errors="coerce")
        volume = _int_cell(row.get("volume"))
        if pd.isna(day) or volume is None:
            continue
        day_key = day.strftime("%Y%m%d")
        records[(code, day_key)] = {
            "code": code,
            "date": day_key,
            "volume": volume,
            "source": "TPEX_LATEST_SNAPSHOT",
        }
    if not records:
        return
    path.parent.mkdir(parents=True, exist_ok=True)
    temp_name = None
    try:
        with tempfile.NamedTemporaryFile(
            "w", encoding="utf-8", dir=str(path.parent),
            prefix=f".{path.name}.", suffix=".tmp", delete=False,
        ) as handle:
            temp_name = handle.name
            for key in sorted(records):
                handle.write(json.dumps(records[key], ensure_ascii=False) + "\n")
        os.replace(temp_name, path)
    except OSError as exc:
        logger.warning("Could not persist TPEx official history %s: %s", path, exc)
        if temp_name:
            try:
                os.unlink(temp_name)
            except OSError:
                pass


def _load_tpex_history(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    code = str(stock_code).strip().upper().removesuffix(".TWO")
    start = pd.Timestamp(start_date).normalize()
    end = pd.Timestamp(end_date).normalize()
    rows = []
    for (record_code, day), row in _read_tpex_history_records(_tpex_history_path()).items():
        if record_code != code:
            continue
        parsed_day = pd.to_datetime(day, format="%Y%m%d", errors="coerce")
        if pd.notna(parsed_day) and start <= parsed_day <= end:
            rows.append({"date": parsed_day, "volume": row["volume"]})
    result = pd.DataFrame(rows, columns=_HISTORY_COLUMNS)
    if not result.empty:
        result = result.drop_duplicates("date", keep="last").sort_values("date")
    return result


def fetch_twse_volume(stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Fetch TWSE official historical volume (shares), month by month."""
    code = str(stock_code).strip().upper().removesuffix(".TW")
    if not (code.isdigit() and 4 <= len(code) <= 6):
        return pd.DataFrame(columns=_HISTORY_COLUMNS)
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
    result = pd.DataFrame(rows, columns=_HISTORY_COLUMNS)
    if not result.empty:
        result = result.drop_duplicates("date", keep="last").sort_values("date")
    return result


def fetch_tpex_latest_volume(stock_code: str) -> pd.DataFrame:
    """Fetch TPEx official volume snapshot; this endpoint is latest-day only."""
    code = str(stock_code).strip().upper().removesuffix(".TWO")
    if not (code.isdigit() and 4 <= len(code) <= 6):
        return pd.DataFrame(columns=_HISTORY_COLUMNS)
    try:
        response = requests.get(
            _TPEX_URL,
            headers={**_HEADERS, "Referer": "https://www.tpex.org.tw/openapi/"},
            timeout=_TIMEOUT,
        )
        response.raise_for_status()
        payload = response.json()
        if not isinstance(payload, list):
            return pd.DataFrame(columns=_HISTORY_COLUMNS)
        for row in payload:
            if not isinstance(row, dict) or str(row.get("SecuritiesCompanyCode", "")).strip() != code:
                continue
            day = _ad_date(row.get("Date"))
            volume = _int_cell(row.get("TradingShares"))
            if day and volume is not None:
                return pd.DataFrame([{"date": pd.to_datetime(day), "volume": volume}])
    except Exception as exc:
        logger.warning("TPEx official latest volume fetch failed for %s: %s", code, exc)
    return pd.DataFrame(columns=_HISTORY_COLUMNS)


def overlay_official_tw_volume(frame: pd.DataFrame, stock_code: str, start_date: str, end_date: str) -> pd.DataFrame:
    """Overlay verified official volume; retain TPEx snapshots across daily runs."""
    if frame is None or frame.empty:
        return frame
    code = str(stock_code).strip().upper()
    if code.endswith(".TW"):
        official = fetch_twse_volume(code, start_date, end_date)
        source = "TWSE_STOCK_DAY"
    elif code.endswith(".TWO"):
        latest = fetch_tpex_latest_volume(code)
        if latest is not None and not latest.empty:
            _upsert_tpex_history(code, latest)
        official = _load_tpex_history(code, start_date, end_date)
        source = "TPEX_LATEST_SNAPSHOT_HISTORY"
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
    out.attrs["taiwan_volume_policy"] = "official_overlay_only; unmatched_rows_remain_yahoo_unverified"
    out.attrs["taiwan_official_volume_source"] = source
    out.attrs["tpex_official_history_path"] = str(_tpex_history_path()) if code.endswith(".TWO") else None
    return out
