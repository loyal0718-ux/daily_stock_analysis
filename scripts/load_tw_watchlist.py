#!/usr/bin/env python3
"""Resolve the central Taiwan watchlist into the legacy STOCK_LIST string.

The versioned config/tw_watchlist.json file is authoritative. This script
performs local validation only; it never calls market-data or AI APIs.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any, Iterable

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "tw_watchlist.json"
SYMBOL_RE = re.compile(r"^\d{4,6}(?:\.TW)?$", re.IGNORECASE)


class WatchlistConfigError(ValueError):
    """Raised when the Taiwan watchlist is malformed or contains other markets."""


def _normalize_symbol(value: object) -> str:
    symbol = str(value or "").strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise WatchlistConfigError(f"Unsupported Taiwan symbol: {value!r}")
    return symbol if symbol.endswith(".TW") else f"{symbol}.TW"


def _validate_symbols(values: Iterable[object]) -> list[str]:
    symbols: list[str] = []
    seen: set[str] = set()
    for value in values:
        symbol = _normalize_symbol(value)
        if symbol in seen:
            raise WatchlistConfigError(f"Duplicate symbol: {symbol}")
        seen.add(symbol)
        symbols.append(symbol)
    if not symbols:
        raise WatchlistConfigError("Taiwan watchlist has no enabled instruments")
    return symbols


def _validate_instrument(item: dict) -> str:
    if item.get("market") != "tw":
        raise WatchlistConfigError(
            f"Instrument {item.get('symbol')!r} is not tagged market='tw'"
        )
    if not isinstance(item.get("enabled"), bool):
        raise WatchlistConfigError(
            f"Instrument {item.get('symbol')!r} must have boolean enabled"
        )
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise WatchlistConfigError(
            f"Instrument {item.get('symbol')!r} must have a non-empty name"
        )
    data_source = item.get("data_source", "auto")
    if data_source not in {"auto", "yfinance", "fugle"}:
        raise WatchlistConfigError(
            f"Instrument {item.get('symbol')!r} has unsupported data_source: {data_source!r}"
        )
    monitoring = item.get("monitoring", {})
    if not isinstance(monitoring, dict):
        raise WatchlistConfigError(
            f"Instrument {item.get('symbol')!r} monitoring must be an object"
        )
    allowed_thresholds = {"alert_price", "stop_loss", "take_profit"}
    unknown = set(monitoring) - allowed_thresholds
    if unknown:
        raise WatchlistConfigError(
            f"Instrument {item.get('symbol')!r} has unknown monitoring fields: {sorted(unknown)}"
        )
    for field in allowed_thresholds:
        value = monitoring.get(field)
        if value is not None and (
            isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0
        ):
            raise WatchlistConfigError(
                f"Instrument {item.get('symbol')!r} {field} must be a positive number or null"
            )
    return _normalize_symbol(item.get("symbol"))


def _positive_optional_number(value: Any, *, field: str, symbol: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool):
        raise WatchlistConfigError(f"{symbol}: {field} must be a positive number or null")
    try:
        number = float(value)
    except (TypeError, ValueError) as exc:
        raise WatchlistConfigError(f"{symbol}: {field} must be a positive number or null") from exc
    if number <= 0:
        raise WatchlistConfigError(f"{symbol}: {field} must be greater than zero")
    return number


def load_watchlist_config(config_path: Path = DEFAULT_CONFIG) -> list[dict[str, Any]]:
    """Load validated instrument metadata without fetching quotes or creating alerts."""
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise WatchlistConfigError(f"Cannot read watchlist config: {exc}") from exc
    if not isinstance(payload, dict) or payload.get("schema_version") != 1:
        raise WatchlistConfigError("Unsupported watchlist schema_version")
    if payload.get("market") != "tw":
        raise WatchlistConfigError("Central watchlist market must be 'tw'")
    instruments = payload.get("instruments")
    if not isinstance(instruments, list):
        raise WatchlistConfigError("'instruments' must be a list")
    enabled_instruments: list[dict[str, Any]] = []
    configured_symbols: set[str] = set()
    seen: set[str] = set()
    for item in instruments:
        if not isinstance(item, dict):
            raise WatchlistConfigError("Each instrument must be an object")
        symbol = _validate_instrument(item)
        if symbol in seen:
            raise WatchlistConfigError(f"Duplicate symbol: {symbol}")
        seen.add(symbol)
        if item["enabled"]:
            enabled_symbols.append(symbol)
    return _validate_symbols(enabled_symbols)


def main() -> int:
    try:
        symbols = load_watchlist()
    except WatchlistConfigError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    print(",".join(symbols))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
