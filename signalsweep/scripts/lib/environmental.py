"""Shared environmental/weather item helper (signalsweep 3.19.0+).

Consumed by v3.19.0 adapters: noaa, openweather, epa_airnow, nasa_power.
Parallels `financial_markets.py` (v3.18), `reviews.py` (v3.17).

Standardized metadata keys:
  platform (str — e.g., "noaa", "openweather")
  measurement_type (str — e.g., "temperature", "precipitation", "aqi")
  station_id (str, where applicable)
  location (str — free-form label, e.g., "New York, NY" or lat/lon)
  latitude / longitude (float, where surfaced)
  unit (str — e.g., "°F", "mm", "µg/m³")
  value (float, single-point reading, where surfaced)
  observation_date (ISO date)
"""

from __future__ import annotations

from typing import Any


def _coerce_float(raw: Any) -> float | None:
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def build_environmental_item(
    *,
    item_id: str,
    platform: str,
    title: str,
    snippet: str,
    url: str,
    source_domain: str,
    measurement_type: str = "",
    station_id: str = "",
    location: str = "",
    latitude: Any = None,
    longitude: Any = None,
    unit: str = "",
    value: Any = None,
    observation_date: str | None = None,
    relevance: float = 0.65,
    why_relevant: str = "",
    extra_metadata: dict[str, Any] | None = None,
) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "platform": platform,
        "measurement_type": measurement_type,
        "station_id": station_id,
        "location": location,
        "latitude": _coerce_float(latitude),
        "longitude": _coerce_float(longitude),
        "unit": unit,
        "value": _coerce_float(value),
        "observation_date": observation_date or "",
    }
    if extra_metadata:
        metadata.update(extra_metadata)
    return {
        "id": item_id,
        "title": title[:200],
        "snippet": (snippet or "")[:500],
        "url": url,
        "source_domain": source_domain,
        "date": observation_date,
        "relevance": relevance,
        "why_relevant": why_relevant or f"{platform.title()} — {title[:60]}",
        "metadata": metadata,
    }
