"""NASA POWER — solar/meteorological data for any lat/lon (signalsweep 3.19.0+).

Endpoint: `power.larc.nasa.gov/api/temporal/daily/point`. No auth.

Topic shape: `"lat,lon"` (e.g., "40.7128,-74.0060") — numeric pair parsed.
Non-coord topics return graceful envelope.

Gated by v3.6 public-APIs toggle.
"""

from __future__ import annotations

import re
from typing import Any

from . import environmental, public_api

ENDPOINT = "https://power.larc.nasa.gov/api/temporal/daily/point"
COORD_PATTERN = re.compile(r"^\s*(-?\d+(?:\.\d+)?)\s*,\s*(-?\d+(?:\.\d+)?)\s*$")
DEFAULT_PARAMETERS = "T2M,PRECTOTCORR,ALLSKY_SFC_SW_DWN"  # temp, precip, solar


def _parse_coords(topic: str) -> tuple[float, float] | None:
    m = COORD_PATTERN.match(topic)
    if not m:
        return None
    try:
        return (float(m.group(1)), float(m.group(2)))
    except ValueError:
        return None


def _compact_date(iso: str) -> str:
    """Convert YYYY-MM-DD → YYYYMMDD (NASA POWER format)."""
    if not iso:
        return ""
    return iso.replace("-", "")[:8]


def search_nasa_power(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not public_api.is_public_apis_enabled(cfg):
        return {"items": None, "error": "public_apis_disabled"}
    coords = _parse_coords(topic)
    if not coords:
        return {"items": {"properties": {}, "note": "non-coord-topic"}, "error": None}
    lat, lon = coords
    params = {
        "parameters": cfg.get("NASA_POWER_PARAMETERS", DEFAULT_PARAMETERS),
        "community": cfg.get("NASA_POWER_COMMUNITY", "RE"),
        "longitude": lon,
        "latitude": lat,
        "start": _compact_date(from_date) or "20260101",
        "end": _compact_date(to_date) or "20260131",
        "format": "JSON",
    }
    return public_api.fetch_json(
        ENDPOINT,
        params=params,
        user_agent_suffix="nasa-power-adapter",
        cache_key=f"nasa_power:{lat}:{lon}:{params['start']}:{params['end']}",
    )


def parse_nasa_power_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if isinstance(payload, dict) and payload.get("note") == "non-coord-topic":
        return []
    properties = payload.get("properties") or {}
    parameters = properties.get("parameter") or {}
    geometry = payload.get("geometry") or {}
    coords = geometry.get("coordinates") or [None, None]
    lon, lat = coords[0], coords[1] if len(coords) >= 2 else (None, None)
    out = []
    for param_name, series in parameters.items():
        if not series or not isinstance(series, dict):
            continue
        # Pull last observation
        try:
            last_date = sorted(series.keys())[-1]
            last_value = series[last_date]
        except (IndexError, TypeError):
            continue
        observation_date = f"{last_date[:4]}-{last_date[4:6]}-{last_date[6:8]}" if len(last_date) == 8 else last_date
        out.append(environmental.build_environmental_item(
            item_id=f"nasa_power:{lat}:{lon}:{param_name}:{last_date}",
            platform="nasa_power",
            title=f"NASA POWER {param_name} @ ({lat}, {lon})",
            snippet=f"{param_name}: {last_value} on {observation_date}",
            url=f"https://power.larc.nasa.gov/data-access-viewer/",
            source_domain="power.larc.nasa.gov",
            measurement_type=param_name.lower(),
            location=f"{lat},{lon}",
            latitude=lat,
            longitude=lon,
            value=last_value,
            observation_date=observation_date,
            relevance=0.7,
            why_relevant=f"NASA POWER {param_name} for ({lat}, {lon})",
            extra_metadata={
                "parameter_name": param_name,
                "daily_series_length": len(series),
            },
        ))
    return out
