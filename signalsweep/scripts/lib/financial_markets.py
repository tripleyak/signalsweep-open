"""Shared financial-markets item helper (signalsweep 3.18.0+).

Consumed by v3.18.0 financial adapters: fred, alpha_vantage, polygon_io,
finnhub, sec_xbrl. Parallels `reviews.py` (v3.17) and `demand_signals.py` (v3.9)
helper-module pattern.

Standardized metadata keys across all 5 adapters:
  asset_type (str — e.g., "series", "equity", "economic_indicator", "fund")
  symbol / series_id (platform-native identifier)
  exchange (str, where applicable)
  currency (ISO-4217, where applicable)
  last_value (float, most-recent point)
  last_updated (ISO date)
  platform (str — e.g., "fred", "alpha_vantage")
"""

from __future__ import annotations

from typing import Any


def _coerce_float(raw: Any) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def build_financial_item(
    *,
    item_id: str,
    platform: str,
    title: str,
    snippet: str,
    url: str,
    source_domain: str,
    asset_type: str = "",
    symbol: str = "",
    exchange: str = "",
    currency: str = "",
    last_value: Any = None,
    last_updated: str | None = None,
    relevance: float = 0.65,
    why_relevant: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a signalsweep-standard item dict from financial fields."""
    value = _coerce_float(last_value)
    metadata: dict[str, Any] = {
        "platform": platform,
        "asset_type": asset_type,
        "symbol": symbol,
        "exchange": exchange,
        "currency": currency,
        "last_value": value,
        "last_updated": last_updated or "",
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return {
        "id": item_id,
        "title": title[:200],
        "snippet": (snippet or "")[:500],
        "url": url,
        "source_domain": source_domain,
        "date": last_updated,
        "relevance": relevance,
        "why_relevant": why_relevant or f"{platform.title()} — {title[:60]}",
        "metadata": metadata,
    }
