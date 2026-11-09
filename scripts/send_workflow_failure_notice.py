#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Send a concise Gmail notice when a scheduled dashboard workflow fails."""
import os
import smtplib
import sys
from email.message import EmailMessage
from datetime import datetime, timezone

sender = (os.getenv("EMAIL_SENDER") or "").strip()
password = os.getenv("EMAIL_PASSWORD") or ""
receivers = [x.strip() for x in (os.getenv("EMAIL_RECEIVERS") or "").split(",") if x.strip()]
if not receivers and sender:
    receivers = [sender]
if not sender or not password or not receivers:
    print("Failure email skipped: EMAIL_SENDER / EMAIL_PASSWORD / EMAIL_RECEIVERS is incomplete.")
    sys.exit(0)

workflow = os.getenv("FAILURE_WORKFLOW", "Taiwan stock dashboard")
run_url = os.getenv("FAILURE_RUN_URL", "")
run_id = os.getenv("FAILURE_RUN_ID", "")
run_number = os.getenv("FAILURE_RUN_NUMBER", "")
now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
msg = EmailMessage()
msg["Subject"] = f"⚠️ 台股儀表板工作流程失敗：{workflow}"
msg["From"] = sender
msg["To"] = ", ".join(receivers)
msg.set_content(
    "台股儀表板工作流程執行失敗，請查看 GitHub Actions 紀錄。\n\n"
    f"工作流程：{workflow}\n"
    f"Run ID：{run_id}\n"
    f"Run Number：{run_number}\n"
    f"通知時間：{now}\n"
    f"執行紀錄：{run_url}\n\n"
    "本郵件只表示工作流程失敗，不代表行情或投資判斷。"
)
try:
    with smtplib.SMTP("smtp.gmail.com", 587, timeout=20) as server:
        server.starttls()
        server.login(sender, password)
        server.send_message(msg)
    print(f"Failure notice sent to {len(receivers)} recipient(s).")
except Exception as exc:
    print(f"Failure notice could not be sent: {type(exc).__name__}: {exc}")
    # Do not hide the original workflow failure with a second failure.
    sys.exit(0)
