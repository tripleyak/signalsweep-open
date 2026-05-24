"""NOAA — US weather + climate data (signalsweep 3.19.0+).

NOAA's Climate Data Online (CDO) API v2: `www.ncei.noaa.gov/cdo-web/api/v2/stations`.
Free with `NOAA_CDO_TOKEN` (signup at www.ncdc.noaa.gov/cdo-web/token).

Gated by v3.7 paid-APIs + creds (token-gated, envelope-first).
"""

from __future__ import annotations

from typing import Any

from . import environmental, paid_api

ENDPOINT = "https://www.ncei.noaa.gov/cdo-web/api/v2/stations"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_noaa(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    token = cfg.get("NOAA_CDO_TOKEN")
    if not token:
        return {"items": None, "error": "credentials_missing"}
    limit = DEPTH_LIMITS.get(depth, 25)
    params = {"limit": limit}
    # NOAA CDO v2 supports location/station search; we pass the topic via
    # the free-text station search. For full typed queries pair with
    # downstream data-product endpoints.
    if topic:
        params["locationid"] = topic if topic.upper().startswith("FIPS:") else topic
    return paid_api.fetch_json(ENDPOINT, params=params, extra_headers={"token": token})


def parse_noaa_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    results = response["items"].get("results") or []
    out = []
    for s in results:
        sid = s.get("id") or ""
        if not sid:
            continue
        out.append(environmental.build_environmental_item(
            item_id=f"noaa:{sid}",
            platform="noaa",
            title=s.get("name") or sid,
            snippet=f"{sid} · elevation {s.get('elevation', 'n/a')} {s.get('elevationUnit', '')}",
            url=f"https://www.ncei.noaa.gov/cdo-web/datasets/GHCND/stations/{sid}/detail",
            source_domain="ncei.noaa.gov",
            measurement_type="weather_station",
            station_id=sid,
            location=s.get("name") or "",
            latitude=s.get("latitude"),
            longitude=s.get("longitude"),
            relevance=0.7,
            why_relevant=f"NOAA weather station — {s.get('name', sid)[:60]}",
            extra_metadata={
                "mindate": s.get("mindate", ""),
                "maxdate": s.get("maxdate", ""),
                "datacoverage": s.get("datacoverage", 0),
            },
        ))
    return out
