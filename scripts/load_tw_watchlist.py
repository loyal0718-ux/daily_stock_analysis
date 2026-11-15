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
from typing import Iterable

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


def load_watchlist(config_path: Path = DEFAULT_CONFIG) -> list[str]:
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
    enabled_symbols: list[str] = []
    for item in instruments:
        if not isinstance(item, dict):
            raise WatchlistConfigError("Each instrument must be an object")
        if item.get("market") != "tw":
            raise WatchlistConfigError(
                f"Instrument {item.get('symbol')!r} is not tagged market='tw'"
            )
        if not isinstance(item.get("enabled"), bool):
            raise WatchlistConfigError(
                f"Instrument {item.get('symbol')!r} must have boolean enabled"
            )
        if item["enabled"]:
            enabled_symbols.append(item.get("symbol"))
    return _validate_symbols(enabled_symbols)


def resolve_watchlist(config_path: Path = DEFAULT_CONFIG, override: str | None = None) -> list[str]:
    if override and override.strip():
        # Explicit GitHub variable/secret override remains supported, but is
        # subject to the same Taiwan-only validation as the committed config.
        return _validate_symbols(
            token.strip()
            for token in re.split(r"[,;；，、\s]+", override)
            if token.strip()
        )
    return load_watchlist(config_path)


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
