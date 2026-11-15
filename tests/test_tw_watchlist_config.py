from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.load_tw_watchlist import (
    WatchlistConfigError,
    load_watchlist,
    resolve_watchlist,
)


def test_default_watchlist_is_loaded_from_single_config_file() -> None:
    assert load_watchlist() == [
        "1303.TW", "2408.TW", "2603.TW", "2409.TW", "2344.TW",
        "2454.TW", "3231.TW", "2330.TW", "2881.TW",
    ]


def test_disabled_instrument_is_not_in_runtime_list(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "market": "tw",
        "instruments": [
            {"symbol": "2330", "name": "台積電", "market": "tw", "enabled": True},
            {"symbol": "1303.TW", "name": "南亞", "market": "tw", "enabled": False},
        ],
    }), encoding="utf-8")

    assert load_watchlist(path) == ["2330.TW"]


def test_explicit_override_is_normalized_and_taiwan_only() -> None:
    assert resolve_watchlist(override="2330, 1303.TW；0050") == [
        "2330.TW", "1303.TW", "0050.TW",
    ]
    with pytest.raises(WatchlistConfigError):
        resolve_watchlist(override="AAPL")
    with pytest.raises(WatchlistConfigError):
        resolve_watchlist(override="2330,2330.TW")


@pytest.mark.parametrize("payload", [
    {"schema_version": 1, "market": "cn", "instruments": []},
    {"schema_version": 2, "market": "tw", "instruments": []},
    {"schema_version": 1, "market": "tw", "instruments": [
        {"symbol": "600519", "name": "茅台", "market": "cn", "enabled": True},
    ]},
    {"schema_version": 1, "market": "tw", "instruments": [
        {"symbol": "2330", "name": "台積電", "market": "tw", "enabled": "true"},
    ]},
])
def test_invalid_market_or_schema_fails_closed(tmp_path: Path, payload: dict) -> None:
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps(payload), encoding="utf-8")
    with pytest.raises(WatchlistConfigError):
        load_watchlist(path)


def test_empty_enabled_watchlist_fails_closed(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "market": "tw",
        "instruments": [
            {"symbol": "2330", "name": "台積電", "market": "tw", "enabled": False},
        ],
    }), encoding="utf-8")
    with pytest.raises(WatchlistConfigError):
        load_watchlist(path)



@pytest.mark.parametrize("monitoring", [
    {"alert_price": 0},
    {"stop_loss": -1},
    {"take_profit": "100"},
    {"unexpected": 100},
])
def test_invalid_per_symbol_monitoring_settings_fail_closed(
    tmp_path: Path, monitoring: dict
) -> None:
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "market": "tw",
        "instruments": [{
            "symbol": "2330",
            "name": "台積電",
            "market": "tw",
            "enabled": True,
            "monitoring": monitoring,
        }],
    }), encoding="utf-8")
    with pytest.raises(WatchlistConfigError):
        load_watchlist(path)


def test_positive_monitoring_thresholds_are_accepted(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "market": "tw",
        "instruments": [{
            "symbol": "2330",
            "name": "台積電",
            "market": "tw",
            "enabled": True,
            "monitoring": {
                "alert_price": 2400,
                "stop_loss": 2200,
                "take_profit": 2600,
            },
        }],
    }), encoding="utf-8")
    assert load_watchlist(path) == ["2330.TW"]


def test_duplicate_disabled_symbols_are_rejected(tmp_path: Path) -> None:
    path = tmp_path / "watchlist.json"
    path.write_text(json.dumps({
        "schema_version": 1,
        "market": "tw",
        "instruments": [
            {"symbol": "2330", "name": "台積電", "market": "tw", "enabled": True},
            {"symbol": "2330.TW", "name": "台積電重複", "market": "tw", "enabled": False},
        ],
    }), encoding="utf-8")
    with pytest.raises(WatchlistConfigError):
        load_watchlist(path)
