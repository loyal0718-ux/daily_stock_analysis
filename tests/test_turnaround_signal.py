from src.utils.turnaround_signal import detect_turnaround_signal


def _bar(day, open_, high, low, close, volume):
    return {
        "date": f"2026-11-{day:02d}",
        "open": open_, "high": high, "low": low, "close": close,
        "volume": volume,
    }


def test_selling_exhaustion_allows_small_probe_without_flow_input():
    bars = [
        _bar(5, 260, 266, 249, 249, 100_000),
        _bar(6, 248, 254, 235, 239.5, 114_670),
        _bar(9, 246, 265, 244.5, 263, 57_247),
        _bar(10, 264, 291, 260, 289, 80_000),
    ]
    result = detect_turnaround_signal(bars)
    assert result["status"] in {"breakout_wait_retest", "rebound_confirmed", "trend_confirmed"}
    assert result["flow_policy"].startswith("外資/投信")


def test_probe_candidate_requires_no_new_low_and_close_strength():
    bars = [
        _bar(2, 120, 122, 110, 111, 1000),
        _bar(3, 111, 113, 105, 106, 1100),
        _bar(4, 106, 110, 102, 103, 1000),
        _bar(5, 103, 109, 102.5, 108, 700),
    ]
    result = detect_turnaround_signal(bars)
    assert result["status"] == "probe_candidate"
    assert result["action"] == "probe_tranche_eligible"
    assert result["allocation"]["probe_pct"] == 25


def test_new_low_invalidates_probe_assumption():
    bars = [
        _bar(2, 120, 122, 110, 111, 1000),
        _bar(3, 111, 113, 105, 106, 1100),
        _bar(4, 106, 110, 102, 103, 1000),
        _bar(5, 102, 105, 99, 100, 1200),
    ]
    result = detect_turnaround_signal(bars)
    assert result["status"] == "risk_invalidated"
    assert result["action"] == "stop_and_reassess"


def test_breakout_requires_next_session_retest_before_second_tranche():
    bars = [
        _bar(2, 100, 104, 98, 100, 1000),
        _bar(3, 100, 103, 97, 99, 900),
        _bar(4, 99, 105, 98, 104, 800),
        _bar(5, 104, 106, 103, 105, 850),
    ]
    result = detect_turnaround_signal(bars)
    assert result["status"] == "rebound_confirmed"
    assert result["action"] == "confirmation_tranche_eligible"


def test_insufficient_history_is_not_a_signal():
    result = detect_turnaround_signal([_bar(5, 10, 11, 9, 10, 100)])
    assert result["status"] == "insufficient_data"
    assert result["action"] == "wait_for_more_data"


def test_malformed_ohlcv_blocks_all_turnaround_entries():
    bars = [
        _bar(2, 120, 122, 110, 111, 1000),
        _bar(3, 111, 113, 105, 106, 1100),
        _bar(4, 106, 110, 102, 103, 1000),
        _bar(5, 103, 101, 102.5, 108, 700),  # high is below open/close
    ]
    result = detect_turnaround_signal(bars)
    assert result["status"] == "invalid_data"
    assert result["action"] == "block_signal"
    assert result["data_quality"] == "invalid_ohlcv"


def test_missing_volume_blocks_turnaround_signal():
    bars = [
        _bar(2, 120, 122, 110, 111, 1000),
        _bar(3, 111, 113, 105, 106, 1100),
        _bar(4, 106, 110, 102, 103, 1000),
        _bar(5, 103, 109, 102.5, 108, 700),
    ]
    del bars[-1]["volume"]
    result = detect_turnaround_signal(bars)
    assert result["status"] == "invalid_data"
    assert result["action"] == "block_signal"

def test_duplicate_session_date_blocks_turnaround_signal():
    bars = [
        _bar(2, 120, 122, 110, 111, 1000),
        _bar(3, 111, 113, 105, 106, 1100),
        _bar(4, 106, 110, 102, 103, 1000),
        _bar(4, 103, 109, 102.5, 108, 700),
    ]
    result = detect_turnaround_signal(bars)
    assert result["status"] == "invalid_data"
    assert result["action"] == "block_signal"
    assert result["data_quality"] == "duplicate_trading_date"


def test_unparseable_session_date_blocks_turnaround_signal():
    bars = [
        _bar(2, 120, 122, 110, 111, 1000),
        _bar(3, 111, 113, 105, 106, 1100),
        _bar(4, 106, 110, 102, 103, 1000),
        _bar(5, 103, 109, 102.5, 108, 700),
    ]
    bars[-1]["date"] = "not-a-date"
    result = detect_turnaround_signal(bars)
    assert result["status"] == "invalid_data"
    assert result["action"] == "block_signal"
    assert result["data_quality"] == "invalid_trading_date"
