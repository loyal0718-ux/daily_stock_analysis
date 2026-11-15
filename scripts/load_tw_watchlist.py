#!/usr/bin/env python3
"""Load and validate the central Taiwan watchlist without external API calls."""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_CONFIG = ROOT / "config" / "tw_watchlist.json"
SYMBOL_RE = re.compile(r"^\\d{4,6}(?:\\.TW)?$", re.IGNORECASE)
ALLOWED_MONITORING_FIELDS = {"alert_price", "stop_loss", "take_profit"}


class WatchlistConfigError(ValueError):
    """Raised when the Taiwan watchlist is malformed or contains other markets."""


def _normalize_symbol(value: object) -> str:
    symbol = str(value or "").strip().upper()
    if not SYMBOL_RE.fullmatch(symbol):
        raise WatchlistConfigError(f"Unsupported Taiwan symbol: {value!r}")
    return symbol if symbol.endswith(".TW") else f"{symbol}.TW"


def _positive_optional_number(value: Any, *, field: str, symbol: str) -> float | None:
    if value is None:
        return None
    if isinstance(value, bool) or not isinstance(value, (int, float)) or value <= 0:
        raise WatchlistConfigError(
            f"Instrument {symbol} {field} must be a positive number or null"
        )
    return float(value)


def _validate_instrument(item: dict[str, Any]) -> dict[str, Any]:
    raw_symbol = item.get("symbol")
    symbol = _normalize_symbol(raw_symbol)
    if item.get("market") != "tw":
        raise WatchlistConfigError(f"Instrument {raw_symbol!r} is not tagged market='tw'")
    if not isinstance(item.get("enabled"), bool):
        raise WatchlistConfigError(f"Instrument {raw_symbol!r} must have boolean enabled")
    name = item.get("name")
    if not isinstance(name, str) or not name.strip():
        raise WatchlistConfigError(f"Instrument {raw_symbol!r} must have a non-empty name")

    data_source = item.get("data_source", "auto")
    if data_source != "auto":
        raise WatchlistConfigError(
            f"Instrument {raw_symbol!r} has unsupported data_source: {data_source!r}"
        )

    monitoring = item.get("monitoring", {})
    if not isinstance(monitoring, dict):
        raise WatchlistConfigError(f"Instrument {raw_symbol!r} monitoring must be an object")
    unknown = set(monitoring) - ALLOWED_MONITORING_FIELDS
    if unknown:
        raise WatchlistConfigError(
            f"Instrument {raw_symbol!r} has unknown monitoring fields: {sorted(unknown)}"
        )
    normalized_monitoring = {
        field: _positive_optional_number(
            monitoring.get(field), field=field, symbol=symbol
        )
        for field in sorted(ALLOWED_MONITORING_FIELDS)
    }
    stop_loss = normalized_monitoring["stop_loss"]
    take_profit = normalized_monitoring["take_profit"]
    if stop_loss is not None and take_profit is not None and stop_loss >= take_profit:
        raise WatchlistConfigError(
            f"Instrument {raw_symbol!r} stop_loss must be below take_profit"
        )

    return {
        **item,
        "symbol": symbol,
        "name": name.strip(),
        "data_source": data_source,
        "monitoring": normalized_monitoring,
    }


def load_watchlist_config(config_path: Path = DEFAULT_CONFIG) -> list[dict[str, Any]]:
    """Return validated enabled instrument metadata; never creates alert rules."""
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

    validated: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in instruments:
        if not isinstance(item, dict):
            raise WatchlistConfigError("Each instrument must be an object")
        normalized = _validate_instrument(item)
        symbol = normalized["symbol"]
        if symbol in seen:
            raise WatchlistConfigError(f"Duplicate symbol: {symbol}")
        seen.add(symbol)
        if normalized["enabled"]:
            validated.append(normalized)

    if not validated:
        raise WatchlistConfigError("Taiwan watchlist has no enabled instruments")
    return validated


def load_watchlist(config_path: Path = DEFAULT_CONFIG) -> list[str]:
    """Return enabled Taiwan symbols in the legacy .TW format."""
    return [item["symbol"] for item in load_watchlist_config(config_path)]


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
