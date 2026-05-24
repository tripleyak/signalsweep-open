"""Foursquare Places API (signalsweep 3.24.0+).

Endpoint: `api.foursquare.com/v3/places/search`. Requires `FOURSQUARE_API_KEY`.
v3.7 paid-APIs + creds.
"""

from __future__ import annotations

from typing import Any

from . import paid_api

ENDPOINT = "https://api.foursquare.com/v3/places/search"
DEPTH_LIMITS = {"quick": 10, "default": 25, "deep": 50}


def search_foursquare(
    topic: str,
    from_date: str,
    to_date: str,
    depth: str = "default",
    config: dict[str, Any] | None = None,
) -> dict[str, Any]:
    cfg = config or {}
    if not paid_api.is_paid_apis_enabled(cfg):
        return {"items": None, "error": "paid_apis_disabled"}
    api_key = cfg.get("FOURSQUARE_API_KEY")
    if not api_key:
        return {"items": None, "error": "credentials_missing"}
    params = {"query": topic, "limit": DEPTH_LIMITS.get(depth, 25)}
    if cfg.get("FOURSQUARE_NEAR"):
        params["near"] = cfg["FOURSQUARE_NEAR"]
    return paid_api.fetch_json(ENDPOINT, params=params, extra_headers={"Authorization": api_key, "Accept": "application/json"})


def parse_foursquare_response(response: dict[str, Any]) -> list[dict[str, Any]]:
    if response.get("error") or not response.get("items"):
        return []
    results = response["items"].get("results") or []
    out = []
    for r in results:
        fsq_id = r.get("fsq_id")
        if not fsq_id:
            continue
        location = r.get("location") or {}
        categories = r.get("categories") or []
        out.append({
            "id": f"foursquare:{fsq_id}",
            "title": f"{r.get('name')} — {location.get('formatted_address', '')[:80]}",
            "snippet": ", ".join([c.get("name", "") for c in categories[:3]]),
            "url": f"https://foursquare.com/v/{fsq_id}",
            "source_domain": "foursquare.com",
            "date": None,
            "relevance": 0.7,
            "why_relevant": f"Foursquare place — {r.get('name')}",
            "metadata": {
                "platform": "foursquare",
                "fsq_id": fsq_id,
                "categories": [c.get("name") for c in categories],
                "address": location.get("formatted_address"),
                "latitude": (r.get("geocodes") or {}).get("main", {}).get("latitude"),
                "longitude": (r.get("geocodes") or {}).get("main", {}).get("longitude"),
            },
        })
    return out
