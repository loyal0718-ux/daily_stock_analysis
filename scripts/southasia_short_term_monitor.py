#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""南亞（1303）短線觀察：只發送有意義的價位事件，不產生自動買賣指令。"""
from __future__ import annotations

import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from zoneinfo import ZoneInfo

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from src.config import get_config
from data_provider.base import DataFetcherManager
from src.notification_sender.telegram_sender import TelegramSender

TZ = ZoneInfo("Asia/Taipei")
STATE_DIR = ROOT / ".cache" / "southasia"
CODE = "1303.TW"
WATCH_PRICE = 300.0
LOWER_WATCH = 292.0
MAX_QUOTE_AGE_SECONDS = 180


def parse_time(value: str | None):
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=ZoneInfo("UTC"))
        return dt.astimezone(TZ)
    except (TypeError, ValueError):
        return None


def marker(name: str) -> Path:
    return STATE_DIR / f"{datetime.now(TZ):%Y%m%d}-{name}.sent"


def send(sender: TelegramSender, message: str) -> None:
    if not sender.send_to_telegram(message):
        raise RuntimeError("Telegram 推播失敗")


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
    now = datetime.now(TZ)
    config = get_config()
    token = (os.getenv("TELEGRAM_BOT_TOKEN") or getattr(config, "telegram_bot_token", "") or "").strip()
    chat_id = (os.getenv("TELEGRAM_CHAT_ID") or getattr(config, "telegram_chat_id", "") or "").strip()
    if not token or not chat_id:
        raise RuntimeError("缺少 Telegram Bot Token 或 Chat ID；不允許靜默略過")

    manager = DataFetcherManager()
    quote = manager.get_realtime_quote(CODE)
    if quote is None:
        raise RuntimeError("Fugle 即時行情無回應")
    source = getattr(getattr(quote, "source", None), "value", getattr(quote, "source", "unknown"))
    if source != "fugle":
        raise RuntimeError(f"行情來源不是 Fugle：{source}")

    price = getattr(quote, "price", None)
    provider_time = parse_time(getattr(quote, "provider_timestamp", None))
    if price is None or float(price) <= 0:
        raise RuntimeError("南亞行情價格缺失或不合法")
    if provider_time is None:
        raise RuntimeError("Fugle 未提供有效行情時間")
    age = max(0, int((now - provider_time).total_seconds()))
    if age > MAX_QUOTE_AGE_SECONDS:
        raise RuntimeError(f"行情過期：資料時間 {provider_time:%H:%M:%S}，延遲 {age} 秒")

    price = float(price)
    change_pct = getattr(quote, "change_pct", None)
    change_text = f"{float(change_pct):+.2f}%" if change_pct is not None else "未提供"
    high = getattr(quote, "high", None)
    low = getattr(quote, "low", None)
    open_price = getattr(quote, "open_price", None)
    def fmt(value):
        return f"{float(value):.2f}" if value is not None else "—"

    header = (
        f"南亞 1303 短線監控｜{now:%m/%d %H:%M}\n"
        f"現價：{price:.2f}（{change_text}）｜行情時間：{provider_time:%H:%M:%S}\n"
        f"開高低：{fmt(open_price)} / {fmt(high)} / {fmt(low)}"
    )
    STATE_DIR.mkdir(parents=True, exist_ok=True)
    events: list[str] = []

    under300 = marker("under300")
    near292 = marker("near292")
    recovered = marker("recovered")

    if price < WATCH_PRICE and not under300.exists():
        events.append(
            "🔎【進入觀察區】南亞跌破 300 元。這只是啟動觀察，不是買進訊號；"
            "先確認賣壓是否收斂、低點是否守住，再評估第一筆。"
        )
        under300.write_text(now.isoformat(), encoding="utf-8")

    if price <= LOWER_WATCH and not near292.exists():
        events.append(
            "⚠️【接近前低區】南亞來到 292 元或以下。請留意 289.5–292 元附近的承接；"
            "若持續破低且無法收復，不應因價格便宜而進場。"
        )
        near292.write_text(now.isoformat(), encoding="utf-8")

    if price >= WATCH_PRICE and under300.exists() and not recovered.exists():
        events.append(
            "↗️【收復 300 元】南亞已回到 300 元以上。仍需觀察能否站穩，"
            "單次收復不代表趨勢反轉，也不構成追價指令。"
        )
        recovered.write_text(now.isoformat(), encoding="utf-8")

    if events:
        send(TelegramSender(config), header + "\n\n" + "\n\n".join(events) +
             "\n\n策略資金上限：50,000 元；本訊息為條件警示，非自動下單。")
        print(f"Alert sent: {len(events)} event(s)")
    else:
        print(
            f"No new alert. price={price:.2f}, provider_time={provider_time.isoformat()}, "
            f"age_seconds={age}"
        )


if __name__ == "__main__":
    main()
