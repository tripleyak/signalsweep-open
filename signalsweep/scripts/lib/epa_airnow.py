"""EPA AirNow — US air quality index (signalsweep 3.19.0+).

Endpoint: `www.airnowapi.org/aq/observation/zipCode/current/` (current AQI by ZIP).
Free with `EPA_AIRNOW_API_KEY` (signup at docs.airnowapi.org).

Topic shape: numeric US ZIP code. Non-ZIP topics return graceful envelope.
Gated by v3.7 paid-APIs + creds.
"""

from __future__ import annotations

import re
from typing import Any

from . import environmental, paid_api

ENDPOINT = "https://www.airnowapi.org/aq/observation/zipCode/current/"
ZIP_PATTERN = re.compile(r"^\d{5}$")


def _looks_like_zip(topic: str) -> bool:
    return bool(ZIP_PATTERN.match(topic.strip()))


def search_epa_airnow(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("EPA_AIRNOW_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    if not _looks_like_zip(topic):
        return {"items": {"observations": [], "note": "non-zip-topic"}, "error": None}
    params = {
        "format": "application/json",
        "zipCode": topic.strip(),
        "distance": cfg.get("EPA_AIRNOW_DISTANCE", "25"),
        "API_KEY": api_key,
    }
    return paid_api.fetch_json(ENDPOINT, params=params)


def parse_epa_airnow_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    payload = response["items"]
    if isinstance(payload, dict) and payload.get("note") == "non-zip-topic":
        return []
    # AirNow returns a JSON array at the top level.
    observations = payload if isinstance(payload, list) else payload.get("observations") or []
    out = []
    for obs in observations:
        parameter = obs.get("ParameterName") or ""
        aqi = obs.get("AQI")
        report_area = obs.get("ReportingArea") or ""
        state = obs.get("StateCode") or ""
        date_observed = obs.get("DateObserved", "").strip()
        item_id = f"epa_airnow:{report_area}:{parameter}:{date_observed}".replace(" ", "_")
        out.append(environmental.build_environmental_item(
            item_id=item_id,
            platform="epa_airnow",
            title=f"{report_area}, {state} — AQI {aqi} ({parameter})",
            snippet=f"{obs.get('Category', {}).get('Name', '')} · AQI {aqi} for {parameter}".strip(" ·"),
            url="https://www.airnow.gov/",
            source_domain="airnow.gov",
            measurement_type="air_quality",
            location=f"{report_area}, {state}",
            latitude=obs.get("Latitude"),
            longitude=obs.get("Longitude"),
            unit="AQI",
            value=aqi,
            observation_date=date_observed,
            relevance=0.7,
            why_relevant=f"EPA AirNow {parameter} AQI for {report_area}",
            extra_metadata={
                "parameter": parameter,
                "category": obs.get("Category", {}).get("Name", ""),
                "category_number": obs.get("Category", {}).get("Number"),
                "hour_observed": obs.get("HourObserved"),
            },
        ))
    return out
