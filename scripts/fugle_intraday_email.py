#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Fetch the configured Taiwan watchlist from Fugle and email a timestamped snapshot."""
from datetime import datetime
from zoneinfo import ZoneInfo
import os
import sys
from pathlib import Path

# Allow direct execution as `python scripts/fugle_intraday_email.py` from repo root.
REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from src.config import get_config
from data_provider.base import DataFetcherManager
from src.notification_sender.email_sender import EmailSender

TZ = ZoneInfo("Asia/Taipei")
EXPECTED = ["1303.TW","2408.TW","2603.TW","2409.TW","2344.TW","2454.TW","3231.TW","2330.TW","2881.TW"]

def as_local(value):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(TZ)
    except Exception:
        return None

def fmt(value, digits=2):
    try:
        return f"{float(value):,.{digits}f}"
    except (TypeError, ValueError):
        return "—"

def main():
    now = datetime.now(TZ)
    config = get_config()
    codes = list(getattr(config, "stock_list", []) or [])
    if codes != EXPECTED:
        raise RuntimeError(f"Watchlist mismatch: expected {EXPECTED}, got {codes}")

    manager = DataFetcherManager()
    rows = []
    failures = []
    for code in codes:
        try:
            quote = manager.get_realtime_quote(code)
            if quote is None:
                raise RuntimeError("quote unavailable")
            source = getattr(getattr(quote, "source", None), "value", getattr(quote, "source", "unknown"))
            provider_dt = as_local(getattr(quote, "provider_timestamp", None))
            stale = getattr(quote, "is_stale", None)
            if source != "fugle":
                failures.append(f"{code}: source={source}, expected=fugle")
                status = "來源異常"
            elif provider_dt is None:
                failures.append(f"{code}: missing provider timestamp")
                status = "缺少行情時間"
            elif now.hour >= 14 and provider_dt.date() == now.date() and provider_dt.hour == 13 and provider_dt.minute >= 25:
                status = "當日收盤資料"
            elif stale:
                failures.append(f"{code}: stale quote ({provider_dt.isoformat()})")
                status = "行情過期"
            else:
                status = "盤中有效"

            name = getattr(quote, "name", "") or code
            price = fmt(getattr(quote, "price", None), 2)
            change = getattr(quote, "change_pct", None)
            change_text = f"{fmt(change, 2)}%" if change is not None else "—"
            provider_text = provider_dt.strftime("%H:%M:%S") if provider_dt else "時間未知"
            rows.append((code, name, price, change_text, provider_text, status))
        except Exception as exc:
            failures.append(f"{code}: {type(exc).__name__}: {exc}")
            rows.append((code, code, "—", "—", "—", "取得失敗"))

    title = f"台股盤中行情快照｜{now:%Y-%m-%d %H:%M}（台北時間）"
    lines = [
        f"# {title}",
        "",
        f"資料來源：Fugle Taiwan Quote API；產生時間：{now:%Y-%m-%d %H:%M:%S}",
        "注意：此郵件為行情快照，不是即時逐筆推播；請以券商下單畫面為準。",
        "",
        "| 代號 | 名稱 | 價格（元） | 漲跌幅 | 行情時間（台北） | 狀態 |",
        "|---|---|---:|---:|---:|---|",
    ]
    for code, name, price, change, ts, status in rows:
        lines.append(f"| {code} | {name} | {price} | {change} | {ts} | {status} |")
    lines.extend(["", f"資料品質：{'全部通過' if not failures else f'{len(failures)} 檔需注意'}"])
    if failures:
        lines.extend(["", "## 異常明細"])
        lines.extend([f"- {item}" for item in failures])
    body = "\n".join(lines)

    sender = EmailSender(config)
    sent = sender.send_to_email(body, subject=title)
    if not sent:
        raise RuntimeError("SMTP email delivery failed")
    print(f"Intraday email sent. symbols={len(rows)}, issues={len(failures)}")
    if failures:
        print("\n".join(failures))
        sys.exit(1)

if __name__ == "__main__":
    main()
