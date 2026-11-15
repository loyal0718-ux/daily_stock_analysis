"""Deterministic three-stage selling-exhaustion and rebound detector.

This detector uses completed daily OHLCV bars only. It does not use institutional
flows as an entry veto; flows remain contextual evidence for the analyst.
"""
from __future__ import annotations

import math
from datetime import date
from typing import Any, Dict, Iterable, List, Optional


def _number(value: Any) -> Optional[float]:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if math.isfinite(parsed) else None


def _bar_dict(bar: Any) -> Dict[str, Any]:
    if isinstance(bar, dict):
        return {str(k).lower(): v for k, v in bar.items()}
    if hasattr(bar, "to_dict"):
        try:
            return {str(k).lower(): v for k, v in bar.to_dict().items()}
        except Exception:
            return {}
    if hasattr(bar, "__dict__"):
        return {str(k).lower(): v for k, v in vars(bar).items()}
    return {}


def detect_turnaround_signal(bars: Iterable[Any]) -> Dict[str, Any]:
    """Return an explainable stage/status/action payload from completed OHLCV bars.

    Stage 1: a non-breaking low, positive close response, and either volume
    contraction or a meaningful lower wick -> allow a 20-25% probe.
    Stage 2: breakout above the prior session high -> wait for a retest; only
    after the next session holds that level is the 30% confirmation tranche
    eligible.
    Stage 3: rising lows and bullish MA structure -> evaluate the remaining
    reserve based on risk/reward.
    """
    rows = [_bar_dict(item) for item in bars]
    rows = [row for row in rows if _number(row.get("close")) and _number(row.get("low"))]
    rows.sort(key=lambda row: str(row.get("date") or row.get("trade_date") or ""))
    if len(rows) < 4:
        return {
            "version": 1, "status": "insufficient_data", "stage": 0,
            "action": "wait_for_more_data",
            "reason": "至少需要 4 根完整日 K 才能評估止跌結構",
            "allocation": {"probe_pct": 25, "confirmation_pct": 30, "reserve_pct": 45},
            "data_quality": "insufficient",
        }

    latest = rows[-1]
    previous = rows[-2]
    prior = rows[-4:-1]
    close = _number(latest.get("close"))
    low = _number(latest.get("low"))
    high = _number(latest.get("high"))
    open_price = _number(latest.get("open"))
    prev_close = _number(previous.get("close"))
    prev_high = _number(previous.get("high"))
    prev_low = _number(previous.get("low"))
    volume = _number(latest.get("volume"))
    prior_lows = [_number(row.get("low")) for row in prior]
    prior_lows = [value for value in prior_lows if value is not None]
    prior_volumes = [_number(row.get("volume")) for row in rows[-4:-1]]
    prior_volumes = [value for value in prior_volumes if value is not None and value > 0]

    new_low = bool(prior_lows and low < min(prior_lows))
    higher_low = bool(prev_low is not None and low >= prev_low)
    close_up = bool(prev_close is not None and close > prev_close)
    range_size = (high - low) if high is not None and low is not None else 0.0
    lower_wick = (
        max(0.0, min(open_price, close) - low) / range_size
        if open_price is not None and range_size > 0 else 0.0
    )
    volume_baseline = sum(prior_volumes) / len(prior_volumes) if prior_volumes else None
    volume_contracting = bool(
        volume is not None and volume_baseline is not None
        and volume <= volume_baseline * 0.85
    )
    exhaustion = (
        not new_low and close_up and (volume_contracting or lower_wick >= 0.30)
    )

    # A breakout day is deliberately not enough for a tranche increase. The
    # following completed session must retest and hold the breakout level.
    previous_close = _number(previous.get("close"))
    breakout_level = _number(rows[-3].get("high"))
    breakout_on_previous = bool(
        previous_close is not None and breakout_level is not None
        and previous_close > breakout_level
    )
    retest_holds = bool(
        breakout_on_previous and prev_close is not None
        and prev_low is not None
        and prev_low >= breakout_level * 0.99
        and close >= breakout_level
    )
    breakout_today = bool(
        prev_high is not None and close > prev_high
        and open_price is not None and close > open_price
        and high is not None and range_size > 0
        and (close - low) / range_size >= 0.65
    )

    closes = [_number(row.get("close")) for row in rows[-20:]]
    closes = [value for value in closes if value is not None]
    ma5 = sum(closes[-5:]) / 5 if len(closes) >= 5 else None
    ma10 = sum(closes[-10:]) / 10 if len(closes) >= 10 else None
    lows5 = [_number(row.get("low")) for row in rows[-3:]]
    rising_lows = len(lows5) == 3 and all(
        lows5[i] is not None and lows5[i + 1] is not None and lows5[i + 1] > lows5[i]
        for i in range(2)
    )
    trend_confirmed = bool(
        ma5 is not None and ma10 is not None and close > ma5 >= ma10 and rising_lows
    )

    if new_low:
        status, stage, action = "risk_invalidated", 0, "stop_and_reassess"
        reason = "最新低點跌破近三個交易日低點，止跌假設失效，依既定風險條件處理"
    elif trend_confirmed:
        status, stage, action = "trend_confirmed", 3, "evaluate_reserve"
        reason = "低點墊高且收盤站上 MA5、MA10，趨勢結構改善；剩餘資金仍須檢查風險報酬"
    elif retest_holds:
        status, stage, action = "rebound_confirmed", 2, "confirmation_tranche_eligible"
        reason = "前一交易日突破前高後，最新交易日回測守住突破位"
    elif breakout_today:
        status, stage, action = "breakout_wait_retest", 2, "wait_for_retest"
        reason = "收盤突破前一交易日高點，但尚未完成隔日回測，不提前加第二階段部位"
    elif exhaustion:
        status, stage, action = "probe_candidate", 1, "probe_tranche_eligible"
        reason = "低點未再破底、收盤轉強，且出現量縮或下影線承接，允許小額試單"
    else:
        status, stage, action = "watching", 0, "wait_for_price_confirmation"
        reason = "尚未同時滿足賣壓衰竭條件，持續觀察價格與量能"

    return {
        "version": 1,
        "as_of": str(latest.get("date") or latest.get("trade_date") or ""),
        "status": status,
        "stage": stage,
        "action": action,
        "reason": reason,
        "signals": {
            "no_new_low": not new_low,
            "higher_low_vs_previous": higher_low,
            "close_strength": close_up,
            "volume_contraction": volume_contracting if volume is not None else None,
            "lower_wick_ratio": round(lower_wick, 3) if range_size > 0 else None,
            "breakout_today": breakout_today,
            "breakout_retest_holds": retest_holds,
            "rising_lows": rising_lows,
            "ma5": round(ma5, 3) if ma5 is not None else None,
            "ma10": round(ma10, 3) if ma10 is not None else None,
        },
        "allocation": {"probe_pct": 25, "confirmation_pct": 30, "reserve_pct": 45},
        "flow_policy": "外資/投信買賣超只作為輔助證據，不單獨否決止跌試單",
        "data_quality": "daily_ohlcv",
    }


__all__ = ["detect_turnaround_signal"]
